"""
pia/utils.py
Shared utilities: config loading, logging, path helpers, token counter.
"""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from colorama import Fore, Style, init as colorama_init

colorama_init(autoreset=True)

# ── Logging ──────────────────────────────────────────────────────────────────

class PiaFormatter(logging.Formatter):
    LEVEL_COLOURS = {
        logging.DEBUG:    Fore.CYAN,
        logging.INFO:     Fore.GREEN,
        logging.WARNING:  Fore.YELLOW,
        logging.ERROR:    Fore.RED,
        logging.CRITICAL: Fore.MAGENTA,
    }

    def format(self, record: logging.LogRecord) -> str:
        colour = self.LEVEL_COLOURS.get(record.levelno, "")
        level  = f"{colour}{record.levelname:<8}{Style.RESET_ALL}"
        return f"[PIA] {level} {record.getMessage()}"


def get_logger(name: str = "pia") -> logging.Logger:
    logger = logging.getLogger(name)
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(PiaFormatter())
        logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger


log = get_logger()


# ── Config ───────────────────────────────────────────────────────────────────

_CONFIG: dict[str, Any] | None = None
_CONFIG_PATH = Path(__file__).parent / "config.yaml"


def load_config(path: Path | str | None = None) -> dict[str, Any]:
    global _CONFIG
    if _CONFIG is not None:
        return _CONFIG

    cfg_path = Path(path) if path else _CONFIG_PATH
    if not cfg_path.exists():
        raise FileNotFoundError(f"Config file not found: {cfg_path}")

    with cfg_path.open("r", encoding="utf-8") as f:
        _CONFIG = yaml.safe_load(f)

    _validate_config(_CONFIG)
    return _CONFIG


def _validate_config(cfg: dict) -> None:
    """Warn about un-replaced placeholder values."""
    def _walk(obj: Any, path: str = "") -> None:
        if isinstance(obj, dict):
            for k, v in obj.items():
                _walk(v, f"{path}.{k}" if path else k)
        elif isinstance(obj, list):
            for i, v in enumerate(obj):
                _walk(v, f"{path}[{i}]")
        elif isinstance(obj, str) and obj.startswith("<REPLACE_THIS"):
            log.warning(f"Placeholder not filled: {path} = {obj!r}")

    _walk(cfg)


def cfg(key_path: str, default: Any = None) -> Any:
    """
    Dot-path accessor.  cfg("anthropic.api_key")
    """
    parts  = key_path.split(".")
    node   = load_config()
    for part in parts:
        if isinstance(node, dict):
            node = node.get(part, default)
        else:
            return default
    return node


# ── Path helpers ─────────────────────────────────────────────────────────────

def ensure_dir(path: Path | str) -> Path:
    p = Path(path)
    p.mkdir(parents=True, exist_ok=True)
    return p


def safe_read_file(path: Path | str, max_bytes: int | None = None) -> str | None:
    """
    Read a text file with charset detection fallback.
    Returns None if the file is binary or unreadable.
    """
    import chardet

    p = Path(path)
    try:
        raw = p.read_bytes()
    except OSError as e:
        log.debug(f"Cannot read {p}: {e}")
        return None

    if max_bytes and len(raw) > max_bytes:
        raw = raw[:max_bytes]

    # Try UTF-8 first (fast path)
    try:
        return raw.decode("utf-8")
    except UnicodeDecodeError:
        pass

    # Detect charset
    detected = chardet.detect(raw)
    enc = detected.get("encoding") or "latin-1"
    try:
        return raw.decode(enc, errors="replace")
    except Exception:
        return None


# ── Token counting ───────────────────────────────────────────────────────────

_TOKENIZER = None


def count_tokens(text: str) -> int:
    global _TOKENIZER
    if _TOKENIZER is None:
        try:
            import tiktoken
            _TOKENIZER = tiktoken.get_encoding("cl100k_base")
        except Exception:
            # Fallback: rough word-based estimate
            return len(text.split()) * 4 // 3
    return len(_TOKENIZER.encode(text, disallowed_special=()))


def truncate_to_tokens(text: str, max_tokens: int) -> str:
    """Truncate text to at most max_tokens tokens."""
    if count_tokens(text) <= max_tokens:
        return text
    # Binary search for the right character cutoff
    lo, hi = 0, len(text)
    while lo < hi - 1:
        mid = (lo + hi) // 2
        if count_tokens(text[:mid]) <= max_tokens:
            lo = mid
        else:
            hi = mid
    return text[:lo]


# ── Misc ─────────────────────────────────────────────────────────────────────

def slugify(text: str) -> str:
    """Convert a string to a safe filename slug."""
    import re
    text = text.lower().strip()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "-", text)
    return text.strip("-")
