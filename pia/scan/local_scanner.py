"""
pia/scan/local_scanner.py

Recursively walks every local project root defined in config.yaml and
returns a list of ProjectFile dicts for the analysis phase.

Treats each immediate sub-folder of a root path as one "project".
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from utils import cfg, log, safe_read_file


# ── Data model ───────────────────────────────────────────────────────────────

@dataclass
class ProjectFile:
    project_name:  str
    project_root:  str       # Absolute path to the project folder
    relative_path: str       # Path relative to project root
    abs_path:      str
    file_type:     str       # Extension without dot
    content:       str
    source:        str = "local"
    metadata:      dict = field(default_factory=dict)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _should_skip_dir(name: str, exclude_set: set[str]) -> bool:
    return name.lower() in exclude_set or name.startswith(".")


def _should_include_file(path: Path, include_exts: set[str], max_bytes: int) -> bool:
    if path.suffix.lower() not in include_exts:
        return False
    try:
        if path.stat().st_size > max_bytes:
            return False
    except OSError:
        return False
    return True


def _parse_notebook_cells(content: str) -> str:
    """Extract source cells from .ipynb JSON string."""
    try:
        import json, nbformat
        nb = nbformat.reads(content, as_version=4)
        parts = []
        for cell in nb.cells:
            if cell.cell_type in ("code", "markdown") and cell.source.strip():
                tag = "# CODE\n" if cell.cell_type == "code" else "# MARKDOWN\n"
                parts.append(tag + cell.source.strip())
        return "\n\n".join(parts)
    except Exception:
        return content


# ── Main scanner ─────────────────────────────────────────────────────────────

def scan_local_projects(roots: list[str] | None = None) -> list[ProjectFile]:
    """
    Scan all local project roots.  Returns a flat list of ProjectFile objects.
    """
    cfg_roots      = roots or cfg("projects.local.roots", [])
    include_exts   = set(cfg("scan.include_extensions", [".py", ".js", ".md"]))
    exclude_dirs   = {d.lower() for d in cfg("scan.exclude_dirs", [])}
    max_bytes      = cfg("scan.max_file_size_bytes", 150_000)

    if not cfg("projects.local.enabled", True):
        log.info("Local project scanning disabled in config.")
        return []

    if not cfg_roots:
        log.warning("No local project roots configured.")
        return []

    all_files: list[ProjectFile] = []

    for root_str in cfg_roots:
        root_path = Path(root_str)
        if not root_path.exists():
            log.warning(f"Local root does not exist: {root_path}")
            continue

        log.info(f"Scanning local root: {root_path}")

        # Each immediate subfolder = one project
        project_dirs: list[Path] = []
        for entry in sorted(root_path.iterdir()):
            if entry.is_dir() and not entry.name.startswith("."):
                project_dirs.append(entry)

        # If root itself contains code files (flat layout), treat root as a project
        if not project_dirs:
            project_dirs = [root_path]

        for proj_dir in project_dirs:
            proj_name  = proj_dir.name
            proj_files = _scan_project_dir(
                proj_dir, proj_name, include_exts, exclude_dirs, max_bytes
            )
            all_files.extend(proj_files)
            log.info(f"  [{proj_name}] {len(proj_files)} files found")

    log.info(f"Local scan complete — {len(all_files)} files across all projects")
    return all_files


def _scan_project_dir(
    proj_dir:    Path,
    proj_name:   str,
    include_exts: set[str],
    exclude_dirs: set[str],
    max_bytes:   int,
) -> list[ProjectFile]:
    files: list[ProjectFile] = []

    for dirpath_str, dirs, filenames in os.walk(proj_dir):
        dirs[:] = [
            d for d in dirs
            if not _should_skip_dir(d, exclude_dirs)
        ]

        dirpath = Path(dirpath_str)

        for fname in filenames:
            fpath = dirpath / fname

            if not _should_include_file(fpath, include_exts, max_bytes):
                continue

            ext = fpath.suffix.lower()

            content = safe_read_file(fpath, max_bytes=max_bytes)
            if not content or not content.strip():
                continue

            if ext == ".ipynb":
                content = _parse_notebook_cells(content)

            rel = str(fpath.relative_to(proj_dir))

            files.append(ProjectFile(
                project_name  = proj_name,
                project_root  = str(proj_dir),
                relative_path = rel,
                abs_path      = str(fpath),
                file_type     = ext.lstrip("."),
                content       = content,
                source        = "local",
                metadata      = {
                    "project":      proj_name,
                    "relative_path": rel,
                    "file_type":    ext.lstrip("."),
                    "source":       "local",
                },
            ))

    return files


# ── CLI helper ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    files = scan_local_projects()
    for f in files[:10]:
        print(f"  [{f.project_name}] {f.relative_path} ({f.file_type})")
    print(f"\nTotal: {len(files)} files")
