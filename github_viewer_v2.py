#!/usr/bin/env python3
"""
GitHub Export Viewer  v2
=========================
Browse the github_export/ directory produced by github_extractor_v2.py
and github_export/_external_sources/ produced by platform_extractor.py.

Commands:
  (no args)                          Overall stats
  list                               All repos in a table
  show    <owner__repo>              Detailed summary for one repo
  text    <owner__repo> [ext]        All text files (optionally filter by extension)
  readmes <owner__repo>              README files only
  issues  <owner__repo>              All issues (open + closed)
  tree    <owner__repo>              Directory tree
  search  <keyword>                  Search metadata, descriptions, and topics
  trending [daily|weekly|monthly]    GitHub Trending results
  trending weekly python             Weekly trending, Python only
  collections                        List all scraped GitHub Collections
  collection <slug>                  Repos inside one collection
  sources                            Which sources were used in last extraction

  ── External Platform Sources (platform_extractor.py) ──
  external                           Summary of all external source data
  external <source>                  All discoveries from one source (e.g. hackernews)
  external <source> [date]           Forward-scan file for a specific date
  discoveries [keyword]              Search across all external source discoveries
  discoveries --source <name>        Filter discoveries to one source
  discoveries --min-score <n>        Filter by minimum score
  ext-summary                        Compact stats table across all sources

Examples:
  python github_viewer_v2.py
  python github_viewer_v2.py list
  python github_viewer_v2.py show kenechukwu__solar-sizer-pro
  python github_viewer_v2.py text kenechukwu__solar-sizer-pro .yaml
  python github_viewer_v2.py trending weekly
  python github_viewer_v2.py collections
  python github_viewer_v2.py collection clean-code
  python github_viewer_v2.py search "machine learning"
  python github_viewer_v2.py external
  python github_viewer_v2.py external hackernews
  python github_viewer_v2.py external hackernews 2026-05-27
  python github_viewer_v2.py discoveries pytorch
  python github_viewer_v2.py discoveries --source paperswithcode --min-score 50
  python github_viewer_v2.py ext-summary
"""

import sys
import json
import re
from pathlib import Path
from datetime import datetime

EXPORT_DIR = Path("github_export")
EXT_DIR    = EXPORT_DIR / "_external_sources"

VIEWER_TRUNCATE = 6_000


# ══════════════════════════════════════════════════════════
# HELPERS
# ══════════════════════════════════════════════════════════
def load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def fmt_num(n) -> str:
    return f"{n:,}" if isinstance(n, int) else str(n)


def divider(char="─", width=70):
    print(char * width)


def header(title: str):
    print(f"\n  {'═'*60}")
    print(f"  {title}")
    print(f"  {'═'*60}\n")


def _truncate(s: str, n: int = 80) -> str:
    s = (s or "").replace("\n", " ")
    return s[:n] + "…" if len(s) > n else s


# ══════════════════════════════════════════════════════════
# STATS
# ══════════════════════════════════════════════════════════
def cmd_stats():
    index = load_json(EXPORT_DIR / "_index.json")
    if not index:
        print("\n  No _index.json found. Run github_extractor_v2.py first.\n")
        return

    repos         = index.get("repos", [])
    total_files   = sum(r.get("file_count", 0)       for r in repos)
    total_text    = sum(r.get("text_file_count", 0)  for r in repos)
    total_readmes = sum(r.get("readme_count", 0)     for r in repos)
    total_issues  = sum(r.get("issue_count", 0)      for r in repos)
    forks         = sum(1 for r in repos if r.get("is_fork"))
    starred       = sum(1 for r in repos if r.get("is_starred"))
    owned         = sum(1 for r in repos if not r.get("is_fork") and not r.get("is_starred"))
    errors        = sum(1 for r in repos if r.get("status") == "error")

    td_dir    = EXPORT_DIR / "_trending"
    td_files  = list(td_dir.glob("*.json")) if td_dir.exists() else []
    cd_dir    = EXPORT_DIR / "_collections"
    cd_index  = load_json(cd_dir / "_index.json") if cd_dir.exists() else None
    coll_count = cd_index.get("count", 0) if cd_index else 0

    # External sources summary
    ext_sources = 0
    ext_total   = 0
    if EXT_DIR.exists():
        for src_dir in EXT_DIR.iterdir():
            if src_dir.is_dir():
                ext_sources += 1
                fwd = src_dir / "forward"
                if fwd.exists():
                    for f in fwd.glob("*.json"):
                        try:
                            data = load_json(f)
                            ext_total += len(data) if isinstance(data, list) else 0
                        except Exception:
                            pass

    elapsed_min = index.get("elapsed_seconds", 0) / 60

    print(f"""
  ╔══════════════════════════════════════════════╗
  ║       GitHub Export Summary  v2              ║
  ╚══════════════════════════════════════════════╝

  User         : @{index.get("github_user", "?")}
  Extracted at : {index.get("extracted_at", "?")[:19].replace("T", "  ")}
  Sources      : {index.get("sources", "?")}
  Elapsed      : {elapsed_min:.1f} minutes

  ┌───────────────────────────────────────────┐
  │  Repositories     {fmt_num(len(repos)):>8}                │
  │    Owned          {fmt_num(owned):>8}                │
  │    Forks          {fmt_num(forks):>8}                │
  │    Starred        {fmt_num(starred):>8}                │
  │                                           │
  │  Total files      {fmt_num(total_files):>8}                │
  │  Text files       {fmt_num(total_text):>8}                │
  │  READMEs          {fmt_num(total_readmes):>8}                │
  │  Issues           {fmt_num(total_issues):>8}                │
  │                                           │
  │  Trending sets    {fmt_num(len(td_files)):>8}                │
  │  Collections      {fmt_num(coll_count):>8}                │
  │                                           │
  │  Ext. sources     {fmt_num(ext_sources):>8}                │
  │  Ext. discoveries {fmt_num(ext_total):>8}                │
  │                                           │
  │  Errors           {fmt_num(errors):>8}                │
  └───────────────────────────────────────────┘
  Output → {index.get("output_dir", str(EXPORT_DIR))}
""")


# ══════════════════════════════════════════════════════════
# LIST
# ══════════════════════════════════════════════════════════
def cmd_list():
    index = load_json(EXPORT_DIR / "_index.json")
    if not index:
        print("  No _index.json found.")
        return
    repos = sorted(index.get("repos", []), key=lambda r: r.get("full_name", ""))
    print(f"\n  {'REPO':<44} {'FILES':>7} {'TEXT':>6} {'ISSUES':>7}  FLAGS")
    divider()
    for r in repos:
        flags = []
        if r.get("is_fork"):                flags.append("fork")
        if r.get("is_starred"):             flags.append("⭐")
        if r.get("status") == "error":      flags.append("❌")
        if r.get("status") == "skipped_resume": flags.append("skip")
        name = r.get("full_name", "?")[:43]
        print(
            f"  {name:<44} "
            f"{fmt_num(r.get('file_count', 0)):>7} "
            f"{fmt_num(r.get('text_file_count', 0)):>6} "
            f"{fmt_num(r.get('issue_count', 0)):>7}  "
            f"{', '.join(flags)}"
        )
    print(f"\n  Total: {len(repos)} repos\n")


# ══════════════════════════════════════════════════════════
# SHOW
# ══════════════════════════════════════════════════════════
def cmd_show(repo_dir_name: str):
    d = EXPORT_DIR / repo_dir_name
    if not d.exists():
        matches = [x for x in EXPORT_DIR.iterdir()
                   if x.is_dir() and repo_dir_name.lower() in x.name.lower()]
        if len(matches) == 1:
            d = matches[0]
            print(f"  (matched: {d.name})\n")
        elif len(matches) > 1:
            print("  Ambiguous match. Did you mean one of:")
            for m in matches:
                print(f"    {m.name}")
            return
        else:
            print(f"  No directory found for: {repo_dir_name}")
            return

    meta     = load_json(d / "metadata.json")
    issues   = load_json(d / "issues.json") or []
    tree     = load_json(d / "directory_tree.json") or []
    tf_index = load_json(d / "text_files" / "_index.json") or \
               load_json(d / "readmes" / "_index.json") or []
    is_tf    = (d / "text_files").exists()

    if not meta:
        print("  No metadata.json found.")
        return

    readmes    = [f for f in tf_index if f.get("is_readme", "saved_as" in f)]
    other_text = [f for f in tf_index if not f.get("is_readme", False)]
    lang_list  = ", ".join(
        f"{k} ({v:,}B)" for k, v in (meta.get("languages") or {}).items()
    ) or (meta.get("language") or "?")

    print(f"""
  ┌────────────────────────────────────────────────┐
  │  {meta['full_name']:<46}│
  └────────────────────────────────────────────────┘

  Description : {meta.get('description') or '(none)'}
  Languages   : {lang_list}
  Topics      : {', '.join(meta.get('topics', [])) or '(none)'}
  License     : {(meta.get('license') or {}).get('name', '(none)')}
  Visibility  : {meta.get('visibility', '?')}   |   Branch: {meta.get('default_branch', '?')}

  ⭐ Stars     : {fmt_num(meta.get('stargazers_count', 0))}
  🍴 Forks     : {fmt_num(meta.get('forks_count', 0))}
  👁  Watchers  : {fmt_num(meta.get('watchers_count', 0))}
  📦 Size      : {meta.get('size_kb', 0):,} KB

  🔀 Fork      : {meta.get('fork', False)}  {"← from " + meta['parent']['full_name'] if meta.get('parent') else ""}
  ⭐ Starred   : {meta.get('_is_starred', False)}
  🗄  Archived  : {meta.get('archived', False)}

  Created     : {(meta.get('created_at') or '')[:10]}
  Last push   : {(meta.get('pushed_at') or '')[:10]}

  📄 Files     : {sum(1 for i in tree if i.get('type') == 'blob')} total in tree
  📝 Text files: {len(tf_index)} {'(text_files/)' if is_tf else '(readmes/ only)'}
       READMEs : {len(readmes)}
       Other   : {len(other_text)}
  🐛 Issues    : {len(issues)}  ({sum(1 for i in issues if i['state'] == 'open')} open,  {sum(1 for i in issues if i['state'] == 'closed')} closed)
""")

    if tf_index:
        display = tf_index[:25]
        for tf in display:
            tag  = " [README]" if tf.get("is_readme") else ""
            size = tf.get("size", 0)
            print(f"    📄  {tf.get('original_path', tf.get('saved_as', '?')):<55} {size:>8,} B{tag}")
        if len(tf_index) > 25:
            print(f"    … and {len(tf_index) - 25} more")
    print()


# ══════════════════════════════════════════════════════════
# TEXT FILES
# ══════════════════════════════════════════════════════════
def cmd_text_files(repo_dir_name: str, ext_filter: str = ""):
    d = EXPORT_DIR / repo_dir_name
    tf_dir = d / "text_files"
    if not tf_dir.exists():
        tf_dir = d / "readmes"
        if not tf_dir.exists():
            print(f"  No text_files/ directory found for: {repo_dir_name}")
            return
        print("  (showing readmes/ — run extractor v2 to get full text_files/)\n")

    index = load_json(tf_dir / "_index.json") or []
    if not index:
        print("  No text files were extracted.")
        return

    items = index
    if ext_filter:
        ext = ext_filter.lower()
        if not ext.startswith("."):
            ext = "." + ext
        items = [
            f for f in index
            if Path(f.get("original_path", f.get("saved_as", ""))).suffix.lower() == ext
            or f.get("original_path", "").lower().endswith(ext_filter.lower())
        ]

    if not items:
        print(f"  No text files matching '{ext_filter}'.")
        return

    print(f"\n  {len(items)} text file(s)"
          + (f" matching '{ext_filter}'" if ext_filter else "") + "\n")

    for tf in items:
        saved_path = tf_dir / tf["saved_as"]
        orig_path  = tf.get("original_path", tf["saved_as"])
        size       = tf.get("size", 0)
        tag        = "  [README]" if tf.get("is_readme") else ""
        print(f"\n  {'═'*66}")
        print(f"  📄  {orig_path}{tag}  ({size:,} bytes)")
        print(f"  {'─'*66}")
        if saved_path.exists():
            content = saved_path.read_text(encoding="utf-8")
            if len(content) > VIEWER_TRUNCATE:
                print(content[:VIEWER_TRUNCATE])
                print(f"\n  … (truncated to {VIEWER_TRUNCATE:,} chars — full file: {saved_path})")
            else:
                print(content)
        else:
            print("  (file not found on disk)")


# ══════════════════════════════════════════════════════════
# ISSUES
# ══════════════════════════════════════════════════════════
def cmd_issues(repo_dir_name: str):
    issues = load_json(EXPORT_DIR / repo_dir_name / "issues.json") or []
    if not issues:
        print(f"  No issues found for: {repo_dir_name}")
        return

    open_issues   = [i for i in issues if i["state"] == "open"]
    closed_issues = [i for i in issues if i["state"] == "closed"]
    print(f"\n  {len(issues)} total issues  "
          f"({len(open_issues)} open,  {len(closed_issues)} closed)\n")

    for label, group in [("OPEN", open_issues), ("CLOSED", closed_issues)]:
        if not group:
            continue
        print(f"\n  ── {label} {'─'*54}")
        for issue in group:
            labels  = ", ".join(issue.get("labels", [])) or "—"
            date    = (issue.get("created_at") or "")[:10]
            print(f"\n  #{issue['number']}  {issue['title']}")
            print(f"       @{issue.get('user','?')}  |  {labels}  |  {date}")
            if issue.get("body"):
                preview = (issue["body"] or "")[:250].replace("\n", " ")
                tail    = "…" if len(issue.get("body", "")) > 250 else ""
                print(f"       {preview}{tail}")
            n_comments = len(issue.get("comments", []))
            if n_comments:
                print(f"       💬 {n_comments} comment(s)")
    print()


# ══════════════════════════════════════════════════════════
# TREE
# ══════════════════════════════════════════════════════════
def cmd_tree(repo_dir_name: str):
    f = EXPORT_DIR / repo_dir_name / "directory_tree.txt"
    if f.exists():
        print(f.read_text(encoding="utf-8"))
    else:
        print(f"  No directory_tree.txt for: {repo_dir_name}")


# ══════════════════════════════════════════════════════════
# SEARCH (repos)
# ══════════════════════════════════════════════════════════
def cmd_search(keyword: str):
    kw = keyword.lower()
    print(f"\n  Searching for '{keyword}' across all metadata …\n")
    found = 0
    for d in sorted(EXPORT_DIR.iterdir()):
        if not d.is_dir() or d.name.startswith("_"):
            continue
        meta = load_json(d / "metadata.json")
        if not meta:
            continue
        haystack = " ".join([
            meta.get("full_name", ""),
            meta.get("description") or "",
            " ".join(meta.get("topics", [])),
            meta.get("language") or "",
            " ".join(meta.get("languages", {}).keys()),
        ]).lower()
        if kw in haystack:
            stars = meta.get("stargazers_count", 0)
            print(f"  ✓  {meta['full_name']:<52}  ⭐{stars:>6}  {meta.get('language','?')}")
            if meta.get("description"):
                print(f"      {meta['description'][:100]}")
            found += 1
    print(f"\n  Found: {found} repo(s)\n")


# ══════════════════════════════════════════════════════════
# TRENDING
# ══════════════════════════════════════════════════════════
def cmd_trending(since: str = "daily", language: str = ""):
    td_dir = EXPORT_DIR / "_trending"
    if not td_dir.exists():
        print("\n  No trending data found.")
        print("  Run: python github_extractor_v2.py --sources trending\n")
        return

    suffix = f"_{language.lower()}" if language else ""
    fname  = f"{since}{suffix}.json"
    data   = load_json(td_dir / fname)

    if not data:
        files = sorted(td_dir.glob("*.json"))
        if not files:
            print("  No trending files in _trending/.")
            return
        print(f"\n  '{fname}' not found.  Available trending files:\n")
        for f in files:
            d = load_json(f)
            if d:
                lang_label = f"  [{d.get('language_filter','all')}]" \
                             if d.get("language_filter") != "all" else ""
                print(f"    • {f.stem:<22}  {d.get('since','')}{lang_label}  "
                      f"({d.get('count',0)} repos, {d.get('scraped_at','')[:10]})")
        print(f"\n  Usage: python github_viewer_v2.py trending [daily|weekly|monthly] [language]\n")
        return

    repos      = data.get("repos", [])
    lang_label = f"  [{data.get('language_filter')}]" \
                 if data.get("language_filter") != "all" else ""
    scraped    = data.get("scraped_at", "")[:10]

    print(f"\n  GitHub Trending — {since.upper()}{lang_label}   (scraped {scraped})")
    print(f"  {len(repos)} repositories\n")
    print(f"  {'#':>3}  {'REPOSITORY':<46} {'LANG':<13} {'⭐ TOTAL':>10}  PERIOD")
    divider()
    for r in repos:
        lang   = (r.get("language") or "—")[:12]
        name   = r.get("full_name", "?")[:45]
        stars  = fmt_num(r.get("stars", 0))
        period = r.get("stars_this_period", "")[:22]
        print(f"  {r.get('rank', 0):>3}  {name:<46} {lang:<13} {stars:>10}  {period}")
    print()
    print("  Top descriptions:")
    for r in repos[:5]:
        if r.get("description"):
            print(f"    {r['rank']:>2}. {r['full_name']}")
            print(f"        {r['description'][:90]}")
    print()


# ══════════════════════════════════════════════════════════
# COLLECTIONS
# ══════════════════════════════════════════════════════════
def cmd_collections(slug: str = ""):
    cd_dir = EXPORT_DIR / "_collections"
    if not cd_dir.exists():
        print("\n  No collections data found.")
        print("  Run: python github_extractor_v2.py --sources collections\n")
        return

    if not slug:
        index   = load_json(cd_dir / "_index.json")
        if not index:
            print("  No _index.json in _collections/.")
            return
        colls   = index.get("collections", [])
        scraped = index.get("scraped_at", "")[:10]
        print(f"\n  GitHub Collections  ({len(colls)} found, scraped {scraped})\n")
        print(f"  {'SLUG':<38}  NAME")
        divider()
        for c in colls:
            print(f"  {c['slug']:<38}  {c['name']}")
        print(f"\n  View a collection:")
        print(f"    python github_viewer_v2.py collection <slug>\n")
        return

    data = load_json(cd_dir / f"{slug}.json")
    if not data:
        print(f"  Collection '{slug}' not found.")
        return

    print(f"\n  📚  {data['name']}")
    if data.get("description"):
        print(f"  {data['description']}")
    print(f"  {data['url']}\n")

    repos = data.get("repos", [])
    if repos:
        print(f"  Repositories ({len(repos)}):\n")
        print(f"  {'REPO':<52}  {'⭐':>8}  LANG")
        divider()
        for r in repos:
            name  = r.get("full_name", "?")[:51]
            stars = fmt_num(r.get("stars", 0))
            lang  = (r.get("language") or "?")[:12]
            print(f"  {name:<52}  {stars:>8}  {lang}")
            if r.get("description"):
                print(f"    {r['description'][:88]}")
    else:
        print("  No repo details scraped.")
        print("  Re-run extractor with --collections-full to fetch them.")
    print()


# ══════════════════════════════════════════════════════════
# SOURCES
# ══════════════════════════════════════════════════════════
def cmd_sources():
    index = load_json(EXPORT_DIR / "_index.json")
    print(f"\n  Sources used in last GitHub extraction:")
    print(f"    {index.get('sources', 'unknown') if index else '(no _index.json found)'}\n")

    td_dir = EXPORT_DIR / "_trending"
    if td_dir.exists():
        files = sorted(td_dir.glob("*.json"))
        if files:
            print(f"  Trending snapshots ({len(files)}):")
            for f in files:
                d = load_json(f)
                if d:
                    print(f"    • {f.stem:<22}  {d.get('count',0):>3} repos  "
                          f"(scraped {d.get('scraped_at','')[:10]})")

    cd_dir = EXPORT_DIR / "_collections"
    if cd_dir.exists():
        ci = load_json(cd_dir / "_index.json")
        if ci:
            print(f"\n  Collections: {ci.get('count',0)} scraped "
                  f"({ci.get('scraped_at','')[:10]})")

    if EXT_DIR.exists():
        ext_sources = sorted(d.name for d in EXT_DIR.iterdir() if d.is_dir())
        if ext_sources:
            print(f"\n  External platform sources ({len(ext_sources)}):")
            for s in ext_sources:
                fwd_dir  = EXT_DIR / s / "forward"
                hist_dir = EXT_DIR / s / "history"
                fwd_count = len(list(fwd_dir.glob("*.json"))) if fwd_dir.exists() else 0
                hist_count = len(list(hist_dir.glob("*.json"))) if hist_dir.exists() else 0
                print(f"    • {s:<22}  {fwd_count} forward files  |  {hist_count} history batches")
    print()


# ══════════════════════════════════════════════════════════
# EXTERNAL SOURCES  (new)
# ══════════════════════════════════════════════════════════
def _load_ext_source_items(source_name: str, mode: str = "forward", date_filter: str = "") -> list:
    """Load all DiscoveredRepo records for a given source."""
    src_dir = EXT_DIR / source_name / mode
    if not src_dir.exists():
        return []
    all_items = []
    for f in sorted(src_dir.glob("*.json"), reverse=True):
        if date_filter and date_filter not in f.stem:
            continue
        data = load_json(f)
        if isinstance(data, list):
            all_items.extend(data)
    return all_items


def _all_ext_items(mode: str = "forward") -> list:
    """Load everything from every external source."""
    if not EXT_DIR.exists():
        return []
    items = []
    for src_dir in EXT_DIR.iterdir():
        if src_dir.is_dir():
            items.extend(_load_ext_source_items(src_dir.name, mode))
    return items


def cmd_external(source: str = "", date_filter: str = ""):
    if not EXT_DIR.exists():
        print("\n  No external sources data found.")
        print("  Run: python platform_extractor.py\n")
        return

    if not source:
        # Summary of all sources
        print("\n  ── External Platform Sources ─────────────────────────────────\n")
        print(f"  {'SOURCE':<22}  {'FWD FILES':>10}  {'FWD ITEMS':>10}  {'HIST BATCHES':>13}  LAST RUN")
        divider()
        for src_dir in sorted(EXT_DIR.iterdir()):
            if not src_dir.is_dir():
                continue
            name     = src_dir.name
            fwd_dir  = src_dir / "forward"
            hist_dir = src_dir / "history"
            fwd_files  = sorted(fwd_dir.glob("*.json"))   if fwd_dir.exists()  else []
            hist_files = sorted(hist_dir.glob("*.json"))  if hist_dir.exists() else []
            fwd_item_count = sum(
                len(load_json(f) or []) for f in fwd_files
            )
            last_date = fwd_files[-1].stem if fwd_files else "—"
            print(
                f"  {name:<22}  {len(fwd_files):>10}  {fwd_item_count:>10}  "
                f"{len(hist_files):>13}  {last_date}"
            )
        print(f"\n  View a source:  python github_viewer_v2.py external <source_name>\n")
        return

    # Single source view
    src_dir = EXT_DIR / source
    if not src_dir.exists():
        available = [d.name for d in EXT_DIR.iterdir() if d.is_dir()]
        print(f"\n  Source '{source}' not found.")
        print(f"  Available: {', '.join(available) or '(none)'}\n")
        return

    items = _load_ext_source_items(source, "forward", date_filter)
    if not items:
        print(f"\n  No forward-scan data for '{source}'" +
              (f" on date '{date_filter}'" if date_filter else "") + ".\n")
        fwd_dir = src_dir / "forward"
        if fwd_dir.exists():
            files = sorted(fwd_dir.glob("*.json"))
            if files:
                print(f"  Available forward files: {', '.join(f.stem for f in files[-10:])}\n")
        return

    # Deduplicate by github_repo for display
    seen  = set()
    dedup = []
    for item in items:
        key = item.get("github_repo", "")
        if key and key not in seen:
            seen.add(key)
            dedup.append(item)

    print(f"\n  {source.upper()}  —  {len(items)} total records  ({len(dedup)} unique repos)")
    if date_filter:
        print(f"  Date filter: {date_filter}")
    print()
    print(f"  {'REPO':<48}  {'SCORE':>7}  TITLE")
    divider()
    for item in sorted(dedup, key=lambda x: x.get("score", 0), reverse=True)[:60]:
        repo  = (item.get("github_repo") or "?")[:47]
        score = item.get("score", 0)
        title = _truncate(item.get("title") or item.get("description") or "", 45)
        pub   = (item.get("published_at") or "")[:10]
        print(f"  {repo:<48}  {score:>7}  {title}")
        if item.get("description") and item.get("description") != item.get("title"):
            print(f"  {'':48}         └─ {_truncate(item['description'], 60)}")
    if len(dedup) > 60:
        print(f"\n  … {len(dedup) - 60} more repos (showing top 60 by score)")
    print()

    # History
    hist_dir = src_dir / "history"
    if hist_dir.exists():
        hist_files = sorted(hist_dir.glob("*.json"))
        if hist_files:
            hist_total = sum(len(load_json(f) or []) for f in hist_files)
            print(f"  Historical batches: {len(hist_files)} files  ({hist_total:,} items)")
            print(f"  First: {hist_files[0].stem}   Last: {hist_files[-1].stem}\n")


# ══════════════════════════════════════════════════════════
# DISCOVERIES SEARCH  (new)
# ══════════════════════════════════════════════════════════
def cmd_discoveries(argv: list):
    """
    Search across all external source discoveries.
    Usage: discoveries [keyword] [--source <name>] [--min-score <n>] [--history]
    """
    # Parse sub-args
    keyword    = ""
    source_filter = ""
    min_score  = 0
    use_history = False

    i = 0
    while i < len(argv):
        a = argv[i]
        if a == "--source" and i + 1 < len(argv):
            source_filter = argv[i + 1]; i += 2
        elif a == "--min-score" and i + 1 < len(argv):
            try:
                min_score = int(argv[i + 1])
            except ValueError:
                pass
            i += 2
        elif a == "--history":
            use_history = True; i += 1
        elif not a.startswith("--"):
            keyword = a; i += 1
        else:
            i += 1

    if not EXT_DIR.exists():
        print("\n  No external sources data found. Run platform_extractor.py first.\n")
        return

    mode = "history" if use_history else "forward"

    # Collect items
    if source_filter:
        items = _load_ext_source_items(source_filter, mode)
        if not items:
            print(f"\n  No data for source '{source_filter}' (mode: {mode}).\n")
            return
    else:
        items = _all_ext_items(mode)

    if not items:
        print(f"\n  No external discovery data found (mode: {mode}).\n")
        return

    # Filter
    kw = keyword.lower()
    filtered = []
    for item in items:
        if item.get("score", 0) < min_score:
            continue
        if kw:
            haystack = " ".join([
                item.get("github_repo", ""),
                item.get("title", ""),
                item.get("description", ""),
                " ".join(item.get("tags", [])),
            ]).lower()
            if kw not in haystack:
                continue
        filtered.append(item)

    # Deduplicate by github_repo, keeping highest-score occurrence
    repo_map: dict[str, dict] = {}
    for item in filtered:
        repo = item.get("github_repo", "")
        if not repo:
            continue
        if repo not in repo_map or item.get("score", 0) > repo_map[repo].get("score", 0):
            repo_map[repo] = item

    results = sorted(repo_map.values(), key=lambda x: x.get("score", 0), reverse=True)

    # Header
    filters = []
    if keyword:         filters.append(f"keyword='{keyword}'")
    if source_filter:   filters.append(f"source={source_filter}")
    if min_score:       filters.append(f"min-score≥{min_score}")
    if use_history:     filters.append("mode=history")
    filter_str = "  " + "  |  ".join(filters) if filters else ""

    print(f"\n  Discoveries — {len(results)} unique repos matched")
    if filter_str:
        print(filter_str)
    print()

    if not results:
        print("  No results.\n")
        return

    print(f"  {'REPO':<46}  {'SOURCE':<16}  {'SCORE':>7}  DATE")
    divider()
    for item in results[:80]:
        repo   = (item.get("github_repo") or "?")[:45]
        source = (item.get("source") or "?")[:15]
        score  = item.get("score", 0)
        date   = (item.get("published_at") or item.get("discovered_at") or "")[:10]
        print(f"  {repo:<46}  {source:<16}  {score:>7}  {date}")
        title = item.get("title") or item.get("description") or ""
        if title:
            print(f"  {'':46}  {'':16}  {'':>7}  └─ {_truncate(title, 55)}")

    if len(results) > 80:
        print(f"\n  … {len(results) - 80} more results not shown (use --min-score to narrow)")
    print()


# ══════════════════════════════════════════════════════════
# EXT-SUMMARY  (compact cross-source stats table)  (new)
# ══════════════════════════════════════════════════════════
def cmd_ext_summary():
    if not EXT_DIR.exists():
        print("\n  No external sources data. Run platform_extractor.py first.\n")
        return

    print("\n  ── External Sources Summary ──────────────────────────────────────\n")

    # State file for cursor info
    state_file = EXPORT_DIR / "_state" / "crawl_state.json"
    state      = load_json(state_file) or {}
    state_srcs = state.get("sources", {})

    grand_fwd = 0
    grand_hist = 0

    print(f"  {'SOURCE':<20}  {'FWD ITEMS':>10}  {'HIST ITEMS':>11}  {'LOOKBACK':^10}  {'LAST SEEN'}")
    divider()

    for src_dir in sorted(EXT_DIR.iterdir()):
        if not src_dir.is_dir():
            continue
        name = src_dir.name

        # Count forward items
        fwd_items = 0
        fwd_d = src_dir / "forward"
        if fwd_d.exists():
            for f in fwd_d.glob("*.json"):
                fwd_items += len(load_json(f) or [])

        # Count history items
        hist_items = 0
        hist_d = src_dir / "history"
        if hist_d.exists():
            for f in hist_d.glob("*.json"):
                hist_items += len(load_json(f) or [])

        grand_fwd  += fwd_items
        grand_hist += hist_items

        # Lookback status
        src_state  = state_srcs.get(name, {})
        lb_state   = src_state.get("lookback", {})
        complete   = lb_state.get("history_complete", False)
        cursor     = lb_state.get("cursor")
        lb_str     = "complete" if complete else (f"p.{cursor.get('page',cursor.get('idx','?'))}" if isinstance(cursor, dict) else "—")

        last_seen  = src_state.get("forward", {}).get("last_seen", "—")
        last_seen  = last_seen[:10] if last_seen != "—" else "—"

        print(
            f"  {name:<20}  {fwd_items:>10,}  {hist_items:>11,}  {lb_str:^10}  {last_seen}"
        )

    print(f"  {'─'*20}  {'─'*10}  {'─'*11}")
    print(f"  {'TOTAL':<20}  {grand_fwd:>10,}  {grand_hist:>11,}")

    # Top repos across all sources
    all_items = _all_ext_items("forward")
    if all_items:
        repo_scores: dict[str, dict] = {}
        for item in all_items:
            repo = item.get("github_repo", "")
            if not repo:
                continue
            if repo not in repo_scores or item.get("score", 0) > repo_scores[repo].get("score", 0):
                repo_scores[repo] = item

        top10 = sorted(repo_scores.values(), key=lambda x: x.get("score", 0), reverse=True)[:10]
        if top10:
            print(f"\n  Top 10 repos by score (forward scans):\n")
            print(f"  {'REPO':<46}  {'SOURCE':<16}  SCORE")
            divider()
            for item in top10:
                repo   = (item.get("github_repo") or "?")[:45]
                source = (item.get("source") or "?")[:15]
                score  = item.get("score", 0)
                print(f"  {repo:<46}  {source:<16}  {score:>7,}")

    print()


# ══════════════════════════════════════════════════════════
# ENTRY POINT
# ══════════════════════════════════════════════════════════
def main():
    argv = sys.argv[1:]

    if not argv or argv[0] in ("stats", "summary"):
        cmd_stats()

    elif argv[0] == "list":
        cmd_list()

    elif argv[0] == "show" and len(argv) >= 2:
        cmd_show(argv[1])

    elif argv[0] in ("text", "texts") and len(argv) >= 2:
        ext = argv[2] if len(argv) >= 3 else ""
        cmd_text_files(argv[1], ext)

    elif argv[0] == "readmes" and len(argv) >= 2:
        cmd_text_files(argv[1], ".md")

    elif argv[0] == "issues" and len(argv) >= 2:
        cmd_issues(argv[1])

    elif argv[0] == "tree" and len(argv) >= 2:
        cmd_tree(argv[1])

    elif argv[0] == "search" and len(argv) >= 2:
        cmd_search(" ".join(argv[1:]))

    elif argv[0] == "trending":
        since    = "daily"
        language = ""
        for a in argv[1:]:
            if a in ("daily", "weekly", "monthly"):
                since = a
            else:
                language = a
        cmd_trending(since, language)

    elif argv[0] in ("collections", "collection"):
        slug = argv[1] if len(argv) >= 2 else ""
        cmd_collections(slug)

    elif argv[0] == "sources":
        cmd_sources()

    # ── External sources commands ────────────────────────
    elif argv[0] == "external":
        # external
        # external <source>
        # external <source> <date>  e.g. external hackernews 2026-05-27
        source      = argv[1] if len(argv) >= 2 else ""
        date_filter = argv[2] if len(argv) >= 3 else ""
        cmd_external(source, date_filter)

    elif argv[0] == "discoveries":
        # discoveries [keyword] [--source <name>] [--min-score <n>] [--history]
        cmd_discoveries(argv[1:])

    elif argv[0] == "ext-summary":
        cmd_ext_summary()

    else:
        print(__doc__)


if __name__ == "__main__":
    main()
