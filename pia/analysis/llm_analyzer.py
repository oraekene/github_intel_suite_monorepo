"""
pia/analysis/llm_analyzer.py

Sends project files + retrieved KB context to Claude Sonnet and
parses structured improvement findings.

Output per file:
  {
    "project":       str,
    "file_path":     str,
    "file_type":     str,
    "source":        str,
    "findings": [
      {
        "category":   str,        # one of CATEGORIES
        "title":      str,        # short headline
        "description": str,       # detailed explanation
        "source_repo": str,       # which KB repo demonstrates this
        "severity":   str,        # "high" | "medium" | "low"
        "suggestion": str         # concrete code/config suggestion
      },
      ...
    ],
    "summary":       str,         # 2-sentence overall assessment
    "error":         str | None
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
from analysis.constraints import build_constraints_block
from analysis.user_prompts_loader import get_prompts_for_module

if TYPE_CHECKING:
    from scan.local_scanner import ProjectFile


# ── Categories ────────────────────────────────────────────────────────────────

CATEGORIES = [
    "Architecture",
    "Error Handling",
    "Performance",
    "Security",
    "Testing",
    "DX / Tooling",
    "Documentation",
    "Code Quality",
]

# ── Token budget for file content sent to LLM ────────────────────────────────
FILE_CONTENT_TOKEN_LIMIT = 1_500

# ── System prompt ─────────────────────────────────────────────────────────────

SYSTEM_PROMPT = """You are PIA (Project Intelligence Analyst), an expert software architect and code reviewer.

Your job is to analyse a developer's project file, compare it against curated open-source patterns from a knowledge base, and produce specific, actionable improvement suggestions.

Rules:
- Be concrete. Reference line numbers or specific constructs when possible.
- Always attribute each suggestion to a source repository from the knowledge base.
- If the knowledge base context has nothing useful for a finding, still include the finding but mark source_repo as "general best practice".
- Do NOT suggest trivial cosmetic changes.
- Severity guide:
    high   = missing entirely, poses real risk (security hole, no error handling, broken architecture)
    medium = suboptimal pattern that degrades reliability or maintainability
    low    = nice-to-have improvement

Respond ONLY with valid JSON matching this exact schema (no markdown fences, no preamble):
{
  "findings": [
    {
      "category": "<one of: Architecture | Error Handling | Performance | Security | Testing | DX / Tooling | Documentation | Code Quality>",
      "title": "<short headline, max 10 words>",
      "description": "<2-4 sentence explanation of the problem>",
      "source_repo": "<repo name from KB, or 'general best practice'>",
      "severity": "<high | medium | low>",
      "suggestion": "<concrete code snippet or config change, 3-15 lines>"
    }
  ],
  "summary": "<2 sentence overall assessment of this file>"
}

If there are genuinely no improvements to suggest, return:
{"findings": [], "summary": "This file looks well-structured with no significant improvements identified."}
"""


# ── User prompt builder ───────────────────────────────────────────────────────

def _build_user_prompt(
    pf: "ProjectFile",
    context: str,
    constraints_block: str = "",
    user_guidance: str = "",
) -> str:
    file_content = truncate_to_tokens(pf.content, FILE_CONTENT_TOKEN_LIMIT)

    constraint_section = ""
    if constraints_block.strip():
        constraint_section = f"\n## Project Constraints\n{constraints_block.strip()}\n"

    guidance_section = ""
    if user_guidance.strip():
        guidance_section = f"\n## Developer Guidance\n{user_guidance.strip()}\n"

    return f"""## File Under Review

**Project:** {pf.project_name}
**Path:** {pf.relative_path}
**Type:** {pf.file_type}
**Source:** {pf.source}
{constraint_section}{guidance_section}
```{pf.file_type}
{file_content}
```

---

{context}

---

Analyse the file above using the knowledge base patterns provided.
Respect the constraints and developer guidance above when making suggestions.
Identify specific improvements and return valid JSON only."""


# ── API client (lazy singleton) ───────────────────────────────────────────────

_CLIENT: anthropic.Anthropic | None = None

def _get_client() -> anthropic.Anthropic:
    global _CLIENT
    if _CLIENT is None:
        api_key = cfg("anthropic.api_key", "")
        if not api_key or api_key.startswith("<REPLACE"):
            raise ValueError(
                "Anthropic API key not set. "
                "Fill in 'anthropic.api_key' in config.yaml"
            )
        _CLIENT = anthropic.Anthropic(api_key=api_key)
    return _CLIENT


# ── JSON parser (robust) ──────────────────────────────────────────────────────

def _parse_response(text: str) -> dict:
    # Strip markdown code fences if present
    text = re.sub(r"^```(?:json)?\s*", "", text.strip(), flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text.strip(), flags=re.MULTILINE)
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError as e:
        # Try to extract just the JSON object
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except Exception:
                pass
        log.debug(f"JSON parse failed: {e}\nRaw: {text[:300]}")
        return {"findings": [], "summary": f"(Parse error: {e})", "error": str(e)}


# ── Single file analyser ──────────────────────────────────────────────────────

def analyse_file(
    pf:       "ProjectFile",
    context:  str | None = None,
    retries:  int = 2,
) -> dict:
    """
    Analyse a single ProjectFile.  Returns a structured result dict.
    """
    if context is None:
        context, _ = retrieve_context_for_file(pf)

    constraints   = build_constraints_block()
    user_guidance = get_prompts_for_module("code_review")

    prompt = _build_user_prompt(pf, context, constraints, user_guidance)
    client = _get_client()
    model  = cfg("anthropic.model", "claude-sonnet-4-20250514")
    max_tok= cfg("anthropic.max_tokens", 2000)

    for attempt in range(retries + 1):
        try:
            response = client.messages.create(
                model      = model,
                max_tokens = max_tok,
                system     = SYSTEM_PROMPT,
                messages   = [{"role": "user", "content": prompt}],
            )
            raw_text = response.content[0].text
            parsed   = _parse_response(raw_text)

            # Normalise output
            findings = parsed.get("findings", [])
            min_findings = cfg("reports.min_findings_to_report", 1)

            return {
                "project":   pf.project_name,
                "file_path": pf.relative_path,
                "file_type": pf.file_type,
                "source":    pf.source,
                "findings":  findings,
                "summary":   parsed.get("summary", ""),
                "error":     parsed.get("error"),
            }

        except anthropic.RateLimitError:
            wait = 30 * (attempt + 1)
            log.warning(f"Rate limit — waiting {wait}s (attempt {attempt + 1}/{retries + 1})")
            time.sleep(wait)
        except anthropic.APIStatusError as e:
            log.error(f"API error for {pf.relative_path}: {e}")
            if attempt == retries:
                return _error_result(pf, str(e))
            time.sleep(5)
        except Exception as e:
            log.error(f"Unexpected error for {pf.relative_path}: {e}")
            if attempt == retries:
                return _error_result(pf, str(e))
            time.sleep(2)

    return _error_result(pf, "All retries exhausted")


def _error_result(pf: "ProjectFile", msg: str) -> dict:
    return {
        "project":   pf.project_name,
        "file_path": pf.relative_path,
        "file_type": pf.file_type,
        "source":    pf.source,
        "findings":  [],
        "summary":   "",
        "error":     msg,
    }


# ── Batch analyser ────────────────────────────────────────────────────────────

def analyse_project_files(
    project_files: list["ProjectFile"],
    delay_between: float = 1.0,
) -> list[dict]:
    """
    Analyse a list of project files sequentially.
    Returns a list of result dicts.
    """
    max_files = cfg("anthropic.max_files_per_run", 60)
    files     = project_files[:max_files]

    if len(project_files) > max_files:
        log.warning(
            f"Capped at {max_files} files per run "
            f"(config: anthropic.max_files_per_run). "
            f"{len(project_files) - max_files} files skipped."
        )

    results: list[dict] = []

    from tqdm import tqdm
    for pf in tqdm(files, desc="Analysing files"):
        result = analyse_file(pf)
        results.append(result)
        time.sleep(delay_between)

    total_findings = sum(len(r["findings"]) for r in results)
    errors         = sum(1 for r in results if r.get("error"))

    log.info(
        f"Analysis complete — {len(results)} files, "
        f"{total_findings} findings, {errors} errors"
    )
    return results
