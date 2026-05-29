"""
pia/analysis/retriever.py

Wraps the vector store with analysis-phase logic:
• Builds a rich query from a project file's content
• Retrieves the most relevant knowledge-base chunks
• Formats them into a structured context block for the LLM
"""

from __future__ import annotations

import re
from typing import TYPE_CHECKING

from utils import cfg, log, truncate_to_tokens
from ingest.vectorstore import get_store

if TYPE_CHECKING:
    from scan.local_scanner import ProjectFile


# ── Token budgets ─────────────────────────────────────────────────────────────

FILE_CONTENT_MAX_TOKENS    = 1_800   # max tokens from the project file itself
CONTEXT_CHUNK_MAX_TOKENS   = 350     # max tokens per retrieved chunk (summary)
TOTAL_CONTEXT_MAX_TOKENS   = 2_000   # max total for all retrieved chunks


# ── Reputation eligibility filter ────────────────────────────────────────────

def _filter_by_reputation(results: list[dict]) -> list[dict]:
    """
    Remove chunks from KB repos that have not yet passed benchmarking.

    A repo is allowed through if:
      • reputation.enabled is False (feature disabled), OR
      • the repo is eligible for at least one domain in the registry, OR
      • the repo is unknown to the registry AND fallback_to_ineligible is True
        (handles first-run / bootstrap state before any benchmarking has run)

    If filtering would leave zero results and fallback_to_ineligible is True,
    the full unfiltered list is returned with a warning so analysis never
    gets an empty context window.
    """
    if not cfg("reputation.enabled", True):
        return results

    from ingest.reputation_store import get_reputation_store
    registry = get_reputation_store()

    eligible: list[dict] = []
    ineligible_repos: set[str] = set()

    for r in results:
        repo = r.get("metadata", {}).get("repo", "")

        # Unknown repo = not yet registered at all (e.g. very first ingest
        # before benchmarker has run).  Treat as eligible only if fallback on.
        if not registry.is_known(repo):
            if cfg("reputation.fallback_to_ineligible", True):
                eligible.append(r)
            else:
                ineligible_repos.add(repo)
            continue

        if registry.is_eligible_any(repo):
            eligible.append(r)
        else:
            ineligible_repos.add(repo)

    if ineligible_repos:
        log.debug(
            f"Retriever: filtered out chunks from "
            f"{len(ineligible_repos)} ineligible repo(s): "
            f"{', '.join(sorted(ineligible_repos))}"
        )

    # Fallback: if all results were filtered out, restore them with a warning
    if not eligible and results:
        if cfg("reputation.fallback_to_ineligible", True):
            log.warning(
                "Retriever: no eligible repos matched this query — "
                "falling back to unfiltered results.  "
                "Run the full pipeline to benchmark new repos."
            )
            return results
        log.warning(
            "Retriever: no eligible repos and fallback is disabled — "
            "returning empty context."
        )
        return []

    return eligible


# ── Query builder ─────────────────────────────────────────────────────────────

def _build_query(pf: "ProjectFile") -> str:
    """
    Build a targeted semantic search query from a project file.
    We want to surface relevant patterns, not just keyword matches.
    """
    content = pf.content
    ext     = pf.file_type.lower()

    # Extract meaningful signals from the file
    signals: list[str] = []

    # 1. Imports / dependencies → technology context
    if ext in ("py", "ipynb"):
        imports = re.findall(r"^(?:import|from)\s+([\w.]+)", content, re.MULTILINE)
        if imports:
            signals.append("imports: " + ", ".join(dict.fromkeys(imports[:12])))

    if ext in ("js", "ts", "jsx", "tsx"):
        requires = re.findall(r'(?:require|import)[( ]["\']([^"\']+)', content)
        if requires:
            signals.append("requires: " + ", ".join(dict.fromkeys(requires[:12])))

    if ext in ("json", "toml") and "package" in pf.relative_path.lower():
        # package.json / pyproject.toml — dependencies ARE the content
        signals.append(content[:600])

    # 2. Function/class definitions → domain context
    if ext in ("py", "ipynb"):
        defs = re.findall(r"^(?:def|class|async def)\s+(\w+)", content, re.MULTILINE)
        if defs:
            signals.append("defines: " + ", ".join(defs[:12]))

    # 3. Comment/docstring keywords — captures intent
    comments = re.findall(r"#\s*(.+)$|\"\"\"(.+?)\"\"\"", content, re.MULTILINE)
    comment_text = " ".join(
        (a or b).strip() for a, b in comments if (a or b).strip()
    )[:400]
    if comment_text:
        signals.append(comment_text)

    # 4. First 400 chars of content for general context
    signals.append(content[:400])

    query_parts = [
        f"Project: {pf.project_name}",
        f"File: {pf.relative_path} ({ext})",
    ] + signals

    return "\n".join(query_parts)[:1_200]


# ── Context formatter ─────────────────────────────────────────────────────────

def _format_context(results: list[dict]) -> str:
    """
    Format retrieved chunks into a clearly structured context block
    that the LLM can parse and attribute.
    """
    if not results:
        return "(No relevant patterns found in knowledge base)"

    lines = ["## Relevant Patterns from Your Curated Open Source Library\n"]
    total_tokens = 0

    for i, r in enumerate(results, 1):
        meta     = r.get("metadata", {})
        repo     = meta.get("repo", "unknown-repo")
        fname    = meta.get("filename", "")
        score    = r.get("score", 0.0)
        content  = r.get("content", "")

        # Truncate individual chunks
        content  = truncate_to_tokens(content, CONTEXT_CHUNK_MAX_TOKENS)
        chunk_t  = len(content.split()) * 4 // 3  # rough estimate

        total_tokens += chunk_t
        if total_tokens > TOTAL_CONTEXT_MAX_TOKENS and i > 2:
            lines.append(f"\n*(Additional {len(results) - i + 1} results omitted to stay within context budget)*")
            break

        lines.append(
            f"### [{i}] Source: `{repo}` — `{fname}` (relevance: {score:.2f})\n"
            f"```\n{content}\n```\n"
        )

    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────

def retrieve_context_for_file(
    pf: "ProjectFile",
    k:  int | None = None,
) -> tuple[str, list[dict]]:
    """
    For a given project file, query the knowledge base and return:
    (formatted_context_string, raw_results_list)
    """
    store = get_store()

    if store.count() == 0:
        log.warning("Vector store is empty — skipping retrieval.")
        return ("(Knowledge base is empty — run ingest first)", [])

    query   = _build_query(pf)
    results = store.semantic_search(query, k=k)

    # Gate: remove chunks from repos that haven't passed benchmarking yet
    results = _filter_by_reputation(results)

    if not results:
        log.debug(
            f"No relevant KB chunks for {pf.project_name}/{pf.relative_path}"
        )

    context = _format_context(results)
    return context, results


def retrieve_context_bulk(
    project_files: list["ProjectFile"],
    k: int | None = None,
) -> list[tuple["ProjectFile", str, list[dict]]]:
    """
    Retrieve context for a list of files.
    Returns list of (ProjectFile, context_str, raw_results).
    """
    out = []
    for pf in project_files:
        ctx, raw = retrieve_context_for_file(pf, k=k)
        out.append((pf, ctx, raw))
    return out
