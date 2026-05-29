"""
pia/analysis/user_prompts.py

Loads and assembles user guidance prompts from:
  1. config.yaml  → user_prompts.inline
  2. user_prompts.yaml (path set in config.yaml → user_prompts.file)

Provides per-module prompt getters so each analysis module only receives
the guidance relevant to it.
"""

from __future__ import annotations

from pathlib import Path

import yaml

from utils import cfg, log


_LOADED: dict | None = None
_ROOT = Path(__file__).parent.parent   # pia/ root


def _load_prompts_file() -> dict:
    global _LOADED
    if _LOADED is not None:
        return _LOADED

    prompts_path_str = cfg("user_prompts.file", "user_prompts.yaml")
    if not prompts_path_str:
        _LOADED = {}
        return _LOADED

    prompts_path = _ROOT / prompts_path_str
    if not prompts_path.exists():
        log.debug(f"User prompts file not found: {prompts_path} (optional)")
        _LOADED = {}
        return _LOADED

    try:
        with prompts_path.open("r", encoding="utf-8") as f:
            _LOADED = yaml.safe_load(f) or {}
        log.info(f"User prompts loaded from {prompts_path}")
    except Exception as e:
        log.warning(f"Could not load user prompts file: {e}")
        _LOADED = {}

    return _LOADED


def _clean(text: str | None) -> str:
    """Strip YAML comment-only lines and leading/trailing whitespace."""
    if not text:
        return ""
    lines = [
        line for line in text.splitlines()
        if not line.strip().startswith("#")
    ]
    return "\n".join(lines).strip()


def get_prompts_for_module(module: str) -> str:
    """
    Return assembled user guidance for a specific analysis module.

    Args:
        module: one of "code_review", "intent_analysis", "comparison",
                or "general" (applies to all).

    Returns:
        A single formatted string ready for prompt injection,
        or "" if no guidance is configured.
    """
    file_prompts = _load_prompts_file()
    inline       = _clean(cfg("user_prompts.inline", ""))

    parts: list[str] = []

    # General always applies
    general = _clean(file_prompts.get("general", ""))
    if general:
        parts.append(general)

    # Always-flag rules
    always_flag = _clean(file_prompts.get("always_flag", ""))
    if always_flag:
        parts.append(f"Always flag:\n{always_flag}")

    # Always-ignore rules
    always_ignore = _clean(file_prompts.get("always_ignore", ""))
    if always_ignore:
        parts.append(f"Always ignore / do not suggest:\n{always_ignore}")

    # Module-specific
    if module in file_prompts:
        mod_text = _clean(file_prompts[module])
        if mod_text:
            parts.append(mod_text)

    # Inline config block (applies to everything)
    if inline:
        parts.append(inline)

    assembled = "\n\n".join(p for p in parts if p)
    return assembled
