"""
pia/ingest/repo_benchmarker.py

Benchmarks newly ingested KB repos against existing domain champions.

Called automatically during Phase 1 (ingest) whenever chunks from a new
or changed repo are written to ChromaDB.  The result is written to the
ReputationStore, which the retriever then uses to gate which repos are
allowed to contribute suggestions.

Algorithm per repo per domain:
─────────────────────────────
1.  Check whether the repo has relevant content for this domain
    (similarity query filtered to that repo — if max score < threshold, skip).
2.  Fetch content excerpts from the new repo + all currently eligible repos.
3.  If no eligible repos exist for this domain:
        → sole_entry verdict, is_eligible = True (first in wins).
4.  Otherwise run a focused LLM comparison that produces numeric 1–10 scores
    across five universal code-quality dimensions.
5.  Compute a weighted composite score.
6.  Compare against the current champion score:
        new_score >= champion_score  AND  new_score >= min_score_threshold
            → is_eligible = True,  verdict = "winner" or "tied"
        otherwise
            → is_eligible = False, verdict = "loser"
7.  Write the result to ReputationStore.

Domain discovery (in priority order):
  1. reputation.domains     (explicit config list)
  2. comparison.scheduled_topics
  3. Built-in taxonomy of 8 universal software domains
"""

from __future__ import annotations

import json
import re
import time
from typing import TYPE_CHECKING

import anthropic

from utils import cfg, log, truncate_to_tokens
from ingest.vectorstore import get_store
from ingest.reputation_store import get_reputation_store

# ── Constants ─────────────────────────────────────────────────────────────────

# How similar does a repo's content need to be to a domain topic to be
# included in that domain's benchmark?  (cosine similarity 0–1)
MIN_DOMAIN_RELEVANCE  = 0.28

# Number of chunks fetched per repo for the benchmark comparison prompt.
CHUNKS_PER_REPO       = 3

# Tokens shown per chunk in the benchmark prompt.
CHUNK_PREVIEW_TOKENS  = 250

# Minimum composite score (1–10) a repo must reach even if it beats the champion.
# Prevents a "winner by default" in a field of mediocre repos from poisoning
# suggestions.  Configurable via reputation.min_score_threshold.
DEFAULT_MIN_THRESHOLD = 5.0

# Retry / rate-limit settings.
MAX_RETRIES   = 3
RETRY_WAIT_S  = 30

# ── Fallback domain taxonomy ──────────────────────────────────────────────────
# Used when neither reputation.domains nor comparison.scheduled_topics is set.

DEFAULT_DOMAINS = [
    "error handling and resilience",
    "authentication and security",
    "data access and persistence",
    "api design and routing",
    "testing strategies",
    "async processing and concurrency",
    "configuration and environment management",
    "logging and observability",
]

# ── Scoring dimensions + weights ──────────────────────────────────────────────

DIMENSIONS = ["correctness", "robustness", "simplicity", "completeness", "best_practices"]

WEIGHTS: dict[str, float] = {
    "correctness":    0.30,
    "robustness":     0.25,
    "simplicity":     0.20,
    "completeness":   0.15,
    "best_practices": 0.10,
}

# ── LLM prompt ────────────────────────────────────────────────────────────────

BENCHMARK_SYSTEM = """\
You are PIA-Benchmark, a precise software architect scoring open-source projects.

Given code/doc excerpts from one or more projects for a specific domain, score each
project on five dimensions (integer 1–10):

  correctness   — Does it actually solve the problem correctly and completely?
  robustness    — Does it handle errors, edge cases, and failures well?
  simplicity    — Is it easy to understand, adapt, and maintain?
  completeness  — Does it cover the full domain, not just the happy path?
  best_practices — Does it follow proven, scalable patterns?

Calibration: 10 = best-in-class, 7 = solid and good, 5 = adequate but unremarkable,
3 = noticeable problems, 1 = severely lacking.

Score only what you can observe in the excerpts — do not infer virtues not
shown.  If a project has no relevant excerpts, score it 1 across all dimensions.

Respond ONLY with valid JSON (no preamble, no markdown fences):
{
  "scores": {
    "<repo_name>": {
      "correctness":    <1-10 integer>,
      "robustness":     <1-10 integer>,
      "simplicity":     <1-10 integer>,
      "completeness":   <1-10 integer>,
      "best_practices": <1-10 integer>
    }
  },
  "reasoning": "<one sentence: what most differentiated the top scorer from the rest>"
}
"""


# ── API client (lazy singleton) ───────────────────────────────────────────────

_CLIENT: anthropic.Anthropic | None = None


def _get_client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        api_key = cfg("anthropic.api_key", "")
        if not api_key or api_key.startswith("<REPLACE"):
            raise ValueError("Anthropic API key not set in config.yaml")
        _CLIENT = anthropic.Anthropic(api_key=api_key)
    return _CLIENT


# ── Domain helpers ────────────────────────────────────────────────────────────

def _get_benchmark_domains() -> list[str]:
    """
    Resolve which domains to benchmark against, in priority order.
    """
    explicit = cfg("reputation.domains", []) or []
    if explicit:
        return [d.strip() for d in explicit if d.strip()]

    scheduled = cfg("comparison.scheduled_topics", []) or []
    if scheduled:
        return [t.strip() for t in scheduled if t.strip()]

    return DEFAULT_DOMAINS


# ── Chunk retrieval helpers ───────────────────────────────────────────────────

def _get_repo_chunks_for_domain(
    repo: str,
    domain: str,
    n: int = CHUNKS_PER_REPO,
) -> list[dict]:
    """
    Fetch the most relevant chunks from a specific repo for a given domain.
    Returns an empty list if the repo has no relevant content.
    """
    store = get_store()
    try:
        results = store.semantic_search(
            domain,
            k=n * 4,          # fetch extra, then filter
            min_score=0.0,    # we apply our own threshold below
        )
        repo_chunks = [r for r in results if r["metadata"].get("repo") == repo]
        return repo_chunks[:n]
    except Exception as e:
        log.debug(f"Chunk fetch failed for repo='{repo}' domain='{domain}': {e}")
        return []


def _max_relevance_score(chunks: list[dict]) -> float:
    """Return the highest similarity score in a list of chunks."""
    if not chunks:
        return 0.0
    return max(c.get("score", 0.0) for c in chunks)


def _format_chunks_block(repo: str, chunks: list[dict]) -> str:
    if not chunks:
        return f"### Source: {repo}\n(no relevant excerpts found)\n"
    parts = []
    for c in chunks:
        preview = truncate_to_tokens(c.get("content", ""), CHUNK_PREVIEW_TOKENS)
        ft = c.get("metadata", {}).get("file_type", "")
        parts.append(f"  [{ft}]  {preview}")
    joined = "\n\n".join(parts)
    return f"### Source: {repo}\n{joined}\n"


# ── Composite score ────────────────────────────────────────────────────────────

def _composite(dim_scores: dict[str, float]) -> float:
    """Weighted average of dimension scores (1–10 range)."""
    if not dim_scores:
        return 0.0
    total_w = sum(WEIGHTS.get(d, 0.1) for d in dim_scores)
    if total_w == 0:
        return 0.0
    score = sum(v * WEIGHTS.get(d, 0.1) for d, v in dim_scores.items())
    return round(score / total_w, 3)


# ── LLM benchmark call ────────────────────────────────────────────────────────

def _run_benchmark_call(
    domain: str,
    repo_chunks: dict[str, list[dict]],
) -> dict[str, dict[str, float]] | None:
    """
    Run the benchmark LLM call.

    Args:
        domain:      The domain being benchmarked.
        repo_chunks: {repo_name: [chunk_dicts]}.

    Returns:
        {repo_name: {dimension: score}} or None on failure.
    """
    # Build the prompt
    sections = [
        f"## Domain: {domain}\n",
        "## Project Excerpts\n",
    ]
    for repo, chunks in repo_chunks.items():
        sections.append(_format_chunks_block(repo, chunks))

    sections.append("\nScore each project as instructed. Return valid JSON only.")
    prompt = "\n".join(sections)

    client  = _get_client()
    model   = cfg("anthropic.model", "claude-sonnet-4-20250514")
    max_tok = 800

    for attempt in range(MAX_RETRIES):
        try:
            response = client.messages.create(
                model      = model,
                max_tokens = max_tok,
                system     = BENCHMARK_SYSTEM,
                messages   = [{"role": "user", "content": prompt}],
            )
            raw = response.content[0].text
            return _parse_benchmark_response(raw, list(repo_chunks.keys()))

        except anthropic.RateLimitError:
            wait = RETRY_WAIT_S * (attempt + 1)
            log.warning(f"Rate limit during benchmark — waiting {wait}s")
            time.sleep(wait)
        except Exception as e:
            log.error(f"Benchmark LLM call failed (attempt {attempt + 1}): {e}")
            if attempt == MAX_RETRIES - 1:
                return None
            time.sleep(3)

    return None


def _parse_benchmark_response(
    text: str,
    expected_repos: list[str],
) -> dict[str, dict[str, float]] | None:
    """
    Parse Claude's benchmark JSON response.
    Returns {repo_name: {dimension: float}} or None.
    """
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text.strip(), flags=re.MULTILINE)
    text = text.strip()

    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                parsed = json.loads(match.group())
            except Exception:
                log.debug(f"Benchmark JSON parse failed. Raw: {text[:200]}")
                return None
        else:
            log.debug(f"No JSON found in benchmark response. Raw: {text[:200]}")
            return None

    raw_scores = parsed.get("scores", {})
    if not raw_scores:
        log.debug("Benchmark response contained no scores.")
        return None

    # Normalise: coerce all dimension values to float, clamp to 1–10
    result: dict[str, dict[str, float]] = {}
    for repo in expected_repos:
        repo_raw = raw_scores.get(repo, {})
        if not repo_raw:
            # Model may use partial repo name — try partial match
            for key in raw_scores:
                if repo.lower() in key.lower() or key.lower() in repo.lower():
                    repo_raw = raw_scores[key]
                    break

        dims: dict[str, float] = {}
        for dim in DIMENSIONS:
            try:
                val = float(repo_raw.get(dim, 5))
                dims[dim] = max(1.0, min(10.0, val))
            except (TypeError, ValueError):
                dims[dim] = 5.0     # safe fallback

        result[repo] = dims

    return result


# ── Single-repo benchmarker ───────────────────────────────────────────────────

def _benchmark_one_repo(repo: str, domain: str, registry) -> None:
    """
    Evaluate one repo for one domain and update the registry.
    """
    log.info(f"  Benchmarking '{repo}' / '{domain}'…")

    # Step 1: Check relevance
    new_chunks = _get_repo_chunks_for_domain(repo, domain)
    relevance  = _max_relevance_score(new_chunks)

    if relevance < MIN_DOMAIN_RELEVANCE:
        log.debug(
            f"  '{repo}' not relevant to '{domain}' "
            f"(max_score={relevance:.3f} < {MIN_DOMAIN_RELEVANCE}) — skipping"
        )
        return

    log.debug(f"  '{repo}' relevance to '{domain}': {relevance:.3f}")

    # Step 2: Find eligible competitors
    eligible_repos = registry.get_eligible_repos(domain)

    # Step 3: Sole-entry shortcut
    if not eligible_repos:
        DEFAULT_SOLE_SCORE = 6.5   # Decent but not perfect — we've seen nothing better
        dim_scores = {d: DEFAULT_SOLE_SCORE for d in DIMENSIONS}
        registry.upsert_record(
            repo             = repo,
            domain           = domain,
            composite_score  = DEFAULT_SOLE_SCORE,
            dimension_scores = dim_scores,
            is_eligible      = True,
            champion_score   = 0.0,
            verdict          = "sole_entry",
            repos_compared   = [],
        )
        log.info(
            f"  '{repo}' is first entry for '{domain}' → eligible "
            f"(sole_entry, score={DEFAULT_SOLE_SCORE})"
        )
        return

    # Step 4: Build comparison payload (new repo + all eligible competitors)
    repos_to_compare = [repo] + eligible_repos
    repo_chunks: dict[str, list[dict]] = {}
    for r in repos_to_compare:
        repo_chunks[r] = _get_repo_chunks_for_domain(r, domain)

    # Step 5: LLM benchmark call
    scores = _run_benchmark_call(domain, repo_chunks)

    if scores is None:
        log.warning(
            f"  Benchmark call failed for '{repo}' / '{domain}' "
            f"— marking ineligible until next run"
        )
        registry.upsert_record(
            repo             = repo,
            domain           = domain,
            composite_score  = 0.0,
            dimension_scores = {},
            is_eligible      = False,
            champion_score   = registry.get_champion_score(domain),
            verdict          = "error",
            repos_compared   = eligible_repos,
        )
        return

    # Step 6: Compute composite scores
    new_composite = _composite(scores.get(repo, {}))

    champion_score = max(
        _composite(scores.get(r, {}))
        for r in eligible_repos
    )

    min_threshold: float = float(cfg("reputation.min_score_threshold", DEFAULT_MIN_THRESHOLD))

    qualifies = (
        new_composite >= champion_score
        and new_composite >= min_threshold
    )

    if new_composite > champion_score:
        verdict = "winner"
    elif new_composite == champion_score:
        verdict = "tied"
    else:
        verdict = "loser"

    # Step 7: Re-evaluate current champion if new repo wins
    # (The champion was evaluated at a previous point in time — if the new repo
    # beats it, the champion's is_eligible stays True; the registry now has two
    # eligible repos for this domain, which gives more context variety.)

    registry.upsert_record(
        repo             = repo,
        domain           = domain,
        composite_score  = new_composite,
        dimension_scores = scores.get(repo, {}),
        is_eligible      = qualifies,
        champion_score   = champion_score,
        verdict          = verdict,
        repos_compared   = eligible_repos,
    )

    log.info(
        f"  '{repo}' / '{domain}': "
        f"score={new_composite:.2f}  champion={champion_score:.2f}  "
        f"threshold={min_threshold}  verdict={verdict}  eligible={qualifies}"
    )


# ── Public API ────────────────────────────────────────────────────────────────

def benchmark_repos(new_repo_names: list[str]) -> dict[str, dict]:
    """
    Benchmark a list of newly ingested or re-ingested repos.

    Called from run_pipeline.py after Phase 1 (ingest) whenever
    upsert_chunks() reports new/changed content.

    Args:
        new_repo_names: Repo names that had at least one new or changed chunk.

    Returns:
        Summary dict: {repo_name: {domain: {eligible, score, verdict}}}
    """
    if not cfg("reputation.enabled", True):
        log.info("Reputation gating disabled (reputation.enabled = false) — skipping")
        return {}

    if not new_repo_names:
        log.debug("No new repos to benchmark.")
        return {}

    registry = get_reputation_store()
    domains  = _get_benchmark_domains()

    log.info(f"Benchmarking {len(new_repo_names)} repo(s) across {len(domains)} domain(s):")
    for r in new_repo_names:
        log.info(f"  • {r}")
    log.info(f"Domains: {', '.join(domains)}")

    summary: dict[str, dict] = {}

    for repo in new_repo_names:
        registry.register_new_repo(repo)
        summary[repo] = {}

        for domain in domains:
            try:
                _benchmark_one_repo(repo, domain, registry)
                rec = registry.get_record(repo, domain)
                if rec:
                    summary[repo][domain] = {
                        "eligible": rec["is_eligible"],
                        "score":    rec["composite_score"],
                        "verdict":  rec["verdict"],
                    }
            except Exception as e:
                log.error(f"Benchmark error for '{repo}' / '{domain}': {e}")
                summary[repo][domain] = {"eligible": False, "score": 0.0, "verdict": "error"}

            time.sleep(0.5)     # small back-off between LLM calls

    # Log a concise summary
    for repo, domains_result in summary.items():
        eligible_count = sum(1 for v in domains_result.values() if v.get("eligible"))
        total_count    = len(domains_result)
        log.info(
            f"  {repo}: eligible in {eligible_count}/{total_count} domains "
            + ("✅" if eligible_count > 0 else "❌ (will not contribute suggestions yet)")
        )

    return summary


def force_eligible(repo: str, reason: str = "manual override") -> None:
    """
    Mark a repo as eligible in all domains it covers, bypassing scoring.
    Useful for seeding trusted repos that were in the KB before reputation
    tracking was introduced.

    Args:
        repo:   Repo name (folder name in knowledge base).
        reason: Human-readable reason stored in the verdict field.
    """
    registry = get_reputation_store()
    domains  = _get_benchmark_domains()

    for domain in domains:
        chunks    = _get_repo_chunks_for_domain(repo, domain)
        relevance = _max_relevance_score(chunks)
        if relevance < MIN_DOMAIN_RELEVANCE:
            continue
        registry.upsert_record(
            repo             = repo,
            domain           = domain,
            composite_score  = 7.0,
            dimension_scores = {d: 7.0 for d in DIMENSIONS},
            is_eligible      = True,
            champion_score   = 0.0,
            verdict          = f"manual:{reason}",
            repos_compared   = [],
        )
    log.info(f"force_eligible: '{repo}' marked eligible across all relevant domains")
