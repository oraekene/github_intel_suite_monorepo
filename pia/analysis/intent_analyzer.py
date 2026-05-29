"""
pia/analysis/intent_analyzer.py

Deep intent analysis engine.  Given a project file and its project-level
intent profile, this module:

  1. Extracts the intended purpose of every function / class / section.
  2. Identifies MISSING sub-functions, helpers, and guard clauses that are
     needed to fully achieve each unit's intent.
  3. Identifies MISSING whole features that are needed at the project level.
  4. Optionally suggests a fundamentally different architectural approach
     when one from the KB would better achieve the same intent.

Output schema per file:
  {
    "project":          str,
    "file_path":        str,
    "unit_intents": [
      {
        "unit":          str,    # function / class / section name
        "stated_intent": str,    # what the code is trying to do
        "gaps": [
          {
            "gap_type":      "sub-function" | "guard" | "feature" | "integration",
            "title":         str,
            "description":   str,
            "severity":      "high" | "medium" | "low",
            "suggestion":    str   # concrete code or design guidance
          }
        ]
      }
    ],
    "project_level_gaps": [
      {
        "title":       str,
        "description": str,
        "severity":    str,
        "suggestion":  str
      }
    ],
    "architectural_alternatives": [
      {
        "title":       str,
        "rationale":   str,
        "source_repo": str,
        "trade_offs":  str,
        "sketch":      str   # pseudo-code or design sketch
      }
    ],
    "summary":  str,
    "error":    str | None
  }
"""

from __future__ import annotations

import json
import re
import time
from typing import TYPE_CHECKING

import anthropic

from utils import cfg, log, truncate_to_tokens
from analysis.retriever import retrieve_context_for_file

if TYPE_CHECKING:
    from scan.local_scanner import ProjectFile


# ── Token budgets ──────────────────────────────────────────────────────────────
FILE_CONTENT_TOKENS  = 2_000   # larger budget — intent needs full context
PROJECT_PROFILE_TOKENS = 600


# ── System prompt ──────────────────────────────────────────────────────────────

INTENT_SYSTEM_PROMPT = """\
You are PIA-Intent, an expert software architect focused on understanding
developer *intent* — what a piece of code is genuinely trying to achieve —
and identifying where the implementation falls short of that intent.

Your job per file:
  A) For each function, class, or logical section: state its intent, then
     list every MISSING element that is required to fully achieve that intent.
     This includes: missing sub-functions, missing guard clauses, missing
     error paths, missing validation, missing tests, missing integrations.
  B) At the project level: identify missing whole features or cross-cutting
     concerns that the project's stated purpose requires but that appear
     absent from the scanned code.
  C) Where the KB context shows a fundamentally better architectural approach
     that more cleanly achieves the same intent, propose it as an alternative
     with trade-offs clearly stated.

Rules:
  - Focus on INTENT GAPS, not style.  Ask: "Given what this is trying to do,
    what's missing?"
  - Severity guide:
      high   = gap breaks the stated intent entirely (e.g. function claims to
                validate input but has no validation at all)
      medium = gap means the intent is only partially achieved
      low    = gap means the intent could be achieved more robustly
  - For architectural_alternatives: only include when a KB source demonstrates
    a clearly superior approach.  Max 2 alternatives per file.
  - Be concrete — name the missing functions, sketch the code.
  - Constraints from the project profile must be respected when suggesting
    alternatives (e.g. don't suggest microservices if the project is a
    single-device CLI tool).

Respond ONLY with valid JSON matching this schema (no markdown, no preamble):
{
  "unit_intents": [
    {
      "unit": "<function/class/section name>",
      "stated_intent": "<one sentence: what this unit is trying to do>",
      "gaps": [
        {
          "gap_type": "<sub-function | guard | feature | integration | test>",
          "title": "<max 10 words>",
          "description": "<2-3 sentences explaining the gap>",
          "severity": "<high | medium | low>",
          "suggestion": "<concrete code or design guidance, 3-15 lines>"
        }
      ]
    }
  ],
  "project_level_gaps": [
    {
      "title": "<max 10 words>",
      "description": "<2-3 sentences>",
      "severity": "<high | medium | low>",
      "suggestion": "<concrete guidance>"
    }
  ],
  "architectural_alternatives": [
    {
      "title": "<short name for the approach>",
      "rationale": "<why this approach better achieves the intent>",
      "source_repo": "<KB repo that demonstrates this pattern>",
      "trade_offs": "<what you gain and what you give up>",
      "sketch": "<pseudo-code or architecture sketch, 5-20 lines>"
    }
  ],
  "summary": "<2 sentence overall intent-gap assessment>"
}

If there are no intent gaps, return:
{
  "unit_intents": [],
  "project_level_gaps": [],
  "architectural_alternatives": [],
  "summary": "The file fully realises its stated intent with no significant gaps identified."
}
"""


def _build_intent_prompt(
    pf: "ProjectFile",
    project_profile: str,
    kb_context: str,
    user_system_prompt: str = "",
    constraints_block: str = "",
) -> str:
    file_content = truncate_to_tokens(pf.content, FILE_CONTENT_TOKENS)
    profile_snip = truncate_to_tokens(project_profile, PROJECT_PROFILE_TOKENS)

    user_guidance = ""
    if user_system_prompt.strip():
        user_guidance = f"\n\n## Developer Guidance\n{user_system_prompt.strip()}\n"

    constraint_section = ""
    if constraints_block.strip():
        constraint_section = f"\n\n## Project Constraints\n{constraints_block.strip()}\n"

    return f"""## Project Profile
{profile_snip}
{user_guidance}{constraint_section}
## File Under Review
**Project:** {pf.project_name}
**Path:** {pf.relative_path}
**Type:** {pf.file_type}

```{pf.file_type}
{file_content}
```

---

## Relevant KB Patterns (for architectural alternatives)
{kb_context}

---

Perform deep intent analysis on the file above.
Return valid JSON only."""


# ── Lazy API client ────────────────────────────────────────────────────────────

_CLIENT: anthropic.Anthropic | None = None

def _get_client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        api_key = cfg("anthropic.api_key", "")
        if not api_key or api_key.startswith("<REPLACE"):
            raise ValueError("Anthropic API key not set in config.yaml")
        _CLIENT = anthropic.Anthropic(api_key=api_key)
    return _CLIENT


# ── JSON parser ────────────────────────────────────────────────────────────────

def _parse(text: str) -> dict:
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text.strip(), flags=re.MULTILINE)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        return {
            "unit_intents": [],
            "project_level_gaps": [],
            "architectural_alternatives": [],
            "summary": "(parse error)",
            "error": "JSON parse failed",
        }


# ── Public API ─────────────────────────────────────────────────────────────────

def analyse_intent(
    pf: "ProjectFile",
    project_profile: str,
    user_system_prompt: str = "",
    constraints_block: str = "",
    retries: int = 2,
) -> dict:
    """
    Run deep intent analysis on a single project file.
    Returns structured intent gap report.
    """
    kb_context, _ = retrieve_context_for_file(pf)

    prompt = _build_intent_prompt(
        pf,
        project_profile,
        kb_context,
        user_system_prompt,
        constraints_block,
    )
    client  = _get_client()
    model   = cfg("anthropic.model", "claude-sonnet-4-20250514")
    max_tok = cfg("anthropic.intent_max_tokens", 3000)

    for attempt in range(retries + 1):
        try:
            response = client.messages.create(
                model      = model,
                max_tokens = max_tok,
                system     = INTENT_SYSTEM_PROMPT,
                messages   = [{"role": "user", "content": prompt}],
            )
            raw   = response.content[0].text
            parsed = _parse(raw)

            return {
                "project":                  pf.project_name,
                "file_path":                pf.relative_path,
                "unit_intents":             parsed.get("unit_intents", []),
                "project_level_gaps":       parsed.get("project_level_gaps", []),
                "architectural_alternatives": parsed.get("architectural_alternatives", []),
                "summary":                  parsed.get("summary", ""),
                "error":                    parsed.get("error"),
            }

        except anthropic.RateLimitError:
            wait = 30 * (attempt + 1)
            log.warning(f"Rate limit hit — waiting {wait}s")
            time.sleep(wait)
        except Exception as e:
            log.error(f"Intent analysis error for {pf.relative_path}: {e}")
            if attempt == retries:
                return {
                    "project":   pf.project_name,
                    "file_path": pf.relative_path,
                    "unit_intents": [],
                    "project_level_gaps": [],
                    "architectural_alternatives": [],
                    "summary": "",
                    "error": str(e),
                }
            time.sleep(3)

    return {
        "project":   pf.project_name,
        "file_path": pf.relative_path,
        "unit_intents": [],
        "project_level_gaps": [],
        "architectural_alternatives": [],
        "summary": "",
        "error": "All retries exhausted",
    }
