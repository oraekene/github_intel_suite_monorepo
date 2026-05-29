"""
pia/analysis/project_profiler.py

Builds a concise whole-project intent profile from all scanned files.

The profile is passed into every subsequent intent analysis call so that
per-file gaps can be judged in the context of what the whole project is
trying to achieve.

Output:
  {
    "project_name":  str,
    "one_liner":     str,   # "X is a tool that does Y for Z users"
    "subsystems":    [{"name": str, "role": str}],
    "tech_stack":    [str],
    "stated_goals":  [str],
    "profile_text":  str    # formatted block ready to inject into prompts
  }
"""

from __future__ import annotations

import json
import re
import time
from typing import TYPE_CHECKING

import anthropic

from utils import cfg, log, truncate_to_tokens

if TYPE_CHECKING:
    from scan.local_scanner import ProjectFile


# ── Token budgets ─────────────────────────────────────────────────────────────
#
# We build a "digest" of the project: the first N tokens from each of the
# most representative files (README, entry points, config files).
#
MAX_DIGEST_FILES  = 12
TOKENS_PER_FILE   = 400
MAX_PROFILE_TOKENS = 800   # profile text fed into downstream prompts


PROFILER_SYSTEM = """\
You are analysing a software project to build a concise intent profile.
Given a sample of files from the project, identify:
  - What the project is (one sentence)
  - Its major subsystems and what each does
  - The technology stack in use
  - The core user-facing goals it is trying to achieve

Respond ONLY with valid JSON (no preamble, no markdown fences):
{
  "one_liner":   "<X is a Y that does Z for W users>",
  "subsystems":  [{"name": "<subsystem>", "role": "<one-sentence purpose>"}],
  "tech_stack":  ["<tech1>", "<tech2>"],
  "stated_goals": ["<goal1>", "<goal2>"]
}
"""


def _representative_files(files: list["ProjectFile"]) -> list["ProjectFile"]:
    """
    Pick the most representative files for profiling.
    Priority: README > entry points > config > other.
    """
    priority_names = {"readme", "main", "app", "index", "__init__", "setup",
                      "config", "pyproject", "package", "requirements"}

    def score(pf: "ProjectFile") -> int:
        stem = pf.relative_path.lower()
        for p in priority_names:
            if p in stem:
                return 0
        if pf.file_type in ("md", "txt"):
            return 1
        if pf.file_type in ("yaml", "toml", "json"):
            return 2
        return 3

    return sorted(files, key=score)[:MAX_DIGEST_FILES]


def _build_digest(files: list["ProjectFile"]) -> str:
    parts = []
    for pf in files:
        snippet = truncate_to_tokens(pf.content, TOKENS_PER_FILE)
        parts.append(f"### {pf.relative_path}\n```\n{snippet}\n```")
    return "\n\n".join(parts)


_CLIENT: anthropic.Anthropic | None = None

def _get_client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        api_key = cfg("anthropic.api_key", "")
        _CLIENT = anthropic.Anthropic(api_key=api_key)
    return _CLIENT


def _parse(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text.strip(), flags=re.MULTILINE)
    try:
        return json.loads(text.strip())
    except Exception:
        return {}


def build_project_profile(
    project_name: str,
    files: list["ProjectFile"],
) -> dict:
    """
    Build a whole-project intent profile from a list of ProjectFile objects.
    Returns a dict with a 'profile_text' key ready for prompt injection.
    """
    if not files:
        return _empty_profile(project_name)

    rep_files = _representative_files(files)
    digest    = _build_digest(rep_files)

    user_msg = (
        f"Project name: {project_name}\n\n"
        f"Here is a sample of its files:\n\n{digest}"
    )

    try:
        client  = _get_client()
        model   = cfg("anthropic.model", "claude-sonnet-4-20250514")

        response = client.messages.create(
            model      = model,
            max_tokens = 800,
            system     = PROFILER_SYSTEM,
            messages   = [{"role": "user", "content": user_msg}],
        )
        raw    = response.content[0].text
        parsed = _parse(raw)
    except Exception as e:
        log.warning(f"Project profiler failed for {project_name}: {e}")
        return _empty_profile(project_name)

    one_liner    = parsed.get("one_liner", f"{project_name} (profile unavailable)")
    subsystems   = parsed.get("subsystems", [])
    tech_stack   = parsed.get("tech_stack", [])
    stated_goals = parsed.get("stated_goals", [])

    # Build a formatted block for prompt injection
    subsystem_lines = "\n".join(
        f"  • {s['name']}: {s['role']}" for s in subsystems
    )
    goal_lines = "\n".join(f"  • {g}" for g in stated_goals)
    stack_line = ", ".join(tech_stack) if tech_stack else "unknown"

    profile_text = (
        f"**Project:** {project_name}\n"
        f"**Summary:** {one_liner}\n"
        f"**Stack:** {stack_line}\n"
        f"**Subsystems:**\n{subsystem_lines}\n"
        f"**Goals:**\n{goal_lines}"
    )

    # Truncate if too long
    profile_text = truncate_to_tokens(profile_text, MAX_PROFILE_TOKENS)

    result = {
        "project_name":  project_name,
        "one_liner":     one_liner,
        "subsystems":    subsystems,
        "tech_stack":    tech_stack,
        "stated_goals":  stated_goals,
        "profile_text":  profile_text,
    }

    log.info(f"Project profile built for '{project_name}': {one_liner[:60]}")
    return result


def _empty_profile(project_name: str) -> dict:
    return {
        "project_name": project_name,
        "one_liner":    f"{project_name} (no files available to profile)",
        "subsystems":   [],
        "tech_stack":   [],
        "stated_goals": [],
        "profile_text": f"**Project:** {project_name}\n(Profile unavailable)",
    }
