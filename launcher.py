#!/usr/bin/env python3
"""
GitHub Intelligence Suite — TUI Launcher  (v2)
================================================
All parameters from all 4 tools exposed.
Settings auto-loaded from suite_config.json and optionally saved back.

Usage:
  python launcher.py            # interactive menu
  python launcher.py extract    # run full extraction with saved config
  python launcher.py platform   # run platform extractor
  python launcher.py view stats # viewer quick command
  python launcher.py pia        # run PIA pipeline
"""

from __future__ import annotations
import os, sys, subprocess
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from config_manager import ConfigManager, PLATFORM_SOURCES, GH_SOURCES_ALL, cfg as _boot_cfg  # noqa: F401

try:
    from rich.console import Console
    from rich.panel   import Panel
    from rich.table   import Table
    from rich.prompt  import Prompt, Confirm
    from rich.rule    import Rule
    from rich         import box as rbox
    HAS_RICH = True
    console  = Console()
except ImportError:
    HAS_RICH = False
    console  = None

HERE         = Path(__file__).resolve().parent
EXTRACTOR    = HERE / "github_extractor_v2.py"
PLATFORM     = HERE / "platform_extractor.py"
VIEWER       = HERE / "github_viewer_v2.py"
PIA_DIR      = HERE / "pia"
PIA_PIPELINE = PIA_DIR / "scheduler" / "run_pipeline.py"
PIA_CONFIG   = PIA_DIR / "config.yaml"

cfg = ConfigManager()   # launcher gets its own instance

# ── output helpers ────────────────────────────────────────────────────────────
def p(msg=""):       print(msg)
def info(m):  (console.print(f"  [cyan]ℹ  {m}[/cyan]")  if HAS_RICH else print(f"  ℹ  {m}"))
def ok(m):    (console.print(f"  [green]✓  {m}[/green]") if HAS_RICH else print(f"  ✓  {m}"))
def warn(m):  (console.print(f"  [yellow]⚠  {m}[/yellow]") if HAS_RICH else print(f"  ⚠  {m}"))
def err(m):   (console.print(f"  [red]✗  {m}[/red]")    if HAS_RICH else print(f"  ✗  {m}"))
def rule(t=""): (console.print(Rule(t, style="dim")) if HAS_RICH else print("  " + "─"*50))

def ask(prompt: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    if HAS_RICH:
        return Prompt.ask(f"  [yellow]{prompt}[/yellow]", default=default or "")
    val = input(f"  {prompt}{hint}: ").strip()
    return val if val else default

def ask_bool(prompt: str, default: bool = False) -> bool:
    cur = "Y/n" if default else "y/N"
    if HAS_RICH:
        return Confirm.ask(f"  [yellow]{prompt}[/yellow]", default=default)
    v = input(f"  {prompt} [{cur}]: ").strip().lower()
    return (v.startswith("y") if v else default)

def header():
    if HAS_RICH:
        console.print()
        console.print(Panel.fit(
            "[bold cyan]GitHub Intelligence Suite[/bold cyan]  [dim]v2[/dim]\n"
            "[dim]Extract · Discover · Analyse · Report[/dim]",
            border_style="cyan", padding=(0, 4)))
        console.print(f"  [dim]Config: {cfg._path}[/dim]")
        console.print()
    else:
        print("\n" + "═"*54)
        print("  GitHub Intelligence Suite  v2")
        print("═"*54)

def main_menu():
    if HAS_RICH:
        t = Table(show_header=False, box=rbox.SIMPLE, padding=(0, 2))
        t.add_column("key", style="bold yellow", width=4)
        t.add_column("label")
        t.add_column("note", style="dim", width=48)
        rows = [
            ("", "[bold cyan]── EXTRACT ──────────────────────────────────────────────[/bold cyan]", ""),
            ("1", "GitHub Extractor",         "owned/forks/starred/trending/collections + advanced"),
            ("2", "Platform Extractor",        "hackernews·pypi·npm·cratesio·devto·lobsters·reddit+3"),
            ("3", "Full Extraction  (1→2)",    "chain both with current config"),
            ("", "[bold cyan]── VIEW ─────────────────────────────────────────────────[/bold cyan]", ""),
            ("4", "Stats overview",            "summary of last extraction"),
            ("5", "Trending",                  "period + language filter"),
            ("6", "List repos",                "full repo table"),
            ("7", "Search repos",              "keyword search"),
            ("8", "Inspect repo",              "show / text-files / readmes / issues / tree"),
            ("9", "External sources",          "browse platform extractor output + date filter"),
            ("d", "Discoveries",               "all filters: keyword · source · min-score · history"),
            ("e", "Ext summary",               "cross-source stats table"),
            ("V", "Custom viewer command",     "enter any viewer subcommand"),
            ("", "[bold cyan]── PIA ──────────────────────────────────────────────────[/bold cyan]", ""),
            ("P", "Run PIA pipeline",          "all options from config"),
            ("i", "Ingest only",               "--ingest-only"),
            ("n", "Scan only",                 "--scan-only"),
            ("C", "Compare topic",             "--compare-topic  (one-off)"),
            ("k", "Clear KB + re-embed",       "--clear-kb  ⚠ destructive"),
            ("R", "Open reports folder",       ""),
            ("", "[bold cyan]── TOOLS ────────────────────────────────────────────────[/bold cyan]", ""),
            ("L", "Platform: list plugins",    "--list-sources"),
            ("H", "Platform: health check",   "--check"),
            ("c", "Edit config.yaml  (PIA)",   "open in $EDITOR"),
            ("s", "Setup / install deps",      "pip install all requirements"),
            ("cfg","Show current config",      "print suite_config.json"),
            ("q", "Quit", ""),
        ]
        for key, label, note in rows:
            t.add_row(key, label, note)
        console.print(Panel(t, title="[bold]Menu[/bold]", border_style="dim"))
    else:
        print("  EXTRACT")
        for k, l in [("1","GitHub Extractor"),("2","Platform Extractor"),("3","Full (1→2)")]:
            print(f"  [{k}] {l}")
        print("  VIEW")
        for k, l in [("4","Stats"),("5","Trending"),("6","List repos"),("7","Search"),
                     ("8","Inspect repo"),("9","External sources"),("d","Discoveries"),
                     ("e","Ext summary"),("V","Custom viewer command")]:
            print(f"  [{k}] {l}")
        print("  PIA")
        for k, l in [("P","Run PIA"),("i","Ingest only"),("n","Scan only"),
                     ("C","Compare topic"),("k","Clear KB"),("R","Open reports")]:
            print(f"  [{k}] {l}")
        print("  TOOLS")
        for k, l in [("L","List plugins"),("H","Health check"),("c","Edit config.yaml"),
                     ("s","Setup"),("cfg","Show config"),("q","Quit")]:
            print(f"  [{k}] {l}")


# ── subprocess runner ─────────────────────────────────────────────────────────
def run(cmd: list, cwd: Path = HERE) -> int:
    rule()
    display = " ".join(str(c) for c in cmd)
    if HAS_RICH: console.print(f"  [dim]$ {display}[/dim]")
    else:        print(f"  $ {display}")
    rule()
    env = {**os.environ, "EXPORT_DIR": cfg.output_dir()}
    try:
        return subprocess.run([str(c) for c in cmd], cwd=str(cwd), env=env).returncode
    except KeyboardInterrupt:
        warn("Interrupted.")
        return 1
    except FileNotFoundError as exc:
        err(str(exc)); return 2


def check(path: Path, name: str) -> bool:
    if not path.exists():
        warn(f"{name} not found at: {path}")
        warn("Place it in the same folder as launcher.py")
        return False
    return True


# ── SECTION: prompt helpers (read from config, let user override) ─────────────
def _ask_overriding(section: str, key: str, label: str, hint: str = "") -> str:
    default = str(cfg.get(section, key) or "")
    if hint:
        info(hint)
    return ask(label, default)

def _ask_bool_overriding(section: str, key: str, label: str) -> bool:
    default = bool(cfg.get(section, key))
    return ask_bool(label, default)

def _prompt_save(changes: dict, section: str):
    """Offer to persist changes back to suite_config.json."""
    if not changes:
        return
    if ask_bool("Save these settings to suite_config.json for future runs?", False):
        for k, v in changes.items():
            cfg.set(section, k, v)
        cfg.save()
        ok("Saved.")


# ══════════════════════════════════════════════════════════════════════════════
# ACTIONS
# ══════════════════════════════════════════════════════════════════════════════

def action_github():
    if not check(EXTRACTOR, "github_extractor_v2.py"): return
    rule("GitHub Extractor — settings")
    changes = {}

    # sources
    cur_sources = cfg.get("github_extractor", "sources") or []
    info(f"Available: {', '.join(GH_SOURCES_ALL)}")
    raw = ask("Sources (comma-separated)", ",".join(cur_sources))
    sources = [s.strip() for s in raw.split(",") if s.strip()]
    changes["sources"] = sources

    # per-source extras
    single_repo = ask("Single repo override (owner/repo, blank = use sources)", cfg.get("github_extractor","repo") or "")
    if single_repo: changes["repo"] = single_repo

    if "trending" in sources:
        langs = ask("Trending languages (blank = all)", cfg.get("github_extractor","trending_langs") or "")
        changes["trending_langs"] = langs

    if "collections" in sources:
        full = ask_bool("Collections full (scrape each collection's repo list)?",
                        cfg.get("github_extractor","collections_full"))
        changes["collections_full"] = full

    # content
    rule("Content")
    skip_txt  = ask_bool("Skip text files?",  cfg.get("github_extractor","skip_text_files"))
    changes["skip_text_files"] = skip_txt
    if not skip_txt:
        exts = ask("Extra file extensions to extract (blank = none)", cfg.get("github_extractor","text_extensions") or "")
        changes["text_extensions"] = exts
    skip_iss = ask_bool("Skip issues?", cfg.get("github_extractor","skip_issues"))
    changes["skip_issues"] = skip_iss

    # behaviour
    rule("Behaviour")
    resume   = ask_bool("Resume (skip already-extracted repos)?", cfg.get("github_extractor","resume"))
    changes["resume"] = resume
    schedule = ask("Schedule (e.g. 6h, 1d; blank = once)", cfg.get("github_extractor","schedule") or "")
    changes["schedule"] = schedule
    searxng  = ask("SearXNG URL (blank = disabled)", cfg.get("github_extractor","searxng_url") or "")
    changes["searxng_url"] = searxng

    # chain
    chain = ask_bool("Chain → Platform Extractor afterwards?", cfg.get("github_extractor","chain_platform"))
    changes["chain_platform"] = chain
    if chain:
        pf = ask("Platform sources filter (blank = all)", cfg.get("github_extractor","platform_sources_filter") or "")
        changes["platform_sources_filter"] = pf

    # build & run
    token = (cfg.get("github_extractor","token") or "").strip() or os.environ.get("GITHUB_TOKEN","")
    if not token:
        token = ask("GitHub token (blank = use GITHUB_TOKEN env)", "")
        if token: changes["token"] = token

    # temporarily apply changes for cmd building
    saved = {}
    for k, v in changes.items():
        saved[k] = cfg.get("github_extractor", k)
        cfg.set("github_extractor", k, v)

    cmd = cfg.build_github_cmd(sys.executable, EXTRACTOR)

    # restore
    for k, v in saved.items():
        cfg.set("github_extractor", k, v)

    run(cmd)
    _prompt_save(changes, "github_extractor")


def action_platform():
    if not check(PLATFORM, "platform_extractor.py"): return
    rule("Platform Extractor — settings")
    changes = {}

    mode = ask("Mode (forward / lookback / both)", cfg.get("platform_extractor","mode") or "forward")
    changes["mode"] = mode

    cur = cfg.get("platform_extractor","sources") or PLATFORM_SOURCES
    info(f"Available plugins: {', '.join(PLATFORM_SOURCES)}")
    raw = ask("Sources (comma-separated, blank = all enabled)", ",".join(cur))
    sources = [s.strip() for s in raw.split(",") if s.strip()] or list(PLATFORM_SOURCES)
    changes["sources"] = sources

    schedule = ask("Schedule (e.g. 6h; blank = once)", cfg.get("platform_extractor","schedule") or "")
    changes["schedule"] = schedule

    floor    = ask("Floor date (YYYY-MM-DD)", cfg.get("platform_extractor","floor_date") or "2024-01-01")
    changes["floor_date"] = floor

    batch    = ask("Lookback batch size", str(cfg.get("platform_extractor","lookback_batch") or 50))
    try:    changes["lookback_batch"] = int(batch)
    except: pass

    searxng  = ask("SearXNG URL (blank = disabled)", cfg.get("platform_extractor","searxng_url") or "")
    changes["searxng_url"] = searxng

    config_y = ask("Custom config.yaml path (blank = default)", cfg.get("platform_extractor","config_yaml") or "")
    changes["config_yaml"] = config_y

    saved = {}
    for k, v in changes.items():
        saved[k] = cfg.get("platform_extractor", k)
        cfg.set("platform_extractor", k, v)

    cmd = cfg.build_platform_cmd(sys.executable, PLATFORM)

    for k, v in saved.items():
        cfg.set("platform_extractor", k, v)

    run(cmd)
    _prompt_save(changes, "platform_extractor")


def action_full():
    if not check(EXTRACTOR, "github_extractor_v2.py"): return
    if not check(PLATFORM,  "platform_extractor.py"):  return
    rule("Full Extraction — using saved config")
    info("Runs GitHub Extractor → Platform Extractor in sequence.")
    info("Edit settings via menu options 1 and 2, or use the GUI.")
    saved_chain = cfg.get("github_extractor","chain_platform")
    cfg.set("github_extractor","chain_platform", True)
    cmd = cfg.build_github_cmd(sys.executable, EXTRACTOR)
    cfg.set("github_extractor","chain_platform", saved_chain)
    run(cmd)


def action_view_trending():
    rule("Trending")
    period = ask("Period (daily/weekly/monthly)", cfg.get("viewer","trending_period") or "daily")
    lang   = ask("Language filter (blank = all)", cfg.get("viewer","trending_lang") or "")
    cfg.set("viewer","trending_period", period)
    cfg.set("viewer","trending_lang", lang)
    args = ["trending", period] + ([lang] if lang else [])
    run([sys.executable, str(VIEWER)] + args)


def action_inspect_repo():
    rule("Inspect repo")
    repo = ask("Repo name (owner__repo format)")
    if not repo: return
    info("Commands: show · text · readmes · issues · tree")
    cmd_name = ask("Command", "show")
    args = [cmd_name, repo]
    if cmd_name == "text":
        ext = ask("Extension filter (e.g. .py, blank = all)", cfg.get("viewer","text_ext_filter") or "")
        if ext:
            args.append(ext)
            cfg.set("viewer","text_ext_filter", ext)
    run([sys.executable, str(VIEWER)] + args)


def action_external():
    rule("External sources")
    src  = ask("Source name (blank = all)", cfg.get("viewer","external_source") or "")
    date = ask("Date filter YYYY-MM-DD (blank = latest)", cfg.get("viewer","external_date") or "")
    cfg.set("viewer","external_source", src)
    cfg.set("viewer","external_date",   date)
    args = ["external"] + ([src] if src else []) + ([date] if date else [])
    run([sys.executable, str(VIEWER)] + args)


def action_discoveries():
    rule("Discoveries")
    kw    = ask("Keyword (blank = all)")
    src   = ask("Source filter (e.g. hackernews; blank = all)", cfg.get("viewer","discoveries_source") or "")
    score = ask("Min score (0 = no filter)", str(cfg.get("viewer","discoveries_min_score") or 0))
    hist  = ask_bool("Use history (lookback) data?", cfg.get("viewer","discoveries_history") or False)

    cfg.set("viewer","discoveries_source",   src)
    cfg.set("viewer","discoveries_history",  hist)
    try:   cfg.set("viewer","discoveries_min_score", int(score))
    except: pass

    args = ["discoveries"]
    if kw:    args.append(kw)
    disc_args = cfg.build_discoveries_args()
    run([sys.executable, str(VIEWER)] + args + disc_args)


def action_pia(overrides: dict | None = None):
    if not PIA_DIR.exists():
        warn(f"pia/ not found at: {PIA_DIR}"); return
    rule("PIA Pipeline")
    changes = {}

    if overrides:
        changes.update(overrides)
    else:
        # Full interactive config
        project = ask("Project (partial match, blank = all)", cfg.get("pia","project") or "")
        changes["project"] = project

        force_elig = ask("Force eligible repo (blank = none)", cfg.get("pia","force_eligible") or "")
        changes["force_eligible"] = force_elig

        rule("Analysis options")
        changes["no_intent"]     = ask_bool("Skip intent gap analysis? (saves API cost)", cfg.get("pia","no_intent"))
        changes["no_compare"]    = ask_bool("Skip comparison engine?   (saves API cost)", cfg.get("pia","no_compare"))
        changes["skip_benchmark"]= ask_bool("Skip Phase 1.5 benchmarking?",               cfg.get("pia","skip_benchmark"))

        if not changes["no_compare"]:
            ct = ask("Compare topic (blank = use config)", cfg.get("pia","compare_topic") or "")
            changes["compare_topic"] = ct
            cr = ask("Pin comparison repos (comma-sep; blank = auto)", cfg.get("pia","compare_repos") or "")
            changes["compare_repos"] = cr

        rule("Advanced")
        cfg_yaml = ask("Custom config.yaml path (blank = pia/config.yaml)", cfg.get("pia","config_yaml") or "")
        changes["config_yaml"] = cfg_yaml

        clear = ask_bool("⚠  Clear KB (wipe vector store)?", False)
        if clear and not ask_bool("   Confirm: this is DESTRUCTIVE. Are you sure?", False):
            clear = False
        changes["clear_kb"] = clear

    saved = {}
    for k, v in changes.items():
        saved[k] = cfg.get("pia", k)
        cfg.set("pia", k, v)

    cmd = cfg.build_pia_cmd(sys.executable, PIA_PIPELINE)

    for k, v in saved.items():
        cfg.set("pia", k, v)

    run(cmd, cwd=PIA_DIR)
    _prompt_save(changes, "pia")


def action_compare_topic():
    rule("PIA — One-off comparison")
    topic = ask("Compare topic", cfg.get("pia","compare_topic") or "")
    repos = ask("Pin repos (comma-sep; blank = auto)", cfg.get("pia","compare_repos") or "")
    if not topic: return
    overrides = {"compare_topic": topic, "compare_repos": repos,
                 "ingest_only": False, "scan_only": False, "clear_kb": False}
    action_pia(overrides)


def action_setup():
    rule("Setup")
    req = PIA_DIR / "requirements.txt"
    pkgs = ["PyGithub", "requests", "scrapling", "rich"]
    cmd = ([sys.executable, "-m", "pip", "install", "-r", str(req)] + pkgs
           if req.exists() else
           [sys.executable, "-m", "pip", "install"] + pkgs)
    run(cmd)
    info("Optional: installing Scrapling browser backend…")
    subprocess.run([sys.executable, "-m", "scrapling", "install"], check=False)


def action_show_config():
    import json
    rule("Current config  (suite_config.json)")
    if HAS_RICH:
        from rich.syntax import Syntax
        console.print(Syntax(json.dumps(cfg._data, indent=2), "json", theme="monokai"))
    else:
        print(json.dumps(cfg._data, indent=2))


def action_edit_config():
    if not PIA_CONFIG.exists():
        warn(f"config.yaml not found at: {PIA_CONFIG}"); return
    editor = os.environ.get("EDITOR", "notepad" if sys.platform=="win32" else "nano")
    subprocess.run([editor, str(PIA_CONFIG)])


def action_open_reports():
    d = PIA_DIR / "reports"
    if not d.exists():
        warn("Reports folder not found. Run PIA pipeline first."); return
    ok(f"Reports at: {d}")
    if sys.platform == "win32":   os.startfile(str(d))
    elif sys.platform == "darwin": subprocess.run(["open", str(d)])
    else:                          subprocess.run(["xdg-open", str(d)], check=False)


# ══════════════════════════════════════════════════════════════════════════════
# MAIN LOOP
# ══════════════════════════════════════════════════════════════════════════════
def main():
    # fast CLI shortcuts
    if len(sys.argv) > 1:
        cmd = sys.argv[1].lower()
        if cmd in ("extract","github"): action_github(); return
        if cmd == "platform":           action_platform(); return
        if cmd == "full":               action_full(); return
        if cmd == "view":               run([sys.executable, str(VIEWER)] + sys.argv[2:]); return
        if cmd == "pia":                action_pia(); return
        if cmd == "setup":              action_setup(); return
        if cmd == "config":             action_show_config(); return

    while True:
        header()
        main_menu()

        choice = (Prompt.ask("[yellow]Choice[/yellow]", default="q")
                  if HAS_RICH else input("  Choice [q]: ").strip()) or "q"
        choice = choice.lower().strip()
        p()

        if   choice == "1":   action_github()
        elif choice == "2":   action_platform()
        elif choice == "3":   action_full()
        elif choice == "4":   run([sys.executable, str(VIEWER), "stats"])
        elif choice == "5":   action_view_trending()
        elif choice == "6":   run([sys.executable, str(VIEWER), "list"])
        elif choice == "7":
            kw = ask("Search keyword")
            if kw: run([sys.executable, str(VIEWER), "search", kw])
        elif choice == "8":   action_inspect_repo()
        elif choice == "9":   action_external()
        elif choice == "d":   action_discoveries()
        elif choice == "e":   run([sys.executable, str(VIEWER), "ext-summary"])
        elif choice == "v":
            raw = ask("Viewer command (e.g. trending daily python)")
            if raw: run([sys.executable, str(VIEWER)] + raw.split())
        elif choice == "p":   action_pia()
        elif choice == "i":   action_pia({"ingest_only": True, "scan_only": False})
        elif choice == "n":   action_pia({"scan_only": True,  "ingest_only": False})
        elif choice == "c":   action_compare_topic()
        elif choice == "k":
            if ask_bool("⚠  Clear KB — WIPE vector store. Are you sure?", False):
                action_pia({"clear_kb": True, "ingest_only": True})
        elif choice == "r":   action_open_reports()
        elif choice == "l":
            if check(PLATFORM,"platform_extractor.py"):
                run([sys.executable, str(PLATFORM), "--list-sources"])
        elif choice == "h":
            if check(PLATFORM,"platform_extractor.py"):
                run([sys.executable, str(PLATFORM), "--check"])
        elif choice == "cfg": action_show_config()
        elif choice == "s":   action_setup()
        elif choice == "edit":action_edit_config()
        elif choice in ("q","quit","exit",""):
            (console.print("[dim]  Goodbye.[/dim]\n") if HAS_RICH else print("  Goodbye."))
            break
        else:
            warn(f"Unknown option: {choice!r}")
            continue

        p()
        input("  Press Enter to return to menu…")

if __name__ == "__main__":
    main()
