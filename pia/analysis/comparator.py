"""
pia/analysis/comparator.py

Multi-approach comparison engine.

Given a topic (e.g. "authentication", "rate limiting", "data pipeline"),
this module:
  1. Discovers all KB projects that contain relevant chunks.
  2. Groups the chunks by source repo.
  3. Asks Claude to do a structured side-by-side comparison.
  4. Returns a verdict: which approach is best for the user's context.

Can also be triggered per-file: if the file is doing something that multiple
KB projects do differently, surface a comparison automatically.

User can optionally pin specific KB repos to include in the comparison.

Output schema:
  {
    "topic":        str,
    "approaches":   [
      {
        "source_repo": str,
        "approach_name": str,
        "summary":   str,
        "pros":      [str],
        "cons":      [str],
        "best_for":  str
      }
    ],
    "comparison_matrix": [
      {"dimension": str, "scores": {"repo_name": str, ...}}
    ],
    "verdict": {
      "winner":      str,          # repo name or "tie"
      "rationale":   str,
      "caveat":      str           # "best only if …"
    },
    "error": str | None
  }
"""

from __future__ import annotations

import json
import re
import time
from collections import defaultdict
from typing import TYPE_CHECKING

import anthropic

from utils import cfg, log, truncate_to_tokens
from ingest.vectorstore import get_store

if TYPE_CHECKING:
    from scan.local_scanner import ProjectFile


# ── Token budgets ─────────────────────────────────────────────────────────────
CHUNK_PREVIEW_TOKENS  = 300   # tokens per KB chunk shown to LLM
MAX_CHUNKS_PER_REPO   = 4     # cap chunks shown per repo
MIN_SIMILARITY        = 0.35  # minimum score to include a chunk
MAX_REPOS_TO_COMPARE  = 5     # cap total repos in one comparison

COMPARISON_SYSTEM = """\
You are PIA-Compare, an expert software architect conducting a structured
comparison of how multiple open-source projects approach the same problem.

Your job:
  1. Understand each approach from the provided code/doc excerpts.
  2. Compare them across relevant technical dimensions.
  3. Deliver a clear, opinionated verdict — which approach is best, and for
     what context.

Be concrete.  Don't hedge.  If one approach is clearly better, say so and
explain why.  Acknowledge trade-offs fairly.

Respond ONLY with valid JSON (no preamble, no markdown fences):
{
  "approaches": [
    {
      "source_repo":    "<repo name>",
      "approach_name":  "<descriptive name for this approach>",
      "summary":        "<2-3 sentences describing the approach>",
      "pros":           ["<pro1>", "<pro2>"],
      "cons":           ["<con1>", "<con2>"],
      "best_for":       "<one sentence: ideal context for this approach>"
    }
  ],
  "comparison_matrix": [
    {
      "dimension": "<e.g. Complexity, Performance, Testability, ...>",
      "scores": {
        "<repo1>": "<rating or brief note>",
        "<repo2>": "<rating or brief note>"
      }
    }
  ],
  "verdict": {
    "winner":    "<repo name, or 'tie — depends on context'>",
    "rationale": "<2-4 sentences explaining why>",
    "caveat":    "<condition under which the verdict changes, or 'none'>"
  }
}
"""


_CLIENT: anthropic.Anthropic | None = None

def _get_client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        api_key = cfg("anthropic.api_key", "")
        _CLIENT = anthropic.Anthropic(api_key=api_key)
    return _CLIENT


def _parse(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text.strip(), flags=re.MULTILINE)
    try:
        return json.loads(text.strip())
    except Exception:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return {"approaches": [], "comparison_matrix": [], "verdict": {}, "error": "parse error"}


def _group_chunks_by_repo(chunks: list[dict]) -> dict[str, list[dict]]:
    """Group retrieved chunks by source repo (metadata key: 'repo')."""
    grouped: dict[str, list[dict]] = defaultdict(list)
    for chunk in chunks:
        repo = chunk.get("metadata", {}).get("repo", "unknown")
        if len(grouped[repo]) < MAX_CHUNKS_PER_REPO:
            grouped[repo].append(chunk)
    return dict(grouped)


def _build_comparison_prompt(
    topic: str,
    grouped: dict[str, list[dict]],
    constraints_block: str = "",
    user_system_prompt: str = "",
) -> str:
    sections = []
    for repo, chunks in grouped.items():
        excerpts = []
        for c in chunks:
            preview = truncate_to_tokens(c.get("text", ""), CHUNK_PREVIEW_TOKENS)
            excerpts.append(f"  [{c.get('metadata', {}).get('file_type', '')}]\n  {preview}")
        joined = "\n\n".join(excerpts)
        sections.append(f"### Source: {repo}\n{joined}")

    repo_block = "\n\n".join(sections)

    constraint_section = ""
    if constraints_block.strip():
        constraint_section = f"\n\n## Project Constraints\n{constraints_block.strip()}\n"

    user_guidance = ""
    if user_system_prompt.strip():
        user_guidance = f"\n\n## Developer Guidance\n{user_system_prompt.strip()}\n"

    return (
        f"## Comparison Topic\n{topic}\n"
        f"{constraint_section}"
        f"{user_guidance}"
        f"\n## Approaches from Knowledge Base\n\n{repo_block}"
        f"\n\nCompare these approaches and return valid JSON only."
    )


# ── Public API ─────────────────────────────────────────────────────────────────

def compare_approaches(
    topic: str,
    pinned_repos: list[str] | None = None,
    constraints_block: str = "",
    user_system_prompt: str = "",
    top_k: int = 30,
) -> dict:
    """
    Discover and compare how multiple KB projects approach the given topic.

    Args:
        topic:             What to compare (e.g. "authentication flow",
                           "async task queue", "error handling strategy").
        pinned_repos:      Optional list of repo names to always include.
        constraints_block: Formatted constraints text for context.
        user_system_prompt: Optional developer guidance.
        top_k:             How many KB chunks to retrieve for the topic.

    Returns:
        Comparison result dict.
    """
    store = get_store()

    # Retrieve relevant KB chunks
    try:
        results = store.semantic_search(topic, k=top_k)
    except Exception as e:
        log.error(f"Comparator KB query failed: {e}")
        return {"topic": topic, "approaches": [], "comparison_matrix": [], "verdict": {}, "error": str(e)}

    # Filter by similarity threshold
    threshold = cfg("knowledge_base.similarity_threshold", MIN_SIMILARITY)
    chunks = [
        r for r in results
        if r.get("score", 0) >= threshold
    ]

    # Group by repo — metadata field is "repo" (not "source_repo")
    grouped = _group_chunks_by_repo(chunks)

    # Enforce pinned repos (try to retrieve extra chunks for them if missing)
    if pinned_repos:
        for repo in pinned_repos:
            if repo not in grouped:
                try:
                    pinned_results = store.semantic_search(
                        f"{topic} {repo}", k=10,
                        where={"repo": repo}
                    )
                    if pinned_results:
                        grouped[repo] = pinned_results[:MAX_CHUNKS_PER_REPO]
                        log.info(f"Pinned repo '{repo}' added to comparison")
                except Exception:
                    log.warning(f"Could not retrieve chunks for pinned repo '{repo}'")

    if not grouped:
        return {
            "topic":            topic,
            "approaches":       [],
            "comparison_matrix": [],
            "verdict":          {"winner": "n/a", "rationale": "No relevant KB sources found for this topic.", "caveat": "n/a"},
            "error":            None,
        }

    # Cap total repos
    if len(grouped) > MAX_REPOS_TO_COMPARE:
        # Keep pinned repos + top similarity ones
        pinned_set = set(pinned_repos or [])
        others = [r for r in grouped if r not in pinned_set]
        keep   = list(pinned_set) + others[: MAX_REPOS_TO_COMPARE - len(pinned_set)]
        grouped = {k: grouped[k] for k in keep if k in grouped}

    log.info(f"Comparing {len(grouped)} approaches for topic: '{topic}'")

    prompt = _build_comparison_prompt(topic, grouped, constraints_block, user_system_prompt)

    client  = _get_client()
    model   = cfg("anthropic.model", "claude-sonnet-4-20250514")
    max_tok = cfg("anthropic.comparison_max_tokens", 2500)

    for attempt in range(3):
        try:
            response = client.messages.create(
                model      = model,
                max_tokens = max_tok,
                system     = COMPARISON_SYSTEM,
                messages   = [{"role": "user", "content": prompt}],
            )
            raw    = response.content[0].text
            parsed = _parse(raw)

            return {
                "topic":             topic,
                "repos_compared":    list(grouped.keys()),
                "approaches":        parsed.get("approaches", []),
                "comparison_matrix": parsed.get("comparison_matrix", []),
                "verdict":           parsed.get("verdict", {}),
                "error":             parsed.get("error"),
            }

        except anthropic.RateLimitError:
            wait = 30 * (attempt + 1)
            log.warning(f"Rate limit — waiting {wait}s")
            time.sleep(wait)
        except Exception as e:
            log.error(f"Comparison error for topic '{topic}': {e}")
            if attempt == 2:
                return {
                    "topic":    topic,
                    "approaches": [],
                    "comparison_matrix": [],
                    "verdict":  {},
                    "error":    str(e),
                }
            time.sleep(3)

    return {"topic": topic, "approaches": [], "comparison_matrix": [], "verdict": {}, "error": "All retries exhausted"}


def auto_compare_for_file(
    pf: "ProjectFile",
    constraints_block: str = "",
    user_system_prompt: str = "",
) -> list[dict]:
    """
    Detect comparison-worthy topics in a project file and run comparisons.
    Returns a list of comparison results (0-2 per file).

    This is called automatically during analysis if
    comparison.auto_detect is enabled in config.yaml.
    """
    # Use the file content as the query to find what the file is doing
    content_snippet = truncate_to_tokens(pf.content, 400)

    store = get_store()

    # Find how many distinct repos have relevant content
    try:
        results = store.semantic_search(content_snippet, k=25)
    except Exception:
        return []

    grouped = _group_chunks_by_repo(results)

    if len(grouped) < 2:
        # Need at least 2 approaches to compare
        return []

    # Extract topic from file path + content (heuristic)
    topic = f"{pf.file_type} patterns in {pf.relative_path} ({pf.project_name})"

    result = compare_approaches(
        topic,
        constraints_block=constraints_block,
        user_system_prompt=user_system_prompt,
    )

    return [result] if result.get("approaches") else []
