# GitHub Intelligence Suite — Use-Case FAQ

> **How to read this document.**  
> Each use case follows a single person from the moment they feel a need to the moment that need is fully resolved. Every step documents: what the user needs at that exact moment, what they type or click, which config key changes and to what value, *why* that specific choice solves the problem, and what concrete outcome is created.  
> Every one of the suite's 40 configurable parameters appears in at least one use case.

---

## Table of Contents

| # | Use Case | Key Parameters Covered |
|---|----------|------------------------|
| 1 | [First-time setup and extracting your own repos](#uc-01) | `output_dir` · `token` · `sources[owned,forks,starred]` · `resume` |
| 2 | [Full AI code-quality self-assessment with PIA](#uc-02) | `project` · `skip_benchmark` · `no_intent` · `no_compare` · `ingest_only` · `scan_only` |
| 3 | [Trending language research](#uc-03) | `sources[trending]` · `trending_langs` · `trending_period` · `trending_lang` |
| 4 | [Continuous ecosystem discovery — forward mode](#uc-04) | `mode=forward` · all 5 discovery plugins · `schedule` · `discoveries_source` · `discoveries_min_score` |
| 5 | [Historical deep-scan — catching up on a full year](#uc-05) | `mode=lookback` · `floor_date` · `lookback_batch` · `discoveries_history` · `external_date` |
| 6 | [Fast lightweight extraction when time is limited](#uc-06) | `skip_text_files` · `skip_issues` · `resume` (interrupted) · `no_intent` · `no_compare` |
| 7 | [Single-repo deep dive](#uc-07) | `repo` · `text_ext_filter` · `text` · `readmes` · `issues` · `tree` |
| 8 | [Automated recurring pipeline with chaining](#uc-08) | `github.schedule` · `chain_platform` · `platform_sources_filter` · `platform.schedule` |
| 9 | [Rust ecosystem intelligence feed](#uc-09) | `cratesio` · `thisweekrust` · `lobsters` · `reddit` · `mode=both` · `trending_langs=rust` |
| 10 | [SearXNG meta-search discovery](#uc-10) | `github.searxng_url` · `platform.searxng_url` · `sources[searxng]` |
| 11 | [Targeted AI comparison — how does my project stack up?](#uc-11) | `compare_topic` · `compare_repos` · `force_eligible` · `no_intent=true` |
| 12 | [Rebuilding the knowledge base after a major re-extraction](#uc-12) | `clear_kb` · `ingest_only` · `scan_only` |
| 13 | [Multi-environment setup with custom config paths](#uc-13) | `platform.config_yaml` · `pia.config_yaml` · custom `output_dir` |
| 14 | [GitHub Collections exploration](#uc-14) | `sources[collections]` · `collections_full` |
| 15 | [Extracting non-standard file types from repos](#uc-15) | `text_extensions` |

---

<a name="uc-01"></a>
## Use Case 1 — First-Time Setup and Extracting Your Own Repos

**Persona:** Sarah, a software engineer, has been building side projects on GitHub for five years. She has 40 repos — some personal, some forked from others she contributed to, plus a large starred collection she uses as reference. She has never used the suite before. Her goal: build a local, searchable snapshot of everything she owns and has starred so she can browse it offline and eventually feed it into PIA.

---

### Step 1.1 — Downloading and placing the files

**User's need:** Sarah needs all the suite's files in one place on her machine before she can do anything.

**Action:** She extracts `github_intel_suite_v2.zip` into `C:\Tools\github_intel_suite\`. She copies `github_extractor_v2.py`, `platform_extractor.py`, and `github_viewer_v2.py` into that same folder. She extracts `pia_v3_reputation.zip` so that `pia\` is a direct child of that folder.

**What is modified:** Nothing in config yet — this is file-system placement only.

**Why:** The suite uses relative paths. All three `.py` scripts and `pia\` must be siblings of `launcher.py` and `gui_app.py`. Placing them elsewhere would cause "not found" errors at runtime.

**Outcome:** The folder now contains:
```
C:\Tools\github_intel_suite\
  config_manager.py
  gui_app.py
  launcher.py
  setup.bat
  run_gui.bat
  github_extractor_v2.py
  platform_extractor.py
  github_viewer_v2.py
  pia\
    config.yaml
    scheduler\run_pipeline.py
    ...
```

---

### Step 1.2 — Running setup

**User's need:** Sarah needs all Python dependencies installed. She does not want to manually figure out what to `pip install`.

**Action:** She double-clicks `setup.bat`.

**What happens:**
1. `setup.bat` checks that Python 3.10+ is on `PATH`.
2. Creates `.venv\` virtual environment in the suite folder.
3. Runs `pip install -r pia\requirements.txt` (covers `rich`, `anthropic`, `chromadb`, `sentence-transformers`, etc.).
4. Runs `pip install PyGithub requests scrapling` (covers the extractors).
5. Runs `python -m scrapling install` for the optional browser back-end.

**What is modified:** No config keys. The `.venv\` folder is created on disk.

**Why:** A virtual environment isolates the suite's dependencies from the system Python, preventing version conflicts. `scrapling` is needed to scrape GitHub trending and collections pages, which don't have public APIs.

**Outcome:** All dependencies installed. Terminal window shows "Setup complete!" Sarah can now launch the GUI.

---

### Step 1.3 — Opening the GUI and checking component status

**User's need:** Before doing anything, Sarah wants to confirm everything is wired up correctly.

**Action:** She double-clicks `run_gui.bat`. The GUI opens. She clicks the **⚙ Setup** tab.

**What she sees:**
```
✓ Found    GitHub Extractor
✓ Found    Platform Extractor
✓ Found    Viewer
✓ Found    PIA (pia/)
✗ Not found   Output directory
```

**What is modified:** Nothing yet.

**Why the output directory shows "not found":** `github_export\` does not exist until the first extraction is run. This is expected.

**Outcome:** Sarah confirms three scripts and PIA are in place. She proceeds to configure.

---

### Step 1.4 — Setting the output directory

**User's need:** Sarah wants her extraction saved to `D:\data\github_export` (her data drive) rather than the default `github_export` subfolder next to the scripts.

**Action:** In the **⚙ Setup** tab, she clicks **Browse** next to the "Output directory" field and selects `D:\data\github_export`.

**Config modified:**
```json
"global": {
  "output_dir": "D:\\data\\github_export"
}
```

**Why:** Both extractors read `global.output_dir` when building their `--output` argument. Setting it once here means neither extractor needs to be configured separately. The viewer also reads `EXPORT_DIR` from the environment, which the GUI sets to this value before every viewer run.

**Outcome:** Saved to `suite_config.json`. Every future extraction and viewer command will use `D:\data\github_export` automatically.

---

### Step 1.5 — Entering the GitHub token

**User's need:** To extract owned, forked, and starred repos, the GitHub API requires authentication. Without a token, only public data is accessible and rate limits are very tight (60 requests/hour vs 5,000).

**Action:**
1. Sarah opens `github.com → Settings → Developer Settings → Personal access tokens → Tokens (classic)`.
2. Creates a token with scopes: `repo`, `read:user`, `read:org`.
3. Copies the token.
4. Back in the GUI **⚙ Setup** tab, she pastes it into the **Token** field and clicks **Save to env**.

**Config modified:**
```json
"github_extractor": {
  "token": "ghp_XXXXXXXXXXXXXXXXXXXX"
}
```

**Why:** The token is saved to `suite_config.json` and injected as `--token` when the extractor runs. It is also immediately set in the current process environment via `os.environ["GITHUB_TOKEN"]` so any subprocess spawned in this session inherits it. The field uses `show="*"` masking so the token is never visible on screen.

**Outcome:** Token persisted. Future runs will not prompt for it.

---

### Step 1.6 — Configuring the GitHub extraction sources

**User's need:** Sarah wants to capture everything she owns plus everything she has starred. She does not want trending repos yet — those are for a different use case. She does not want collections.

**Action:** In the **⬇ GitHub** tab, she checks:
- ✅ `owned`
- ✅ `forks`
- ✅ `starred`
- ☐ `trending` (unchecked)
- ☐ `collections` (unchecked)

**Config modified:**
```json
"github_extractor": {
  "sources": ["owned", "forks", "starred"]
}
```

**Why:**
- `owned` — captures all repos Sarah created herself. This is the data that matters most for PIA analysis later.
- `forks` — she has forked 12 repos she contributes to; those contain her own commits and are part of her active work.
- `starred` — her 300+ starred repos form her personal reference library; including them enriches the knowledge base PIA uses.
- `trending` and `collections` excluded — not relevant to this extraction goal and would add unnecessary time.

**Outcome:** When extraction runs, the extractor will call the GitHub API for owned repos, forked repos, and starred repos only.

---

### Step 1.7 — Leaving content extraction at defaults

**User's need:** Sarah wants the full picture of each repo, including file contents and issues, so PIA can do the richest possible analysis.

**Action:** She leaves all content toggles at their defaults:
- `skip_text_files` → ☐ unchecked (default `false`)
- `skip_issues`     → ☐ unchecked (default `false`)
- `text_extensions` → blank (default, extract all registered extensions)

**Why `skip_text_files = false`:** Keeping text file extraction on means each repo's source code is saved locally. PIA's embedding step needs this raw text to understand what each repo actually does — without it, PIA only has metadata.

**Why `skip_issues = false`:** GitHub issues contain discussions, feature requests, and bug reports that describe the *intent* and *pain points* of a project. PIA's intent-gap analysis uses this to understand what a project's users are asking for that isn't implemented yet.

**Why `text_extensions = ""`:** The default registered extensions (`.py`, `.js`, `.ts`, `.go`, `.rs`, `.md`, `.yaml`, etc.) are sufficient. Sarah is not working with unusual formats yet (see Use Case 15 for that).

**Config modified:** None — these are already the default values. Explicitly verified but not changed.

**Outcome:** Each extracted repo will include: metadata, README, directory tree, source code files, and issues.

---

### Step 1.8 — Enabling resume

**User's need:** Sarah's starred collection has 300+ repos. The extraction could take 30–60 minutes. She wants to be able to stop it partway through and pick up where she left off without re-extracting repos already done.

**Action:** In the **⬇ GitHub** tab, she checks **Resume (skip already-extracted repos)** — which is already checked by default. She verifies it is on.

**Config modified:**
```json
"github_extractor": {
  "resume": true
}
```

**Why:** When `resume = true`, the extractor checks whether a repo's output folder already exists in `output_dir` before making any API calls for it. If the folder exists, it is skipped entirely. This means if the process is interrupted (her laptop sleeps, the internet drops, etc.), re-running the extractor will continue from where it stopped rather than starting over and re-using API quota.

**Outcome:** The extractor will skip any repo that already has a folder in `D:\data\github_export\`. On first run, nothing is skipped. On subsequent runs, only new or not-yet-extracted repos are processed.

---

### Step 1.9 — Running the extraction

**User's need:** Sarah is ready to actually extract.

**Action:** She clicks **▶ Run GitHub Extractor** in the **⬇ GitHub** tab.

**What the console shows:**
```
══════════════════════════════════════════════
  GitHub Extractor
══════════════════════════════════════════════
  $ python github_extractor_v2.py
      --token ghp_XXX
      --output D:\data\github_export
      --sources owned,forks,starred
      --resume

[owned]   Fetching repos for user: sarah-codes
  ✓ sarah-codes/api-gateway  → D:\data\github_export\sarah-codes__api-gateway\
  ✓ sarah-codes/blog-engine  → ...
  ...
[forks]   Fetching forks...
  ...
[starred] Fetching 347 starred repos...
  ...
✓ Extraction complete. 391 repos processed.
```

**What is modified on disk:** `D:\data\github_export\` is created, containing one subfolder per repo named `owner__repo`. Each folder contains `meta.json`, `issues.json`, `tree.json`, and text file dumps.

**Outcome:** 391 repos extracted. `D:\data\github_export\` now contains the full snapshot. The GUI's status bar shows "✓ Done".

---

### Step 1.10 — Reviewing results in the Viewer

**User's need:** Sarah wants to confirm the extraction worked correctly and explore what was captured.

**Action:** She switches to the **🔍 View** tab and clicks **📊 Stats**.

**What appears in console:**
```
  Extraction stats
  ────────────────────────────────────────────
  Total repos:         391
  With source code:    388
  With issues:         274
  Total issues:        12,847
  Total text files:    28,431
  Languages:           Python (183), JavaScript (61), TypeScript (44)...
  Sources:             owned (41), forks (12), starred (347) - wait, that's...
```

**Action:** She then clicks **📋 List repos** to see the full table. She spots `tensorflow__tensorflow` in her starred list and clicks into it.

**Action:** She types `tensorflow__tensorflow` into the "Repo name" field and clicks **Full detail**.

**What appears:** Full metadata including stars, last push date, language, description, and a list of all extracted files.

**Outcome:** Sarah confirms the extraction is complete and accurate. She has a local, browsable snapshot of all 391 repos.

---
---

<a name="uc-02"></a>
## Use Case 2 — Full AI Code-Quality Self-Assessment with PIA

**Persona:** Marco is a backend engineer. He has three projects in `C:\Projects\`: `auth-service`, `data-pipeline`, and `invoice-generator`. He wants PIA to compare each against the best open-source equivalents in his extracted knowledge base and produce improvement reports.

**Prerequisite:** Use Case 1 has been completed — `github_export\` exists with 300+ repos.

---

### Step 2.1 — Configuring PIA's config.yaml

**User's need:** Before PIA can run, it needs to know Marco's Anthropic API key, where his projects live, and where the extracted GitHub repos are.

**Action:** In the **⚙ Setup** tab, he clicks **Edit PIA config.yaml**.

**He sets:**
```yaml
anthropic:
  api_key: "sk-ant-api03-XXXXXXXXX"

knowledge_base:
  source_dir: "D:/data/github_export"

projects:
  local:
    roots:
      - "C:/Projects"
```

**Why `knowledge_base.source_dir`:** PIA ingests everything in this directory as its reference library. It reads each repo's metadata, source files, and issues to build embeddings. Pointing it at the correct extraction output is essential — without it, PIA has nothing to compare against.

**Why `projects.local.roots`:** PIA scans subdirectories of each root to discover projects. Since Marco's three projects are all in `C:\Projects\`, one root entry finds all of them.

**Outcome:** PIA knows where to find data and how to authenticate with Claude.

---

### Step 2.2 — Running a full first-time PIA pipeline

**User's need:** Marco wants to run the complete pipeline: ingest the KB, scan his projects, analyse them, and generate reports. He is running it for the first time so he wants every phase active — no shortcuts.

**Action:** In the **🤖 PIA** tab, he verifies all options are at defaults:
- `ingest_only` → ☐ unchecked
- `scan_only`   → ☐ unchecked
- `no_intent`   → ☐ unchecked (will run intent gap analysis)
- `no_compare`  → ☐ unchecked (will run comparisons)
- `skip_benchmark` → ☐ unchecked (will benchmark KB repos for reputation scoring)
- `project`     → blank (analyse all projects)
- `compare_topic` → blank
- `compare_repos` → blank
- `force_eligible` → blank
- `clear_kb`    → ☐ unchecked (no existing KB to clear)
- `config_yaml` → blank (use default `pia/config.yaml`)

He clicks **▶ Run PIA Pipeline**.

**Config used (no changes from defaults):**
```json
"pia": {
  "ingest_only": false,
  "scan_only": false,
  "no_intent": false,
  "no_compare": false,
  "skip_benchmark": false,
  "project": "",
  "clear_kb": false
}
```

**What the console shows (summarised):**
```
Phase 1   — Ingesting knowledge base
  Embedding 391 repos into ChromaDB...
  ✓ 391 repos embedded (28,431 chunks)

Phase 1.5 — Benchmarking KB repos for reputation scores
  Scoring repos by stars, recency, issue health, code quality signals...
  ✓ 391 repos scored

Phase 2   — Scanning projects
  Discovered 3 projects under C:/Projects
    • auth-service
    • data-pipeline
    • invoice-generator

Phase 3   — Analysing: auth-service
  Intent analysis:  identifying what this project does vs what its issues ask for...
  Comparison:       finding top 5 similar KB repos...
  Gap report:       generating improvement recommendations...

Phase 3   — Analysing: data-pipeline
  ...

Phase 3   — Analysing: invoice-generator
  ...

Phase 4   — Writing reports
  ✓ pia/reports/auth-service_report.md
  ✓ pia/reports/data-pipeline_report.md
  ✓ pia/reports/invoice-generator_report.md

✓ Pipeline complete.
```

**Why `skip_benchmark = false` on first run:** The reputation benchmark (Phase 1.5) scores each KB repo by a composite metric (stars trajectory, issue close rate, code churn, maintenance signals). These scores determine which repos are eligible for comparison. On first run, no scores exist — skipping it would mean all repos are treated as equally valid comparators, which produces lower-quality recommendations.

**Outcome:** Three reports generated in `pia/reports/`. Each contains: project summary, intent gap analysis, ranked comparison repos, and specific improvement recommendations.

---

### Step 2.3 — Re-running analysis on a single project after fixing issues

**User's need:** Marco reads the `auth-service` report, implements some of the recommended changes, and wants to re-run the analysis on just that project without waiting for the other two to process again.

**Action:** In the **🤖 PIA** tab, he types `auth-service` into the **Project** field. Leaves all other options at defaults. Clicks **▶ Run PIA Pipeline**.

**Config modified:**
```json
"pia": {
  "project": "auth-service"
}
```

**Why `project` partial match:** PIA matches the value against discovered project names using substring matching. `auth-service` uniquely identifies his project. He could also type just `auth` if it uniquely matches.

**Why not re-ingest:** The KB is unchanged — he did not add new repos. Re-ingestion would waste 10+ minutes re-embedding the same 391 repos. PIA automatically skips Phase 1 when the KB already exists and `ingest_only` / `clear_kb` are not set.

**What the console shows:**
```
Phase 1   — KB already exists. Skipping ingest.
Phase 1.5 — Reputation scores already exist. Skipping benchmark.
Phase 2   — Scanning for project matching 'auth-service'...
  Found: auth-service
Phase 3   — Analysing: auth-service...
Phase 4   — Writing report...
  ✓ pia/reports/auth-service_report.md (updated)
```

**Outcome:** Only `auth-service` is re-analysed. The other two reports are untouched. Processing time drops from ~8 minutes to ~90 seconds.

---

### Step 2.4 — Ingest-only: updating the KB when new repos are added

**User's need:** Marco ran the extractor again and added 50 new repos to the KB. The embeddings are stale. He wants to re-embed without re-running the full analysis.

**Action:** In the **🤖 PIA** tab, he clicks **📥 Ingest only**.

**Config used (overridden for this button):**
```json
"pia": {
  "ingest_only": true,
  "scan_only": false
}
```

**Why `ingest_only`:** This runs only Phase 1 (embed) and Phase 1.5 (benchmark), then exits. No projects are scanned. No API calls to Claude are made. This is ~5–10 minutes of local embedding work, not 30+ minutes of full analysis.

**Outcome:** ChromaDB updated with 50 new repos. Marco can now run scan-only (next step) when he is ready to regenerate reports.

---

### Step 2.5 — Scan-only: re-generating reports after KB update

**User's need:** KB is now current. Marco wants to regenerate all three reports using the updated knowledge base without re-ingesting again.

**Action:** He clicks **🔍 Scan only**.

**Config used:**
```json
"pia": {
  "ingest_only": false,
  "scan_only": true
}
```

**Why `scan_only`:** Skips Phase 1 entirely. Goes straight to Phase 2 (discover projects) → Phase 3 (analyse) → Phase 4 (report). Uses the already-current ChromaDB. Saves 10+ minutes of embedding time.

**Outcome:** Three updated reports generated using the richer KB. Marco opens `pia\reports\` and reads the improved recommendations.

---
---

<a name="uc-03"></a>
## Use Case 3 — Trending Language Research

**Persona:** Priya is a tech lead evaluating which new frameworks to adopt. She wants to see what is gaining momentum on GitHub in Python and TypeScript specifically, across daily, weekly, and monthly windows.

---

### Step 3.1 — Configuring sources for trending-only extraction

**User's need:** Priya only wants trending repos — not her own. She wants to avoid a long extraction of her personal repos when she just needs the trending data.

**Action:** In the **⬇ GitHub** tab, she unchecks `owned`, `forks`, `starred`, `collections`, and checks only `trending`.

**Config modified:**
```json
"github_extractor": {
  "sources": ["trending"]
}
```

**Why trending-only:** Each source type is fetched and processed independently. Running with only `trending` keeps the extraction to a few minutes instead of potentially hours.

---

### Step 3.2 — Setting trending language filters

**User's need:** GitHub trending lists hundreds of repos across all languages. Priya only cares about Python and TypeScript.

**Action:** In the **⬇ GitHub** tab, she types `python,typescript` into the **Trending languages** field.

**Config modified:**
```json
"github_extractor": {
  "trending_langs": "python,typescript"
}
```

**Why:** Without this filter, the extractor fetches trending repos for every language (20+ language-specific lists plus the global list). With `trending_langs = "python,typescript"`, it only fetches those two language-specific lists plus the global list filtered post-fetch. This reduces extraction time and keeps the output focused.

**Outcome:** When the extractor runs, only Python and TypeScript trending repos will be captured.

---

### Step 3.3 — Running the extraction

**Action:** Priya clicks **▶ Run GitHub Extractor**.

**Console output (abbreviated):**
```
[trending] Fetching trending — python (daily)...   23 repos
[trending] Fetching trending — python (weekly)...  25 repos
[trending] Fetching trending — python (monthly)... 25 repos
[trending] Fetching trending — typescript (daily)... 25 repos
...
✓ 147 unique trending repos extracted.
```

**Outcome:** 147 repos in `github_export/_trending/` and individual repo folders.

---

### Step 3.4 — Viewing daily trending in the Viewer

**User's need:** Priya wants to see what is trending *today* in Python.

**Action:** In the **🔍 View** tab, she sets:
- **Period** → `daily`
- **Language** → `python`

She clicks **▶ Trending**.

**Viewer config used:**
```json
"viewer": {
  "trending_period": "daily",
  "trending_lang": "python"
}
```

**What appears in console:**
```
  GitHub Trending — python — daily
  ─────────────────────────────────────────────────────────
  REPO                                      STARS   DELTA   DESCRIPTION
  microsoft/promptflow                      8,421   +312    Prompt engineering toolkit
  pydantic/pydantic-ai                      4,102   +287    AI agent framework
  ...
```

**Why `trending_period = "daily"`:** Daily trending reflects what is *right now* catching attention — useful for spotting viral projects. Weekly and monthly reflect sustained momentum, more useful for adoption decisions.

---

### Step 3.5 — Switching to weekly trending for sustained momentum view

**User's need:** Priya wants to see which Python projects have had consistent momentum over the past week, not just a single-day spike.

**Action:** She changes **Period** to `weekly` and clicks **▶ Trending** again.

**Viewer config modified:**
```json
"viewer": {
  "trending_period": "weekly"
}
```

**What appears:** A different ranked list — projects that have accumulated the most stars over the week. Some projects appear in both daily and weekly; those are the strongest signals.

---

### Step 3.6 — Viewing the cross-language ext-summary

**User's need:** Priya wants a single table showing how many repos were captured per source and language, to confirm the extraction breadth.

**Action:** She clicks **📈 Ext summary** in the quick actions.

**What appears:**
```
  External sources + trending summary
  ────────────────────────────────────────────────────────
  Source             Repos    Last updated
  ─────────────────────────────────────────────────────────
  trending/python    73       2025-05-28
  trending/typescript 74      2025-05-28
  ...
```

**Outcome:** Priya confirms the right data was captured. She now has a local list of momentum repos in her two target languages, browsable without internet.

---
---

<a name="uc-04"></a>
## Use Case 4 — Continuous Ecosystem Discovery in Forward Mode

**Persona:** James is a developer advocate at a startup. He wants to discover new interesting open-source projects across Hacker News, PyPI, npm, Papers With Code, and Dev.to as they are published — not scan the past, just stay current going forward.

---

### Step 4.1 — Understanding forward mode

**User's need:** James needs to understand what "forward" means before configuring it.

**Concept:** `mode = forward` fetches the most recent items from each source plugin — typically the last page or two of new entries. Each run captures what is new *since the last run*. Data accumulates in daily timestamped files under `github_export/_external_sources/{source}/forward/YYYY-MM-DD.json`. This is designed for daily or recurring runs.

**Contrast with `lookback`:** Lookback (Use Case 5) pagcinates backward through a source's full history. Forward is fast (~2–3 min per source). Lookback is slow (can take hours for large sources).

---

### Step 4.2 — Selecting sources

**User's need:** James wants: Hacker News (Show HN posts), Papers With Code (ML papers with repos), PyPI (new packages), npm (new packages), Dev.to (project announcements). He does not want Reddit (too noisy for his audience) or the Rust-specific sources.

**Action:** In the **🌐 Platform** tab, he checks:
- ✅ `hackernews`
- ✅ `paperswithcode`
- ✅ `npm`
- ✅ `pypi`
- ✅ `devto`
- ☐ `cratesio` (unchecked)
- ☐ `lobsters` (unchecked)
- ☐ `reddit` (unchecked)
- ☐ `thisweekrust` (unchecked)
- ☐ `searxng` (unchecked)

**Config modified:**
```json
"platform_extractor": {
  "sources": ["hackernews", "paperswithcode", "npm", "pypi", "devto"]
}
```

**Why each source:**
- `hackernews` — Show HN posts are the gold standard signal for "a developer just launched something interesting." The Algolia API surfaces them reliably.
- `paperswithcode` — Every ML paper published with a code repo. Essential for staying current with research-to-production pipelines.
- `pypi` — New package releases on PyPI. James's company builds Python tooling; knowing what's being published helps competitive awareness.
- `npm` — Same for JavaScript/TypeScript ecosystem, covering his frontend audience.
- `devto` — Project launch announcements from the practitioner community, often complementary to HN.

---

### Step 4.3 — Setting mode to forward

**User's need:** James confirms he only wants new items, not historical backfill.

**Action:** He sets **Mode** → `forward`.

**Config modified:**
```json
"platform_extractor": {
  "mode": "forward"
}
```

**Why not `lookback` or `both`:** `lookback` would spend hours scanning historical data he doesn't need. `forward` is fast and targeted. He can always add a one-time `lookback` run later if he wants history (see Use Case 5).

---

### Step 4.4 — Setting a recurring schedule

**User's need:** James wants this to run every morning at startup without him having to remember to trigger it manually.

**Action:** He types `12h` into the **Schedule** field in the Platform tab.

**Config modified:**
```json
"platform_extractor": {
  "schedule": "12h"
}
```

**Why `12h`:** A 12-hour interval means twice daily — once in the morning and once in the evening. Most sources update on this cadence. Faster (e.g. `1h`) would work but would mostly fetch empty results and waste requests. Slower (e.g. `24h`) risks missing items that fall off the "recent" page of fast-moving sources like npm.

**How schedule works:** When the extractor runs with `--schedule 12h`, it executes the forward pass, then sleeps 12 hours, then runs again in a loop until the process is stopped.

**Practical note:** James launches this from a terminal via `launcher.bat platform` (or `launcher.sh`) and leaves the window open, or sets up a Windows Task Scheduler / cron job to call `launcher.bat platform` at startup.

---

### Step 4.5 — Running the platform extractor

**Action:** He clicks **▶ Run Platform Extractor**.

**Console output (abbreviated):**
```
[hackernews]     Fetching forward (recent)...
  ✓ 47 new items  →  github_export/_external_sources/hackernews/forward/2025-05-28.json
[paperswithcode] Fetching forward...
  ✓ 31 new papers with repos
[npm]            Fetching forward...
  ✓ 120 new packages with GitHub repos
[pypi]           Fetching forward...
  ✓ 84 new packages
[devto]          Fetching forward...
  ✓ 22 new project posts
Sleeping 12h before next run...
```

**Outcome:** First day's data captured. Items are stored as JSON in `_external_sources/{source}/forward/2025-05-28.json`.

---

### Step 4.6 — Browsing discoveries in the Viewer

**User's need:** The next morning James wants to browse what was discovered, focusing on items with a high relevance score from Hacker News only.

**Action:** In the **🔍 View** tab, he fills in the Discoveries panel:
- **Keyword** → blank (show all)
- **Source filter** → `hackernews`
- **Min score** → `50`
- **Use history** → ☐ unchecked (use forward data)

He clicks **▶ Search Discoveries**.

**Viewer config used:**
```json
"viewer": {
  "discoveries_source": "hackernews",
  "discoveries_min_score": 50,
  "discoveries_history": false
}
```

**What appears in console:**
```
  Discoveries — 14 unique repos matched
  source=hackernews  |  min-score≥50

  REPO                            SOURCE      SCORE   DATE
  ─────────────────────────────────────────────────────────────────
  astral-sh/uv                    hackernews     94   2025-05-27
     └─ Show HN: uv — Python package manager in Rust
  microsoft/graphrag              hackernews     87   2025-05-27
     └─ Show HN: GraphRAG — knowledge graph RAG...
  ...
```

**Why `min_score = 50`:** Each discovery item is scored 0–100 by the plugin based on signals like upvotes, comment count, recency, and whether it has a confirmed GitHub repo link. A floor of 50 filters out low-quality signals (new packages with 0 downloads, HN posts with 1 point) while retaining genuinely interesting finds.

**Why `discoveries_source = "hackernews"`:** James is reviewing source-by-source. He'll repeat this with `paperswithcode` next.

---

### Step 4.7 — Viewing raw external source data for a specific source

**User's need:** James wants to see the raw file for the paperswithcode data from yesterday, including items that might be below his score threshold, to understand what was captured.

**Action:** In the **External source browser** section of the **🔍 View** tab:
- **Source name** → `paperswithcode`
- **Date** → `2025-05-27`

He clicks **Browse external**.

**Viewer config used:**
```json
"viewer": {
  "external_source": "paperswithcode",
  "external_date": "2025-05-27"
}
```

**What appears:** The raw list of 31 papers, including title, GitHub URL, abstract summary, and score — for *all* items regardless of score filter.

**Why separate from discoveries:** The `external` command shows raw per-source files by date. The `discoveries` command aggregates and filters across all sources. Both are useful for different browsing needs.

---

### Step 4.8 — Listing all available sources

**User's need:** James wants to see which sources have data files on disk to confirm everything ran.

**Action:** He clicks **📊 Stats** in quick actions, which includes a source summary. Alternatively in the TUI, he runs **L: Platform — list plugins**.

**What appears:**
```
  External sources on disk:
  hackernews       forward: 3 files    history: 0 files
  paperswithcode   forward: 3 files    history: 0 files
  npm              forward: 3 files    history: 0 files
  pypi             forward: 3 files    history: 0 files
  devto            forward: 3 files    history: 0 files
```

**Outcome:** James confirms three days of data for each source. The pipeline is working.

---
---

<a name="uc-05"></a>
## Use Case 5 — Historical Deep-Scan: Catching Up on a Full Year

**Persona:** Lena is a researcher who just discovered this suite. She wants to back-fill a full year of discoveries from Hacker News and Papers With Code — from January 2024 to today — before switching to forward mode.

---

### Step 5.1 — Setting mode to lookback

**User's need:** Lena needs to paginate backward through source history rather than just fetch today's new items.

**Action:** In the **🌐 Platform** tab, she sets **Mode** → `lookback`.

**Config modified:**
```json
"platform_extractor": {
  "mode": "lookback"
}
```

**Why `lookback` not `both`:** She will run `lookback` first to build the historical archive, then switch to `forward` for ongoing updates. Running `both` is appropriate when she wants to make sure no gap exists between the historical scan and the forward scan in a single pass — but for now she separates them for clarity.

---

### Step 5.2 — Setting the floor date

**User's need:** Lena wants to go back to January 1, 2024 and no further. Without a floor date, `lookback` would paginate all the way back to the source's beginning, which for some sources is 2014.

**Action:** She sets **Floor date** → `2024-01-01`.

**Config modified:**
```json
"platform_extractor": {
  "floor_date": "2024-01-01"
}
```

**Why this matters:** Each source paginates backward by fetching pages of items ordered newest-first. `floor_date` tells the extractor to stop when it encounters an item published before that date. Without it, the extractor would run for potentially days on large sources. With it, HN lookback for 2024 takes ~40–60 minutes depending on internet speed.

---

### Step 5.3 — Tuning the lookback batch size

**User's need:** Lena's internet connection is fast and she wants the lookback to run as quickly as possible. The default batch size is 50 items per page fetch.

**Action:** She sets **Lookback batch** → `100`.

**Config modified:**
```json
"platform_extractor": {
  "lookback_batch": 100
}
```

**Why increasing the batch:** A larger batch size means each API call retrieves more items, so fewer total HTTP requests are made, and the total time is reduced. The risk of increasing it is that some APIs rate-limit by items-per-request. For HN (Algolia) and Papers With Code (REST), 100 is safe. For npm, stay at 50 or below.

**Why not always set it high:** Some sources paginate differently — for example, Reddit uses `after` cursors and is sensitive to large batches. The default of 50 is conservative and safe across all plugins.

---

### Step 5.4 — Selecting only the relevant sources

**User's need:** Lena only wants HN and Papers With Code history. Running lookback on npm or PyPI would take an enormous amount of time and produce data she does not need.

**Action:** She unchecks everything except `hackernews` and `paperswithcode`.

**Config modified:**
```json
"platform_extractor": {
  "sources": ["hackernews", "paperswithcode"]
}
```

**Outcome after running:** `_external_sources/hackernews/history/` and `_external_sources/paperswithcode/history/` are populated with one JSON file per batch, covering all of 2024 and 2025 up to today.

---

### Step 5.5 — Viewing history-mode discoveries

**User's need:** After lookback completes, Lena wants to browse the full year's discoveries, filtered by minimum quality score.

**Action:** In the **🔍 View** tab, she opens the Discoveries panel and checks **Use history (lookback) data**.

**Viewer config modified:**
```json
"viewer": {
  "discoveries_history": true,
  "discoveries_min_score": 60
}
```

**Why `discoveries_history = true`:** Without this flag, the `discoveries` command reads from `forward/` directories. Her forward data is empty (she hasn't run forward mode yet). Setting `history = true` makes it read from `history/` directories instead, which is where lookback data is stored.

**What appears:** Aggregated list of all HN and Papers With Code items scoring 60+ from Jan 2024 through today. Sorted by score descending.

---

### Step 5.6 — Viewing raw historical data for a specific date

**User's need:** Lena wants to inspect exactly what was published on a particular date — say, the week when a major ML paper dropped.

**Action:** In the **External source browser** section:
- **Source name** → `paperswithcode`
- **Date** → `2024-06-15`

She clicks **Browse external**.

**Viewer config used:**
```json
"viewer": {
  "external_source": "paperswithcode",
  "external_date": "2024-06-15"
}
```

**What appears:** All Papers With Code items from that specific batch file, with their GitHub repo links, titles, abstracts, and scores.

**Why this is useful:** Historical browsing by date lets Lena reconstruct what was happening in the ecosystem at a specific time — useful for research timelines, "what was the state of the art in June 2024" type questions.

---
---

<a name="uc-06"></a>
## Use Case 6 — Fast Lightweight Extraction When Time Is Limited

**Persona:** David is on a flight with sporadic Wi-Fi. He wants to quickly refresh his repo metadata and trending data in under 20 minutes, then resume a fuller extraction later. He also wants to run PIA cheaply without spending API credits on analyses he does not need right now.

---

### Step 6.1 — Skipping text file extraction

**User's need:** Extracting source code is the slowest part of the extraction. For a quick refresh, David only needs metadata, issues, and tree structure — not the full file contents.

**Action:** In the **⬇ GitHub** tab, he checks **Skip text files (tree + metadata + issues only)**.

**Config modified:**
```json
"github_extractor": {
  "skip_text_files": true
}
```

**Why:** Text file extraction makes one API call per file in a repo, often 50–200 calls per large repo. Skipping it reduces a 60-minute extraction to under 10 minutes. The metadata and issues are still fully extracted — enough to keep PIA's KB somewhat current and to browse the viewer.

**Trade-off:** Without text files, PIA's comparisons will be shallower (based on metadata and issues only, not code patterns). David plans to run a full extraction at home later.

---

### Step 6.2 — Skipping issue extraction

**User's need:** Even without text files, fetching all issues for 400 repos takes many API calls. David wants the absolute fastest pass.

**Action:** He also checks **Skip issues (2-3x faster)**.

**Config modified:**
```json
"github_extractor": {
  "skip_issues": true
}
```

**Why:** Issues add 1–5 API calls per repo (paginating through issues and comments). For 400 repos, that's 400–2000 extra calls. Skipping them cuts total API usage dramatically. David will re-enable issues on his next full run at home.

**Combined effect of both flags:** A 400-repo extraction that normally takes 60–90 minutes now completes in 8–12 minutes on a stable connection.

---

### Step 6.3 — Using resume to handle an interrupted run

**User's need:** David's Wi-Fi drops mid-extraction at repo #180. He reconnects and wants to continue without re-extracting the 180 repos already done.

**Action:** He verifies **Resume** is checked (it defaults to `true`) and clicks **▶ Run GitHub Extractor** again.

**Config used:**
```json
"github_extractor": {
  "resume": true
}
```

**What happens:** The extractor checks each repo's target folder in `github_export\`. For repos #1–180, the folders already exist → skipped instantly. Extraction resumes from repo #181.

**Why resume works even with the skip flags:** The extractor marks a repo as "done" by the existence of its output folder and a `meta.json` file inside it. The content of the extraction (with or without text files) does not affect whether the folder counts as complete.

---

### Step 6.4 — Running a cheap PIA analysis

**User's need:** David wants a quick PIA pass to see fresh reports but without spending API credits on intent analysis or the comparison engine — he just wants the basic code structure summaries.

**Action:** In the **🤖 PIA** tab, he checks:
- ✅ `No intent gap analysis (--no-intent)`
- ✅ `No comparison engine (--no-compare)`

He clicks **▶ Run PIA Pipeline**.

**Config modified:**
```json
"pia": {
  "no_intent": true,
  "no_compare": false
}
```

Wait — he actually wants *both* disabled:

**Config modified:**
```json
"pia": {
  "no_intent": true,
  "no_compare": true
}
```

**Why `no_intent = true`:** Intent gap analysis compares what a project claims to do (README, description) against what its issues reveal users are actually asking for. It is the most API-intensive phase (~3–5 Claude calls per project). Skipping it saves significant cost when David just wants structural comparisons.

**Why `no_compare = true`:** The comparison engine retrieves the top-N similar KB repos and asks Claude to produce a detailed comparison. Also expensive. With both disabled, PIA still scans, fingerprints, and structures the projects — it just does not call Claude.

**Outcome:** PIA completes in 30 seconds (all local processing, no API calls). The output is a structural report rather than a deep AI-written analysis. David gets useful data on the flight; he will re-enable both phases at home.

---
---

<a name="uc-07"></a>
## Use Case 7 — Single-Repo Deep Dive

**Persona:** Yuki is evaluating `fastapi/fastapi` for adoption in her team. She wants to extract and thoroughly inspect just that one repo — its README, source code structure, issues, and specifically its `.py` files — without extracting anything else.

---

### Step 7.1 — Setting single-repo mode

**User's need:** Yuki does not want to extract all her starred repos — just this one.

**Action:** In the **⬇ GitHub** tab, she types `fastapi/fastapi` into the **Single repo override** field.

**Config modified:**
```json
"github_extractor": {
  "repo": "fastapi/fastapi"
}
```

**Why:** When `repo` is set to a non-empty value, it *overrides* the `sources` list entirely. The extractor ignores owned/forks/starred/trending and processes only this one repo. It makes the same API calls it would for any other repo — metadata, tree, text files, issues — just limited to this single target.

**Important:** After this use case, Yuki should clear the `repo` field (set it back to blank) so her next full extraction isn't accidentally limited to this one repo.

---

### Step 7.2 — Running the single-repo extraction

**Action:** She clicks **▶ Run GitHub Extractor**.

**Console:**
```
[repo]  Processing fastapi/fastapi...
  ✓ Metadata     → github_export/fastapi__fastapi/meta.json
  ✓ Tree         → github_export/fastapi__fastapi/tree.json
  ✓ Text files   → 847 files extracted
  ✓ Issues       → 2,341 issues extracted
✓ Done. 1 repo processed.
```

**Outcome:** `github_export/fastapi__fastapi/` fully populated in ~3 minutes.

---

### Step 7.3 — Viewing the repo's full detail

**User's need:** Yuki wants a high-level summary of what was captured.

**Action:** In the **🔍 View** tab, she types `fastapi__fastapi` into the **Repo name** field and clicks **Full detail**.

**What appears:** Stars count, language, description, last push date, number of text files extracted, number of issues, top contributors, tags, and a list of the first 20 extracted files.

---

### Step 7.4 — Browsing the directory tree

**User's need:** Yuki wants to understand the project's architecture before reading code.

**Action:** With `fastapi__fastapi` still in the repo name field, she clicks **Directory tree**.

**What appears:**
```
  fastapi/fastapi
  ├── fastapi/
  │   ├── __init__.py
  │   ├── applications.py
  │   ├── routing.py
  │   ├── dependencies/
  │   └── ...
  ├── tests/
  │   └── ...
  ├── docs/
  └── pyproject.toml
```

---

### Step 7.5 — Reading only the Python source files

**User's need:** Yuki wants to read the actual source code but skip the docs and test files — only `.py` files in the main `fastapi/` module directory.

**Action:** In the **Ext filter** field under the repo name, she types `.py`. She clicks **View text files**.

**Viewer config used:**
```json
"viewer": {
  "text_ext_filter": ".py"
}
```

**What appears in console:**
```
  Text files — fastapi__fastapi — filter: .py
  ─────────────────────────────────────────────
  fastapi/__init__.py          (42 lines)
  fastapi/applications.py      (387 lines)
  fastapi/routing.py           (891 lines)
  ...
  847 files → 312 matched .py filter
```

Each file's content is printed in full to the console (scrollable).

**Why `text_ext_filter`:** Without a filter, `text files` dumps all 847 extracted files — 60,000+ lines. The `.py` filter narrows it to only Python source, which is what Yuki actually needs to read.

---

### Step 7.6 — Viewing only the README files

**User's need:** Yuki wants to read all README files (there may be multiple — root `README.md`, per-module READMEs, etc.) without wading through source code.

**Action:** She clicks **Readmes** (with `fastapi__fastapi` in the repo name field).

**What appears:**
```
  READMEs — fastapi__fastapi
  ─────────────────────────────
  README.md           (root)
  docs/README.md      ...
```

---

### Step 7.7 — Browsing issues to understand common pain points

**User's need:** Yuki wants to understand what users most commonly complain about or request.

**Action:** She clicks **Issues** for `fastapi__fastapi`.

**What appears:**
```
  Issues — fastapi__fastapi — 2,341 total
  ──────────────────────────────────────────
  #9840  open   [QUESTION] Dependency injection with async generators...
  #9832  closed [BUG] 422 error not returning custom error model...
  ...
```

**Outcome:** Yuki reads through 20+ issues, understands the main pain points, and makes an informed adoption decision. The entire workflow took under 10 minutes.

---
---

<a name="uc-08"></a>
## Use Case 8 — Automated Recurring Pipeline with Chaining

**Persona:** Chen runs a developer tooling newsletter. He wants the full extraction pipeline — GitHub trending plus platform discovery — to run automatically every day at midnight so his morning reading list is always fresh when he wakes up.

---

### Step 8.1 — Setting GitHub extractor schedule

**User's need:** The GitHub extractor should run once every 24 hours automatically.

**Action:** In the **⬇ GitHub** tab, he types `24h` into the **Schedule** field.

**Config modified:**
```json
"github_extractor": {
  "schedule": "24h"
}
```

**How this works:** When launched, the extractor runs its full extraction, then sleeps 24 hours, then runs again in a loop until the process is killed. Chen will start it in a terminal window or as a background service.

---

### Step 8.2 — Enabling chain to platform extractor

**User's need:** After each GitHub extraction, Chen wants the platform extractor to run automatically — he does not want to manage two separate scheduled processes.

**Action:** He checks **Run Platform Extractor automatically after GitHub extraction**.

**Config modified:**
```json
"github_extractor": {
  "chain_platform": true
}
```

**Why chaining:** When `chain_platform = true`, the GitHub extractor calls `platform_extractor.py` as a subprocess after its own run completes — passing the same output directory. This means one process manages the entire extraction cycle. Chen only needs to keep one window open.

---

### Step 8.3 — Filtering which platform sources to run in the chain

**User's need:** Chen only wants Hacker News and npm to run in the chained platform pass. PyPI is not relevant to his newsletter audience.

**Action:** In the **Platform sources filter** field (below the chain checkbox), he types `hackernews,npm`.

**Config modified:**
```json
"github_extractor": {
  "platform_sources_filter": "hackernews,npm"
}
```

**Why:** `platform_sources_filter` is passed as `--platform-sources` to the platform extractor subprocess. It overrides the platform extractor's own `sources` config for that invocation only. This lets Chen run the full platform extractor independently with all sources, but keep the chained pass limited to just two.

---

### Step 8.4 — Setting platform extractor schedule independently

**User's need:** Chen also wants the ability to run the platform extractor standalone on a 6-hour cycle to catch breaking news between the 24-hour GitHub cycles.

**Action:** In the **🌐 Platform** tab, he types `6h` into its **Schedule** field.

**Config modified:**
```json
"platform_extractor": {
  "schedule": "6h"
}
```

**How this coexists with chaining:** The platform extractor's `schedule` is only used when it is run *directly* (e.g. `launcher.bat platform`). When launched as a subprocess by the GitHub extractor chain, the schedule is ignored — it just runs once and exits. So Chen can have `schedule = "6h"` set for standalone use without affecting the chain behavior.

---

### Step 8.5 — Launching the automated pipeline

**Action:** Chen opens a terminal, navigates to the suite folder, and runs:
```bat
launcher.bat extract
```

Or, using the GUI, he clicks **▶ Run GitHub Extractor** — but for a background process he prefers the terminal.

**What runs:**
1. GitHub extraction (trending + owned) — ~15 min
2. Chain triggers → platform extractor with `hackernews,npm` — ~5 min
3. Process sleeps 24h
4. Repeats

**Outcome:** Every morning, Chen's `github_export\` folder has the latest trending repos and a fresh set of HN + npm discoveries. He opens the viewer with his coffee.

---
---

<a name="uc-09"></a>
## Use Case 9 — Rust Ecosystem Intelligence Feed

**Persona:** Fatima is a systems programmer deeply invested in the Rust ecosystem. She wants comprehensive coverage of everything happening in Rust — crates releases, This Week in Rust newsletter content, Lobsters discussions, Reddit posts, and GitHub trending in Rust — using a lookback scan to catch up on the past 6 months, then switching to `both` for ongoing coverage.

---

### Step 9.1 — Configuring platform sources to Rust-relevant only

**User's need:** Fatima only wants sources that publish Rust content. Irrelevant sources like PyPI or npm would waste time and pollute her results.

**Action:** In the **🌐 Platform** tab, she uses the **Select none** button to clear all sources, then manually checks:
- ✅ `cratesio` — Rust package registry
- ✅ `thisweekrust` — the canonical weekly Rust newsletter with curated links
- ✅ `lobsters` — tech link aggregator with a strong Rust community
- ✅ `reddit` — r/rust and r/programming subreddits

**Config modified:**
```json
"platform_extractor": {
  "sources": ["cratesio", "thisweekrust", "lobsters", "reddit"]
}
```

**Why each source:**
- `cratesio` — every published crate has a GitHub link; this catches new Rust libraries the moment they appear.
- `thisweekrust` — curated by humans; every link in This Week in Rust is editorially selected as worth reading. Very high signal-to-noise.
- `lobsters` — Lobsters users tag posts with `rust`; the API exposes tag-filtered feeds, so the plugin fetches only Rust-tagged posts.
- `reddit` — r/rust is one of the most active language-specific subreddits; new project announcements, Show-and-Tell threads, and release posts appear here first.

---

### Step 9.2 — Setting mode to both for initial catch-up plus ongoing

**User's need:** Fatima wants to catch up on the past 6 months in one run and also capture today's new items — without running two separate commands.

**Action:** She sets **Mode** → `both`.

**Config modified:**
```json
"platform_extractor": {
  "mode": "both"
}
```

**Why `both`:** The extractor runs the `forward` pass first (fetches today's new items), then runs the `lookback` pass (paginates backward to `floor_date`). Running them in sequence in one command means Fatima ends up with both historical and current data after a single invocation.

---

### Step 9.3 — Setting floor date to 6 months ago

**User's need:** She wants backfill for the past 6 months, not further.

**Action:** She sets **Floor date** → `2024-11-28` (6 months before today).

**Config modified:**
```json
"platform_extractor": {
  "floor_date": "2024-11-28"
}
```

---

### Step 9.4 — Adding GitHub trending for Rust

**User's need:** In addition to the platform sources, Fatima wants GitHub trending repos in Rust.

**Action:** In the **⬇ GitHub** tab, she checks only `trending` in sources and sets **Trending languages** → `rust`.

**Config modified:**
```json
"github_extractor": {
  "sources": ["trending"],
  "trending_langs": "rust"
}
```

**Outcome after both runs:** Fatima has:
- `_external_sources/cratesio/history/` — 6 months of new crate releases
- `_external_sources/thisweekrust/history/` — every issue of TWIR for the last 6 months
- `_external_sources/lobsters/history/` — Rust-tagged posts
- `_external_sources/reddit/history/` — r/rust posts
- `_trending/rust/` — current Rust trending repos

She runs discoveries with `source=cratesio` and `min_score=40` to find the most-adopted new crates.

---
---

<a name="uc-10"></a>
## Use Case 10 — SearXNG Meta-Search Discovery

**Persona:** Oliver self-hosts a SearXNG instance on his home server at `http://192.168.1.50:8888`. He wants to use it as an additional discovery layer — feeding custom search queries through SearXNG and extracting any GitHub repo links it finds.

---

### Step 10.1 — Setting the SearXNG URL in the GitHub extractor

**User's need:** The GitHub extractor can use SearXNG to augment its trending and collections scraping — fetching additional repos through search queries that SearXNG executes across multiple search engines simultaneously.

**Action:** In the **⬇ GitHub** tab, he types `http://192.168.1.50:8888` into the **SearXNG URL** field.

**Config modified:**
```json
"github_extractor": {
  "searxng_url": "http://192.168.1.50:8888"
}
```

**Why this helps:** SearXNG searches across Bing, DuckDuckGo, and others simultaneously. For GitHub-specific queries (e.g. "new Rust async runtime github"), it surfaces repos that might not appear in GitHub trending or any single API-based source. The extractor passes the URL to the scraping engine, which then uses it for augmentation queries.

---

### Step 10.2 — Adding the SearXNG platform plugin

**User's need:** Oliver also wants the platform extractor to run discovery queries directly through SearXNG — for software-specific searches like "best Python HTTP client library 2025".

**Action:** In the **🌐 Platform** tab, he checks ✅ `searxng` in the sources list.

**Config modified:**
```json
"platform_extractor": {
  "sources": ["hackernews", "pypi", "searxng"]
}
```

---

### Step 10.3 — Setting the platform SearXNG URL

**User's need:** The platform extractor's SearXNG plugin needs to know the URL of the instance separately from the GitHub extractor's setting (they are stored independently).

**Action:** In the **Advanced** section of the **🌐 Platform** tab, he types `http://192.168.1.50:8888` into the **SearXNG URL** field.

**Config modified:**
```json
"platform_extractor": {
  "searxng_url": "http://192.168.1.50:8888"
}
```

**Why two separate SearXNG URL fields:** `github_extractor.searxng_url` is passed as `--searxng-url` to the GitHub extractor script. `platform_extractor.searxng_url` is passed as `--searxng-url` to the platform extractor script. Each script uses it differently — the GitHub extractor uses it for repo augmentation; the platform SearXNG plugin uses it as its primary data source. They may point to different instances in a multi-server setup.

**Outcome:** Both extractors will route their search queries through Oliver's SearXNG instance, giving him a self-hosted, ad-free, cross-engine discovery layer without relying on any single search provider.

---
---

<a name="uc-11"></a>
## Use Case 11 — Targeted AI Comparison: How Does My Project Stack Up on Caching?

**Persona:** Reza built `cachepilot`, a Python caching middleware. He wants PIA to find the best caching libraries in his knowledge base and produce a detailed side-by-side comparison — without running intent analysis (he knows what his project does) and without re-ingesting the KB.

---

### Step 11.1 — Targeting a specific project

**User's need:** Reza only wants to analyse `cachepilot`, not all his other projects.

**Action:** In the **🤖 PIA** tab, he types `cachepilot` into the **Project** field.

**Config modified:**
```json
"pia": {
  "project": "cachepilot"
}
```

---

### Step 11.2 — Skipping intent analysis to save API cost

**User's need:** Intent analysis is expensive and Reza already knows `cachepilot`'s intent. He wants to skip it and focus API budget on the comparison.

**Action:** He checks ✅ **No intent gap analysis (--no-intent)**.

**Config modified:**
```json
"pia": {
  "no_intent": true
}
```

**Why:** Intent gap analysis reads the project's issues, README, and commit messages, then asks Claude to infer what users want that the project doesn't yet provide. It costs ~3–5 API calls per project. Reza already has a clear feature roadmap — he doesn't need PIA to derive it from scratch.

---

### Step 11.3 — Setting a focused compare topic

**User's need:** The default comparison finds similar repos broadly. Reza wants PIA to specifically compare `cachepilot` to other repos on the topic of "in-memory cache invalidation strategies" — much more targeted than a general similarity search.

**Action:** In the **Compare topic** field, he types `in-memory cache invalidation strategies`.

**Config modified:**
```json
"pia": {
  "compare_topic": "in-memory cache invalidation strategies"
}
```

**Why `compare_topic`:** When set, PIA constructs a targeted retrieval query against the KB rather than using a broad "similar to this project" embedding search. This surfaces repos that specifically discuss cache invalidation — even if they aren't broadly similar to `cachepilot` — producing more relevant comparisons.

---

### Step 11.4 — Pinning known excellent comparison repos

**User's need:** Reza knows that `jonaslsg/cachebox` and `tkem/cachetools` are the best-in-class examples he wants to benchmark against. He wants them included in the comparison regardless of their embedding similarity score.

**Action:** In the **Pin compare repos** field, he types `jonaslsg__cachebox,tkem__cachetools` (using the `owner__repo` format used in the KB folder names).

**Config modified:**
```json
"pia": {
  "compare_repos": "jonaslsg__cachebox,tkem__cachetools"
}
```

**Why `compare_repos`:** Without this, PIA picks comparison repos entirely by embedding similarity and reputation score. Those two repos might score lower (fewer stars, older) even though they are architecturally the most relevant. Pinning them guarantees they appear in the comparison regardless of their automatic ranking.

---

### Step 11.5 — Force-marking a repo as eligible

**User's need:** Reza also wants `redis-py` included, but it scored below PIA's reputation threshold during benchmarking (because it's a wrapper, not a standalone cache — low "code complexity" score). He wants to override the threshold.

**Action:** He types `redis__redis-py` into the **Force eligible** field.

**Config modified:**
```json
"pia": {
  "force_eligible": "redis__redis-py"
}
```

**Why `force_eligible`:** During Phase 1.5, PIA scores each KB repo and marks low-scorers as ineligible for comparison (to avoid cluttering reports with low-quality references). `force_eligible` bypasses this gate for a specific repo — it will appear as a comparison candidate regardless of its benchmark score. This is useful when a repo's reputation score is low for structural reasons (wrappers, bindings, forks) but it is still a meaningful comparison target.

---

### Step 11.6 — Running the targeted comparison

**Action:** Reza clicks **▶ Run PIA Pipeline**.

**Console output:**
```
Phase 1   — KB already exists. Skipping ingest.
Phase 1.5 — Reputation scores exist. Skipping benchmark.
Phase 2   — Scanning for project matching 'cachepilot'...
Phase 3   — Analysing: cachepilot
  No intent analysis (--no-intent)
  Comparison: topic='in-memory cache invalidation strategies'
    Retrieved from KB: jonaslsg__cachebox (pinned), tkem__cachetools (pinned),
                       redis__redis-py (force-eligible), beaker__beaker...
  Generating comparison report...
Phase 4   — Writing report:  pia/reports/cachepilot_report.md
✓ Done.
```

**Outcome:** The report contains a detailed comparison of `cachepilot` against the best KB repos specifically on the topic Reza cared about, with his pinned repos guaranteed to appear. Processing took ~90 seconds.

---
---

<a name="uc-12"></a>
## Use Case 12 — Rebuilding the Knowledge Base After a Major Re-Extraction

**Persona:** Sofia ran a full re-extraction after adding 200 new repos to her knowledge base. The ChromaDB vector store is now stale — it still contains embeddings from the old extraction. She needs to wipe it and re-embed everything from scratch, then optionally re-run analysis on one project.

---

### Step 12.1 — Wiping the old KB

**User's need:** Sofia needs to clear the ChromaDB store completely before re-ingesting, because old embeddings from deleted or updated repos will otherwise persist and contaminate comparisons.

**Action:** In the **🤖 PIA** tab, she checks ✅ **Clear knowledge base before run ⚠ DESTRUCTIVE**.

**Config modified:**
```json
"pia": {
  "clear_kb": true
}
```

**The confirmation dialog:** The GUI shows a warning dialog: `"This will WIPE the vector store. Are you sure?"`. Sofia clicks **Yes**.

**Why the extra confirmation:** `--clear-kb` is irreversible. All embeddings are deleted. Re-ingestion takes 10–30 minutes depending on KB size. The GUI forces an explicit confirmation to prevent accidental data loss.

---

### Step 12.2 — Running ingest-only to rebuild the KB

**User's need:** Sofia only wants to rebuild the KB right now — she does not need analysis reports yet. She will run analysis after verifying the KB is correct.

**Action:** She clicks **📥 Ingest only** (which internally sets `ingest_only=true` for this run only, overriding what is in config).

**Config used for this button press:**
```json
{
  "ingest_only": true,
  "scan_only": false,
  "clear_kb": true
}
```

**Console output:**
```
Phase 1   — Clear KB: wiping ChromaDB...
  ✓ Vector store cleared.
Phase 1   — Ingesting 591 repos...
  Embedding: sarah-codes__api-gateway   (chunk 1/12)...
  ...
  ✓ 591 repos, 41,823 chunks embedded.
Phase 1.5 — Benchmarking 591 repos...
  ✓ All repos scored.
✓ Ingest complete.
```

**Outcome:** Fresh, accurate ChromaDB with all 591 repos correctly embedded.

---

### Step 12.3 — Clearing the clear_kb flag

**User's need:** Sofia must un-check `clear_kb` immediately after the wipe. If she forgets and runs again, the brand-new KB will be deleted again.

**Action:** She un-checks **Clear knowledge base** in the PIA tab.

**Config modified:**
```json
"pia": {
  "clear_kb": false
}
```

**This is saved automatically** (auto-save debounce triggers within 1.2 seconds of the un-check).

---

### Step 12.4 — Running scan-only to regenerate reports

**User's need:** KB is now current. Sofia wants to regenerate all her project reports without re-ingesting again.

**Action:** She clicks **🔍 Scan only**.

**Config used:**
```json
{
  "scan_only": true,
  "ingest_only": false
}
```

**Console:**
```
Phase 1   — Skipping ingest (scan-only mode).
Phase 2   — Discovering projects...
Phase 3   — Analysing 3 projects...
Phase 4   — Reports written.
✓ Done.
```

**Outcome:** Fresh reports generated against the new KB in ~3 minutes. The clear→ingest→scan workflow ensures maximum KB accuracy.

---
---

<a name="uc-13"></a>
## Use Case 13 — Multi-Environment Setup with Custom Config Paths

**Persona:** Tomás is a DevOps engineer. He has two separate environments: `work` (a shared team server with PIA configured for team projects) and `personal` (his laptop with personal projects). He needs the suite to use different `config.yaml` files and different output directories depending on which context he is running in.

---

### Step 13.1 — Setting a custom output directory for the work environment

**User's need:** On the work server, extracted repos should go to `/data/shared/github_export` rather than the default `./github_export`.

**Action:** In the **⚙ Setup** tab, he sets **Output directory** → `/data/shared/github_export`.

**Config modified:**
```json
"global": {
  "output_dir": "/data/shared/github_export"
}
```

**Why this propagates everywhere:** Both extractors read `global.output_dir` when building their `--output` argument. The viewer inherits it via the `EXPORT_DIR` environment variable set before each subprocess call. One setting controls all four tools.

---

### Step 13.2 — Setting a custom platform extractor config

**User's need:** The work server has a shared `platform_config_work.yaml` that specifies Reddit credentials, custom subreddits, and rate-limit settings tuned for the server's IP. Tomás does not want to modify the default config.

**Action:** In the **🌐 Platform** tab's **Advanced** section, he clicks **Browse** next to **Custom config.yaml** and selects `/etc/github_intel/platform_config_work.yaml`.

**Config modified:**
```json
"platform_extractor": {
  "config_yaml": "/etc/github_intel/platform_config_work.yaml"
}
```

**What this does:** When the platform extractor runs, it is passed `--config /etc/github_intel/platform_config_work.yaml`. This file overrides the default per-plugin settings (timeouts, auth tokens, subreddit lists, etc.) without modifying the central `suite_config.json`.

---

### Step 13.3 — Setting a custom PIA config for the work environment

**User's need:** The work PIA instance uses a different Anthropic API key (the company's key), different project roots, and a different KB source directory. The team maintains this at `/etc/github_intel/pia_config_work.yaml`.

**Action:** In the **🤖 PIA** tab's **Advanced** section, he clicks **Browse** next to **Custom config.yaml** and selects `/etc/github_intel/pia_config_work.yaml`.

**Config modified:**
```json
"pia": {
  "config_yaml": "/etc/github_intel/pia_config_work.yaml"
}
```

**What this does:** PIA is launched with `--config /etc/github_intel/pia_config_work.yaml`, which overrides `pia/config.yaml` entirely for this run. The team config specifies the shared API key, the server's project roots, and the server's output paths.

---

### Step 13.4 — Switching back to personal environment

**User's need:** At home, Tomás uses his personal config. He wants a quick way to switch.

**Action:** He maintains two `suite_config.json` files:
- `suite_config_work.json`
- `suite_config_personal.json`

He copies the appropriate one over `suite_config.json` before launching. Or, in the TUI, he uses the CLI flag mechanism and a shell alias:

```bash
alias intel-work='cp suite_config_work.json suite_config.json && ./launcher.sh'
alias intel-personal='cp suite_config_personal.json suite_config.json && ./launcher.sh'
```

**Why `suite_config.json` supports this pattern:** The `ConfigManager` always reads from a single file. Swapping the file is a zero-configuration context switch. The file format is plain JSON, easily diff-able and version-controllable.

---
---

<a name="uc-14"></a>
## Use Case 14 — GitHub Collections Exploration

**Persona:** Angela is a new developer trying to discover curated sets of repos around specific themes like "machine learning", "developer tools", and "open source games" — which GitHub organizes into "Collections". She wants to extract several collections and then browse them.

---

### Step 14.1 — Enabling collections source

**User's need:** GitHub Collections are manually curated by GitHub staff and community. They are a high-quality signal for "this topic matters, here are the canonical repos for it." Angela wants to extract them.

**Action:** In the **⬇ GitHub** tab, she checks ✅ `collections` and unchecks all other sources.

**Config modified:**
```json
"github_extractor": {
  "sources": ["collections"]
}
```

---

### Step 14.2 — Enabling full collection scraping

**User's need:** By default, the collections extractor fetches the list of GitHub's public collections and the metadata for each, but does not deeply scrape each collection's member repo list. Angela wants the full repo list for every collection, not just the collection names.

**Action:** She checks ✅ **Collections full (scrape each collection's repo list — slower)**.

**Config modified:**
```json
"github_extractor": {
  "collections_full": true
}
```

**Why `collections_full` is off by default:** Each collection contains 20–100 repos. Scraping them all requires one HTTP request per collection (GitHub has ~200+ collections), which adds 200+ scraping calls using Scrapling. This takes 15–30 minutes. With `collections_full = false`, only collection names and top-level metadata are fetched (fast). With it `true`, the full member list for every collection is scraped and each member repo is then extracted.

**When to use `collections_full = true`:**
- You want a comprehensive, thematically organized KB for PIA (high quality because collections are curated).
- You have time for a longer extraction.
- You want to use `viewer: collections` to browse themed repo lists.

---

### Step 14.3 — Running the extraction

**Action:** Angela clicks **▶ Run GitHub Extractor**.

**Console (abbreviated):**
```
[collections] Fetching GitHub Collections list...
  Found 218 public collections.
[collections] Scraping member repos (collections_full=true)...
  machine-learning:     47 repos
  developer-tools:      38 repos
  open-source-games:    29 repos
  ...
[collections] Extracting 1,847 unique member repos...
  ✓ microsoft__vscode
  ✓ tensorflow__tensorflow
  ...
✓ Done. 1,847 repos extracted.
```

---

### Step 14.4 — Browsing collections in the Viewer

**User's need:** Angela wants to browse the collections thematically.

**Action:** In the **🔍 View** tab, she clicks **📚 Collections** in the quick actions.

**What appears:**
```
  GitHub Collections (218 total)
  ──────────────────────────────────────
  3d-printing            (14 repos)
  accessibility          (8 repos)
  ai-assistants          (22 repos)
  ...
  machine-learning       (47 repos)
  ...
```

**Action:** She then types `machine-learning` into the custom viewer command box (or in the TUI: `V` → `collections machine-learning`) to see all repos in that collection.

**Outcome:** Angela browses 218 themed collections, each with their curated repo lists — all extracted locally and browsable offline.

---
---

<a name="uc-15"></a>
## Use Case 15 — Extracting Non-Standard File Types

**Persona:** Ben is a backend engineer working with a polyglot codebase. His repos contain `.proto` files (Protobuf schema definitions), `.graphql` files (GraphQL schemas), and `.hcl` files (Terraform infrastructure code). These are not in the extractor's default registered extensions, so they are normally skipped. Ben needs them extracted so PIA can analyse infrastructure and API design patterns.

---

### Step 15.1 — Understanding the default extension list

**User's need:** Ben first needs to understand what is and is not extracted by default.

**Default registered extensions (common set):**
`.py`, `.js`, `.ts`, `.jsx`, `.tsx`, `.go`, `.rs`, `.java`, `.kt`, `.rb`, `.php`, `.cs`, `.cpp`, `.c`, `.h`, `.swift`, `.sh`, `.bash`, `.yml`, `.yaml`, `.toml`, `.json`, `.md`, `.rst`, `.txt`, `.sql`, `.html`, `.css`, `.scss`

**What is NOT in the default list:** `.proto`, `.graphql`, `.hcl`, `.tf`, `.avro`, `.thrift`, `.pydantic`, `.prisma`, and other domain-specific schema or config formats.

**Why these are excluded by default:** The default list is a balance between coverage and extraction time. Including every possible extension would dramatically increase extraction size. Domain-specific formats are left to the user to add explicitly.

---

### Step 15.2 — Adding custom extensions

**User's need:** Ben wants `.proto`, `.graphql`, and `.hcl` files extracted in addition to the defaults.

**Action:** In the **⬇ GitHub** tab, in the **Content extraction** section, he types `.proto,.graphql,.hcl` into the **Extra extensions** field.

**Config modified:**
```json
"github_extractor": {
  "text_extensions": ".proto,.graphql,.hcl"
}
```

**How this works:** The value is passed as `--text-extensions .proto,.graphql,.hcl` to the extractor. The extractor appends these extensions to its internal registered list. Any file with these extensions found in a repo's tree is then read and saved to the output folder, exactly like `.py` or `.go` files.

**Precision matters:** Extensions must include the leading dot (`.proto` not `proto`). Comma-separated, no spaces.

---

### Step 15.3 — Running extraction and verifying custom files were captured

**Action:** Ben runs the GitHub extractor on his own repos.

**Console shows (for one repo):**
```
sarah-codes__api-gateway
  ✓ api_gateway/auth.proto       extracted
  ✓ api_gateway/user.proto       extracted
  ✓ schemas/api.graphql          extracted
  ✓ infra/main.hcl               extracted
  ...
```

---

### Step 15.4 — Viewing the custom file types in the Viewer

**User's need:** Ben wants to confirm the `.proto` files are accessible and readable.

**Action:** In the **🔍 View** tab, he types his repo name `bencodes__api-gateway` into the **Repo name** field, types `.proto` into the **Ext filter**, and clicks **View text files**.

**Viewer config used:**
```json
"viewer": {
  "text_ext_filter": ".proto"
}
```

**What appears:** All `.proto` file contents for that repo, printed to the console. Ben confirms his Protobuf schemas were extracted correctly.

---

### Step 15.5 — PIA now analyses infrastructure patterns

**User's need:** Ben re-runs PIA after the extraction. Because `.hcl` files are now in the KB, PIA can find similar infrastructure patterns in other repos.

**Action:** He runs PIA with `compare_topic = "terraform infrastructure patterns for microservices"`.

**Config modified:**
```json
"pia": {
  "compare_topic": "terraform infrastructure patterns for microservices"
}
```

**Outcome:** PIA's comparison now includes `.hcl`-heavy repos from the KB in the comparison results — repos it could not previously surface because their infrastructure code was invisible. Ben receives recommendations specifically about his Terraform setup that reference comparable open-source infrastructure.

---

## Parameter Coverage Summary

| Parameter | Use Case(s) |
|-----------|-------------|
| `global.output_dir` | 1, 13 |
| `github_extractor.token` | 1 |
| `github_extractor.sources` | 1, 3, 7, 8, 9, 14 |
| `github_extractor.collections_full` | 14 |
| `github_extractor.repo` | 7 |
| `github_extractor.trending_langs` | 3, 9 |
| `github_extractor.skip_text_files` | 6 |
| `github_extractor.text_extensions` | 15 |
| `github_extractor.skip_issues` | 6 |
| `github_extractor.resume` | 1, 6 |
| `github_extractor.schedule` | 8 |
| `github_extractor.searxng_url` | 10 |
| `github_extractor.chain_platform` | 8 |
| `github_extractor.platform_sources_filter` | 8 |
| `platform_extractor.mode` | 4, 5, 9 |
| `platform_extractor.sources[hackernews]` | 4, 10 |
| `platform_extractor.sources[paperswithcode]` | 4, 5 |
| `platform_extractor.sources[npm]` | 4, 8 |
| `platform_extractor.sources[pypi]` | 4 |
| `platform_extractor.sources[cratesio]` | 9 |
| `platform_extractor.sources[devto]` | 4 |
| `platform_extractor.sources[lobsters]` | 9 |
| `platform_extractor.sources[reddit]` | 9 |
| `platform_extractor.sources[thisweekrust]` | 9 |
| `platform_extractor.sources[searxng]` | 10 |
| `platform_extractor.schedule` | 4, 8 |
| `platform_extractor.floor_date` | 5, 9 |
| `platform_extractor.lookback_batch` | 5 |
| `platform_extractor.config_yaml` | 13 |
| `platform_extractor.searxng_url` | 10 |
| `pia.ingest_only` | 2, 12 |
| `pia.scan_only` | 2, 12 |
| `pia.project` | 2, 11 |
| `pia.force_eligible` | 11 |
| `pia.no_intent` | 6, 11 |
| `pia.no_compare` | 6, 11 |
| `pia.compare_topic` | 11, 15 |
| `pia.compare_repos` | 11 |
| `pia.skip_benchmark` | 2 |
| `pia.clear_kb` | 12 |
| `pia.config_yaml` | 13 |
| `viewer.trending_period` | 3 |
| `viewer.trending_lang` | 3 |
| `viewer.external_source` | 4, 5 |
| `viewer.external_date` | 5 |
| `viewer.discoveries_source` | 4 |
| `viewer.discoveries_min_score` | 4 |
| `viewer.discoveries_history` | 5 |
| `viewer.text_ext_filter` | 7, 15 |

**All 40 parameters covered across 15 use cases.**
