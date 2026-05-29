"""
pia/report/generator.py

Aggregates LLM analysis results into:
  1. Per-project Markdown reports  (reports/<date>/<project>.md)
  2. A master summary report       (reports/<date>/00_SUMMARY.md)

Report sections:
  - Executive summary (overall health score)
  - Findings by category (with source attribution)
  - Intent gaps: missing sub-functions, features, architectural alternatives
  - Approach comparisons with verdicts
  - Per-file detail
  - Quick wins (low-effort, high-impact list)
"""

from __future__ import annotations

import json
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Sequence

from utils import cfg, ensure_dir, log, slugify


# ── Constants ─────────────────────────────────────────────────────────────────

SEVERITY_ORDER   = {"high": 0, "medium": 1, "low": 2}
SEVERITY_EMOJI   = {"high": "🔴", "medium": "🟡", "low": "🟢"}
CATEGORY_EMOJI   = {
    "Architecture":    "🏗️",
    "Error Handling":  "🛡️",
    "Performance":     "⚡",
    "Security":        "🔒",
    "Testing":         "🧪",
    "DX / Tooling":    "🛠️",
    "Documentation":   "📝",
    "Code Quality":    "✨",
}


# ── Scoring helper ────────────────────────────────────────────────────────────

def _health_score(findings: list[dict]) -> int:
    """
    Simple 0–100 health score.  Starts at 100, deducted per finding severity.
    """
    deductions = {"high": 12, "medium": 5, "low": 2}
    score = 100
    for f in findings:
        score -= deductions.get(f.get("severity", "low"), 2)
    return max(0, score)


def _score_label(score: int) -> str:
    if score >= 85: return "✅ Healthy"
    if score >= 65: return "⚠️  Needs Attention"
    return "🔴 Critical Issues"


# ── Per-project report ────────────────────────────────────────────────────────

def _build_project_report(
    project_name: str,
    file_results: list[dict],
    run_date:     str,
) -> str:
    all_findings = [f for r in file_results for f in r.get("findings", [])]
    score        = _health_score(all_findings)
    errors       = [r for r in file_results if r.get("error")]

    # Group findings by category
    by_category: dict[str, list[dict]] = defaultdict(list)
    for finding in all_findings:
        cat = finding.get("category", "Code Quality")
        by_category[cat].append(finding)

    # Group findings by file
    by_file: dict[str, list[dict]] = defaultdict(list)
    for r in file_results:
        for f in r.get("findings", []):
            by_file[r["file_path"]].append(f)

    # Quick wins: low severity but high value (easy to implement)
    quick_wins = [
        f for f in all_findings
        if f.get("severity") == "low"
    ]
    high_priority = [
        f for f in all_findings
        if f.get("severity") == "high"
    ]

    lines: list[str] = []

    # ── Header ────────────────────────────────────────────────────────────────
    lines += [
        f"# PIA Report: `{project_name}`",
        f"",
        f"> Generated: {run_date}  |  Files analysed: {len(file_results)}  "
        f"|  Findings: {len(all_findings)}  |  Health: **{score}/100** {_score_label(score)}",
        f"",
        "---",
        "",
    ]

    # ── High priority alerts ──────────────────────────────────────────────────
    if high_priority:
        lines += [
            "## 🚨 High Priority Issues",
            "",
        ]
        for f in high_priority:
            lines += [
                f"### {f.get('title', 'Untitled')}",
                f"**Category:** {f.get('category')}  |  "
                f"**Source:** `{f.get('source_repo', 'N/A')}`",
                "",
                f"{f.get('description', '')}",
                "",
                "**Suggested fix:**",
                f"```",
                f"{f.get('suggestion', '')}",
                f"```",
                "",
            ]
        lines.append("---\n")

    # ── By category ──────────────────────────────────────────────────────────
    lines += ["## Findings by Category", ""]

    for cat in sorted(by_category.keys(),
                      key=lambda c: min(SEVERITY_ORDER.get(f.get("severity","low"),2)
                                        for f in by_category[c])):
        emoji    = CATEGORY_EMOJI.get(cat, "📌")
        cat_finds = sorted(
            by_category[cat],
            key=lambda f: SEVERITY_ORDER.get(f.get("severity", "low"), 2)
        )
        lines += [f"### {emoji} {cat}", ""]

        for f in cat_finds:
            sev  = f.get("severity", "low")
            icon = SEVERITY_EMOJI.get(sev, "🟢")
            lines += [
                f"#### {icon} {f.get('title', 'Untitled')} `[{sev}]`",
                f"",
                f"**Source repo:** `{f.get('source_repo', 'N/A')}`",
                f"",
                f"{f.get('description', '')}",
                f"",
                f"<details>",
                f"<summary>💡 Suggested implementation</summary>",
                f"",
                f"```",
                f"{f.get('suggestion', '(No suggestion provided)')}",
                f"```",
                f"</details>",
                f"",
            ]
        lines.append("")

    # ── Per-file breakdown ────────────────────────────────────────────────────
    if cfg("reports.include_file_detail", True) and by_file:
        lines += ["---", "", "## File-by-File Breakdown", ""]

        for r in sorted(file_results, key=lambda x: -len(x.get("findings", []))):
            fpath    = r["file_path"]
            finds    = r.get("findings", [])
            summary  = r.get("summary", "")
            err      = r.get("error")

            if err:
                lines.append(f"- ❌ `{fpath}` — *Error: {err}*")
                continue
            if not finds and not summary:
                continue

            fscore = _health_score(finds)
            lines += [
                f"### `{fpath}` — {fscore}/100",
                f"",
            ]
            if summary:
                lines += [f"*{summary}*", ""]

            for f in sorted(finds, key=lambda x: SEVERITY_ORDER.get(x.get("severity","low"),2)):
                icon = SEVERITY_EMOJI.get(f.get("severity","low"), "🟢")
                lines.append(
                    f"- {icon} **{f.get('title')}** "
                    f"({f.get('category')}) — "
                    f"`{f.get('source_repo', 'N/A')}`"
                )
            lines.append("")

    # ── Quick wins ────────────────────────────────────────────────────────────
    if quick_wins:
        lines += ["---", "", "## 🎯 Quick Wins", ""]
        lines.append("Low-effort improvements you can tackle right now:\n")
        for f in quick_wins[:8]:
            lines.append(f"- [ ] **{f.get('title')}** ({f.get('category')}) — {f.get('description', '')[:100]}…")
        lines.append("")

    return "\n".join(lines)


# ── Summary report ────────────────────────────────────────────────────────────

def _build_summary_report(
    all_results_by_project: dict[str, list[dict]],
    run_date: str,
) -> str:
    rows: list[tuple[str, int, int, int, int]] = []

    for proj, file_results in all_results_by_project.items():
        all_f  = [f for r in file_results for f in r.get("findings", [])]
        score  = _health_score(all_f)
        highs  = sum(1 for f in all_f if f.get("severity") == "high")
        meds   = sum(1 for f in all_f if f.get("severity") == "medium")
        lows   = sum(1 for f in all_f if f.get("severity") == "low")
        rows.append((proj, score, highs, meds, lows))

    rows.sort(key=lambda x: x[1])   # lowest score first

    lines: list[str] = [
        "# PIA — Master Summary",
        "",
        f"> Run date: {run_date}  |  Projects: {len(rows)}",
        "",
        "| Project | Health | 🔴 High | 🟡 Medium | 🟢 Low |",
        "|---------|--------|---------|----------|--------|",
    ]

    for proj, score, h, m, l in rows:
        label = _score_label(score)
        lines.append(f"| `{proj}` | **{score}** {label} | {h} | {m} | {l} |")

    lines += [
        "",
        "---",
        "",
        "## Projects Needing Immediate Attention",
        "",
    ]

    urgent = [(p, s, h) for p, s, h, *_ in rows if h > 0 or s < 65]
    if urgent:
        for proj, score, highs in urgent:
            lines.append(f"- **`{proj}`** — Score: {score}/100, High issues: {highs}")
    else:
        lines.append("*No critical issues found across all projects. Great work!*")

    lines += [
        "",
        "---",
        "",
        "## How to Read This Report",
        "",
        "- Each project has its own detailed report in this folder.",
        "- **Score** is computed as 100 − (12×high + 5×medium + 2×low).",
        "- Findings reference the open-source repo in your knowledge base",
        "  that demonstrates the recommended pattern.",
        "- Collapsed `<details>` blocks contain concrete code suggestions.",
        "",
    ]

    return "\n".join(lines)


# ── Intent gap report builder ─────────────────────────────────────────────────

GAP_EMOJI = {
    "sub-function":  "🔧",
    "guard":         "🛡️",
    "feature":       "✨",
    "integration":   "🔗",
    "test":          "🧪",
}


def _render_intent_section(intent_results: list[dict]) -> str:
    """Render the intent gap analysis section for a project report."""
    if not intent_results:
        return ""

    lines: list[str] = [
        "",
        "---",
        "",
        "## 🎯 Intent Gap Analysis",
        "",
        "> *What the code is trying to do — and what's missing to fully achieve it.*",
        "",
    ]

    for ir in intent_results:
        file_path = ir.get("file_path", "")
        summary   = ir.get("summary", "")
        unit_intents = ir.get("unit_intents", [])
        project_gaps = ir.get("project_level_gaps", [])
        arch_alts    = ir.get("architectural_alternatives", [])

        if not (unit_intents or project_gaps or arch_alts):
            continue

        lines.append(f"### `{file_path}`")
        if summary:
            lines.append(f"> {summary}")
        lines.append("")

        # Unit-level gaps
        for ui in unit_intents:
            gaps = ui.get("gaps", [])
            if not gaps:
                continue
            unit     = ui.get("unit", "?")
            intent   = ui.get("stated_intent", "")
            lines.append(f"#### `{unit}` — {intent}")
            for gap in gaps:
                sev  = gap.get("severity", "low")
                gtyp = gap.get("gap_type", "")
                icon = GAP_EMOJI.get(gtyp, "➕")
                sevicon = SEVERITY_EMOJI.get(sev, "🟢")
                lines.append(f"- {sevicon} {icon} **{gap.get('title','')}** ({gtyp})")
                lines.append(f"  {gap.get('description','')}")
                suggestion = gap.get("suggestion", "").strip()
                if suggestion:
                    lines.append(f"  <details><summary>Suggestion</summary>")
                    lines.append(f"  \n  ```\n  {suggestion}\n  ```\n  </details>")
            lines.append("")

        # Project-level gaps
        if project_gaps:
            lines.append("#### 🗺️ Project-Level Missing Features")
            for pg in project_gaps:
                sev = pg.get("severity", "low")
                sevicon = SEVERITY_EMOJI.get(sev, "🟢")
                lines.append(f"- {sevicon} **{pg.get('title','')}**")
                lines.append(f"  {pg.get('description','')}")
                if pg.get("suggestion"):
                    lines.append(f"  <details><summary>Suggestion</summary>")
                    lines.append(f"  \n  ```\n  {pg['suggestion']}\n  ```\n  </details>")
            lines.append("")

        # Architectural alternatives
        if arch_alts:
            lines.append("#### 🏗️ Architectural Alternatives Worth Considering")
            for alt in arch_alts:
                lines.append(f"**{alt.get('title','')}** *(from {alt.get('source_repo','?')})*")
                lines.append(f"> {alt.get('rationale','')}")
                lines.append(f"*Trade-offs:* {alt.get('trade_offs','')}")
                sketch = alt.get("sketch", "").strip()
                if sketch:
                    lines.append(f"```\n{sketch}\n```")
                lines.append("")

    return "\n".join(lines)


# ── Comparison report builder ─────────────────────────────────────────────────

def _render_comparison_section(comparison_results: list[dict]) -> str:
    """Render the multi-approach comparison section for a project report."""
    if not comparison_results:
        return ""

    lines: list[str] = [
        "",
        "---",
        "",
        "## ⚖️ Approach Comparisons",
        "",
        "> *Side-by-side analysis of how different open-source projects solve the same problems.*",
        "",
    ]

    for cr in comparison_results:
        topic = cr.get("topic", "Unknown topic")
        repos = cr.get("repos_compared", [])
        approaches = cr.get("approaches", [])
        matrix = cr.get("comparison_matrix", [])
        verdict = cr.get("verdict", {})

        if not approaches:
            continue

        lines.append(f"### 🔍 {topic}")
        lines.append(f"*Comparing: {', '.join(f'`{r}`' for r in repos)}*")
        lines.append("")

        # Approaches
        for ap in approaches:
            repo = ap.get("source_repo", "?")
            name = ap.get("approach_name", "")
            summary = ap.get("summary", "")
            pros = ap.get("pros", [])
            cons = ap.get("cons", [])
            best_for = ap.get("best_for", "")
            lines.append(f"**`{repo}` — {name}**")
            lines.append(f"{summary}")
            if pros:
                lines.append("✅ " + " · ".join(pros))
            if cons:
                lines.append("❌ " + " · ".join(cons))
            if best_for:
                lines.append(f"*Best for:* {best_for}")
            lines.append("")

        # Comparison matrix
        if matrix:
            # Build header from all repos
            all_repos = list(dict.fromkeys(
                repo for row in matrix for repo in row.get("scores", {}).keys()
            ))
            header = "| Dimension | " + " | ".join(all_repos) + " |"
            sep    = "|-----------|" + "|".join(["---"] * len(all_repos)) + "|"
            lines += [header, sep]
            for row in matrix:
                dim    = row.get("dimension", "?")
                scores = row.get("scores", {})
                cells  = " | ".join(scores.get(r, "—") for r in all_repos)
                lines.append(f"| {dim} | {cells} |")
            lines.append("")

        # Verdict
        if verdict:
            winner    = verdict.get("winner", "")
            rationale = verdict.get("rationale", "")
            caveat    = verdict.get("caveat", "")
            lines.append(f"**🏆 Verdict: `{winner}`**")
            lines.append(rationale)
            if caveat and caveat.lower() != "none":
                lines.append(f"*Caveat:* {caveat}")
            lines.append("")

    return "\n".join(lines)


# ── Public API ────────────────────────────────────────────────────────────────

def generate_reports(
    results: list[dict],
    intent_results: list[dict] | None = None,
    comparison_results: list[dict] | None = None,
) -> dict[str, Path]:
    """
    Generate all reports from analysis results.

    Args:
        results:            Standard code-review results (list of file dicts).
        intent_results:     Optional intent gap analysis results.
        comparison_results: Optional multi-approach comparison results.

    Returns:
        Dict mapping project names (+ 'SUMMARY') to output file Paths.
    """
    out_dir  = Path(cfg("reports.output_dir", "reports"))
    run_date = datetime.now().strftime("%Y-%m-%d_%H-%M")
    run_dir  = ensure_dir(out_dir / run_date)

    # Group by project
    by_project: dict[str, list[dict]] = defaultdict(list)
    for r in results:
        by_project[r["project"]].append(r)

    # Group intent results by project
    intent_by_project: dict[str, list[dict]] = defaultdict(list)
    for ir in (intent_results or []):
        intent_by_project[ir["project"]].append(ir)

    # Group comparison results by project (comparisons are project-scoped)
    comparison_by_project: dict[str, list[dict]] = defaultdict(list)
    for cr in (comparison_results or []):
        # Comparisons tagged with a project are written to that project's report;
        # untagged ones go to a standalone comparisons report.
        proj = cr.get("project", "__comparisons__")
        comparison_by_project[proj].append(cr)

    written: dict[str, Path] = {}
    min_findings = cfg("reports.min_findings_to_report", 1)

    for proj, file_results in by_project.items():
        total_findings = sum(len(r.get("findings", [])) for r in file_results)
        proj_intent    = intent_by_project.get(proj, [])
        proj_compare   = comparison_by_project.get(proj, [])

        # Skip only if nothing to report at all
        has_intent_content = any(
            ir.get("unit_intents") or ir.get("project_level_gaps") or ir.get("architectural_alternatives")
            for ir in proj_intent
        )
        if total_findings < min_findings and not has_intent_content and not proj_compare:
            log.debug(f"Skipping report for {proj} (no findings)")
            continue

        # Build base report
        report_md = _build_project_report(proj, file_results, run_date)

        # Append intent section
        intent_section = _render_intent_section(proj_intent)
        if intent_section:
            report_md += intent_section

        # Append comparison section
        compare_section = _render_comparison_section(proj_compare)
        if compare_section:
            report_md += compare_section

        outpath = run_dir / f"{slugify(proj)}.md"
        outpath.write_text(report_md, encoding="utf-8")
        written[proj] = outpath
        log.info(f"  Written: {outpath}")

    # Standalone comparisons (not tied to a specific project)
    standalone_comparisons = comparison_by_project.get("__comparisons__", [])
    if standalone_comparisons:
        compare_md  = "# PIA — Approach Comparisons\n"
        compare_md += f"\n> Run date: {run_date}\n"
        compare_md += _render_comparison_section(standalone_comparisons)
        cpath = run_dir / "00_COMPARISONS.md"
        cpath.write_text(compare_md, encoding="utf-8")
        written["COMPARISONS"] = cpath
        log.info(f"  Comparisons: {cpath}")

    # Summary
    summary_md   = _build_summary_report(by_project, run_date)
    summary_path = run_dir / "00_SUMMARY.md"
    summary_path.write_text(summary_md, encoding="utf-8")
    written["SUMMARY"] = summary_path
    log.info(f"  Summary: {summary_path}")

    # Raw JSON
    all_data = {
        "code_review":   results,
        "intent":        intent_results or [],
        "comparisons":   comparison_results or [],
    }
    json_path = run_dir / "raw_results.json"
    json_path.write_text(
        json.dumps(all_data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    log.info(f"\n✅ Reports written to: {run_dir}")
    return written
