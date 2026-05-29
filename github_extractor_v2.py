#!/usr/bin/env python3
"""
GitHub Full Repository Extractor v2
=====================================
Extracts from configurable sources:
  - Owned repos, forks, starred repos
  - GitHub Trending (daily / weekly / monthly, optionally by language)
  - GitHub Collections (GitHub-curated repo lists)

From each repo, extracts:
  1. All text/documentation files (README + configurable extensions)
  2. Full directory tree (every file)
  3. All issues (open + closed) with comments
  4. Full metadata

NEW in v2:
  --sources          select what to include: owned, forks, starred, trending, collections
  --text-extensions  additional file extensions to download content for
  --skip-text-files  only extract tree + metadata + issues (fastest)
  --schedule 6h/1d   run automatically on a recurring schedule
  --trending-langs   filter trending by language (e.g. python,rust)
  --collections-full scrape individual collection pages for their repo lists
  --platform         also run platform_extractor.py after GitHub extraction
  --platform-sources comma-separated platform sources (default: all enabled)
  --searxng-url      SearXNG instance for platform discovery side-channel

HTML Scraping:
  Uses Scrapling (auto-matching, resilient selectors) instead of BeautifulSoup.
  Falls back to requests + BeautifulSoup if Scrapling is not installed.
  Install: pip install scrapling

Output structure:
  github_export/
    _index.json                  ← master index of all repos extracted
    _trending/
      daily.json                 ← today's trending repos (all languages)
      daily_python.json          ← today's trending Python repos
      weekly.json
      monthly.json
    _collections/
      _index.json                ← list of all collections
      clean-code.json            ← repos in that collection
    _external_sources/           ← written by platform_extractor (--platform)
      hackernews/ ...
      paperswithcode/ ...
    _state/
      crawl_state.json           ← platform extractor cursor state
    {owner}__{repo}/
      metadata.json
      directory_tree.txt / .json
      issues.json
      text_files/
        _index.json
        README.md
        docs__guide.md
        ...
      readmes/
        _index.json
        README.md

Install:
  pip install PyGithub requests scrapling
  scrapling install              # optional: Camoufox stealth backend

Usage:
  python github_extractor_v2.py --token ghp_xxx
  python github_extractor_v2.py --token ghp_xxx --sources owned,trending
  python github_extractor_v2.py --sources trending --trending-langs python,rust
  python github_extractor_v2.py --token ghp_xxx --schedule 6h
  python github_extractor_v2.py --sources trending --platform
  python github_extractor_v2.py --sources trending --platform --platform-sources hackernews,pypi
"""

import os
import re
import sys
import json
import time
import subprocess
import argparse
import traceback
from pathlib import Path
from datetime import datetime, timezone
from typing import Optional

try:
    from github import Github, GithubException, RateLimitExceededException
    import requests
except ImportError:
    print("Missing packages. Run: pip install PyGithub requests")
    sys.exit(1)

# ── Scrapling (preferred) ────────────────────────────────────────────────────
try:
    from scrapling.fetchers import Fetcher as ScraplingFetcher
    HAS_SCRAPLING = True
except ImportError:
    HAS_SCRAPLING = False

# ── BeautifulSoup (fallback) ─────────────────────────────────────────────────
try:
    from bs4 import BeautifulSoup
    HAS_BS4 = True
except ImportError:
    HAS_BS4 = False

if not HAS_SCRAPLING and not HAS_BS4:
    print(
        "⚠  Neither Scrapling nor BeautifulSoup is installed.\n"
        "   Trending and Collections scraping will be unavailable.\n"
        "   Install Scrapling (recommended): pip install scrapling\n"
        "   Or BeautifulSoup (fallback):     pip install beautifulsoup4\n"
    )


# ══════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════
OUTPUT_DIR = Path("github_export")
RATE_LIMIT_PAUSE = 60
MAX_RETRIES = 3

DEFAULT_TEXT_EXTENSIONS: set = {
    ".md", ".markdown", ".rst", ".txt", ".adoc", ".asciidoc",
    ".textile", ".rdoc", ".pod", ".wiki",
    ".yaml", ".yml", ".toml", ".ini", ".cfg", ".conf",
    ".json", ".csv", ".tsv", ".xml",
    ".html", ".htm",
    ".tex", ".graphql", ".proto",
}

DEFAULT_TEXT_FILENAMES: set = {
    "dockerfile", "makefile", "procfile", "vagrantfile",
    "gemfile", "pipfile", "requirements.txt", "requirements-dev.txt",
    "license", "licence", "changelog", "changes", "history",
    "contributing", "authors", "maintainers", "notice", "todo",
    "readme", "install", "news", ".gitignore", ".gitattributes",
    ".editorconfig", ".npmrc", "package.json", "composer.json",
    "cargo.toml", "go.mod", "pyproject.toml", "setup.cfg",
    "pipfile.lock", "poetry.lock", "gemfile.lock",
}

MAX_TEXT_FILE_BYTES = 500_000

TRENDING_URL    = "https://github.com/trending"
COLLECTIONS_URL = "https://github.com/collections"
SCRAPE_HEADERS  = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0 Safari/537.36"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ══════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════
def log(msg: str, level: str = "INFO"):
    ts  = datetime.now().strftime("%H:%M:%S")
    sym = {"INFO": "•", "OK": "✓", "WARN": "⚠", "ERR": "✗", "SKIP": "→"}.get(level, "•")
    print(f"  [{ts}] {sym} {msg}")


def safe_filename(name: str) -> str:
    return name.replace("/", "__")


def parse_interval(s: str) -> int:
    total = 0
    for val, unit in re.findall(r'(\d+)\s*([dhms])', s.lower()):
        n = int(val)
        if   unit == 'd': total += n * 86400
        elif unit == 'h': total += n * 3600
        elif unit == 'm': total += n * 60
        elif unit == 's': total += n
    return total


def with_retry(fn, *args, label: str = "", **kwargs):
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            return fn(*args, **kwargs)
        except RateLimitExceededException:
            log(f"Rate limited on '{label}'. Pausing {RATE_LIMIT_PAUSE}s …", "WARN")
            time.sleep(RATE_LIMIT_PAUSE)
        except GithubException as e:
            if e.status in (409, 404):
                log(f"'{label}' inaccessible ({e.status}). Skipping.", "SKIP")
                return None
            if attempt == MAX_RETRIES:
                log(f"GitHub error on '{label}': {e}", "ERR")
                return None
            time.sleep(5 * attempt)
        except Exception as e:
            if attempt == MAX_RETRIES:
                log(f"Unexpected error on '{label}': {e}", "ERR")
                return None
            time.sleep(3 * attempt)
    return None


# ══════════════════════════════════════════════════════════
# TEXT FILE DETECTION
# ══════════════════════════════════════════════════════════
def is_text_file(path: str, extensions: set, filenames: set) -> bool:
    p          = Path(path)
    name_lower = p.name.lower()
    suffix     = p.suffix.lower()
    if name_lower in filenames:
        return True
    for ext in extensions:
        if len(ext) > 4 and name_lower.endswith(ext):
            return True
    return suffix in extensions


def is_readme(path: str) -> bool:
    return Path(path).name.upper().startswith("README")


# ══════════════════════════════════════════════════════════
# SCRAPLING FETCH HELPER
# ══════════════════════════════════════════════════════════
def _fetch_page(url: str, session: Optional[requests.Session] = None):
    """
    Fetch a page and return a (page_object, raw_text) tuple.
    page_object supports .css(selector) if Scrapling is available,
    otherwise falls back to BeautifulSoup.
    Returns (None, None) on failure.
    """
    if HAS_SCRAPLING:
        try:
            fetcher = ScraplingFetcher(auto_match=True)
            page    = fetcher.get(url, headers=SCRAPE_HEADERS, timeout=20)
            return page, None
        except Exception as e:
            log(f"Scrapling fetch failed for {url}: {e} — trying requests fallback.", "WARN")

    # Fallback: requests + BeautifulSoup
    sess = session or requests.Session()
    try:
        resp = sess.get(url, headers=SCRAPE_HEADERS, timeout=20)
        resp.raise_for_status()
        if HAS_BS4:
            soup = BeautifulSoup(resp.text, "html.parser")
            return _BS4Wrapper(soup), None
        return None, resp.text
    except Exception as e:
        log(f"Could not fetch {url}: {e}", "ERR")
        return None, None


class _BS4Wrapper:
    """Minimal wrapper so BS4 results look like Scrapling results."""
    def __init__(self, soup):
        self._soup = soup

    def css(self, selector: str) -> list:
        return [_BS4ElementWrapper(el) for el in self._soup.select(selector)]

    def css_first(self, selector: str):
        el = self._soup.select_one(selector)
        return _BS4ElementWrapper(el) if el else None


class _BS4ElementWrapper:
    def __init__(self, el):
        self._el = el

    @property
    def text(self) -> str:
        return self._el.get_text(strip=True) if self._el else ""

    @property
    def attrib(self) -> dict:
        return dict(self._el.attrs) if self._el else {}

    def css(self, selector: str) -> list:
        return [_BS4ElementWrapper(e) for e in self._el.select(selector)] if self._el else []

    def css_first(self, selector: str):
        if not self._el:
            return None
        el = self._el.select_one(selector)
        return _BS4ElementWrapper(el) if el else None

    def find_parent(self, tags):
        if not self._el:
            return None
        p = self._el.find_parent(tags)
        return _BS4ElementWrapper(p) if p else None


# ══════════════════════════════════════════════════════════
# 1. METADATA
# ══════════════════════════════════════════════════════════
def extract_metadata(repo) -> dict:
    def ts(dt): return dt.isoformat() if dt else None

    meta = {
        "id":          repo.id,
        "node_id":     repo.node_id,
        "full_name":   repo.full_name,
        "name":        repo.name,
        "owner": {
            "login":      repo.owner.login,
            "id":         repo.owner.id,
            "type":       repo.owner.type,
            "avatar_url": repo.owner.avatar_url,
            "html_url":   repo.owner.html_url,
        },
        "description":      repo.description,
        "homepage":         repo.homepage,
        "html_url":         repo.html_url,
        "clone_url":        repo.clone_url,
        "ssh_url":          repo.ssh_url,
        "default_branch":   repo.default_branch,
        "language":         repo.language,
        "languages":        {},
        "topics":           [],
        "visibility":       getattr(repo, "visibility", "private" if repo.private else "public"),
        "private":          repo.private,
        "fork":             repo.fork,
        "archived":         repo.archived,
        "has_issues":       repo.has_issues,
        "has_wiki":         repo.has_wiki,
        "has_pages":        repo.has_pages,
        "has_discussions":  getattr(repo, "has_discussions", False),
        "size_kb":          repo.size,
        "stargazers_count": repo.stargazers_count,
        "watchers_count":   repo.watchers_count,
        "forks_count":      repo.forks_count,
        "open_issues_count":repo.open_issues_count,
        "pushed_at":        ts(repo.pushed_at),
        "created_at":       ts(repo.created_at),
        "updated_at":       ts(repo.updated_at),
        "license":          None,
        "parent":           None,
        "source":           None,
    }

    try:
        meta["languages"] = with_retry(repo.get_languages, label=f"{repo.full_name}/languages") or {}
    except Exception:
        pass

    try:
        meta["topics"] = list(repo.get_topics()) if hasattr(repo, "get_topics") else []
    except Exception:
        pass

    if repo.license:
        try:
            meta["license"] = {
                "key":     repo.license.key,
                "name":    repo.license.name,
                "spdx_id": repo.license.spdx_id,
            }
        except Exception:
            pass

    if repo.fork:
        try:
            if repo.parent:
                meta["parent"] = {"full_name": repo.parent.full_name, "html_url": repo.parent.html_url}
            if repo.source:
                meta["source"] = {"full_name": repo.source.full_name, "html_url": repo.source.html_url}
        except Exception:
            pass

    return meta


# ══════════════════════════════════════════════════════════
# 2. DIRECTORY TREE
# ══════════════════════════════════════════════════════════
def extract_tree(repo) -> tuple:
    branch = repo.default_branch or "main"
    try:
        tree = with_retry(repo.get_git_tree, branch, recursive=True, label=f"{repo.full_name}/tree")
        if tree is None:
            return [], "(empty repository)"

        items = [
            {"path": i.path, "type": i.type, "mode": i.mode, "sha": i.sha, "size": i.size}
            for i in tree.tree
        ]

        text_lines = [f"📁 {repo.full_name}  [{branch}]", ""]
        for path in sorted(i["path"] for i in items):
            parts  = path.split("/")
            depth  = len(parts) - 1
            indent = "    " * depth
            name   = parts[-1]
            entry  = next((i for i in items if i["path"] == path), {})
            icon   = "📁" if entry.get("type") == "tree" else "📄"
            sz     = entry.get("size") or 0
            size_str = ""
            if entry.get("type") == "blob" and sz:
                size_str = f"  ({sz/1024:.1f} KB)" if sz >= 1024 else f"  ({sz} B)"
            text_lines.append(f"{indent}{icon} {name}{size_str}")

        truncated = ""
        if getattr(tree, "truncated", False):
            truncated = "\n\n⚠ Tree truncated by GitHub API (repo has >100k files)."
            log(f"Tree truncated for {repo.full_name}", "WARN")

        return items, "\n".join(text_lines) + truncated

    except Exception as e:
        log(f"Tree extraction failed for {repo.full_name}: {e}", "ERR")
        return [], f"(error: {e})"


# ══════════════════════════════════════════════════════════
# 3. TEXT FILES
# ══════════════════════════════════════════════════════════
def extract_text_files(repo, tree_items, extensions, filenames, max_bytes=MAX_TEXT_FILE_BYTES):
    candidates = []
    for item in tree_items:
        if item.get("type") != "blob":
            continue
        sz = item.get("size") or 0
        if sz > max_bytes:
            continue
        if is_text_file(item["path"], extensions, filenames):
            candidates.append(item["path"])

    if not candidates:
        try:
            root = with_retry(repo.get_readme, label=f"{repo.full_name}/readme")
            if root:
                entry = {
                    "path":      root.path,
                    "content":   root.decoded_content.decode("utf-8", errors="replace"),
                    "encoding":  root.encoding,
                    "size":      root.size,
                    "is_readme": True,
                }
                return [entry], [entry]
        except Exception:
            pass
        return [], []

    branch  = repo.default_branch or "main"
    results = []
    for fpath in candidates:
        try:
            contents = with_retry(
                repo.get_contents, fpath, ref=branch,
                label=f"{repo.full_name}/{fpath}"
            )
            if not contents:
                continue
            if isinstance(contents, list):
                contents = contents[0]
            text = contents.decoded_content.decode("utf-8", errors="replace")
            results.append({
                "path":      fpath,
                "content":   text,
                "encoding":  contents.encoding,
                "size":      contents.size,
                "is_readme": is_readme(fpath),
            })
        except Exception as e:
            log(f"Could not fetch {fpath}: {e}", "WARN")

    readmes = [r for r in results if r["is_readme"]]
    return results, readmes


# ══════════════════════════════════════════════════════════
# 4. ISSUES
# ══════════════════════════════════════════════════════════
def extract_issues(repo) -> list:
    def ts(dt): return dt.isoformat() if dt else None

    all_issues = []
    for state in ("open", "closed"):
        try:
            paged = with_retry(
                repo.get_issues, state=state,
                label=f"{repo.full_name}/issues[{state}]"
            )
            if not paged:
                continue
            for issue in paged:
                if issue.pull_request:
                    continue
                issue_data = {
                    "number":     issue.number,
                    "title":      issue.title,
                    "state":      issue.state,
                    "body":       issue.body,
                    "user":       issue.user.login if issue.user else None,
                    "assignees":  [a.login for a in issue.assignees],
                    "labels":     [l.name for l in issue.labels],
                    "milestone":  issue.milestone.title if issue.milestone else None,
                    "created_at": ts(issue.created_at),
                    "updated_at": ts(issue.updated_at),
                    "closed_at":  ts(issue.closed_at),
                    "closed_by":  issue.closed_by.login if issue.closed_by else None,
                    "html_url":   issue.html_url,
                    "reactions":  {},
                    "comments":   [],
                }
                try:
                    for r in issue.get_reactions():
                        issue_data["reactions"][r.content] = \
                            issue_data["reactions"].get(r.content, 0) + 1
                except Exception:
                    pass
                try:
                    for c in issue.get_comments():
                        issue_data["comments"].append({
                            "id":         c.id,
                            "user":       c.user.login if c.user else None,
                            "body":       c.body,
                            "created_at": ts(c.created_at),
                            "updated_at": ts(c.updated_at),
                            "html_url":   c.html_url,
                        })
                except Exception:
                    pass
                all_issues.append(issue_data)
        except Exception as e:
            log(f"Issues fetch error ({state}): {e}", "WARN")

    all_issues.sort(key=lambda x: x["number"])
    return all_issues


# ══════════════════════════════════════════════════════════
# 5. GITHUB TRENDING SCRAPER  (Scrapling-first)
# ══════════════════════════════════════════════════════════
def scrape_trending(
    since:    str = "daily",
    language: str = "",
    session:  Optional[requests.Session] = None,
) -> list:
    if not HAS_SCRAPLING and not HAS_BS4:
        log("No scraping library available — install scrapling.", "WARN")
        return []

    url  = f"{TRENDING_URL}/{language.lower()}" if language else TRENDING_URL
    url += f"?since={since}"

    page, _ = _fetch_page(url, session)
    if page is None:
        return []

    articles = page.css("article.Box-row")
    if not articles:
        log("No trending articles found — GitHub may have updated their HTML.", "WARN")
        return []

    results = []
    for rank, article in enumerate(articles, 1):
        try:
            h2_link   = article.css_first("h2 a")
            if not h2_link:
                continue
            full_name = h2_link.attrib.get("href", "").strip("/")

            desc_el     = article.css_first("p") or article.css_first(".color-fg-muted p")
            description = desc_el.text if desc_el else ""

            lang_el   = article.css_first('[itemprop="programmingLanguage"]')
            lang_tag  = lang_el.text if lang_el else ""

            stars_el  = article.css_first('a[href$="/stargazers"]')
            stars_raw = stars_el.text.replace(",", "").replace(" ", "") if stars_el else "0"
            try:
                stars = int(float(stars_raw.lower().replace("k", "")) * 1000) \
                        if "k" in stars_raw.lower() else int(stars_raw)
            except Exception:
                stars = 0

            forks_el  = article.css_first('a[href$="/network/members"]')
            forks_raw = forks_el.text.replace(",", "") if forks_el else "0"
            try:
                forks = int(forks_raw)
            except Exception:
                forks = 0

            period_els  = article.css(".f6 span.d-inline-block")
            period_text = period_els[-1].text if period_els else ""

            contributors = [
                img.attrib.get("alt", "").lstrip("@")
                for img in article.css("a img.avatar")
            ][:5]

            results.append({
                "rank":             rank,
                "full_name":        full_name,
                "url":              f"https://github.com/{full_name}",
                "description":      description,
                "language":         lang_tag,
                "stars":            stars,
                "forks":            forks,
                "stars_this_period": period_text,
                "contributors":     contributors,
                "since":            since,
                "scraped_at":       datetime.now().isoformat(),
            })
        except Exception as e:
            log(f"Error parsing trending article #{rank}: {e}", "WARN")

    log(f"Trending ({since}, lang={language or 'all'}): {len(results)} repos", "OK")
    return results


# ══════════════════════════════════════════════════════════
# 6. GITHUB COLLECTIONS SCRAPER  (Scrapling-first)
# ══════════════════════════════════════════════════════════
def scrape_collections(
    session: Optional[requests.Session] = None,
    max_collections: int = 50,
) -> list:
    if not HAS_SCRAPLING and not HAS_BS4:
        log("No scraping library available — install scrapling.", "WARN")
        return []

    page, _ = _fetch_page(COLLECTIONS_URL, session)
    if page is None:
        return []

    results   = []
    seen_slugs = set()

    for link in page.css("a[href^='/collections/']"):
        href = link.attrib.get("href", "")
        slug = href.replace("/collections/", "").strip("/")
        if not slug or "/" in slug or slug in seen_slugs:
            continue
        seen_slugs.add(slug)

        parent = link.find_parent(["article", "div", "li"])
        name   = slug.replace("-", " ").title()
        desc   = ""
        if parent:
            h = parent.css_first("h1") or parent.css_first("h2") or parent.css_first("h3")
            if h:
                name = h.text
            p = parent.css_first("p")
            if p:
                desc = p.text

        results.append({
            "slug":        slug,
            "name":        name,
            "description": desc,
            "url":         f"https://github.com/collections/{slug}",
            "repos":       [],
        })
        if len(results) >= max_collections:
            break

    log(f"Found {len(results)} GitHub Collections", "OK")
    return results


def scrape_collection_repos(
    slug:    str,
    session: Optional[requests.Session] = None,
) -> list:
    page, _ = _fetch_page(f"https://github.com/collections/{slug}", session)
    if page is None:
        return []

    repos = []
    for article in page.css("article.border") + page.css("article.Box-row"):
        try:
            link = (
                article.css_first("h1 a") or article.css_first("h2 a") or
                article.css_first("h3 a") or article.css_first(".f3 a") or
                article.css_first(".f4 a")
            )
            if not link:
                continue
            full_name = link.attrib.get("href", "").strip("/")
            if not full_name or full_name.count("/") != 1:
                continue

            p    = article.css_first("p") or article.css_first(".color-fg-muted")
            desc = p.text if p else ""

            lang_el = article.css_first('[itemprop="programmingLanguage"]')
            lang    = lang_el.text if lang_el else ""

            stars_el  = article.css_first('a[href$="/stargazers"]')
            stars_raw = stars_el.text.replace(",", "") if stars_el else "0"
            try:
                stars = int(stars_raw)
            except Exception:
                stars = 0

            repos.append({
                "full_name":   full_name,
                "url":         f"https://github.com/{full_name}",
                "description": desc,
                "language":    lang,
                "stars":       stars,
            })
        except Exception:
            pass
    return repos


# ══════════════════════════════════════════════════════════
# WRITE OUTPUT
# ══════════════════════════════════════════════════════════
def write_repo_output(repo_dir, metadata, tree_items, tree_text, text_files, issues):
    repo_dir.mkdir(parents=True, exist_ok=True)
    (repo_dir / "metadata.json").write_text(
        json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (repo_dir / "directory_tree.txt").write_text(tree_text, encoding="utf-8")
    (repo_dir / "directory_tree.json").write_text(
        json.dumps(tree_items, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    (repo_dir / "issues.json").write_text(
        json.dumps(issues, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    tf_dir = repo_dir / "text_files"
    tf_dir.mkdir(exist_ok=True)
    tf_index = []
    for tf in text_files:
        safe_name = tf["path"].replace("/", "__")
        (tf_dir / safe_name).write_text(tf["content"], encoding="utf-8")
        tf_index.append({
            "original_path": tf["path"],
            "saved_as":      safe_name,
            "size":          tf["size"],
            "is_readme":     tf["is_readme"],
        })
    (tf_dir / "_index.json").write_text(
        json.dumps(tf_index, indent=2, ensure_ascii=False), encoding="utf-8"
    )

    rm_dir = repo_dir / "readmes"
    rm_dir.mkdir(exist_ok=True)
    rm_index = []
    for tf in text_files:
        if not tf["is_readme"]:
            continue
        safe_name = tf["path"].replace("/", "__")
        (rm_dir / safe_name).write_text(tf["content"], encoding="utf-8")
        rm_index.append({
            "original_path": tf["path"],
            "saved_as":      safe_name,
            "size":          tf["size"],
        })
    (rm_dir / "_index.json").write_text(
        json.dumps(rm_index, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def write_trending_output(output_dir, since, language, results):
    td = output_dir / "_trending"
    td.mkdir(exist_ok=True)
    suffix = f"_{language.lower()}" if language else ""
    data   = {
        "scraped_at":      datetime.now().isoformat(),
        "since":           since,
        "language_filter": language or "all",
        "count":           len(results),
        "repos":           results,
    }
    (td / f"{since}{suffix}.json").write_text(
        json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log(f"Saved _trending/{since}{suffix}.json  ({len(results)} repos)", "OK")


def write_collections_output(output_dir, collections):
    cd = output_dir / "_collections"
    cd.mkdir(exist_ok=True)
    for coll in collections:
        (cd / f"{coll['slug']}.json").write_text(
            json.dumps(coll, indent=2, ensure_ascii=False), encoding="utf-8"
        )
    idx = {
        "scraped_at":  datetime.now().isoformat(),
        "count":       len(collections),
        "collections": [
            {"slug": c["slug"], "name": c["name"], "url": c["url"]}
            for c in collections
        ],
    }
    (cd / "_index.json").write_text(
        json.dumps(idx, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    log(f"Saved {len(collections)} collections → _collections/", "OK")


# ══════════════════════════════════════════════════════════
# PROCESS ONE REPO
# ══════════════════════════════════════════════════════════
def process_repo(repo, repo_dir, is_starred, skip_issues, skip_text_files,
                 text_extensions, text_filenames):
    label   = repo.full_name
    summary = {
        "full_name":       label,
        "is_fork":         repo.fork,
        "is_starred":      is_starred,
        "status":          "ok",
        "file_count":      0,
        "text_file_count": 0,
        "readme_count":    0,
        "issue_count":     0,
        "error":           None,
    }

    try:
        metadata             = extract_metadata(repo)
        metadata["_is_starred"] = is_starred

        log("  → Directory tree …")
        tree_items, tree_text = extract_tree(repo)
        summary["file_count"] = sum(1 for i in tree_items if i.get("type") == "blob")

        text_files, readmes = [], []
        if not skip_text_files:
            log(f"  → Text files ({len(text_extensions)} ext types) …")
            text_files, readmes = extract_text_files(
                repo, tree_items, text_extensions, text_filenames
            )
            summary["text_file_count"] = len(text_files)
            summary["readme_count"]    = len(readmes)

        issues = []
        if not skip_issues:
            log("  → Issues …")
            issues = extract_issues(repo)
            summary["issue_count"] = len(issues)

        write_repo_output(repo_dir, metadata, tree_items, tree_text, text_files, issues)

        log(
            f"  ✓ {summary['file_count']} files  |  "
            f"{summary['text_file_count']} text files ({summary['readme_count']} READMEs)  |  "
            f"{summary['issue_count']} issues",
            "OK"
        )

    except Exception as e:
        summary["status"] = "error"
        summary["error"]  = str(e)
        log(f"Fatal error on {label}: {e}", "ERR")
        traceback.print_exc()

    return summary


# ══════════════════════════════════════════════════════════
# PLATFORM EXTRACTOR INTEGRATION
# ══════════════════════════════════════════════════════════
def run_platform_extractor(args):
    """Launch platform_extractor.py as a subprocess after GitHub extraction."""
    extractor_path = Path(__file__).parent / "platform_extractor.py"
    if not extractor_path.exists():
        log("platform_extractor.py not found — skipping external sources.", "WARN")
        log("Place platform_extractor.py alongside this script to enable it.", "WARN")
        return

    cmd = [sys.executable, str(extractor_path), "--mode", "forward"]
    if args.output:
        cmd += ["--output", args.output]
    if getattr(args, "platform_sources", ""):
        cmd += ["--sources", args.platform_sources]
    if getattr(args, "searxng_url", ""):
        cmd += ["--searxng-url", args.searxng_url]

    print("\n  ── External Platform Sources ───────────────────────")
    log("Running platform_extractor.py …")
    try:
        subprocess.run(cmd, check=False)
    except Exception as e:
        log(f"platform_extractor.py failed: {e}", "ERR")


# ══════════════════════════════════════════════════════════
# FULL EXTRACTION RUN
# ══════════════════════════════════════════════════════════
def run_extraction(args, g, user):
    output  = OUTPUT_DIR
    output.mkdir(parents=True, exist_ok=True)
    sources = {s.strip().lower() for s in args.sources.split(",")}

    text_extensions = set(DEFAULT_TEXT_EXTENSIONS)
    text_filenames  = set(DEFAULT_TEXT_FILENAMES)
    if args.text_extensions:
        for e in args.text_extensions.split(","):
            e = e.strip().lower()
            if e and not e.startswith("."):
                e = "." + e
            if e:
                text_extensions.add(e)

    print(f"\n  Sources    : {', '.join(sorted(sources))}")
    print(f"  Text types : {len(text_extensions)} extensions + {len(text_filenames)} named files")
    scraper_name = "Scrapling" if HAS_SCRAPLING else "BeautifulSoup" if HAS_BS4 else "NONE"
    print(f"  HTML scraper: {scraper_name}")
    print()

    session      = requests.Session()
    master_index = []
    start        = time.time()

    # ── Trending ─────────────────────────────────────────
    if "trending" in sources:
        print("  ── GitHub Trending ────────────────────────")
        langs = [l.strip() for l in (args.trending_langs or "").split(",") if l.strip()]
        if not langs:
            langs = [""]
        for since in ["daily", "weekly", "monthly"]:
            for lang in langs:
                results = scrape_trending(since=since, language=lang, session=session)
                if results:
                    write_trending_output(output, since, lang, results)
                time.sleep(1)
        print()

    # ── Collections ──────────────────────────────────────
    if "collections" in sources:
        print("  ── GitHub Collections ─────────────────────")
        collections = scrape_collections(session=session)
        if collections:
            if getattr(args, "collections_full", False):
                log("Fetching individual collection repo lists …")
                for coll in collections:
                    coll["repos"] = scrape_collection_repos(coll["slug"], session=session)
                    log(f"  {coll['slug']}: {len(coll['repos'])} repos", "OK")
                    time.sleep(0.5)
            write_collections_output(output, collections)
        print()

    # ── Repos (owned / forks / starred) ──────────────────
    wants_owned   = "owned"   in sources
    wants_forks   = "forks"   in sources
    wants_starred = "starred" in sources
    repos_to_process = []

    if args.repo:
        r = with_retry(g.get_repo, args.repo, label=args.repo)
        if r:
            repos_to_process.append((r, False))
    else:
        if wants_owned or wants_forks:
            print("  Fetching owned/forked repos …")
            for repo in user.get_repos(type="owner"):
                if repo.fork and not wants_forks:
                    continue
                if not repo.fork and not wants_owned:
                    continue
                repos_to_process.append((repo, False))
            print(f"  → {len(repos_to_process)} repos found")

        if wants_starred:
            print("  Fetching starred repos …")
            before = len(repos_to_process)
            seen   = {r.full_name for r, _ in repos_to_process}
            for repo in user.get_starred():
                if repo.full_name not in seen:
                    repos_to_process.append((repo, True))
                    seen.add(repo.full_name)
            print(f"  → {len(repos_to_process) - before} starred repos found")

    total = len(repos_to_process)
    if total:
        print(f"\n  Total repos to process: {total}")
        print("─" * 60 + "\n")

    for idx, (repo, is_starred) in enumerate(repos_to_process, 1):
        print(f"\n[{idx}/{total}] {repo.full_name}")
        repo_dir = output / safe_filename(repo.full_name)

        if args.resume and (repo_dir / "metadata.json").exists():
            log("Already extracted — skipping (--resume).", "SKIP")
            master_index.append({"full_name": repo.full_name, "status": "skipped_resume"})
            continue

        summary = process_repo(
            repo, repo_dir, is_starred,
            skip_issues     = args.skip_issues,
            skip_text_files = args.skip_text_files,
            text_extensions = text_extensions,
            text_filenames  = text_filenames,
        )
        master_index.append(summary)

        (output / "_index.json").write_text(
            json.dumps({
                "extracted_at": datetime.now().isoformat(),
                "github_user":  user.login,
                "sources":      args.sources,
                "repos":        master_index,
            }, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        if idx % 10 == 0:
            try:
                rl      = g.get_rate_limit().core
                elapsed = time.time() - start
                eta     = (elapsed / idx) * (total - idx)
                print(
                    f"\n  ── {idx}/{total} repos  |  "
                    f"{rl.remaining} API calls left  |  "
                    f"ETA ~{eta/60:.1f} min ──\n"
                )
                if rl.remaining < 100:
                    reset_in = (
                        rl.reset.replace(tzinfo=timezone.utc)
                        - datetime.now(timezone.utc)
                    ).total_seconds()
                    log(f"API nearly exhausted. Waiting {reset_in:.0f}s for reset …", "WARN")
                    time.sleep(max(reset_in + 5, 0))
            except Exception:
                pass

    elapsed   = time.time() - start
    ok_count  = sum(1 for s in master_index if s.get("status") == "ok")
    err_count = sum(1 for s in master_index if s.get("status") == "error")

    (output / "_index.json").write_text(
        json.dumps({
            "extracted_at":    datetime.now().isoformat(),
            "github_user":     user.login,
            "sources":         args.sources,
            "total_repos":     total,
            "successful":      ok_count,
            "errors":          err_count,
            "elapsed_seconds": round(elapsed, 1),
            "output_dir":      str(output.resolve()),
            "repos":           master_index,
        }, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print("\n" + "═" * 60)
    print(f"  ✅ GitHub extraction complete in {elapsed/60:.1f} min")
    if total:
        print(f"  ✓ {ok_count} repos extracted" + (f"   ✗ {err_count} errors" if err_count else ""))
    print(f"  📁 {output.resolve()}")
    print("═" * 60 + "\n")

    # ── Optional: run platform_extractor ──
    if getattr(args, "platform", False):
        run_platform_extractor(args)


# ══════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════
def main():
    parser = argparse.ArgumentParser(
        description="GitHub Full Repository Extractor v2",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
SOURCES (comma-separated list, passed to --sources):
  owned        Your own repositories
  forks        Repositories you have forked
  starred      Repositories you have starred
  trending     GitHub Trending (daily + weekly + monthly)
  collections  GitHub curated collections

EXAMPLES:
  python github_extractor_v2.py --token ghp_xxx
  python github_extractor_v2.py --sources trending,collections --platform
  python github_extractor_v2.py --token ghp_xxx --sources owned,trending --trending-langs python,rust
  python github_extractor_v2.py --token ghp_xxx --schedule 6h --platform
  python github_extractor_v2.py --sources trending --platform --platform-sources hackernews,pypi,cratesio
        """
    )
    parser.add_argument("--token", "-t",
                        default=os.environ.get("GITHUB_TOKEN", ""),
                        help="GitHub Personal Access Token (or GITHUB_TOKEN env var)")
    parser.add_argument("--output", "-o",
                        default="github_export",
                        help="Output directory  (default: ./github_export)")
    parser.add_argument("--sources",
                        default="owned,forks,starred",
                        help="Comma-separated sources: owned,forks,starred,trending,collections")
    parser.add_argument("--trending-langs", default="",
                        help="Language filters for trending, e.g. python,rust,javascript")
    parser.add_argument("--collections-full", action="store_true",
                        help="Scrape each collection's repo list (slower but richer)")
    parser.add_argument("--text-extensions", default="",
                        help="Extra extensions to extract content for, e.g. .graphql,.proto")
    parser.add_argument("--skip-text-files", action="store_true",
                        help="Skip text-file content extraction (tree + metadata + issues only)")
    parser.add_argument("--skip-issues", action="store_true",
                        help="Skip issue extraction (2–3× faster)")
    parser.add_argument("--repo", "-r", default=None,
                        help="Process one specific repo: owner/repo")
    parser.add_argument("--resume", action="store_true",
                        help="Skip repos already extracted (safe to re-run after interruption)")
    parser.add_argument("--schedule", default="",
                        help="Run on a repeating schedule: 30m, 6h, 1d …")

    # Platform extractor integration
    parser.add_argument("--platform", action="store_true",
                        help="Also run platform_extractor.py after GitHub extraction")
    parser.add_argument("--platform-sources", default="",
                        help="Platform sources to run (default: all enabled in config)")
    parser.add_argument("--searxng-url", default="",
                        help="SearXNG instance URL for platform discovery side-channel")

    args = parser.parse_args()

    global OUTPUT_DIR
    OUTPUT_DIR = Path(args.output)

    sources     = {s.strip().lower() for s in args.sources.split(",")}
    needs_token = bool(sources & {"owned", "forks", "starred"}) or bool(args.repo)

    if not args.token and needs_token:
        print("\n❌  No GitHub token provided (required for owned / forks / starred).")
        print("    export GITHUB_TOKEN=ghp_yourtoken")
        sys.exit(1)

    g    = None
    user = None
    if args.token:
        g = Github(args.token, per_page=100)
        try:
            user = g.get_user()
            print(f"\n  Authenticated as: @{user.login} ({user.name or 'no name set'})")
            rl = g.get_rate_limit().core
            print(f"  Rate limit: {rl.remaining}/5000 calls remaining")
        except Exception as e:
            print(f"\n❌  Authentication failed: {e}")
            sys.exit(1)

    class _AnonUser:
        login = "anonymous"
        name  = None
        def get_repos(self, **_): return []
        def get_starred(self):    return []

    if user is None:
        user = _AnonUser()
        g    = g or object()

    print("\n" + "═" * 60)
    print("  GitHub Full Repository Extractor  v2")
    print("═" * 60)

    if args.schedule:
        interval = parse_interval(args.schedule)
        if not interval:
            print(f"❌  Cannot parse schedule: {args.schedule!r}  (use e.g. 6h, 1d, 30m)")
            sys.exit(1)
        print(f"\n  Scheduled mode — running every {args.schedule}")
        print("  Press Ctrl+C to stop.\n")
        run_num = 0
        while True:
            run_num += 1
            print(f"\n{'═'*60}")
            print(f"  RUN #{run_num}  —  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            print("═" * 60)
            try:
                run_extraction(args, g, user)
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
        run_extraction(args, g, user)


if __name__ == "__main__":
    main()
