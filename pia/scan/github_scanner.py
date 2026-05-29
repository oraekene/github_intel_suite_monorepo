"""
pia/scan/github_scanner.py

Fetches file content from your GitHub repositories using the
GitHub REST API (via PyGithub).

• Only scans repos you OWN (not forked/starred third-party repos)
• Downloads file content in memory — no disk writes
• Respects rate limits with automatic backoff
"""

from __future__ import annotations

import base64
import time
from dataclasses import dataclass, field

from utils import cfg, log, count_tokens, truncate_to_tokens
from scan.local_scanner import ProjectFile     # reuse same dataclass


# ── Constants ────────────────────────────────────────────────────────────────

RATE_LIMIT_PAUSE = 2.0        # seconds to wait between requests when near limit
MAX_FILE_TOKENS  = 3_000      # truncate very large files before analysis
GITHUB_API_DELAY = 0.3        # polite delay between file fetches (seconds)


# ── Helpers ──────────────────────────────────────────────────────────────────

def _should_include(path: str, include_exts: set[str]) -> bool:
    from pathlib import PurePosixPath
    ext = PurePosixPath(path).suffix.lower()
    return ext in include_exts


def _decode_content(encoded: str) -> str:
    """Decode base64 GitHub file content."""
    try:
        return base64.b64decode(encoded).decode("utf-8", errors="replace")
    except Exception:
        return ""


def _parse_notebook(raw: str) -> str:
    try:
        import nbformat
        nb = nbformat.reads(raw, as_version=4)
        parts = []
        for cell in nb.cells:
            if cell.cell_type in ("code", "markdown") and cell.source.strip():
                tag = "# CODE\n" if cell.cell_type == "code" else "# MARKDOWN\n"
                parts.append(tag + cell.source.strip())
        return "\n\n".join(parts)
    except Exception:
        return raw


# ── Main scanner ─────────────────────────────────────────────────────────────

def scan_github_repos() -> list[ProjectFile]:
    """
    Fetch all files from your owned GitHub repos.
    Returns a flat list of ProjectFile objects.
    """
    if not cfg("projects.github.enabled", False):
        log.info("GitHub scanning disabled in config.")
        return []

    token    = cfg("projects.github.token", "")
    username = cfg("projects.github.username", "")
    exclude  = set(cfg("projects.github.exclude_repos", []))

    if not token or token.startswith("<REPLACE"):
        log.warning("GitHub token not configured — skipping GitHub scan.")
        return []

    try:
        from github import Github, GithubException, RateLimitExceededException
    except ImportError:
        log.error("PyGithub not installed. Run: pip install PyGithub")
        return []

    include_exts = set(cfg("scan.include_extensions", []))
    exclude_dirs = {d.lower() for d in cfg("scan.exclude_dirs", [])}

    g     = Github(token)
    user  = g.get_user(username)
    repos = list(user.get_repos(type="owner"))

    log.info(f"Found {len(repos)} owned repos for @{username}")

    all_files: list[ProjectFile] = []

    for repo in repos:
        if repo.name in exclude:
            log.info(f"  Skipping excluded repo: {repo.name}")
            continue
        if repo.fork:
            log.debug(f"  Skipping fork: {repo.name}")
            continue

        log.info(f"  Scanning repo: {repo.name}")
        repo_files = _fetch_repo_files(
            repo, include_exts, exclude_dirs, g
        )
        all_files.extend(repo_files)
        log.info(f"    → {len(repo_files)} files")
        time.sleep(GITHUB_API_DELAY)

    log.info(f"GitHub scan complete — {len(all_files)} total files")
    return all_files


def _fetch_repo_files(
    repo,
    include_exts: set[str],
    exclude_dirs: set[str],
    g,
) -> list[ProjectFile]:
    from github import GithubException, RateLimitExceededException

    files: list[ProjectFile] = []

    # Get the full recursive file tree
    try:
        tree = repo.get_git_tree(repo.default_branch, recursive=True)
    except GithubException as e:
        log.warning(f"  Could not get tree for {repo.name}: {e}")
        return []

    for item in tree.tree:
        if item.type != "blob":
            continue

        path = item.path

        # Skip excluded directories
        parts = path.split("/")
        if any(p.lower() in exclude_dirs for p in parts[:-1]):
            continue

        if not _should_include(path, include_exts):
            continue

        # Fetch file content
        try:
            _check_rate_limit(g)
            file_obj = repo.get_contents(path)
            if isinstance(file_obj, list):
                continue    # shouldn't happen for blobs

            if file_obj.size > 200_000:
                log.debug(f"  Skipping large file: {path} ({file_obj.size:,} bytes)")
                continue

            raw = _decode_content(file_obj.content)
            if not raw.strip():
                continue

            # Parse notebooks
            from pathlib import PurePosixPath
            ext = PurePosixPath(path).suffix.lower()
            if ext == ".ipynb":
                raw = _parse_notebook(raw)

            # Truncate very large files
            if count_tokens(raw) > MAX_FILE_TOKENS:
                raw = truncate_to_tokens(raw, MAX_FILE_TOKENS)

            files.append(ProjectFile(
                project_name  = repo.name,
                project_root  = f"github:{repo.full_name}",
                relative_path = path,
                abs_path      = f"https://github.com/{repo.full_name}/blob/{repo.default_branch}/{path}",
                file_type     = ext.lstrip("."),
                content       = raw,
                source        = "github",
                metadata      = {
                    "project":       repo.name,
                    "relative_path": path,
                    "file_type":     ext.lstrip("."),
                    "source":        "github",
                    "repo_url":      repo.html_url,
                },
            ))

            time.sleep(GITHUB_API_DELAY)

        except RateLimitExceededException:
            log.warning("GitHub rate limit hit — waiting 60 seconds…")
            time.sleep(60)
        except GithubException as e:
            log.debug(f"  Could not fetch {path}: {e}")

    return files


def _check_rate_limit(g) -> None:
    """Pause if remaining API calls are low."""
    try:
        rl = g.get_rate_limit()
        if rl.core.remaining < 50:
            reset_ts = rl.core.reset.timestamp()
            wait = max(0, reset_ts - time.time()) + 5
            log.warning(f"GitHub rate limit low ({rl.core.remaining} left) — waiting {wait:.0f}s")
            time.sleep(wait)
    except Exception:
        pass
