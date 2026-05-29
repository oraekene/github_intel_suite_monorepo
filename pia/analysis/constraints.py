"""
pia/analysis/constraints.py

Reads all constraint sections from config.yaml and formats them into
a single block ready for injection into LLM prompts.

Constraints guide PIA away from suggestions that are impractical given
the user's real-world context (hardware, deployment, security posture, etc.).
"""

from __future__ import annotations

from utils import cfg


def build_constraints_block() -> str:
    """
    Read all constraint fields from config.yaml and return a formatted
    Markdown block for prompt injection.

    Returns an empty string if no constraints are configured.
    """
    lines: list[str] = []

    c = cfg("constraints", {}) or {}

    # ── Developer device ─────────────────────────────────────────────────────
    dev = c.get("dev_device", {}) or {}
    if dev:
        parts = []
        if dev.get("os"):           parts.append(f"OS: {dev['os']}")
        if dev.get("cpu"):          parts.append(f"CPU: {dev['cpu']}")
        if dev.get("ram_gb"):       parts.append(f"RAM: {dev['ram_gb']}GB")
        if dev.get("storage_type"): parts.append(f"Storage: {dev['storage_type']}")
        if dev.get("gpu"):          parts.append(f"GPU: {dev['gpu']}")
        if parts:
            lines.append("**Developer device:** " + ", ".join(parts))

    # ── Target user device ───────────────────────────────────────────────────
    user_dev = c.get("target_user_device", {}) or {}
    if user_dev:
        parts = []
        if user_dev.get("type"):         parts.append(f"Type: {user_dev['type']}")
        if user_dev.get("min_ram_gb"):   parts.append(f"Min RAM: {user_dev['min_ram_gb']}GB")
        if user_dev.get("connectivity"): parts.append(f"Connectivity: {user_dev['connectivity']}")
        if user_dev.get("notes"):        parts.append(user_dev["notes"])
        if parts:
            lines.append("**Target user device:** " + ", ".join(parts))

    # ── Performance goals ────────────────────────────────────────────────────
    perf = c.get("performance", {}) or {}
    if perf:
        parts = []
        if perf.get("max_response_ms"):     parts.append(f"Max response: {perf['max_response_ms']}ms")
        if perf.get("max_memory_mb"):       parts.append(f"Max memory: {perf['max_memory_mb']}MB")
        if perf.get("target_throughput"):   parts.append(f"Throughput: {perf['target_throughput']}")
        if perf.get("startup_time_budget"): parts.append(f"Startup: {perf['startup_time_budget']}")
        if parts:
            lines.append("**Performance goals:** " + ", ".join(parts))

    # ── Deployment ───────────────────────────────────────────────────────────
    deploy = c.get("deployment", {}) or {}
    if deploy:
        parts = []
        if deploy.get("environment"):        parts.append(deploy["environment"])
        if deploy.get("containerized") is not None:
            parts.append("containerized" if deploy["containerized"] else "bare-metal/local")
        if deploy.get("ci_cd"):              parts.append(f"CI/CD: {deploy['ci_cd']}")
        if deploy.get("cloud_provider"):     parts.append(f"Cloud: {deploy['cloud_provider']}")
        if deploy.get("offline_capable") is not None:
            parts.append("must work offline" if deploy["offline_capable"] else "internet required")
        if parts:
            lines.append("**Deployment:** " + ", ".join(parts))

    # ── Security ─────────────────────────────────────────────────────────────
    sec = c.get("security", {}) or {}
    if sec:
        parts = []
        if sec.get("auth_method"):          parts.append(f"Auth: {sec['auth_method']}")
        if sec.get("data_classification"):  parts.append(f"Data class: {sec['data_classification']}")
        if sec.get("compliance"):
            reqs = sec["compliance"] if isinstance(sec["compliance"], list) else [sec["compliance"]]
            parts.append(f"Compliance: {', '.join(reqs)}")
        if sec.get("encryption_at_rest") is not None:
            parts.append("encryption-at-rest required" if sec["encryption_at_rest"] else "no encryption-at-rest required")
        if sec.get("notes"):
            parts.append(sec["notes"])
        if parts:
            lines.append("**Security:** " + ", ".join(parts))

    # ── Team & maintainability ────────────────────────────────────────────────
    team = c.get("team", {}) or {}
    if team:
        parts = []
        if team.get("size"):                parts.append(f"Team size: {team['size']}")
        if team.get("experience_level"):    parts.append(f"Level: {team['experience_level']}")
        if team.get("tech_debt_tolerance"): parts.append(f"Tech-debt tolerance: {team['tech_debt_tolerance']}")
        if parts:
            lines.append("**Team:** " + ", ".join(parts))

    # ── Compatibility ─────────────────────────────────────────────────────────
    compat = c.get("compatibility", {}) or {}
    if compat:
        parts = []
        if compat.get("min_python"):        parts.append(f"Python ≥{compat['min_python']}")
        if compat.get("min_node"):          parts.append(f"Node ≥{compat['min_node']}")
        if compat.get("browser_targets"):   parts.append(f"Browsers: {', '.join(compat['browser_targets'])}")
        if compat.get("backward_compat"):   parts.append(f"Backward compat: {compat['backward_compat']}")
        if parts:
            lines.append("**Compatibility:** " + ", ".join(parts))

    # ── Licensing & open source ───────────────────────────────────────────────
    lic = c.get("licensing", {}) or {}
    if lic:
        parts = []
        if lic.get("project_license"):      parts.append(f"License: {lic['project_license']}")
        if lic.get("allowed_dep_licenses"): parts.append(f"Allowed deps: {', '.join(lic['allowed_dep_licenses'])}")
        if parts:
            lines.append("**Licensing:** " + ", ".join(parts))

    # ── Accessibility & i18n ─────────────────────────────────────────────────
    a11y = c.get("accessibility", {}) or {}
    if a11y:
        parts = []
        if a11y.get("wcag_level"):  parts.append(f"WCAG {a11y['wcag_level']}")
        if a11y.get("languages"):   parts.append(f"Languages: {', '.join(a11y['languages'])}")
        if parts:
            lines.append("**Accessibility / i18n:** " + ", ".join(parts))

    # ── Budget ────────────────────────────────────────────────────────────────
    budget = c.get("budget", {}) or {}
    if budget:
        parts = []
        if budget.get("max_monthly_infra_usd"): parts.append(f"Infra: ≤${budget['max_monthly_infra_usd']}/mo")
        if budget.get("max_monthly_api_usd"):   parts.append(f"API cost: ≤${budget['max_monthly_api_usd']}/mo")
        if parts:
            lines.append("**Budget:** " + ", ".join(parts))

    # ── Free-form additional notes ────────────────────────────────────────────
    notes = c.get("additional_notes", "") or ""
    if notes.strip():
        lines.append(f"**Additional constraints:** {notes.strip()}")

    if not lines:
        return ""

    return "\n".join(lines)
