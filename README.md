# GitHub Intelligence Suite

> **Extract · Discover · Browse · Analyse** — a complete GitHub intelligence pipeline in one monorepo.

Four tools that work independently or together as a unified suite:

| Tool | What it does |
|---|---|
| `github_extractor_v2.py` | Pulls repos, READMEs, issues, trending, and collections from GitHub |
| `platform_extractor.py` | Discovers GitHub repos via 10 external platforms (HN, PyPI, npm, crates.io, …) |
| `github_viewer_v2.py` | Browse, search, and inspect all extracted data from the terminal |
| `pia/` | **Project Intelligence Analyst** — AI code-review against an open-source knowledge base |

The `launcher.py` / `gui_app.py` front-ends wire everything together with a single config file (`suite_config.json`).

---

## Table of Contents

1. [Repository layout](#1-repository-layout)
2. [Quick start — all platforms](#2-quick-start)
3. [Installation — detailed](#3-installation--detailed)
4. [Tool reference](#4-tool-reference)
   - [GitHub Extractor](#41-github-extractor)
   - [Platform Extractor](#42-platform-extractor)
   - [GitHub Viewer](#43-github-viewer)
   - [PIA — Project Intelligence Analyst](#44-pia--project-intelligence-analyst)
5. [Launcher — TUI](#5-launcher--tui)
6. [GUI](#6-gui-application)
7. [Configuration files](#7-configuration-files)
8. [Scheduling](#8-scheduling)
9. [Building a standalone EXE](#9-building-a-standalone-exe)
10. [Output structure](#10-output-structure)
11. [Troubleshooting](#11-troubleshooting)
12. [FAQ](#12-faq)

---

## 1. Repository layout

```
github-intelligence-suite/
│
│  ── Orchestration ───────────────────────────────────────────────────────────
├── launcher.py              TUI — interactive menu, all params, saves to config
├── gui_app.py               GUI — 5-tab Tkinter app (no terminal needed)
├── config_manager.py        Single source of truth for all 40 settings
├── suite_config.json.example Template config (copy → suite_config.json)
│
│  ── Core tools ──────────────────────────────────────────────────────────────
├── github_extractor_v2.py   GitHub repo extractor (owned/starred/trending/…)
├── platform_extractor.py    External platform discovery (10 plugins)
├── github_viewer_v2.py      Terminal browser for extracted data
│
│  ── PIA sub-project ────────────────────────────────────────────────────────
├── pia/
│   ├── config.yaml.example  Edit → save as config.yaml (add API keys)
│   ├── requirements.txt     PIA-specific Python dependencies
│   ├── test_setup.py        Validates environment before first run
│   ├── user_prompts.yaml    Customisable LLM analysis prompts
│   ├── utils.py             Shared utilities
│   ├── run.bat              One-click run (Windows)
│   ├── setup_pia.bat        PIA-only dependency installer (Windows)
│   ├── setup_scheduler.bat  Registers weekly Windows Task Scheduler job
│   ├── ingest/              Knowledge-base loader + vector store
│   │   ├── chunker.py
│   │   ├── loader.py
│   │   ├── repo_benchmarker.py
│   │   ├── reputation_store.py
│   │   └── vectorstore.py
│   ├── scan/                Project file scanners
│   │   ├── colab_scanner.py
│   │   ├── github_scanner.py
│   │   └── local_scanner.py
│   ├── analysis/            LLM analysis pipeline
│   │   ├── comparator.py
│   │   ├── constraints.py
│   │   ├── intent_analyzer.py
│   │   ├── llm_analyzer.py
│   │   ├── project_profiler.py
│   │   ├── retriever.py
│   │   └── user_prompts_loader.py
│   ├── report/
│   │   └── generator.py
│   └── scheduler/
│       └── run_pipeline.py  Entry point — runs the full 5-phase pipeline
│
│  ── Platform plugins ────────────────────────────────────────────────────────
├── sources/                 Drop custom platform plugins here (auto-discovered)
│
│  ── Shell launchers ────────────────────────────────────────────────────────
├── launcher.bat             Windows TUI launcher
├── launcher.sh              Linux/macOS TUI launcher
├── run_gui.bat              Windows double-click GUI launcher
├── setup.bat                One-time Windows installer (all deps)
├── setup.sh                 One-time Linux/macOS installer (all deps)
├── build_exe.bat            PyInstaller — packages to a standalone .exe
│
│  ── Reference ───────────────────────────────────────────────────────────────
├── FAQ.md                   Long-form FAQ and worked examples
├── .gitignore
└── reports/                 PIA writes reports here (git-ignored)
```

---

## 2. Quick Start

### Windows (non-technical users — GUI)

```bat
1. setup.bat             ← one-time install (~3 min)
2. Double-click run_gui.bat
3. ⚙ Setup tab  → paste your GitHub token
4. ⬇ GitHub tab → pick sources → ▶ Run
5. 🔍 View tab   → browse results
6. 🤖 PIA tab    → run AI analysis (needs Anthropic key)
```

### Windows (developers — TUI)

```bat
setup.bat               REM install once
launcher.bat            REM interactive menu
```

### Linux / macOS

```bash
bash setup.sh           # install once
./launcher.sh           # interactive menu
```

### Direct CLI (any OS)

```bash
# GitHub extraction
python github_extractor_v2.py --token ghp_xxx --sources owned,trending

# Platform discovery
python platform_extractor.py --mode forward

# Browse results
python github_viewer_v2.py list
python github_viewer_v2.py trending daily

# PIA analysis
cd pia && python scheduler/run_pipeline.py
```

---

## 3. Installation — Detailed

### Prerequisites

| Requirement | Minimum | Notes |
|---|---|---|
| Python | 3.10+ | Tick "Add to PATH" on Windows |
| pip | bundled | Used by setup scripts |
| RAM | 4 GB | 8 GB recommended for PIA (embeddings) |
| Disk | ~1.5 GB | PyTorch + ChromaDB for PIA |
| Internet | Required | GitHub API + Anthropic API |

### Step 1 — Install Python

Download from **https://python.org/downloads** and install.  
**Windows:** tick ✅ **"Add Python to PATH"** during setup.

Verify:
```bash
python --version    # should show 3.10+
```

### Step 2 — Clone or download this repo

```bash
git clone https://github.com/YOUR_USERNAME/github-intelligence-suite.git
cd github-intelligence-suite
```

Or download the ZIP from GitHub and extract it anywhere.

### Step 3 — Install base dependencies (extractor + viewer)

**Windows:**
```bat
setup.bat
```

**Linux / macOS:**
```bash
bash setup.sh
```

This installs, for the core tools:
```
PyGithub   requests   scrapling   beautifulsoup4   rich
```

And for PIA (if `pia/requirements.txt` is present):
```
anthropic   chromadb   sentence-transformers   torch (CPU)
tiktoken    chardet    PyGithub   nbformat   rich   jinja2   schedule
```

> **PIA note:** The first install downloads PyTorch (~700 MB). Takes 5–10 min on a slow connection. Subsequent runs use the cache.

### Step 4 — Configure API keys

**Suite config (extractor + viewer + platform):**

```bash
cp suite_config.json.example suite_config.json
```

Edit `suite_config.json` and set at minimum:
```json
{
  "github_extractor": {
    "token": "ghp_YOUR_GITHUB_TOKEN_HERE"
  }
}
```

**PIA config:**

```bash
cp pia/config.yaml.example pia/config.yaml
```

Edit `pia/config.yaml`:
```yaml
anthropic:
  api_key: "sk-ant-YOUR_KEY_HERE"

knowledge_base:
  source_dir: "/path/to/your/exported-repos"
  chroma_dir: "/path/to/pia-data/chroma"

projects:
  github:
    username: "your-github-username"
    token: "ghp_YOUR_TOKEN"
  local:
    roots:
      - "/path/to/your/local/projects"
```

**Getting tokens:**

- **GitHub token:** https://github.com/settings/tokens → Fine-grained → give `Contents: Read` + `Metadata: Read`
- **Anthropic key:** https://console.anthropic.com → API Keys → Create Key

### Step 5 — Test your setup

```bash
# Test extractor + viewer (no token needed for trending only)
python github_extractor_v2.py --sources trending

# Test PIA environment
cd pia && python test_setup.py
```

---

## 4. Tool Reference

### 4.1 GitHub Extractor

`github_extractor_v2.py` — pulls from GitHub and writes to `github_export/`.

**What it extracts per repo:**
- Full metadata (stars, forks, topics, license, languages, fork parents)
- Complete directory tree (every file path + size)
- All text/documentation files (README + 30+ configurable extensions)
- All issues (open + closed) with comments and reactions

**Sources it can pull from:**

| Source | What | Needs token |
|---|---|---|
| `owned` | Your repos | ✅ |
| `forks` | Repos you forked | ✅ |
| `starred` | Repos you starred | ✅ |
| `trending` | GitHub Trending (daily/weekly/monthly, optionally by language) | ❌ |
| `collections` | GitHub-curated collections | ❌ |

**Key flags:**

```bash
# Authenticate
--token ghp_xxx                      # or set GITHUB_TOKEN env var

# Choose sources
--sources owned,trending             # comma-separated
--trending-langs python,rust         # filter trending by language
--collections-full                   # also scrape each collection's repo list

# Control what gets extracted
--skip-text-files                    # tree + metadata + issues only (fastest)
--skip-issues                        # skip issue extraction (~2x faster)
--text-extensions .graphql,.proto    # extra extensions to download

# Single repo mode
--repo torvalds/linux                # extract one specific repo

# Resume / scheduling
--resume                             # skip already-extracted repos
--schedule 6h                        # re-run automatically every 6h (or 1d, 30m …)
--output ./my_export                 # custom output directory

# Chain with platform extractor
--platform                           # run platform_extractor.py after finishing
--platform-sources hackernews,pypi   # only run these platform plugins
--searxng-url http://localhost:8888  # SearXNG meta-search side-channel
```

**Common usage patterns:**

```bash
# First-time full extraction
python github_extractor_v2.py --token ghp_xxx --sources owned,forks,starred,trending

# Fast trending-only (no token needed)
python github_extractor_v2.py --sources trending --trending-langs python,javascript

# Scheduled nightly run with platform discovery
python github_extractor_v2.py --token ghp_xxx --sources owned,trending --schedule 1d --platform

# One repo only
python github_extractor_v2.py --token ghp_xxx --repo microsoft/vscode

# Fastest: tree + metadata only, skip issues and text files
python github_extractor_v2.py --token ghp_xxx --skip-text-files --skip-issues
```

**HTML scraping:** Uses Scrapling by default (more resilient), falls back to BeautifulSoup.
Install the better backend with `pip install scrapling && scrapling install`.

---

### 4.2 Platform Extractor

`platform_extractor.py` — discovers GitHub repos via 10 external platforms. Writes into `github_export/_external_sources/`.

**Built-in plugins:**

| Plugin | Source | Auth | Lookback |
|---|---|---|---|
| `hackernews` | Algolia HN API — Show HN posts | None | ✅ |
| `paperswithcode` | ML papers with GitHub repos | None | ✅ |
| `npm` | Top/new npm packages | None | ✅ |
| `pypi` | PyPI newest packages | None | ❌ |
| `cratesio` | crates.io Rust packages | None | ✅ |
| `devto` | Dev.to project announcements | None | ✅ |
| `lobsters` | Lobsters link aggregator | None | ✅ |
| `reddit` | r/programming, r/rust, r/python etc. | None | ✅ |
| `thisweekrust` | This Week in Rust newsletter | None | ✅ |
| `searxng` | Meta-search side-channel | Self-hosted | ✅ |

**Two crawl modes:**

- **Forward scan** (`--mode forward`): fetches items newer than last seen. Fast. Run frequently.
- **Lookback scan** (`--mode lookback`): walks backward through history page by page. Run once.

**Key flags:**

```bash
--mode forward           # default: just fetch new items
--mode lookback          # advance the historical cursor
--mode both              # forward + lookback in one run
--sources hackernews,pypi,cratesio  # run specific plugins only
--list-sources           # show all plugins with health check
--check                  # run health checks on all plugins
--schedule 6h            # repeat every 6h
--floor-date 2023-01-01  # don't go further back than this date
--lookback-batch 50      # pages to advance per lookback run
--searxng-url http://localhost:8888
--output ./my_export     # custom output dir (must match extractor's)
```

**Common usage:**

```bash
# First run — forward scan all sources
python platform_extractor.py

# Daily update (fast)
python platform_extractor.py --mode forward --schedule 1d

# One-time deep history crawl
python platform_extractor.py --mode lookback --floor-date 2022-01-01

# Specific sources only
python platform_extractor.py --sources hackernews,paperswithcode,cratesio

# Health check
python platform_extractor.py --check
```

**Custom plugins:** Drop a `.py` file in the `sources/` folder that defines a class inheriting `SourcePlugin`. It is auto-discovered on the next run.

---

### 4.3 GitHub Viewer

`github_viewer_v2.py` — terminal browser for everything written by the extractor and platform extractor.

**Commands:**

```
(no args)                             Overall stats summary
list                                  All repos in a table
show    <owner__repo>                 Detailed info for one repo
text    <owner__repo> [ext]           Print text files (filter by extension)
readmes <owner__repo>                 Print READMEs only
issues  <owner__repo>                 Print all issues
tree    <owner__repo>                 Print directory tree
search  <keyword>                     Search names, descriptions, topics

trending [daily|weekly|monthly]       GitHub Trending results
trending weekly python                Weekly trending, Python only
collections                           List all scraped collections
collection <slug>                     Repos in one collection
sources                               Sources used in last extraction

external                              Summary of all external sources
external <source>                     Items from one source (e.g. hackernews)
external <source> <date>              Filter to specific date (e.g. 2026-05-27)
discoveries [keyword]                 Search across all external discoveries
discoveries --source <name>           Filter by source
discoveries --min-score <n>           Filter by minimum score
discoveries --history                 Search historical (lookback) items
ext-summary                           Compact stats table across all sources
```

**Examples:**

```bash
python github_viewer_v2.py                         # overall stats
python github_viewer_v2.py list                    # all repos
python github_viewer_v2.py show torvalds__linux    # one repo detail
python github_viewer_v2.py text torvalds__linux .md  # all .md files
python github_viewer_v2.py issues torvalds__linux  # issues
python github_viewer_v2.py search "machine learning"
python github_viewer_v2.py trending weekly python
python github_viewer_v2.py external hackernews
python github_viewer_v2.py discoveries pytorch --min-score 50
python github_viewer_v2.py ext-summary
```

> **Note:** Repo directory names use double-underscore (`owner__repo`), matching the on-disk folder name.

---

### 4.4 PIA — Project Intelligence Analyst

PIA is a local AI pipeline that analyses **your own projects** against a knowledge base of open-source patterns extracted via the GitHub Extractor.

#### How it works (5 phases)

```
Phase 1 — Ingest   Load exported README/docs into ChromaDB vector store
                   (incremental — only re-embeds new/changed files)
Phase 2 — Scan     Walk local project folders + fetch your GitHub repos
Phase 3 — Retrieve Semantically search KB for patterns relevant to each file
Phase 4 — Analyse  Send file + context to Claude Sonnet → get JSON findings
Phase 5 — Report   Generate per-project Markdown reports + master summary
```

#### PIA config.yaml

Edit `pia/config.yaml` (copy from `pia/config.yaml.example`):

```yaml
anthropic:
  api_key: "sk-ant-..."
  model: "claude-sonnet-4-20250514"
  max_tokens: 2000
  max_files_per_run: 60          # cost control

knowledge_base:
  source_dir: "/path/to/github_export"   # your extracted repos folder
  chroma_dir: "/path/to/pia-data/chroma" # where vector DB is stored
  embedding_model: "all-MiniLM-L6-v2"    # ~90MB, runs on CPU
  chunk_size: 800
  chunk_overlap: 100
  similarity_threshold: 0.35
  top_k_results: 6

projects:
  local:
    enabled: true
    roots:
      - "/path/to/your/projects"
  github:
    enabled: true
    username: "your-username"
    token: "ghp_..."
    include: "owned"
    exclude_repos: ["dotfiles"]
  colab:
    enabled: false
    credentials_file: "/path/to/gdrive-creds.json"
    colab_folder_id: "YOUR_DRIVE_FOLDER_ID"

scan:
  include_extensions: [".py",".js",".ts",".jsx",".tsx",".md",".yaml",".json"]
  exclude_dirs: ["node_modules",".git","dist","build","__pycache__",".venv"]
  max_file_size_kb: 200

reports:
  output_dir: "reports"
  include_raw_json: true
```

#### Running PIA

```bash
cd pia

# Full pipeline (first time or after adding new knowledge)
python scheduler/run_pipeline.py

# Only rebuild knowledge base (added new exported repos)
python scheduler/run_pipeline.py --ingest-only

# Skip re-ingest, re-analyse only (faster)
python scheduler/run_pipeline.py --scan-only

# Analyse one specific project
python scheduler/run_pipeline.py --project my-project-name

# Force a repo to be analysed even if PIA deems it ineligible
python scheduler/run_pipeline.py --force-eligible my-repo

# Skip intent analysis phase
python scheduler/run_pipeline.py --no-intent

# Skip comparison phase
python scheduler/run_pipeline.py --no-compare

# Compare to specific topic repos
python scheduler/run_pipeline.py --compare-topic "vector-database"

# Compare to specific repos
python scheduler/run_pipeline.py --compare-repos chromadb/chroma,qdrant/qdrant

# Skip benchmarking
python scheduler/run_pipeline.py --skip-benchmark

# Wipe and re-embed everything (DESTRUCTIVE)
python scheduler/run_pipeline.py --clear-kb

# Custom config file
python scheduler/run_pipeline.py --config /path/to/other-config.yaml

# Windows one-click
run.bat
```

#### PIA Reports

Reports are written to `reports/YYYY-MM-DD_HH-MM/`:

```
reports/
└── 2026-05-28_09-00/
    ├── 00_SUMMARY.md          ← start here: all projects at a glance
    ├── my-project.md          ← per-project deep dive
    └── raw_results.json       ← machine-readable full output
```

**Health Score formula:**
```
score = 100 − (12 × high_findings) − (5 × medium_findings) − (2 × low_findings)
```

| Score | Label |
|---|---|
| 85–100 | ✅ Healthy |
| 65–84 | ⚠️ Needs Attention |
| 0–64 | 🔴 Critical Issues |

**Finding categories:** Architecture · Error Handling · Performance · Security · Testing · DX/Tooling

#### Scheduled PIA (Windows)

Run `setup_scheduler.bat` as Administrator to register a weekly Task Scheduler job (Mondays at 09:00).

```bat
cd pia
setup_scheduler.bat    REM run as Administrator
```

---

## 5. Launcher — TUI

`launcher.py` is an interactive terminal menu that exposes all parameters from all tools.
Settings are auto-saved to `suite_config.json`.

```bash
python launcher.py        # interactive menu
```

Or pass a sub-command to skip the menu:

```bash
python launcher.py extract      # run GitHub extractor with saved config
python launcher.py platform     # run platform extractor
python launcher.py full         # chain both extractors
python launcher.py view stats   # viewer quick command
python launcher.py view trending weekly python
python launcher.py pia          # run PIA pipeline
```

**Windows bat wrappers:**

```bat
launcher.bat                    REM same as python launcher.py
launcher.bat extract
launcher.bat view trending weekly
launcher.bat pia
```

**Linux/macOS:**

```bash
./launcher.sh
./launcher.sh extract
./launcher.sh view trending weekly python
```

> **Rich library:** The TUI uses `rich` for coloured panels and prompts. If not installed, it falls back to plain text. Run `setup.bat` / `setup.sh` to install it.

---

## 6. GUI Application

`gui_app.py` is a 5-tab Tkinter GUI — no terminal required.

```bash
python gui_app.py
# or
run_gui.bat              # Windows double-click
```

**Tabs:**

| Tab | Contents |
|---|---|
| ⚙ Setup | GitHub token, output dir, SearXNG URL — saved to suite_config.json |
| ⬇ GitHub | All extractor flags: sources, languages, skip options, schedule |
| 🌐 Platform | Mode, sources, schedule, lookback settings |
| 🔍 View | Run any viewer command; results appear in the scrollable output pane |
| 🤖 PIA | PIA pipeline options; logs stream into the output pane |

Settings auto-save when you switch tabs or click Run.

---

## 7. Configuration Files

### suite_config.json

Central config for the extractor, platform extractor, viewer, and launcher/GUI.

```
suite_config.json        # your live config — git-ignored (contains token)
suite_config.json.example  # template to copy from
```

Edit by hand, or let the GUI/TUI manage it. Full schema:

| Section | Key | Default | Notes |
|---|---|---|---|
| `global` | `output_dir` | `github_export` | Shared by both extractors |
| `github_extractor` | `token` | `""` | Or `GITHUB_TOKEN` env var |
| `github_extractor` | `sources` | `["owned","forks","starred","trending"]` | |
| `github_extractor` | `trending_langs` | `""` | e.g. `"python,rust"` |
| `github_extractor` | `skip_text_files` | `false` | |
| `github_extractor` | `skip_issues` | `false` | |
| `github_extractor` | `resume` | `true` | Safe to re-run |
| `github_extractor` | `schedule` | `""` | e.g. `"6h"` or `"1d"` |
| `github_extractor` | `chain_platform` | `false` | Run platform extractor after |
| `platform_extractor` | `mode` | `"forward"` | `forward` / `lookback` / `both` |
| `platform_extractor` | `sources` | all 10 | Comma-separated list |
| `platform_extractor` | `floor_date` | `"2024-01-01"` | Don't go further back |
| `pia` | `ingest_only` | `false` | |
| `pia` | `scan_only` | `false` | |
| `pia` | `project` | `""` | Analyse one project only |
| `pia` | `clear_kb` | `false` | ⚠ destructive — wipes ChromaDB |
| `viewer` | `trending_period` | `"daily"` | Saves last-used period |

### pia/config.yaml

PIA's own config. See [Section 4.4](#44-pia--project-intelligence-analyst) for the full schema.

```
pia/config.yaml            # your live config — git-ignored (contains API key)
pia/config.yaml.example    # template to copy from
```

---

## 8. Scheduling

### Built-in scheduler (all tools)

All three Python tools support `--schedule`:

```bash
python github_extractor_v2.py --token ghp_xxx --schedule 6h
python platform_extractor.py --schedule 1d
```

Format: `30m`, `6h`, `1d`, `2d12h`, etc. Press Ctrl+C to stop.

### Windows Task Scheduler (PIA)

```bat
cd pia
setup_scheduler.bat    REM run as Administrator
```

Registers a weekly task: every Monday at 09:00.
Logs go to `pia/scheduler.log`.

### Linux cron (PIA)

```bash
# Run PIA every Monday at 09:00
0 9 * * 1 cd /path/to/github-intelligence-suite/pia && /usr/bin/python3 scheduler/run_pipeline.py >> logs/pia.log 2>&1

# Run extractor + platform every 6 hours
0 */6 * * * cd /path/to/github-intelligence-suite && python github_extractor_v2.py --token $GITHUB_TOKEN --sources owned,trending --platform >> logs/extractor.log 2>&1
```

---

## 9. Building a Standalone EXE

Package the GUI into a standalone Windows executable that doesn't require Python:

```bat
build_exe.bat
```

Output: `dist/GithubIntelSuite/` — copy the whole folder, double-click `GithubIntelSuite.exe`.

Requires PyInstaller: `pip install pyinstaller`.

---

## 10. Output Structure

All extraction output goes to `github_export/` (configurable via `output_dir`):

```
github_export/
├── _index.json                    Master index of all extracted repos
│
├── _trending/
│   ├── daily.json                 GitHub Trending today (all languages)
│   ├── daily_python.json          Today's Python trending
│   ├── weekly.json
│   └── monthly.json
│
├── _collections/
│   ├── _index.json
│   └── clean-code.json            Repos in that collection
│
├── _external_sources/             Written by platform_extractor
│   ├── hackernews/
│   │   ├── forward/
│   │   │   └── 2026-05-28.json    Today's HN discoveries
│   │   └── history/
│   │       └── page_001.json
│   ├── pypi/
│   ├── npm/
│   └── ...
│
├── _state/
│   └── crawl_state.json           Platform extractor cursor state
│
└── owner__reponame/               One folder per extracted repo
    ├── metadata.json              Full repo metadata
    ├── directory_tree.txt         Human-readable file tree
    ├── directory_tree.json        Machine-readable tree
    ├── issues.json                All issues + comments
    ├── text_files/
    │   ├── _index.json
    │   ├── README.md
    │   └── docs__guide.md         Nested paths use __ separator
    └── readmes/
        ├── _index.json
        └── README.md
```

PIA report output:

```
reports/
└── 2026-05-28_09-00/
    ├── 00_SUMMARY.md
    ├── my-project.md
    └── raw_results.json
```

---

## 11. Troubleshooting

| Symptom | Cause | Fix |
|---|---|---|
| `Python not found` | Not on PATH | Reinstall Python, tick "Add to PATH" |
| `No module named rich` | setup not run | Run `setup.bat` / `bash setup.sh` |
| `No module named github` | setup not run | `pip install PyGithub` |
| `No module named scrapling` | optional dep | `pip install scrapling && scrapling install` |
| Trending returns 0 repos | GitHub HTML changed | Update scrapling: `pip install -U scrapling` |
| PIA: `No module named chromadb` | PIA deps not installed | `cd pia && pip install -r requirements.txt` |
| PIA: torch install hangs | Slow connection | `pip install torch --index-url https://download.pytorch.org/whl/cpu` |
| PIA: `api_key` auth error | Wrong key in config.yaml | Check `pia/config.yaml` → `anthropic.api_key` |
| PIA: no projects found | Wrong `roots` path | Check `pia/config.yaml` → `projects.local.roots` |
| `pia/` not found | Wrong working dir | Run from repo root, not from inside `pia/` |
| GitHub 401 error | Bad token | Regenerate at github.com/settings/tokens |
| GitHub 403 / rate limit | Too many requests | Add `--schedule 6h` or wait for reset |
| `DevToolsActivePort` error | Browser automation issue | Unrelated to this tool — check your other processes |

---

## 12. FAQ

See `FAQ.md` for long-form worked examples including:
- First-time full setup walkthrough
- Running the suite on a low-spec laptop
- Adding a custom platform plugin
- Using PIA with a shared team knowledge base
- Exporting to a standalone EXE for non-technical colleagues

---

## Environment Variables

All secrets can be passed via environment variables instead of config files:

```bash
export GITHUB_TOKEN="ghp_..."          # used by github_extractor_v2.py
export ANTHROPIC_API_KEY="sk-ant-..."  # optional — pia/config.yaml takes precedence
```

---

## System Requirements Summary

| Component | RAM | Disk | Internet |
|---|---|---|---|
| Extractor + Viewer | ~200 MB | ~50 MB + output | GitHub API |
| Platform Extractor | ~200 MB | ~10 MB + output | Various APIs |
| PIA (first install) | 4 GB+ | ~1.5 GB (PyTorch) | Anthropic API |
| PIA (subsequent runs) | 4 GB | ~200 MB/run | Anthropic API |

Tested on: Windows 10/11, Ubuntu 22.04, macOS 13+.  
Python 3.10, 3.11, 3.12 all work.
