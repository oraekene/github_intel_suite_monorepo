"""
pia/scheduler/run_pipeline.py

Master entry point. Orchestrates all phases:
  1.   Ingest       — load + embed third-party knowledge base
  1.5  Benchmark    — score new repos against domain champions (reputation gating)
  2.   Scan         — collect your own project files
  3.   Profile      — build whole-project intent models (one call per project)
  4.   Analyse      — Claude Sonnet code-review analysis (original arm)
  4b.  Intent       — deep intent + gap analysis (new arm)
  4c.  Compare      — multi-approach comparisons (new arm)
  5.   Report       — generate Markdown reports (all arms combined)

Usage:
    python scheduler/run_pipeline.py              # full run (all arms)
    python scheduler/run_pipeline.py --ingest-only
    python scheduler/run_pipeline.py --scan-only  # skip ingest
    python scheduler/run_pipeline.py --project solarsizer-pro
    python scheduler/run_pipeline.py --clear-kb
    python scheduler/run_pipeline.py --no-intent  # skip intent analysis
    python scheduler/run_pipeline.py --no-compare # skip comparisons
    python scheduler/run_pipeline.py --compare-topic "error handling"
    python scheduler/run_pipeline.py --compare-repos "repo-a,repo-b"
    python scheduler/run_pipeline.py --skip-benchmark   # skip Phase 1.5
    python scheduler/run_pipeline.py --force-eligible fastapi  # trust a repo
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from pathlib import Path

# Add the pia root to Python path
sys.path.insert(0, str(Path(__file__).parent.parent))

from utils import cfg, log, load_config


# ── Phase 1: Ingest ───────────────────────────────────────────────────────────

def run_ingest(force_clear: bool = False) -> list[str]:
    """
    Phase 1: load + embed knowledge base.
    Returns the list of repo names that had new or changed chunks
    (used by Phase 1.5 to decide what to benchmark).
    """
    log.info("=" * 60)
    log.info("PHASE 1 — Knowledge Base Ingest")
    log.info("=" * 60)

    from ingest.loader      import load_knowledge_base
    from ingest.chunker     import chunk_documents
    from ingest.vectorstore import get_store

    store = get_store()

    if force_clear:
        log.warning("Clearing existing vector store…")
        store.clear()
        # Also clear the reputation registry so repos are re-benchmarked
        from ingest.reputation_store import get_reputation_store
        get_reputation_store().clear_all()

    docs   = load_knowledge_base()
    chunks = chunk_documents(docs)
    stats  = store.upsert_chunks(chunks)

    new_repos: list[str] = stats.get("new_repos", [])

    log.info(
        f"Ingest done — added: {stats['added']}, "
        f"skipped: {stats['skipped']}, "
        f"store total: {store.count()}"
    )
    if new_repos:
        log.info(f"New/changed repos: {', '.join(new_repos)}")

    return new_repos


# ── Phase 1.5: Repo reputation benchmarking ───────────────────────────────────

def run_benchmarking(new_repos: list[str]) -> None:
    """
    Phase 1.5: Benchmark newly ingested repos against domain champions.

    Only runs for repos that had new or changed chunks in this ingest pass.
    Skipped entirely if reputation.enabled is False or new_repos is empty.
    """
    if not cfg("reputation.enabled", True):
        log.info("Reputation gating disabled — skipping Phase 1.5")
        return

    if not new_repos:
        log.info("No new repos to benchmark — skipping Phase 1.5")
        return

    log.info("=" * 60)
    log.info("PHASE 1.5 — Repo Reputation Benchmarking")
    log.info("=" * 60)
    log.info(
        "Evaluating new repos against domain champions.  "
        "Only repos that win their domains will contribute suggestions."
    )

    from ingest.repo_benchmarker import benchmark_repos

    summary = benchmark_repos(new_repos)

    # Pretty-print final standing
    for repo, domains in summary.items():
        eligible = [d for d, v in domains.items() if v.get("eligible")]
        ineligible = [d for d, v in domains.items() if not v.get("eligible")]
        if eligible:
            log.info(f"  ✅ '{repo}' — eligible in: {', '.join(eligible)}")
        if ineligible:
            log.info(f"  ❌ '{repo}' — NOT eligible in: {', '.join(ineligible)}")

    log.info("Phase 1.5 complete")


# ── Phase 2: Scan ─────────────────────────────────────────────────────────────

def run_scan(project_filter: str | None = None) -> list:
    log.info("=" * 60)
    log.info("PHASE 2 — Project Scan")
    log.info("=" * 60)

    from scan.local_scanner  import scan_local_projects
    from scan.github_scanner import scan_github_repos
    from scan.colab_scanner  import scan_colab_notebooks

    all_files = []

    if cfg("projects.local.enabled", True):
        all_files.extend(scan_local_projects())

    if cfg("projects.github.enabled", False):
        all_files.extend(scan_github_repos())

    if cfg("projects.colab.enabled", False):
        all_files.extend(scan_colab_notebooks())

    if project_filter:
        before = len(all_files)
        all_files = [
            f for f in all_files
            if project_filter.lower() in f.project_name.lower()
        ]
        log.info(f"Project filter '{project_filter}': {before} → {len(all_files)} files")

    # Prioritise source code files for deeper analysis
    PRIORITY_TYPES = {"py", "js", "ts", "jsx", "tsx", "ipynb"}
    all_files.sort(key=lambda f: (0 if f.file_type in PRIORITY_TYPES else 1, f.project_name))

    log.info(f"Scan done — {len(all_files)} files across all sources")
    projects: dict[str, int] = {}
    for f in all_files:
        projects[f.project_name] = projects.get(f.project_name, 0) + 1
    for proj, count in sorted(projects.items()):
        log.info(f"  {proj}: {count} files")

    return all_files


# ── Phase 3: Project profiling ────────────────────────────────────────────────

def run_project_profiling(project_files: list) -> dict[str, dict]:
    """
    Build a whole-project intent profile for each unique project.
    Returns a dict: {project_name: profile_dict}
    """
    if not cfg("intent_analysis.build_project_profile", True):
        return {}

    log.info("=" * 60)
    log.info("PHASE 3 — Project Profiling")
    log.info("=" * 60)

    from analysis.project_profiler import build_project_profile

    # Group files by project
    by_project: dict[str, list] = defaultdict(list)
    for pf in project_files:
        by_project[pf.project_name].append(pf)

    profiles: dict[str, dict] = {}
    for proj_name, files in by_project.items():
        log.info(f"  Profiling '{proj_name}' ({len(files)} files)…")
        profiles[proj_name] = build_project_profile(proj_name, files)

    log.info(f"Profiling done — {len(profiles)} projects profiled")
    return profiles


# ── Phase 4: Code review (original arm) ──────────────────────────────────────

def run_analysis(project_files: list) -> list[dict]:
    log.info("=" * 60)
    log.info("PHASE 4 — Code Review Analysis")
    log.info("=" * 60)

    from analysis.llm_analyzer import analyse_project_files

    results = analyse_project_files(project_files, delay_between=1.2)
    return results


# ── Phase 4b: Intent analysis (new arm) ──────────────────────────────────────

def run_intent_analysis(
    project_files: list,
    profiles: dict[str, dict],
) -> list[dict]:
    log.info("=" * 60)
    log.info("PHASE 4b — Intent Gap Analysis")
    log.info("=" * 60)

    if not cfg("intent_analysis.enabled", True):
        log.info("Intent analysis disabled in config.yaml — skipping")
        return []

    from analysis.intent_analyzer    import analyse_intent
    from analysis.constraints        import build_constraints_block
    from analysis.user_prompts_loader import get_prompts_for_module
    from tqdm import tqdm

    max_files      = cfg("anthropic.max_files_per_run", 60)
    files          = project_files[:max_files]
    constraints    = build_constraints_block()
    user_guidance  = get_prompts_for_module("intent_analysis")

    results: list[dict] = []

    for pf in tqdm(files, desc="Intent analysis"):
        profile      = profiles.get(pf.project_name, {})
        profile_text = profile.get("profile_text", "")

        result = analyse_intent(
            pf,
            project_profile   = profile_text,
            user_system_prompt = user_guidance,
            constraints_block  = constraints,
        )
        results.append(result)
        time.sleep(1.2)

    total_unit_gaps    = sum(
        sum(len(u.get("gaps", [])) for u in r.get("unit_intents", []))
        for r in results
    )
    total_proj_gaps    = sum(len(r.get("project_level_gaps", [])) for r in results)
    total_arch_alts    = sum(len(r.get("architectural_alternatives", [])) for r in results)

    log.info(
        f"Intent analysis done — {len(results)} files, "
        f"{total_unit_gaps} unit gaps, "
        f"{total_proj_gaps} project-level gaps, "
        f"{total_arch_alts} architectural alternatives"
    )
    return results


# ── Phase 4c: Comparisons (new arm) ──────────────────────────────────────────

def run_comparisons(
    project_files: list,
    extra_topics: list[str] | None = None,
    pinned_repos: list[str] | None = None,
) -> list[dict]:
    log.info("=" * 60)
    log.info("PHASE 4c — Approach Comparisons")
    log.info("=" * 60)

    if not cfg("comparison.enabled", True):
        log.info("Comparisons disabled in config.yaml — skipping")
        return []

    from analysis.comparator          import compare_approaches, auto_compare_for_file
    from analysis.constraints         import build_constraints_block
    from analysis.user_prompts_loader  import get_prompts_for_module

    constraints    = build_constraints_block()
    user_guidance  = get_prompts_for_module("comparison")
    pinned         = pinned_repos or cfg("comparison.pinned_repos", []) or []
    results: list[dict] = []

    # Scheduled / explicit topics (from config + CLI)
    scheduled = list(cfg("comparison.scheduled_topics", []) or [])
    if extra_topics:
        scheduled.extend(extra_topics)

    for topic in scheduled:
        log.info(f"  Comparing topic: '{topic}'")
        result = compare_approaches(
            topic,
            pinned_repos       = pinned or None,
            constraints_block  = constraints,
            user_system_prompt = user_guidance,
        )
        results.append(result)
        time.sleep(1.5)

    # Auto-detect per-file comparisons
    if cfg("comparison.auto_detect", False):
        from tqdm import tqdm
        max_files = cfg("anthropic.max_files_per_run", 60)
        for pf in tqdm(project_files[:max_files], desc="Auto-compare"):
            file_comparisons = auto_compare_for_file(
                pf,
                constraints_block  = constraints,
                user_system_prompt = user_guidance,
            )
            # Tag with project name for report routing
            for cr in file_comparisons:
                cr["project"] = pf.project_name
            results.extend(file_comparisons)
            if file_comparisons:
                time.sleep(1.5)

    log.info(f"Comparisons done — {len(results)} comparison reports generated")
    return results


# ── Phase 5: Reports ──────────────────────────────────────────────────────────

def run_reports(
    results:            list[dict],
    intent_results:     list[dict],
    comparison_results: list[dict],
) -> None:
    log.info("=" * 60)
    log.info("PHASE 5 — Report Generation")
    log.info("=" * 60)

    from report.generator import generate_reports

    written = generate_reports(results, intent_results, comparison_results)

    log.info(f"\n📁 Reports saved:")
    for name, path in sorted(written.items()):
        log.info(f"  {name}: {path}")


# ── CLI ───────────────────────────────────────────────────────────────────────

def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="PIA — Project Intelligence Analyst")
    p.add_argument("--ingest-only",   action="store_true",
                   help="Rebuild KB only, then exit")
    p.add_argument("--scan-only",     action="store_true",
                   help="Skip ingest; scan + analyse + report")
    p.add_argument("--project",       type=str, default=None,
                   help="Analyse one project only (partial name match)")
    p.add_argument("--clear-kb",      action="store_true",
                   help="Wipe vector store and re-embed everything")
    p.add_argument("--config",        type=str, default=None,
                   help="Path to a custom config.yaml")
    p.add_argument("--no-intent",     action="store_true",
                   help="Skip intent gap analysis (saves API cost)")
    p.add_argument("--no-compare",    action="store_true",
                   help="Skip comparison engine (saves API cost)")
    p.add_argument("--compare-topic", type=str, default=None,
                   help="Run a one-off comparison on a specific topic, "
                        "e.g. --compare-topic \"rate limiting strategies\"")
    p.add_argument("--compare-repos",   type=str, default=None,
                   help="Comma-separated list of KB repos to pin in comparisons")
    p.add_argument("--skip-benchmark",  action="store_true",
                   help="Skip Phase 1.5 repo benchmarking (use existing reputation scores)")
    p.add_argument("--force-eligible",  type=str, default=None,
                   help="Force a repo to be eligible without benchmarking, e.g. "
                        "--force-eligible fastapi  (useful for trusted seed repos)")
    return p.parse_args()


# ── Main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    args = parse_args()
    load_config(args.config)

    start = time.time()

    log.info("╔══════════════════════════════════════════╗")
    log.info("║  PIA — Project Intelligence Analyst v2   ║")
    log.info("╚══════════════════════════════════════════╝")
    log.info(f"Args: {args}")

    try:
        # Phase 1: Ingest
        new_repos: list[str] = []
        if not args.scan_only:
            new_repos = run_ingest(force_clear=args.clear_kb)

        if args.ingest_only:
            # Still benchmark after a dedicated ingest run
            if not args.skip_benchmark:
                run_benchmarking(new_repos)
            log.info("--ingest-only — stopping after ingest + benchmark.")
            return

        # Phase 1.5: Repo reputation benchmarking
        if not args.scan_only and not args.skip_benchmark:
            run_benchmarking(new_repos)

        # --force-eligible: mark a specific repo eligible before analysis
        if args.force_eligible:
            from ingest.repo_benchmarker import force_eligible
            force_eligible(args.force_eligible, reason="cli --force-eligible")
            log.info(f"Forced '{args.force_eligible}' eligible — proceeding with analysis")

        # Phase 2: Scan
        project_files = run_scan(project_filter=args.project)
        if not project_files:
            log.warning("No project files found — check config.yaml paths.")
            return

        # Phase 3: Project profiling
        profiles = run_project_profiling(project_files)

        # Phase 4: Code review (original arm)
        results = run_analysis(project_files)

        # Phase 4b: Intent analysis (new arm)
        intent_results: list[dict] = []
        if not args.no_intent:
            intent_results = run_intent_analysis(project_files, profiles)

        # Phase 4c: Comparisons (new arm)
        comparison_results: list[dict] = []
        if not args.no_compare:
            extra_topics = [args.compare_topic] if args.compare_topic else None
            pinned_repos = (
                [r.strip() for r in args.compare_repos.split(",")]
                if args.compare_repos else None
            )
            comparison_results = run_comparisons(
                project_files,
                extra_topics = extra_topics,
                pinned_repos = pinned_repos,
            )

        # Phase 5: Reports
        run_reports(results, intent_results, comparison_results)

    except KeyboardInterrupt:
        log.warning("\nInterrupted by user.")
    except Exception as e:
        log.error(f"Pipeline failed: {e}", exc_info=True)
        sys.exit(1)
    finally:
        elapsed = time.time() - start
        log.info(f"\nTotal runtime: {elapsed:.1f}s ({elapsed / 60:.1f} min)")


if __name__ == "__main__":
    main()
