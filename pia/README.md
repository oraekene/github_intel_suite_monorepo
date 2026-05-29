# PIA — Project Intelligence Analyst

> A local AI pipeline that deeply analyses your own software projects against a curated library of open-source patterns — and tells you exactly how to improve them, with source attribution.

---

## What It Does

PIA runs a five-phase pipeline on a schedule:

1. **Ingest** — Loads all your exported GitHub README / docs files into a local vector database (ChromaDB). Runs incrementally — only re-embeds changed files.
2. **Scan** — Recursively walks your local project folders, fetches files from your own GitHub repos, and optionally downloads Google Colab notebooks.
3. **Retrieve** — For each file in your projects, semantically searches the knowledge base for the most relevant open-source patterns.
4. **Analyse** — Sends each file + its retrieved context to Claude Sonnet. Gets structured improvement findings back in JSON.
5. **Report** — Generates a per-project Markdown report and a master summary, including health scores, severity tiers, source attribution, and collapsible code suggestions.

---

## System Requirements

| Requirement | Minimum |
|-------------|---------|
| OS          | Windows 10 |
| Python      | 3.10+ |
| RAM         | 4 GB (8 GB recommended) |
| Disk        | ~1 GB for model + ChromaDB |
| Internet    | Required for API calls |

Works on a Core i3 HP Pavilion with 12 GB RAM. Embedding runs on CPU.

---

## Installation

### Step 1 — Install Python

Download Python 3.10 or later from https://python.org  
✅ Tick **"Add Python to PATH"** during installation.

### Step 2 — Copy PIA to your machine

Put the `pia/` folder anywhere on your laptop, e.g.:
```
C:\Users\YourName\Documents\pia\
```

### Step 3 — Edit config.yaml

Open `config.yaml` in any text editor. Fill in every value marked `<REPLACE_THIS>`:

```yaml
anthropic:
  api_key: "sk-ant-..."          # Your Anthropic API key

knowledge_base:
  source_dir: "C:/Users/YourName/Documents/pia-knowledge"  # Your exported files

projects:
  local:
    roots:
      - "C:/Users/YourName/Projects"    # Your local project parent folder

  github:
    username: "your-github-username"
    token: "ghp_..."                    # GitHub personal access token
```

**Getting an Anthropic API key:**  
→ https://console.anthropic.com → API Keys → Create Key

**Getting a GitHub token:**  
→ GitHub → Settings → Developer settings → Personal access tokens → Fine-grained  
→ Permissions needed: `Contents: Read`, `Metadata: Read`

### Step 4 — Run setup

Double-click `setup.bat` or run in Command Prompt:
```bat
cd C:\Users\YourName\Documents\pia
setup.bat
```

This installs all Python packages (~10 minutes first time, mostly PyTorch download).

### Step 5 — Test your setup

```bat
cd C:\Users\YourName\Documents\pia
.venv\Scripts\activate
python test_setup.py
```

All tests should pass before your first full run.

---

## Running PIA

### Manual run (Command Prompt)

```bat
cd C:\Users\YourName\Documents\pia
run.bat
```

Or with options:
```bat
.venv\Scripts\activate

# Full pipeline (recommended first time)
python scheduler\run_pipeline.py

# Only rebuild knowledge base (after adding new exported files)
python scheduler\run_pipeline.py --ingest-only

# Skip re-ingest, just re-analyse projects (faster)
python scheduler\run_pipeline.py --scan-only

# Analyse one specific project
python scheduler\run_pipeline.py --project solarsizer-pro

# Wipe and re-embed everything from scratch
python scheduler\run_pipeline.py --clear-kb
```

### Scheduled weekly run (Windows Task Scheduler)

Run **as Administrator**:
```bat
setup_scheduler.bat
```

This registers a weekly task that runs every Monday at 09:00.  
PIA will run silently in the background and write reports to your configured output folder.

---

## Knowledge Base Setup

Your knowledge base should be a folder containing all the README / docs files you exported from GitHub (via NotebookLM or directly).

**Recommended structure:**
```
pia-knowledge/
├── langchain/
│   └── README.md
├── fastapi/
│   ├── README.md
│   └── CONTRIBUTING.md
├── chromadb/
│   └── README.md
...
```

Each sub-folder name becomes the "source repo" cited in improvement findings.

**Adding new repos:**  
Drop new files/folders into the knowledge base directory and run:
```bat
python scheduler\run_pipeline.py --ingest-only
```
PIA only re-embeds new/changed files.

---

## Reading Reports

Reports are saved to your configured `reports.output_dir`, organised by run date:

```
reports/
└── 2026-05-26_09-00/
    ├── 00_SUMMARY.md          ← Start here: all projects at a glance
    ├── solarsizer-pro.md
    ├── opencode-intelligence.md
    └── raw_results.json       ← Machine-readable full output
```

### Health Score

```
100 - (12 × high_findings) - (5 × medium_findings) - (2 × low_findings)
```

| Score | Label |
|-------|-------|
| 85–100 | ✅ Healthy |
| 65–84  | ⚠️ Needs Attention |
| 0–64   | 🔴 Critical Issues |

### Finding Categories

| Category | What it checks |
|----------|----------------|
| 🏗️ Architecture | Project structure, separation of concerns, design patterns |
| 🛡️ Error Handling | Missing try/catch, unhandled promises, no fallbacks |
| ⚡ Performance | N+1 queries, unnecessary re-renders, missing caching |
| 🔒 Security | Exposed secrets, missing auth checks, SQL injection risk |
| 🧪 Testing | Missing tests, no test setup, low coverage patterns |
| 🛠️ DX / Tooling | Missing linters, no CI, dependency management |
| 📝 Documentation | Missing docstrings, no README, unclear function names |
| ✨ Code Quality | Dead code, duplicated logic, long functions |

---

## Colab Notebooks Setup (Optional)

To include Google Colab notebooks:

1. Go to https://console.cloud.google.com → Create Project → Enable **Google Drive API**
2. Create a Service Account → Download JSON key
3. Share your Colab folder with the service account's email address
4. In `config.yaml`:
   ```yaml
   colab:
     enabled: true
     credentials_file: "C:/Users/YourName/Documents/pia-data/gdrive-creds.json"
     colab_folder_id: "your-drive-folder-id"
   ```

---

## Cost Estimate

PIA uses the Claude Sonnet API per file analysed.

| Run size | Approx. API cost |
|----------|-----------------|
| 20 files | ~$0.05–$0.10 |
| 60 files | ~$0.15–$0.30 |
| 100 files | ~$0.30–$0.60 |

Control cost with `anthropic.max_files_per_run` in config.yaml.  
The embedding model (sentence-transformers) runs **fully locally** — no API cost.

---

## Troubleshooting

**"Knowledge base dir not found"**  
→ Check `knowledge_base.source_dir` in config.yaml matches your actual folder path. Use forward slashes or double backslashes on Windows.

**"No project files found"**  
→ Check `projects.local.roots` — each path should be the PARENT folder containing individual project sub-folders.

**PyTorch install is slow / fails**  
→ Run manually: `pip install torch --index-url https://download.pytorch.org/whl/cpu`

**GitHub scan returns 0 files**  
→ Verify your token has `Contents: Read` permission. Test with: `curl -H "Authorization: token YOUR_TOKEN" https://api.github.com/user`

**Out of memory during embedding**  
→ Reduce `knowledge_base.chunk_size` in config.yaml to `400` and restart.

---

## File Structure

```
pia/
├── config.yaml              # All configuration
├── requirements.txt         # Python dependencies
├── utils.py                 # Shared utilities
├── test_setup.py            # Pre-flight checks
├── setup.bat                # One-click Windows installer
├── run.bat                  # Run script (manual or scheduled)
├── setup_scheduler.bat      # Register Windows Task Scheduler job
│
├── ingest/
│   ├── loader.py            # Load knowledge base files from disk
│   ├── chunker.py           # Token-aware text chunking
│   └── vectorstore.py       # ChromaDB embed + persist + query
│
├── scan/
│   ├── local_scanner.py     # Recursive local project walker
│   ├── github_scanner.py    # GitHub REST API scanner
│   └── colab_scanner.py     # Google Drive API for .ipynb
│
├── analysis/
│   ├── retriever.py         # Semantic context retrieval
│   └── llm_analyzer.py      # Claude Sonnet analysis engine
│
├── report/
│   └── generator.py         # Markdown report builder
│
└── scheduler/
    └── run_pipeline.py      # Master pipeline orchestrator
```

---

## v2 — New Features

### 🎯 Intent Gap Analysis (`analysis/intent_analyzer.py`)

Goes beyond code review to understand *what each function is trying to do*, then surfaces:

- **Missing sub-functions** — helpers, validation, and guard clauses that are implied by the function's purpose but absent from the code
- **Missing project-level features** — cross-cutting concerns the project needs but doesn't yet have (e.g. a project that manages user data but has no audit log)
- **Architectural alternatives** — when a KB project demonstrates a fundamentally better approach to the same problem, PIA sketches it out with trade-offs

Enable/disable in `config.yaml → intent_analysis.enabled`.

**CLI:** `python scheduler/run_pipeline.py --no-intent` to skip for a cheaper run.

---

### 🏗️ Whole-Project Profiling (`analysis/project_profiler.py`)

Before per-file analysis, PIA builds a concise intent profile of each project by sampling its most representative files. This profile is injected into every subsequent analysis call, so per-file suggestions are always contextualised against the project's actual goals and tech stack.

Enable/disable: `config.yaml → intent_analysis.build_project_profile`.

---

### ⚖️ Multi-Approach Comparisons (`analysis/comparator.py`)

Discovers and compares how multiple KB projects solve the same problem.  For each comparison topic:

1. Retrieves all relevant KB chunks, grouped by source repo
2. Produces a structured side-by-side analysis across technical dimensions
3. Delivers an opinionated **verdict** with rationale and caveats

**Two modes:**
- **Scheduled topics** — define topics in `config.yaml → comparison.scheduled_topics` to always compare on every run
- **Auto-detect** — set `comparison.auto_detect: true` to automatically surface comparisons per-file where ≥2 KB repos are relevant (adds API cost)

**CLI:**
```
# One-off comparison on a specific topic
python scheduler/run_pipeline.py --compare-topic "rate limiting strategies"

# Pin specific KB repos to always include
python scheduler/run_pipeline.py --compare-repos "repo-a,repo-b"
```

**User override:** In `config.yaml → comparison.pinned_repos`, list repo names to always include in scheduled comparisons.

---

### 🧩 Constraints (`analysis/constraints.py` + `config.yaml → constraints`)

Fills in your real-world context so PIA never suggests solutions that are impractical for your situation.

Configure under `config.yaml → constraints`:

| Section | What it controls |
|---------|-----------------|
| `dev_device` | Your laptop hardware (CPU, RAM, storage) |
| `target_user_device` | Who will run the software (desktop, mobile, server…) |
| `performance` | Response time, memory, throughput targets |
| `deployment` | Local, VPS, Docker, serverless, offline-capable |
| `security` | Auth method, data classification, compliance requirements |
| `team` | Solo / small / large, experience level, tech-debt tolerance |
| `compatibility` | Min Python/Node version, browser targets |
| `licensing` | Project license, allowed dependency licenses |
| `accessibility` | WCAG level, supported languages |
| `budget` | Monthly infra / API cost ceiling |
| `additional_notes` | Any other constraints in free text |

Other constraints worth noting in `additional_notes`:
- **Regulatory:** GDPR, HIPAA, PCI-DSS, SOC 2, NDPR, ISO 27001
- **Observability:** logging, metrics, tracing requirements
- **Data residency:** where data must physically reside
- **Disaster recovery:** backup frequency, RTO/RPO
- **Backward compatibility:** whether you can break existing APIs
- **Offline / unreliable networks** (important for Nigerian context)

---

### ✍️ User Guidance Prompts (`user_prompts.yaml`)

A YAML file where you tell PIA your personal preferences, architectural decisions you've already made, and things to always flag or ignore.

Sections: `general`, `code_review`, `intent_analysis`, `comparison`, `always_flag`, `always_ignore`.

Applied to every analysis call — no restart needed between edits.

---

### Updated CLI flags

```
--no-intent       Skip intent gap analysis (saves ~40% of API cost per run)
--no-compare      Skip comparison engine
--compare-topic   Run a one-off named comparison, e.g. "authentication flow"
--compare-repos   Pin specific KB repos for this run's comparisons
```

---

### Updated folder structure

```
pia/
├── config.yaml              ← Now includes intent, comparison, constraints, user_prompts
├── user_prompts.yaml        ← NEW: your personal guidance, injected into all calls
├── analysis/
│   ├── llm_analyzer.py      ← Updated: respects constraints + user prompts
│   ├── intent_analyzer.py   ← NEW: deep intent + gap analysis
│   ├── project_profiler.py  ← NEW: whole-project intent model
│   ├── comparator.py        ← NEW: multi-approach comparison engine
│   ├── constraints.py       ← NEW: reads + formats constraint block
│   ├── user_prompts_loader.py ← NEW: loads + merges user guidance
│   ├── retriever.py
│   └── __init__.py
├── report/
│   └── generator.py         ← Updated: intent + comparison sections in reports
└── scheduler/
    └── run_pipeline.py      ← Updated: all new phases wired in
```
