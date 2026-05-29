"""
pia/ingest/loader.py

Walks the third-party knowledge-base directory (your exported
NotebookLM / GitHub README / docs folder) and returns a list of
Document dicts ready for chunking.

Supports: .md, .txt, .rst, .adoc, .ipynb, .py, .js, .ts, .yaml,
          .yml, .toml, .json, .html (stripped), .csv (first 200 rows)
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterator

from utils import cfg, log, safe_read_file

# ── Data model ───────────────────────────────────────────────────────────────

@dataclass
class RawDocument:
    source_path: str          # Absolute path on disk
    repo_name:   str          # Derived from folder structure
    filename:    str
    file_type:   str          # Extension without dot
    content:     str
    metadata:    dict = field(default_factory=dict)


# ── Extension whitelist ──────────────────────────────────────────────────────

TEXT_EXTENSIONS = {
    ".md", ".txt", ".rst", ".adoc", ".asciidoc",
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".yaml", ".yml", ".toml", ".ini", ".cfg",
    ".json", ".html", ".htm", ".csv", ".sh",
    ".ipynb",
}

SKIP_DIRS = {
    "node_modules", ".git", "__pycache__", ".venv",
    "venv", "env", "dist", "build", ".next",
}

MAX_FILE_BYTES = 200_000   # 200 KB ceiling per file in knowledge base


# ── Notebook parser ──────────────────────────────────────────────────────────

def _extract_notebook(path: Path) -> str:
    """Pull source cells out of a .ipynb file."""
    try:
        import nbformat
        nb = nbformat.read(str(path), as_version=4)
        parts = []
        for cell in nb.cells:
            if cell.cell_type in ("code", "markdown"):
                src = cell.source.strip()
                if src:
                    prefix = "# CODE\n" if cell.cell_type == "code" else "# MARKDOWN\n"
                    parts.append(prefix + src)
        return "\n\n".join(parts)
    except Exception as e:
        log.debug(f"Notebook parse failed for {path}: {e}")
        return safe_read_file(path, max_bytes=MAX_FILE_BYTES) or ""


# ── HTML stripper ────────────────────────────────────────────────────────────

def _strip_html(text: str) -> str:
    """Very lightweight HTML → plain text (no extra deps)."""
    import re
    text = re.sub(r"<script[^>]*>.*?</script>", " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<style[^>]*>.*?</style>",  " ", text, flags=re.DOTALL | re.IGNORECASE)
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"&[a-zA-Z]+;", " ", text)
    text = re.sub(r"\s{3,}", "\n\n", text)
    return text.strip()


# ── CSV truncator ────────────────────────────────────────────────────────────

def _truncate_csv(text: str, max_rows: int = 200) -> str:
    lines = text.splitlines()
    if len(lines) > max_rows + 1:
        lines = lines[:max_rows + 1] + [f"... (truncated to {max_rows} rows)"]
    return "\n".join(lines)


# ── Repo name heuristic ──────────────────────────────────────────────────────

def _infer_repo_name(file_path: Path, base_dir: Path) -> str:
    """
    Given the knowledge-base root and a file path, try to derive a
    meaningful repo/project name.

    Strategy:
    1. If file lives in <base>/<something>/..., use <something> as name.
    2. Otherwise fall back to the file's stem.
    """
    try:
        rel = file_path.relative_to(base_dir)
        parts = rel.parts
        if len(parts) > 1:
            return parts[0]         # first sub-folder = repo name
    except ValueError:
        pass
    return file_path.stem


# ── Main loader ──────────────────────────────────────────────────────────────

def load_knowledge_base(source_dir: str | Path | None = None) -> list[RawDocument]:
    """
    Walk the knowledge-base directory and return all readable documents.
    """
    base = Path(source_dir or cfg("knowledge_base.source_dir"))

    if not base.exists():
        raise FileNotFoundError(
            f"Knowledge base directory not found: {base}\n"
            f"Check 'knowledge_base.source_dir' in config.yaml"
        )

    docs: list[RawDocument] = []
    skipped = 0

    log.info(f"Scanning knowledge base: {base}")

    for root, dirs, files in os.walk(base):
        # Prune skip-dirs in place so os.walk doesn't descend into them
        dirs[:] = [d for d in dirs if d.lower() not in SKIP_DIRS]

        root_path = Path(root)

        for fname in files:
            fpath = root_path / fname
            ext   = fpath.suffix.lower()

            if ext not in TEXT_EXTENSIONS:
                skipped += 1
                continue

            if fpath.stat().st_size > MAX_FILE_BYTES and ext not in {".ipynb"}:
                log.debug(f"Skipping (too large): {fpath.name}")
                skipped += 1
                continue

            # Parse content based on type
            if ext == ".ipynb":
                content = _extract_notebook(fpath)
            elif ext in {".html", ".htm"}:
                raw = safe_read_file(fpath, max_bytes=MAX_FILE_BYTES)
                content = _strip_html(raw) if raw else ""
            elif ext == ".csv":
                raw = safe_read_file(fpath, max_bytes=MAX_FILE_BYTES)
                content = _truncate_csv(raw) if raw else ""
            else:
                content = safe_read_file(fpath, max_bytes=MAX_FILE_BYTES) or ""

            if not content.strip():
                skipped += 1
                continue

            repo_name = _infer_repo_name(fpath, base)

            docs.append(RawDocument(
                source_path = str(fpath),
                repo_name   = repo_name,
                filename    = fname,
                file_type   = ext.lstrip("."),
                content     = content,
                metadata    = {
                    "repo":       repo_name,
                    "filename":   fname,
                    "file_type":  ext.lstrip("."),
                    "source":     str(fpath),
                },
            ))

    log.info(f"Loaded {len(docs)} documents from knowledge base ({skipped} skipped)")
    return docs


# ── CLI helper ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    docs = load_knowledge_base()
    for d in docs[:5]:
        print(f"  [{d.repo_name}] {d.filename} — {len(d.content):,} chars")
    print(f"\nTotal: {len(docs)} documents")
