"""
GitHub Intelligence Suite — Config Manager
============================================
Single source of truth for every configurable parameter.
Loads / saves to  suite_config.json  alongside this file.
Both gui_app.py and launcher.py import this module.
"""

from __future__ import annotations
import json
import sys
from pathlib import Path
from copy import deepcopy

HERE = Path(__file__).resolve().parent
CONFIG_PATH = HERE / "suite_config.json"

# ── All GitHub source names (authoritative list) ─────────────────────────────
GH_SOURCES_ALL = ["owned", "forks", "starred", "trending", "collections"]

# ── All platform plugin names (authoritative list) ────────────────────────────
PLATFORM_SOURCES = [
    "hackernews",
    "paperswithcode",
    "npm",
    "pypi",
    "cratesio",
    "devto",
    "lobsters",
    "reddit",
    "thisweekrust",
    "searxng",
]

# ── Viewer subcommands (authoritative list) ───────────────────────────────────
VIEWER_CMDS = [
    "stats", "list", "show", "text", "readmes",
    "issues", "tree", "search",
    "trending", "collections",
    "external", "ext-summary",
    "sources", "discoveries",
]

# ══════════════════════════════════════════════════════════════════════════════
# DEFAULT CONFIG  — one key per CLI argument, named to match --flag → underscore
# ══════════════════════════════════════════════════════════════════════════════
DEFAULT_CONFIG: dict = {
    # ── global ────────────────────────────────────────────────────────────────
    "global": {
        "output_dir":    "github_export",        # used by both extractors
    },

    # ── github_extractor_v2.py ────────────────────────────────────────────────
    "github_extractor": {
        # authentication
        "token":               "",               # --token / GITHUB_TOKEN env
        # sources
        "sources":             ["owned", "forks", "starred", "trending"],
        "collections_full":    False,            # --collections-full
        "repo":                "",               # --repo  (single-repo mode)
        "trending_langs":      "",               # --trending-langs
        # content
        "skip_text_files":     False,            # --skip-text-files
        "text_extensions":     "",               # --text-extensions
        "skip_issues":         False,            # --skip-issues
        # behaviour
        "resume":              True,             # --resume
        "schedule":            "",               # --schedule  e.g. 6h, 1d
        "searxng_url":         "",               # --searxng-url
        # chaining
        "chain_platform":      False,            # --platform
        "platform_sources_filter": "",           # --platform-sources
    },

    # ── platform_extractor.py ─────────────────────────────────────────────────
    "platform_extractor": {
        # run mode
        "mode":            "forward",            # --mode
        "schedule":        "",                   # --schedule
        "floor_date":      "2024-01-01",         # --floor-date
        "lookback_batch":  50,                   # --lookback-batch
        # sources  (all 10 plugins, all enabled by default)
        "sources":         list(PLATFORM_SOURCES),
        # advanced
        "config_yaml":     "",                   # --config
        "searxng_url":     "",                   # --searxng-url
    },

    # ── PIA  pia/scheduler/run_pipeline.py ──────────────────────────────
    "pia": {
        # run mode
        "ingest_only":      False,               # --ingest-only
        "scan_only":        False,               # --scan-only
        # scope
        "project":          "",                  # --project
        "force_eligible":   "",                  # --force-eligible
        # analysis options
        "no_intent":        False,               # --no-intent
        "no_compare":       False,               # --no-compare
        "compare_topic":    "",                  # --compare-topic
        "compare_repos":    "",                  # --compare-repos
        "skip_benchmark":   False,               # --skip-benchmark
        # maintenance
        "clear_kb":         False,               # --clear-kb  (destructive — default OFF)
        "config_yaml":      "",                  # --config
    },

    # ── github_viewer_v2.py ───────────────────────────────────────────────────
    "viewer": {
        # discoveries filter defaults (used by the discoveries command)
        "discoveries_source":     "",            # --source
        "discoveries_min_score":  0,             # --min-score
        "discoveries_history":    False,         # --history
        # external filter default
        "external_source":        "",            # positional source arg
        "external_date":          "",            # positional date arg
        # text-files filter default
        "text_ext_filter":        "",            # extension filter e.g. .py
        # trending defaults
        "trending_period":        "daily",
        "trending_lang":          "",
    },
}


# ══════════════════════════════════════════════════════════════════════════════
# CONFIG MANAGER
# ══════════════════════════════════════════════════════════════════════════════
class ConfigManager:
    def __init__(self, path: Path = CONFIG_PATH):
        self._path = path
        self._data: dict = deepcopy(DEFAULT_CONFIG)
        self.load()

    # ── persistence ──────────────────────────────────────────────────────────
    def load(self):
        if self._path.exists():
            try:
                on_disk = json.loads(self._path.read_text(encoding="utf-8"))
                self._merge(self._data, on_disk)
            except Exception:
                pass  # corrupt file → keep defaults

    def save(self):
        try:
            self._path.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            pass

    @staticmethod
    def _merge(base: dict, override: dict):
        """Deep-merge override into base (base is modified in-place)."""
        for k, v in override.items():
            if k in base and isinstance(base[k], dict) and isinstance(v, dict):
                ConfigManager._merge(base[k], v)
            elif k in base:
                base[k] = v

    # ── get / set ─────────────────────────────────────────────────────────────
    def get(self, section: str, key: str, default=None):
        return self._data.get(section, {}).get(key, default)

    def set(self, section: str, key: str, value):
        if section not in self._data:
            self._data[section] = {}
        self._data[section][key] = value

    def section(self, name: str) -> dict:
        return self._data.get(name, {})

    # ── command builders ─────────────────────────────────────────────────────
    def build_github_cmd(self, python: str, script: Path) -> list[str]:
        import os
        c   = self._data["github_extractor"]
        gl  = self._data["global"]
        cmd = [python, str(script)]

        token = c["token"] or os.environ.get("GITHUB_TOKEN", "")
        if token:                           cmd += ["--token", token]

        cmd += ["--output", gl["output_dir"]]

        if c["repo"]:
            cmd += ["--repo", c["repo"]]
        else:
            sources = ",".join(c["sources"]) if c["sources"] else "owned"
            cmd += ["--sources", sources]
            if c["trending_langs"]:         cmd += ["--trending-langs", c["trending_langs"]]
            if c["collections_full"]:       cmd += ["--collections-full"]

        if c["skip_text_files"]:            cmd += ["--skip-text-files"]
        if c["text_extensions"]:            cmd += ["--text-extensions", c["text_extensions"]]
        if c["skip_issues"]:                cmd += ["--skip-issues"]
        if c["resume"]:                     cmd += ["--resume"]
        if c["schedule"]:                   cmd += ["--schedule", c["schedule"]]
        if c["searxng_url"]:                cmd += ["--searxng-url", c["searxng_url"]]
        if c["chain_platform"]:             cmd += ["--platform"]
        if c["platform_sources_filter"]:    cmd += ["--platform-sources", c["platform_sources_filter"]]
        return cmd

    def build_platform_cmd(self, python: str, script: Path) -> list[str]:
        c   = self._data["platform_extractor"]
        gl  = self._data["global"]
        cmd = [python, str(script)]

        cmd += ["--mode",   c["mode"]]
        cmd += ["--output", gl["output_dir"]]

        sources = ",".join(c["sources"]) if c["sources"] else ""
        if sources:                         cmd += ["--sources", sources]
        if c["config_yaml"]:                cmd += ["--config", c["config_yaml"]]
        if c["schedule"]:                   cmd += ["--schedule", c["schedule"]]
        if c["floor_date"]:                 cmd += ["--floor-date", c["floor_date"]]
        if c["lookback_batch"] != 50:       cmd += ["--lookback-batch", str(c["lookback_batch"])]
        if c["searxng_url"]:                cmd += ["--searxng-url", c["searxng_url"]]
        return cmd

    def build_pia_cmd(self, python: str, script: Path, overrides: dict | None = None) -> list[str]:
        c   = {**self._data["pia"], **(overrides or {})}
        cmd = [python, str(script)]

        if c.get("ingest_only"):            cmd += ["--ingest-only"]
        if c.get("scan_only"):              cmd += ["--scan-only"]
        if c.get("project"):                cmd += ["--project", c["project"]]
        if c.get("force_eligible"):         cmd += ["--force-eligible", c["force_eligible"]]
        if c.get("no_intent"):              cmd += ["--no-intent"]
        if c.get("no_compare"):             cmd += ["--no-compare"]
        if c.get("compare_topic"):          cmd += ["--compare-topic", c["compare_topic"]]
        if c.get("compare_repos"):          cmd += ["--compare-repos", c["compare_repos"]]
        if c.get("skip_benchmark"):         cmd += ["--skip-benchmark"]
        if c.get("clear_kb"):               cmd += ["--clear-kb"]
        if c.get("config_yaml"):            cmd += ["--config", c["config_yaml"]]
        return cmd

    def build_discoveries_args(self) -> list[str]:
        """Returns the sub-args list for the viewer discoveries command."""
        c    = self._data["viewer"]
        args = []
        if c["discoveries_source"]:         args += ["--source", c["discoveries_source"]]
        if c["discoveries_min_score"] > 0:  args += ["--min-score", str(c["discoveries_min_score"])]
        if c["discoveries_history"]:        args += ["--history"]
        return args

    def output_dir(self) -> str:
        return self._data["global"]["output_dir"]


# ── module-level singleton ────────────────────────────────────────────────────
cfg = ConfigManager()
