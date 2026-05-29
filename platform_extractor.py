#!/usr/bin/env python3
"""
Platform Extractor  v1
======================
Discovers GitHub repos from external platforms and normalises them into a
shared schema.  Works alongside github_extractor_v2.py — writes into the same
github_export/ directory under _external_sources/.

Architecture
  • Plugin-based (drop a .py file into sources/ → auto-discovered)
  • Two-speed crawl: forward scan (frequent) + lookback scan (background)
  • State file: github_export/_state/crawl_state.json
  • Scrapling for all HTML scraping (replaces BeautifulSoup)
  • SearXNG as optional meta-search discovery layer (--searxng-url)

Built-in plugins
  hackernews       Show HN posts via Algolia API  (free, no key)
  paperswithcode   ML papers with GitHub repos   (free REST API)
  npm              Top/new npm packages           (free REST API)
  pypi             Top/new PyPI packages          (free REST API)
  cratesio         crates.io Rust packages        (free REST API)
  devto            Dev.to project announcements   (free REST API)
  lobsters         Lobsters link aggregator       (free JSON API)
  reddit           r/programming etc.             (free JSON API)
  thisweekrust     This Week in Rust newsletter   (GitHub Markdown)
  searxng          Meta-search side-channel       (self-hosted, optional)

Install
  pip install scrapling requests
  scrapling install            # optional: Camoufox backend for stealth mode

Usage
  python platform_extractor.py                              # forward scan, all sources
  python platform_extractor.py --mode forward               # forward scan only
  python platform_extractor.py --mode lookback              # advance lookback cursors
  python platform_extractor.py --mode both                  # forward + lookback
  python platform_extractor.py --sources hackernews,pypi    # specific sources
  python platform_extractor.py --schedule 6h               # repeat every 6 h
  python platform_extractor.py --searxng-url http://localhost:8888
  python platform_extractor.py --list-sources               # show all plugins

Output
  github_export/
    _external_sources/
      hackernews/
        forward/
          2026-05-27.json        ← today's new items (appended on each run)
        history/
          page_001.json          ← historical batches
      paperswithcode/
        forward/...
        history/...
      ...
    _state/
      crawl_state.json           ← all cursor + last-seen state
"""

from __future__ import annotations

import os
import re
import sys
import json
import time
import math
import argparse
import importlib.util
import traceback
from abc import ABC, abstractmethod
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Iterator, Optional

import requests

# ── Scrapling (HTML scraping) ────────────────────────────────────────────────
try:
    from scrapling.fetchers import Fetcher as ScraplingFetcher
    HAS_SCRAPLING = True
except ImportError:
    HAS_SCRAPLING = False


# ══════════════════════════════════════════════════════════
# CONSTANTS
# ══════════════════════════════════════════════════════════
OUTPUT_DIR   = Path("github_export")
STATE_DIR    = OUTPUT_DIR / "_state"
EXT_DIR      = OUTPUT_DIR / "_external_sources"
STATE_FILE   = STATE_DIR / "crawl_state.json"
SOURCES_DIR  = Path(__file__).parent / "sources"

SCRAPE_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}

GITHUB_RE = re.compile(
    r'github\.com/([a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+?)(?:[/#?"\s>]|$)'
)


# ══════════════════════════════════════════════════════════
# LOGGING
# ══════════════════════════════════════════════════════════
def log(msg: str, level: str = "INFO"):
    ts  = datetime.now().strftime("%H:%M:%S")
    sym = {"INFO": "•", "OK": "✓", "WARN": "⚠", "ERR": "✗", "SKIP": "→", "DBG": "·"}.get(level, "•")
    print(f"  [{ts}] {sym} {msg}")


# ══════════════════════════════════════════════════════════
# CORE DATA TYPES
# ══════════════════════════════════════════════════════════
@dataclass
class DiscoveredRepo:
    """Normalised record for one discovered GitHub repo reference."""
    github_repo:   str               # "owner/repo"  (required)
    source:        str               # plugin name, e.g. "hackernews"
    source_url:    str               # permalink to the original post / page
    title:         str = ""          # post title / paper title / package name
    description:   str = ""
    score:         int = 0           # upvotes / stars / citations / downloads
    published_at:  Optional[str] = None   # ISO8601 string
    discovered_at: Optional[str] = None   # auto-set by runner
    tags:          list = field(default_factory=list)
    extra:         dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        if self.discovered_at is None:
            d["discovered_at"] = datetime.now(timezone.utc).isoformat()
        return d


def extract_github_repos(text: str) -> list[str]:
    """Pull all 'owner/repo' strings from arbitrary text."""
    raw = GITHUB_RE.findall(text)
    cleaned = []
    for r in raw:
        r = r.rstrip(".")
        if r.count("/") == 1 and not r.endswith(".git"):
            cleaned.append(r)
        elif r.endswith(".git"):
            cleaned.append(r[:-4])
    return list(dict.fromkeys(cleaned))   # deduplicate, preserve order


# ══════════════════════════════════════════════════════════
# PLUGIN BASE CLASS
# ══════════════════════════════════════════════════════════
class SourcePlugin(ABC):
    """
    Abstract base class for all source plugins.

    To add a new source:
      1. Subclass SourcePlugin
      2. Set NAME, DESCRIPTION, REQUIRES_AUTH, SUPPORTS_LOOKBACK
      3. Implement fetch_recent() and (if SUPPORTS_LOOKBACK) fetch_batch()
      4. Drop the file into sources/  — it's auto-discovered
    """

    NAME:              str  = ""
    DESCRIPTION:       str  = ""
    REQUIRES_AUTH:     bool = False
    SUPPORTS_LOOKBACK: bool = False
    DEFAULT_CONFIG:    dict = {}

    def configure(self, config: dict) -> None:
        self.config = {**self.DEFAULT_CONFIG, **config}

    @abstractmethod
    def fetch_recent(
        self,
        since: datetime,
        limit: int = 50,
    ) -> Iterator[DiscoveredRepo]:
        """
        Yield items published since `since`.
        FORWARD scan — called on every scheduled run. Should be fast.
        """

    def fetch_batch(
        self,
        cursor: Any,
        batch_size: int = 50,
    ) -> tuple[list[DiscoveredRepo], Any]:
        """
        Fetch one historical batch.
        Returns (items, next_cursor).  next_cursor=None when history exhausted.
        Only needed when SUPPORTS_LOOKBACK = True.
        """
        raise NotImplementedError(
            f"Plugin '{self.NAME}' has SUPPORTS_LOOKBACK=True "
            "but did not implement fetch_batch()"
        )

    def get_config_schema(self) -> dict:
        return {}

    def health_check(self) -> tuple[bool, str]:
        return True, "No health check implemented."


# ══════════════════════════════════════════════════════════
# CRAWL STATE (B1 architecture)
# ══════════════════════════════════════════════════════════
class CrawlState:
    """Persists forward + lookback cursor state across runs."""

    def __init__(self, path: Path):
        self.path = path
        self._data = self._load()

    def _load(self) -> dict:
        if self.path.exists():
            try:
                return json.loads(self.path.read_text(encoding="utf-8"))
            except Exception:
                pass
        return {"sources": {}, "global": {}}

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.path.write_text(json.dumps(self._data, indent=2), encoding="utf-8")

    def _src(self, name: str) -> dict:
        self._data["sources"].setdefault(name, {"forward": {}, "lookback": {}})
        return self._data["sources"][name]

    # Forward state
    def get_last_seen(self, name: str, default: datetime) -> datetime:
        raw = self._src(name)["forward"].get("last_seen")
        if raw:
            try:
                return datetime.fromisoformat(raw)
            except Exception:
                pass
        return default

    def set_last_seen(self, name: str, dt: datetime):
        self._src(name)["forward"]["last_seen"] = dt.isoformat()
        self._src(name)["forward"]["last_run"] = datetime.now(timezone.utc).isoformat()

    def increment_forward_count(self, name: str, n: int):
        fwd = self._src(name)["forward"]
        fwd["total_discovered"] = fwd.get("total_discovered", 0) + n

    # Lookback state
    def get_lookback_cursor(self, name: str) -> Optional[dict]:
        return self._src(name)["lookback"].get("cursor")

    def set_lookback_cursor(self, name: str, cursor: Any):
        self._src(name)["lookback"]["cursor"] = cursor
        self._src(name)["lookback"]["last_run"] = datetime.now(timezone.utc).isoformat()

    def is_history_complete(self, name: str) -> bool:
        return self._src(name)["lookback"].get("history_complete", False)

    def mark_history_complete(self, name: str):
        self._src(name)["lookback"]["history_complete"] = True
        log(f"[{name}] History complete — all pages crawled.", "OK")

    def get_floor_date(self, name: str, default: str = "2024-01-01") -> datetime:
        raw = self._src(name)["lookback"].get("floor_date", default)
        try:
            return datetime.fromisoformat(raw).replace(tzinfo=timezone.utc)
        except Exception:
            return datetime(2024, 1, 1, tzinfo=timezone.utc)

    def bump_global(self, n: int):
        g = self._data.setdefault("global", {})
        g["total_discovered"] = g.get("total_discovered", 0) + n
        g["last_run"] = datetime.now(timezone.utc).isoformat()


# ══════════════════════════════════════════════════════════
# OUTPUT WRITER
# ══════════════════════════════════════════════════════════
def write_forward_batch(source: str, items: list[DiscoveredRepo], output_dir: Path):
    """Append today's forward-scan items to _external_sources/{source}/forward/YYYY-MM-DD.json"""
    today = datetime.now().strftime("%Y-%m-%d")
    fwd_dir = output_dir / source / "forward"
    fwd_dir.mkdir(parents=True, exist_ok=True)
    fpath = fwd_dir / f"{today}.json"

    existing = []
    if fpath.exists():
        try:
            existing = json.loads(fpath.read_text(encoding="utf-8"))
        except Exception:
            pass

    # Deduplicate by (github_repo, source_url)
    seen = {(r["github_repo"], r["source_url"]) for r in existing}
    new_items = [r.to_dict() for r in items if (r.github_repo, r.source_url) not in seen]

    fpath.write_text(
        json.dumps(existing + new_items, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    return len(new_items)


def write_lookback_batch(source: str, cursor_label: str, items: list[DiscoveredRepo], output_dir: Path):
    """Write one lookback batch to _external_sources/{source}/history/{cursor_label}.json"""
    hist_dir = output_dir / source / "history"
    hist_dir.mkdir(parents=True, exist_ok=True)
    fpath = hist_dir / f"{cursor_label}.json"
    fpath.write_text(
        json.dumps([r.to_dict() for r in items], indent=2, ensure_ascii=False),
        encoding="utf-8"
    )
    return len(items)


# ══════════════════════════════════════════════════════════
# PLUGIN AUTO-DISCOVERY
# ══════════════════════════════════════════════════════════
def load_external_plugins(sources_dir: Path) -> dict[str, SourcePlugin]:
    """Load all SourcePlugin subclasses from sources/*.py files."""
    plugins: dict[str, SourcePlugin] = {}
    if not sources_dir.exists():
        return plugins
    for py_file in sorted(sources_dir.glob("*.py")):
        if py_file.name.startswith("_"):
            continue
        try:
            spec   = importlib.util.spec_from_file_location(py_file.stem, py_file)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            for attr_name in dir(module):
                attr = getattr(module, attr_name)
                if (
                    isinstance(attr, type)
                    and issubclass(attr, SourcePlugin)
                    and attr is not SourcePlugin
                    and attr.NAME
                ):
                    plugins[attr.NAME] = attr()
                    log(f"Loaded external plugin: {attr.NAME}", "OK")
        except Exception as e:
            log(f"Failed to load plugin {py_file.name}: {e}", "ERR")
    return plugins


# ══════════════════════════════════════════════════════════
# ── BUILT-IN PLUGINS ──────────────────────────────────────
# ══════════════════════════════════════════════════════════

# 1. HACKER NEWS (Show HN) — Algolia API, free, no key
class HackerNewsPlugin(SourcePlugin):
    NAME              = "hackernews"
    DESCRIPTION       = "Hacker News Show HN posts via Algolia API (free, no key)"
    REQUIRES_AUTH     = False
    SUPPORTS_LOOKBACK = True
    DEFAULT_CONFIG    = {"min_score": 5, "tags": "show_hn"}
    BASE              = "https://hn.algolia.com/api/v1/search"

    def _parse_hits(self, hits: list) -> list[DiscoveredRepo]:
        results = []
        for hit in hits:
            text  = (hit.get("url") or "") + " " + (hit.get("title") or "") + " " + (hit.get("story_text") or "")
            repos = extract_github_repos(text)
            if not repos:
                continue
            score = hit.get("points", 0) or 0
            if score < self.config.get("min_score", 5):
                continue
            pub_ts = hit.get("created_at_i", 0)
            pub_dt = datetime.fromtimestamp(pub_ts, tz=timezone.utc).isoformat() if pub_ts else None
            for repo in set(repos):
                results.append(DiscoveredRepo(
                    github_repo  = repo,
                    source       = self.NAME,
                    source_url   = f"https://news.ycombinator.com/item?id={hit['objectID']}",
                    title        = hit.get("title", ""),
                    score        = score,
                    published_at = pub_dt,
                    extra        = {"comments": hit.get("num_comments", 0), "hn_id": hit.get("objectID")},
                ))
        return results

    def fetch_recent(self, since: datetime, limit: int = 50) -> Iterator[DiscoveredRepo]:
        ts  = int(since.timestamp())
        url = (f"{self.BASE}?tags={self.config['tags']}"
               f"&numericFilters=created_at_i>{ts}&hitsPerPage={limit}")
        try:
            data = requests.get(url, timeout=15).json()
            yield from self._parse_hits(data.get("hits", []))
        except Exception as e:
            log(f"[hackernews] fetch_recent failed: {e}", "ERR")

    def fetch_batch(self, cursor: Any, batch_size: int = 50) -> tuple[list, Any]:
        page = cursor.get("page", 0) if cursor else 0
        url  = f"{self.BASE}?tags={self.config['tags']}&hitsPerPage={batch_size}&page={page}"
        try:
            data = requests.get(url, timeout=15).json()
            hits = data.get("hits", [])
            next_cursor = {"page": page + 1} if hits and page < data.get("nbPages", 0) - 1 else None
            return self._parse_hits(hits), next_cursor
        except Exception as e:
            log(f"[hackernews] fetch_batch failed: {e}", "ERR")
            return [], None


# 2. PAPERS WITH CODE — free REST API, best for ML/AI repos
class PapersWithCodePlugin(SourcePlugin):
    NAME              = "paperswithcode"
    DESCRIPTION       = "ML/AI papers with GitHub implementations (free REST API)"
    REQUIRES_AUTH     = False
    SUPPORTS_LOOKBACK = True
    DEFAULT_CONFIG    = {"min_stars": 0}
    BASE              = "https://paperswithcode.com/api/v1"

    def _parse_results(self, results: list) -> list[DiscoveredRepo]:
        out = []
        for paper in results:
            repo_url = (paper.get("repository") or {}).get("url") or paper.get("github_link", "") or ""
            repos    = extract_github_repos(repo_url)
            if not repos:
                # Try abstract / title
                repos = extract_github_repos((paper.get("abstract") or ""))
            if not repos:
                continue
            published = paper.get("published") or paper.get("paper", {}).get("published") or ""
            for repo in set(repos):
                out.append(DiscoveredRepo(
                    github_repo  = repo,
                    source       = self.NAME,
                    source_url   = paper.get("url") or f"https://paperswithcode.com/paper/{paper.get('id','')}",
                    title        = paper.get("title", ""),
                    description  = (paper.get("abstract") or "")[:300],
                    score        = paper.get("stars", 0) or 0,
                    published_at = published or None,
                    tags         = paper.get("tasks") or [],
                    extra        = {"paper_id": paper.get("id"), "arxiv": paper.get("arxiv_id", "")},
                ))
        return out

    def fetch_recent(self, since: datetime, limit: int = 50) -> Iterator[DiscoveredRepo]:
        url = f"{self.BASE}/papers/?ordering=-published_date&page_size={limit}"
        try:
            data    = requests.get(url, timeout=15).json()
            results = data.get("results", [])
            since_s = since.isoformat()
            fresh   = [r for r in results if (r.get("published") or "") >= since_s]
            yield from self._parse_results(fresh)
        except Exception as e:
            log(f"[paperswithcode] fetch_recent failed: {e}", "ERR")

    def fetch_batch(self, cursor: Any, batch_size: int = 50) -> tuple[list, Any]:
        page = cursor.get("page", 1) if cursor else 1
        url  = f"{self.BASE}/papers/?ordering=-published_date&page_size={batch_size}&page={page}"
        try:
            data    = requests.get(url, timeout=15).json()
            results = data.get("results", [])
            next_cursor = {"page": page + 1} if data.get("next") else None
            return self._parse_results(results), next_cursor
        except Exception as e:
            log(f"[paperswithcode] fetch_batch failed: {e}", "ERR")
            return [], None


# 3. NPM — newly published packages with GitHub links
class NpmPlugin(SourcePlugin):
    NAME              = "npm"
    DESCRIPTION       = "New/popular npm packages with GitHub repos (free REST API)"
    REQUIRES_AUTH     = False
    SUPPORTS_LOOKBACK = False
    DEFAULT_CONFIG    = {"min_downloads": 100, "page_size": 100}

    def fetch_recent(self, since: datetime, limit: int = 50) -> Iterator[DiscoveredRepo]:
        # Query recently updated packages via the npm registry search API
        # We search for packages updated since `since`
        try:
            url  = f"https://registry.npmjs.org/-/v1/search?text=*&size={limit}&quality=0.0&maintenance=0.0&popularity=1.0"
            data = requests.get(url, timeout=15).json()
            for obj in data.get("objects", []):
                pkg  = obj.get("package", {})
                links = pkg.get("links", {})
                repo_url = links.get("repository", "") or links.get("homepage", "") or ""
                repos    = extract_github_repos(repo_url)
                if not repos:
                    continue
                pub_date = pkg.get("date", "")
                for repo in set(repos):
                    yield DiscoveredRepo(
                        github_repo  = repo,
                        source       = self.NAME,
                        source_url   = links.get("npm") or f"https://www.npmjs.com/package/{pkg.get('name','')}",
                        title        = pkg.get("name", ""),
                        description  = pkg.get("description", ""),
                        score        = obj.get("score", {}).get("final", 0.0),
                        published_at = pub_date or None,
                        tags         = pkg.get("keywords", [])[:10],
                    )
        except Exception as e:
            log(f"[npm] fetch_recent failed: {e}", "ERR")


# 4. PYPI — Python packages with GitHub links
class PyPIPlugin(SourcePlugin):
    NAME              = "pypi"
    DESCRIPTION       = "New/popular PyPI packages with GitHub repos (free REST API)"
    REQUIRES_AUTH     = False
    SUPPORTS_LOOKBACK = False
    DEFAULT_CONFIG    = {"search_terms": ["machine-learning", "web", "cli", "api", "data"]}

    def fetch_recent(self, since: datetime, limit: int = 50) -> Iterator[DiscoveredRepo]:
        # PyPI doesn't have a "recent by date" search API, so we query
        # the RSS feed for newest packages
        try:
            rss_url = "https://pypi.org/rss/packages.xml"
            resp    = requests.get(rss_url, timeout=15)
            # Parse RSS manually (avoid lxml dependency)
            items   = re.findall(r"<item>(.*?)</item>", resp.text, re.DOTALL)
            for item_xml in items[:limit]:
                pkg_name = re.search(r"<title>([^<]+)</title>", item_xml)
                pub_date = re.search(r"<pubDate>([^<]+)</pubDate>", item_xml)
                link     = re.search(r"<link>([^<]+)</link>", item_xml)
                if not pkg_name:
                    continue
                name     = pkg_name.group(1).strip().split()[0]  # "packagename 1.0.0" → "packagename"
                pkg_url  = f"https://pypi.org/pypi/{name}/json"
                try:
                    pkg_data = requests.get(pkg_url, timeout=10).json()
                    info     = pkg_data.get("info", {})
                    proj_urls = info.get("project_urls") or {}
                    repo_url  = (
                        proj_urls.get("Source") or
                        proj_urls.get("source") or
                        proj_urls.get("Homepage") or
                        proj_urls.get("homepage") or
                        info.get("home_page") or ""
                    )
                    repos = extract_github_repos(repo_url)
                    if not repos:
                        repos = extract_github_repos(
                            " ".join(proj_urls.values()) + " " + (info.get("description") or "")
                        )
                    for repo in set(repos):
                        yield DiscoveredRepo(
                            github_repo  = repo,
                            source       = self.NAME,
                            source_url   = link.group(1) if link else f"https://pypi.org/project/{name}/",
                            title        = name,
                            description  = (info.get("summary") or "")[:200],
                            published_at = pub_date.group(1) if pub_date else None,
                            tags         = (info.get("classifiers") or [])[:5],
                        )
                    time.sleep(0.1)   # gentle rate limiting
                except Exception:
                    pass
        except Exception as e:
            log(f"[pypi] fetch_recent failed: {e}", "ERR")


# 5. CRATES.IO — Rust packages
class CratesIOPlugin(SourcePlugin):
    NAME              = "cratesio"
    DESCRIPTION       = "crates.io Rust packages with GitHub repos (free REST API)"
    REQUIRES_AUTH     = False
    SUPPORTS_LOOKBACK = True
    DEFAULT_CONFIG    = {"sort": "new", "min_downloads": 0}
    BASE              = "https://crates.io/api/v1"

    def _parse_crates(self, crates: list) -> list[DiscoveredRepo]:
        results = []
        for crate in crates:
            repo_url = crate.get("repository") or crate.get("homepage") or ""
            repos    = extract_github_repos(repo_url)
            if not repos:
                continue
            for repo in set(repos):
                results.append(DiscoveredRepo(
                    github_repo  = repo,
                    source       = self.NAME,
                    source_url   = f"https://crates.io/crates/{crate.get('id','')}",
                    title        = crate.get("name", ""),
                    description  = (crate.get("description") or "")[:200],
                    score        = crate.get("downloads", 0) or 0,
                    published_at = crate.get("created_at"),
                    tags         = crate.get("keywords", [])[:5],
                ))
        return results

    def fetch_recent(self, since: datetime, limit: int = 50) -> Iterator[DiscoveredRepo]:
        url = f"{self.BASE}/crates?sort=new&per_page={limit}&page=1"
        try:
            resp  = requests.get(url, headers={"User-Agent": "platform_extractor/1.0"}, timeout=15)
            data  = resp.json()
            since_s = since.isoformat()
            fresh = [c for c in data.get("crates", []) if (c.get("created_at") or "") >= since_s]
            yield from self._parse_crates(fresh)
        except Exception as e:
            log(f"[cratesio] fetch_recent failed: {e}", "ERR")

    def fetch_batch(self, cursor: Any, batch_size: int = 50) -> tuple[list, Any]:
        page = cursor.get("page", 1) if cursor else 1
        url  = f"{self.BASE}/crates?sort=new&per_page={batch_size}&page={page}"
        try:
            resp  = requests.get(url, headers={"User-Agent": "platform_extractor/1.0"}, timeout=15)
            data  = resp.json()
            crates = data.get("crates", [])
            next_cursor = {"page": page + 1} if crates and page < math.ceil(data.get("meta", {}).get("total", 0) / batch_size) else None
            return self._parse_crates(crates), next_cursor
        except Exception as e:
            log(f"[cratesio] fetch_batch failed: {e}", "ERR")
            return [], None


# 6. DEV.TO — project announcements and tutorials
class DevToPlugin(SourcePlugin):
    NAME              = "devto"
    DESCRIPTION       = "Dev.to project announcements and tutorials (free API)"
    REQUIRES_AUTH     = False
    SUPPORTS_LOOKBACK = True
    DEFAULT_CONFIG    = {"tags": "opensource,showdev", "min_reactions": 0}
    BASE              = "https://dev.to/api/articles"

    def _parse_articles(self, articles: list, since: Optional[datetime] = None) -> list[DiscoveredRepo]:
        results = []
        for art in articles:
            if since:
                pub = art.get("published_at", "")
                if pub and pub < since.isoformat():
                    continue
            text  = (art.get("url") or "") + " " + (art.get("description") or "") + " " + (art.get("body_markdown") or "")
            repos = extract_github_repos(text)
            if not repos:
                # Check canonical_url
                if art.get("canonical_url"):
                    repos = extract_github_repos(art["canonical_url"])
            if not repos:
                continue
            for repo in set(repos):
                results.append(DiscoveredRepo(
                    github_repo  = repo,
                    source       = self.NAME,
                    source_url   = art.get("url", ""),
                    title        = art.get("title", ""),
                    description  = (art.get("description") or "")[:200],
                    score        = art.get("positive_reactions_count", 0) or 0,
                    published_at = art.get("published_at"),
                    tags         = [t.get("name", "") for t in (art.get("tags") or [])][:5],
                    extra        = {"comments": art.get("comments_count", 0)},
                ))
        return results

    def fetch_recent(self, since: datetime, limit: int = 50) -> Iterator[DiscoveredRepo]:
        tags = self.config.get("tags", "opensource").split(",")[0]
        url  = f"{self.BASE}?tag={tags.strip()}&per_page={limit}"
        try:
            arts = requests.get(url, timeout=15).json()
            yield from self._parse_articles(arts, since)
        except Exception as e:
            log(f"[devto] fetch_recent failed: {e}", "ERR")

    def fetch_batch(self, cursor: Any, batch_size: int = 50) -> tuple[list, Any]:
        page = cursor.get("page", 1) if cursor else 1
        url  = f"{self.BASE}?tag=opensource&per_page={batch_size}&page={page}"
        try:
            arts = requests.get(url, timeout=15).json()
            if not isinstance(arts, list) or not arts:
                return [], None
            return self._parse_articles(arts), {"page": page + 1}
        except Exception as e:
            log(f"[devto] fetch_batch failed: {e}", "ERR")
            return [], None


# 7. LOBSTERS — curated tech link aggregator
class LobstersPlugin(SourcePlugin):
    NAME              = "lobsters"
    DESCRIPTION       = "Lobsters curated tech link aggregator (free JSON API)"
    REQUIRES_AUTH     = False
    SUPPORTS_LOOKBACK = False
    DEFAULT_CONFIG    = {"tags": "programming,opensource,rust,python"}
    BASE              = "https://lobste.rs"

    def fetch_recent(self, since: datetime, limit: int = 50) -> Iterator[DiscoveredRepo]:
        try:
            data  = requests.get(f"{self.BASE}/hottest.json", timeout=15).json()
            since_s = since.isoformat()
            for story in data[:limit]:
                if (story.get("created_at") or "") < since_s:
                    continue
                url   = story.get("url", "") or ""
                repos = extract_github_repos(url + " " + (story.get("description") or ""))
                if not repos:
                    continue
                for repo in set(repos):
                    yield DiscoveredRepo(
                        github_repo  = repo,
                        source       = self.NAME,
                        source_url   = story.get("short_id_url", story.get("url", "")),
                        title        = story.get("title", ""),
                        score        = story.get("score", 0),
                        published_at = story.get("created_at"),
                        tags         = story.get("tags", []),
                        extra        = {"comments": story.get("comment_count", 0)},
                    )
        except Exception as e:
            log(f"[lobsters] fetch_recent failed: {e}", "ERR")


# 8. REDDIT — r/programming, r/rust, r/python etc.
class RedditPlugin(SourcePlugin):
    NAME              = "reddit"
    DESCRIPTION       = "Reddit subreddit posts with GitHub repos (free JSON API)"
    REQUIRES_AUTH     = False
    SUPPORTS_LOOKBACK = False
    DEFAULT_CONFIG    = {
        "subreddits": "programming,rust,Python,javascript,MachineLearning,golang,opensource",
        "min_score": 10,
    }

    def fetch_recent(self, since: datetime, limit: int = 25) -> Iterator[DiscoveredRepo]:
        subs      = [s.strip() for s in self.config.get("subreddits", "programming").split(",")]
        since_ts  = since.timestamp()
        min_score = self.config.get("min_score", 10)
        headers   = {"User-Agent": "platform_extractor/1.0 (github discovery bot)"}
        for sub in subs:
            try:
                url  = f"https://www.reddit.com/r/{sub}/new.json?limit={limit}"
                data = requests.get(url, headers=headers, timeout=15).json()
                posts = data.get("data", {}).get("children", [])
                for child in posts:
                    post = child.get("data", {})
                    if post.get("created_utc", 0) < since_ts:
                        continue
                    if post.get("score", 0) < min_score:
                        continue
                    text  = (post.get("url") or "") + " " + (post.get("selftext") or "")
                    repos = extract_github_repos(text)
                    if not repos:
                        continue
                    created = datetime.fromtimestamp(post["created_utc"], tz=timezone.utc).isoformat()
                    for repo in set(repos):
                        yield DiscoveredRepo(
                            github_repo  = repo,
                            source       = self.NAME,
                            source_url   = f"https://reddit.com{post.get('permalink', '')}",
                            title        = post.get("title", ""),
                            score        = post.get("score", 0),
                            published_at = created,
                            tags         = [sub.lower()],
                            extra        = {"subreddit": sub, "comments": post.get("num_comments", 0)},
                        )
                time.sleep(0.5)   # Reddit polite crawl delay
            except Exception as e:
                log(f"[reddit] sub={sub} failed: {e}", "WARN")


# 9. THIS WEEK IN RUST — GitHub Markdown newsletter
class ThisWeekInRustPlugin(SourcePlugin):
    NAME              = "thisweekrust"
    DESCRIPTION       = "This Week in Rust newsletter (GitHub Markdown, official repo)"
    REQUIRES_AUTH     = False
    SUPPORTS_LOOKBACK = True
    DEFAULT_CONFIG    = {}
    API_BASE          = "https://api.github.com/repos/rust-lang/this-week-in-rust/contents/content"

    def _get_issue_list(self) -> list[dict]:
        try:
            resp = requests.get(self.API_BASE, timeout=15).json()
            # Filter .md files
            return sorted(
                [f for f in resp if isinstance(f, dict) and f.get("name", "").endswith(".md")],
                key=lambda x: x.get("name", ""),
                reverse=True,
            )
        except Exception as e:
            log(f"[thisweekrust] get_issue_list failed: {e}", "ERR")
            return []

    def _parse_issue(self, file_info: dict) -> list[DiscoveredRepo]:
        download_url = file_info.get("download_url", "")
        name         = file_info.get("name", "")
        if not download_url:
            return []
        try:
            md_text = requests.get(download_url, timeout=15).text
            repos   = extract_github_repos(md_text)
            results = []
            for repo in dict.fromkeys(repos):   # deduplicate preserving order
                results.append(DiscoveredRepo(
                    github_repo  = repo,
                    source       = self.NAME,
                    source_url   = f"https://this-week-in-rust.org/blog/tag/this-week-in-rust/",
                    title        = f"This Week in Rust — {name.replace('.md','')}",
                    tags         = ["rust", "weekly"],
                ))
            return results
        except Exception as e:
            log(f"[thisweekrust] parse_issue {name} failed: {e}", "WARN")
            return []

    def fetch_recent(self, since: datetime, limit: int = 3) -> Iterator[DiscoveredRepo]:
        issues = self._get_issue_list()
        for issue in issues[:limit]:
            # Filename is "YYYY-MM-DD-this-week-in-rust-NNN.md"
            date_match = re.match(r"(\d{4}-\d{2}-\d{2})", issue.get("name", ""))
            if date_match:
                issue_date = datetime.fromisoformat(date_match.group(1)).replace(tzinfo=timezone.utc)
                if issue_date < since:
                    continue
            for item in self._parse_issue(issue):
                yield item

    def fetch_batch(self, cursor: Any, batch_size: int = 3) -> tuple[list, Any]:
        issues = self._get_issue_list()
        idx    = cursor.get("idx", 0) if cursor else 0
        batch  = issues[idx: idx + batch_size]
        if not batch:
            return [], None
        results = []
        for issue in batch:
            results.extend(self._parse_issue(issue))
        next_cursor = {"idx": idx + batch_size} if idx + batch_size < len(issues) else None
        return results, next_cursor


# 10. SEARXNG — optional meta-search side-channel
class SearXNGPlugin(SourcePlugin):
    NAME              = "searxng"
    DESCRIPTION       = "SearXNG meta-search discovery layer (self-hosted, optional)"
    REQUIRES_AUTH     = False
    SUPPORTS_LOOKBACK = False
    DEFAULT_CONFIG    = {
        "base_url": "",        # must be set to a running SearXNG instance
        "queries": [
            "github.com new open source tool",
            "site:javascriptweekly.com github.com",
            "site:golangweekly.com github.com",
            "site:this-week-in-rust.org github.com",
            "site:dev.to github.com show",
        ],
    }

    def configure(self, config: dict) -> None:
        super().configure(config)
        self._base = self.config.get("base_url", "").rstrip("/")

    def fetch_recent(self, since: datetime, limit: int = 50) -> Iterator[DiscoveredRepo]:
        if not self._base:
            log("[searxng] No base_url configured — skipping.", "WARN")
            return
        queries = self.config.get("queries", [])
        for query in queries:
            try:
                url  = f"{self._base}/search?q={requests.utils.quote(query)}&format=json&engines=google,bing,duckduckgo"
                data = requests.get(url, timeout=20).json()
                for result in data.get("results", [])[:limit]:
                    repos = extract_github_repos(
                        (result.get("url") or "") + " " +
                        (result.get("title") or "") + " " +
                        (result.get("content") or "")
                    )
                    for repo in set(repos):
                        yield DiscoveredRepo(
                            github_repo  = repo,
                            source       = self.NAME,
                            source_url   = result.get("url", ""),
                            title        = result.get("title", ""),
                            description  = (result.get("content") or "")[:200],
                            extra        = {"searxng_query": query},
                        )
                time.sleep(1)
            except Exception as e:
                log(f"[searxng] query='{query}' failed: {e}", "WARN")


# ══════════════════════════════════════════════════════════
# REGISTRY — all built-in plugins
# ══════════════════════════════════════════════════════════
BUILTIN_PLUGINS: dict[str, SourcePlugin] = {
    p.NAME: p() for p in [
        HackerNewsPlugin,
        PapersWithCodePlugin,
        NpmPlugin,
        PyPIPlugin,
        CratesIOPlugin,
        DevToPlugin,
        LobstersPlugin,
        RedditPlugin,
        ThisWeekInRustPlugin,
        SearXNGPlugin,
    ]
}


# ══════════════════════════════════════════════════════════
# RUNNER
# ══════════════════════════════════════════════════════════
def run_forward_scan(
    plugins:    dict[str, SourcePlugin],
    state:      CrawlState,
    output_dir: Path,
    lookback_window_hours: int = 48,
) -> dict[str, int]:
    """Run forward scan on all plugins. Returns {source: items_found}."""
    counts = {}
    for name, plugin in plugins.items():
        log(f"[{name}] Forward scan …")
        since    = state.get_last_seen(name, datetime.now(timezone.utc) - timedelta(hours=lookback_window_hours))
        now      = datetime.now(timezone.utc)
        items    = []
        try:
            for item in plugin.fetch_recent(since=since):
                items.append(item)
        except Exception as e:
            log(f"[{name}] fetch_recent crashed: {e}", "ERR")
            traceback.print_exc()
            counts[name] = 0
            continue

        saved = write_forward_batch(name, items, output_dir)
        state.set_last_seen(name, now)
        state.increment_forward_count(name, saved)
        state.bump_global(saved)
        counts[name] = saved
        log(f"[{name}] {saved} new items saved", "OK")

    state.save()
    return counts


def run_lookback_scan(
    plugins:    dict[str, SourcePlugin],
    state:      CrawlState,
    output_dir: Path,
    batch_size: int = 50,
    floor_date: Optional[datetime] = None,
) -> dict[str, int]:
    """Advance lookback cursor by one batch per source. Returns {source: items_found}."""
    counts = {}
    for name, plugin in plugins.items():
        if not plugin.SUPPORTS_LOOKBACK:
            continue
        if state.is_history_complete(name):
            log(f"[{name}] History complete — skipping.", "SKIP")
            counts[name] = 0
            continue

        cursor = state.get_lookback_cursor(name)
        log(f"[{name}] Lookback batch (cursor={cursor}) …")
        try:
            items, next_cursor = plugin.fetch_batch(cursor=cursor, batch_size=batch_size)
        except Exception as e:
            log(f"[{name}] fetch_batch crashed: {e}", "ERR")
            counts[name] = 0
            continue

        # Filter to items on/after floor_date
        effective_floor = floor_date or state.get_floor_date(name)
        if floor_date:
            filtered = []
            for item in items:
                if item.published_at:
                    try:
                        pub = datetime.fromisoformat(item.published_at.replace("Z", "+00:00"))
                        if pub >= effective_floor:
                            filtered.append(item)
                    except Exception:
                        filtered.append(item)
                else:
                    filtered.append(item)
            items = filtered

        # Determine cursor label for filename
        cursor_label = f"page_{cursor.get('page', cursor.get('idx', 0)):05d}" if isinstance(cursor, dict) else "batch_0"

        if items:
            saved = write_lookback_batch(name, cursor_label, items, output_dir)
            state.bump_global(saved)
            counts[name] = saved
            log(f"[{name}] {saved} historical items saved → history/{cursor_label}.json", "OK")
        else:
            counts[name] = 0

        if next_cursor is None:
            state.mark_history_complete(name)
        else:
            state.set_lookback_cursor(name, next_cursor)

    state.save()
    return counts


# ══════════════════════════════════════════════════════════
# CONFIG LOADER
# ══════════════════════════════════════════════════════════
def load_config(config_path: Optional[Path]) -> dict:
    """Load YAML config if present. Falls back to empty dict."""
    if not config_path or not config_path.exists():
        return {}
    try:
        import yaml
        return yaml.safe_load(config_path.read_text(encoding="utf-8")) or {}
    except ImportError:
        log("PyYAML not installed — using default config for all plugins.", "WARN")
        return {}
    except Exception as e:
        log(f"Failed to load config: {e}", "WARN")
        return {}


def configure_plugins(
    plugins:      dict[str, SourcePlugin],
    global_config: dict,
    searxng_url:  Optional[str] = None,
) -> dict[str, SourcePlugin]:
    """Apply config to each plugin. Returns only enabled plugins."""
    sources_cfg = global_config.get("sources", {})
    enabled     = {}

    for name, plugin in plugins.items():
        cfg = sources_cfg.get(name, {})
        # If sources section exists but this plugin isn't listed, skip
        if sources_cfg and name not in sources_cfg:
            continue
        if cfg.get("enabled") is False:
            log(f"[{name}] disabled in config — skipping.", "SKIP")
            continue

        # Override SearXNG base_url from CLI
        if name == "searxng" and searxng_url:
            cfg["base_url"] = searxng_url
        if name == "searxng" and not cfg.get("base_url") and not searxng_url:
            continue   # Don't run SearXNG if no URL provided

        plugin.configure(cfg)
        enabled[name] = plugin

    return enabled


# ══════════════════════════════════════════════════════════
# HELPER
# ══════════════════════════════════════════════════════════
def parse_interval(s: str) -> int:
    total = 0
    for val, unit in re.findall(r'(\d+)\s*([dhms])', s.lower()):
        n = int(val)
        if   unit == 'd': total += n * 86400
        elif unit == 'h': total += n * 3600
        elif unit == 'm': total += n * 60
        elif unit == 's': total += n
    return total


def print_summary(counts: dict, mode: str):
    total = sum(counts.values())
    print(f"\n  ── {mode} scan complete ──")
    for name, n in sorted(counts.items()):
        mark = "✓" if n > 0 else "·"
        print(f"    {mark}  {name:<22} {n:>5} items")
    print(f"    {'':>24} ─────")
    print(f"    {'total':>24} {total:>5}\n")


# ══════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="Platform Extractor — discovers GitHub repos from external platforms",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
MODES:
  forward    Fetch new items since last run  (default, fast)
  lookback   Advance historical cursor one batch per source  (slow, background)
  both       Forward + lookback in one run

EXAMPLES:
  python platform_extractor.py                              # forward, all sources
  python platform_extractor.py --mode lookback              # advance history
  python platform_extractor.py --sources hackernews,pypi    # specific sources
  python platform_extractor.py --schedule 6h               # repeat every 6h
  python platform_extractor.py --searxng-url http://localhost:8888
  python platform_extractor.py --list-sources               # show all plugins
        """,
    )
    parser.add_argument("--mode", default="forward",
                        choices=["forward", "lookback", "both"],
                        help="Scan mode (default: forward)")
    parser.add_argument("--sources", default="",
                        help="Comma-separated plugin names to run (default: all enabled)")
    parser.add_argument("--output", default="github_export",
                        help="Base output directory (default: ./github_export)")
    parser.add_argument("--config", default="config.yaml",
                        help="Config YAML file (default: ./config.yaml)")
    parser.add_argument("--schedule", default="",
                        help="Repeat on a schedule: 6h, 1d, 30m")
    parser.add_argument("--lookback-batch", type=int, default=50,
                        help="Items per lookback batch (default: 50)")
    parser.add_argument("--floor-date", default="",
                        help="Lookback floor date YYYY-MM-DD (default: 2024-01-01)")
    parser.add_argument("--searxng-url", default="",
                        help="SearXNG instance URL e.g. http://localhost:8888")
    parser.add_argument("--list-sources", action="store_true",
                        help="Print all available plugins and exit")
    parser.add_argument("--check", action="store_true",
                        help="Run health checks on all enabled plugins and exit")
    args = parser.parse_args()

    global OUTPUT_DIR, STATE_DIR, EXT_DIR, STATE_FILE
    OUTPUT_DIR = Path(args.output)
    STATE_DIR  = OUTPUT_DIR / "_state"
    EXT_DIR    = OUTPUT_DIR / "_external_sources"
    STATE_FILE = STATE_DIR / "crawl_state.json"

    # ── Collect all plugins ──
    all_plugins = {**BUILTIN_PLUGINS}
    all_plugins.update(load_external_plugins(SOURCES_DIR))

    if args.list_sources:
        print("\n  Available plugins:\n")
        print(f"  {'NAME':<22}  {'LOOKBACK':^9}  {'AUTH':^6}  DESCRIPTION")
        print("  " + "─" * 70)
        for name, p in sorted(all_plugins.items()):
            lb  = "✓" if p.SUPPORTS_LOOKBACK else "—"
            auth = "✓" if p.REQUIRES_AUTH    else "—"
            print(f"  {name:<22}  {lb:^9}  {auth:^6}  {p.DESCRIPTION}")
        print()
        return

    # ── Load config + configure plugins ──
    config       = load_config(Path(args.config))
    plugins      = configure_plugins(all_plugins, config, searxng_url=args.searxng_url)

    # ── Filter to requested sources ──
    if args.sources:
        wanted  = {s.strip() for s in args.sources.split(",") if s.strip()}
        plugins = {k: v for k, v in plugins.items() if k in wanted}
        missing = wanted - set(plugins)
        if missing:
            log(f"Unknown source(s): {', '.join(missing)} — available: {', '.join(all_plugins)}", "WARN")

    if not plugins:
        log("No plugins enabled. Run with --list-sources to see options.", "WARN")
        return

    if args.check:
        print("\n  Plugin health checks:\n")
        for name, plugin in sorted(plugins.items()):
            ok, msg = plugin.health_check()
            mark = "✓" if ok else "✗"
            print(f"  {mark} {name:<22}  {msg}")
        print()
        return

    # ── Init state + dirs ──
    state = CrawlState(STATE_FILE)
    EXT_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    floor_date = None
    if args.floor_date:
        try:
            floor_date = datetime.fromisoformat(args.floor_date).replace(tzinfo=timezone.utc)
        except Exception:
            log(f"Invalid floor-date: {args.floor_date!r} — using default.", "WARN")

    print("\n" + "═" * 60)
    print("  Platform Extractor  v1")
    print(f"  Mode: {args.mode}  |  Sources: {', '.join(plugins)}")
    print("═" * 60)

    def one_run():
        all_counts: dict[str, int] = {}
        if args.mode in ("forward", "both"):
            counts = run_forward_scan(plugins, state, EXT_DIR)
            all_counts.update(counts)
            print_summary(counts, "Forward")
        if args.mode in ("lookback", "both"):
            counts = run_lookback_scan(
                {k: v for k, v in plugins.items() if v.SUPPORTS_LOOKBACK},
                state, EXT_DIR,
                batch_size = args.lookback_batch,
                floor_date = floor_date,
            )
            all_counts.update(counts)
            print_summary(counts, "Lookback")
        return all_counts

    if args.schedule:
        interval = parse_interval(args.schedule)
        if not interval:
            print(f"❌  Cannot parse schedule: {args.schedule!r}")
            sys.exit(1)
        print(f"\n  Scheduled mode — every {args.schedule}.  Press Ctrl+C to stop.\n")
        run_num = 0
        while True:
            run_num += 1
            print(f"\n{'═'*60}")
            print(f"  RUN #{run_num}  —  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("═" * 60)
            try:
                one_run()
            except KeyboardInterrupt:
                print("\n  Stopped.")
                break
            except Exception as e:
                log(f"Run #{run_num} failed: {e}", "ERR")
                traceback.print_exc()
            print(f"\n  ⏱  Next run in {args.schedule}.  Sleeping …\n")
            try:
                time.sleep(interval)
            except KeyboardInterrupt:
                print("\n  Stopped.")
                break
    else:
        one_run()
        g = state._data.get("global", {})
        print(f"  📁 {EXT_DIR.resolve()}")
        print(f"  🗂  Total discovered (all time): {g.get('total_discovered', '?')}\n")


if __name__ == "__main__":
    main()
