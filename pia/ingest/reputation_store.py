"""
pia/ingest/reputation_store.py

Persistent per-repo, per-domain quality registry.

Every KB repo that is ingested for the first time starts with no records.
The repo_benchmarker evaluates it against existing domain champions and writes
a DomainRecord for each topic the repo covers:

    is_eligible = True   → repo's chunks will appear in retrieval context
    is_eligible = False  → repo's chunks are filtered out during retrieval

Schema on disk  (JSON at reputation.registry_path):
{
  "<repo_name>": {
    "<domain>": {
      "composite_score":    float,          # weighted 1–10
      "dimension_scores":   {str: float},   # per-dimension 1–10 scores
      "is_eligible":        bool,
      "champion_score":     float,          # best score in this domain at eval time
      "verdict":            str,            # "winner" | "tied" | "loser" | "sole_entry"
      "repos_compared":     [str],
      "last_evaluated":     str,            # ISO 8601 UTC
      "evaluation_count":   int
    }
  }
}
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from pathlib import Path

from utils import cfg, ensure_dir, log


# ── DomainRecord helpers ──────────────────────────────────────────────────────

def _empty_domain_record() -> dict:
    return {
        "composite_score":   0.0,
        "dimension_scores":  {},
        "is_eligible":       False,
        "champion_score":    0.0,
        "verdict":           "not_evaluated",
        "repos_compared":    [],
        "last_evaluated":    "",
        "evaluation_count":  0,
    }


# ── ReputationStore ───────────────────────────────────────────────────────────

class ReputationStore:
    """
    Thread-safe JSON-backed store.  All public methods are safe to call
    from multiple threads (scheduler may spawn workers).
    """

    def __init__(self, registry_path: str | Path | None = None) -> None:
        # Resolve path: explicit arg → config value → sibling of chroma_dir
        if registry_path:
            resolved = Path(registry_path)
        else:
            cfg_path = cfg("reputation.registry_path", "")
            if cfg_path:
                resolved = Path(cfg_path)
            else:
                chroma_dir = cfg("knowledge_base.chroma_dir", "pia-data/chroma")
                resolved   = Path(chroma_dir).parent / "reputation_registry.json"

        self._path: Path             = resolved
        self._lock: threading.Lock   = threading.Lock()
        self._data: dict[str, dict]  = {}
        self._load()

    # ── Persistence ──────────────────────────────────────────────────────────

    def _load(self) -> None:
        if self._path.exists():
            try:
                raw = json.loads(self._path.read_text(encoding="utf-8"))
                if isinstance(raw, dict):
                    self._data = raw
                    total_domains = sum(len(v) for v in self._data.values())
                    log.info(
                        f"Reputation registry loaded: {len(self._data)} repos, "
                        f"{total_domains} domain records  ({self._path})"
                    )
                else:
                    log.warning("Reputation registry has unexpected format — starting fresh")
                    self._data = {}
            except Exception as e:
                log.warning(f"Could not load reputation registry ({e}) — starting fresh")
                self._data = {}
        else:
            ensure_dir(self._path.parent)
            self._data = {}
            log.info(f"Reputation registry initialised (new): {self._path}")

    def _save(self) -> None:
        """Write current state to disk.  Caller must hold self._lock."""
        try:
            ensure_dir(self._path.parent)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(self._data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            tmp.replace(self._path)          # atomic on most OS / file systems
        except Exception as e:
            log.error(f"Failed to save reputation registry: {e}")

    # ── Read ─────────────────────────────────────────────────────────────────

    def is_eligible(self, repo: str, domain: str) -> bool:
        """True if this repo has been benchmarked and won for this domain."""
        with self._lock:
            rec = self._data.get(repo, {}).get(domain)
            return bool(rec and rec.get("is_eligible", False))

    def is_eligible_any(self, repo: str) -> bool:
        """
        True if the repo is eligible for at least one domain.
        Used by the retriever for a conservative but simple eligibility check.
        """
        with self._lock:
            return any(
                d.get("is_eligible", False)
                for d in self._data.get(repo, {}).values()
            )

    def is_known(self, repo: str) -> bool:
        """True if the repo has been registered (even if never evaluated)."""
        with self._lock:
            return repo in self._data

    def get_champion_score(self, domain: str) -> float:
        """Highest composite score among all eligible repos for this domain."""
        with self._lock:
            best = 0.0
            for repo_data in self._data.values():
                rec = repo_data.get(domain, {})
                if rec.get("is_eligible") and rec.get("composite_score", 0.0) > best:
                    best = rec["composite_score"]
            return best

    def get_eligible_repos(self, domain: str) -> list[str]:
        """All repo names currently eligible for a given domain."""
        with self._lock:
            return [
                repo
                for repo, domains in self._data.items()
                if domains.get(domain, {}).get("is_eligible", False)
            ]

    def get_all_repos(self) -> list[str]:
        with self._lock:
            return list(self._data.keys())

    def get_record(self, repo: str, domain: str) -> dict | None:
        with self._lock:
            rec = self._data.get(repo, {}).get(domain)
            return dict(rec) if rec else None

    def get_repo_summary(self, repo: str) -> dict:
        """Human-readable summary of a repo's standing across all domains."""
        with self._lock:
            domains = self._data.get(repo, {})
            return {
                "repo":              repo,
                "domains_evaluated": len(domains),
                "domains_eligible":  sum(1 for d in domains.values() if d.get("is_eligible")),
                "domains": {
                    k: {
                        "score":    v.get("composite_score", 0.0),
                        "eligible": v.get("is_eligible", False),
                        "verdict":  v.get("verdict", "not_evaluated"),
                    }
                    for k, v in domains.items()
                },
            }

    def get_full_registry(self) -> dict:
        """Return a deep copy of the full registry (for reporting)."""
        with self._lock:
            import copy
            return copy.deepcopy(self._data)

    # ── Write ─────────────────────────────────────────────────────────────────

    def register_new_repo(self, repo: str) -> None:
        """
        Mark a repo as known but not yet evaluated.
        Safe to call multiple times — only creates the top-level key once.
        This prevents the repo from being treated as 'unknown' during retrieval
        and ensures the benchmarker knows it exists.
        """
        with self._lock:
            if repo not in self._data:
                self._data[repo] = {}
                self._save()
                log.info(f"Reputation: registered new repo '{repo}' (awaiting benchmark)")

    def upsert_record(
        self,
        repo:             str,
        domain:           str,
        composite_score:  float,
        dimension_scores: dict[str, float],
        is_eligible:      bool,
        champion_score:   float,
        verdict:          str,
        repos_compared:   list[str],
    ) -> None:
        """Create or update the domain record for a repo."""
        with self._lock:
            if repo not in self._data:
                self._data[repo] = {}

            existing = self._data[repo].get(domain, {})
            self._data[repo][domain] = {
                "composite_score":   round(composite_score, 3),
                "dimension_scores":  {k: round(v, 3) for k, v in dimension_scores.items()},
                "is_eligible":       is_eligible,
                "champion_score":    round(champion_score, 3),
                "verdict":           verdict,
                "repos_compared":    repos_compared,
                "last_evaluated":    datetime.now(timezone.utc).isoformat(),
                "evaluation_count":  existing.get("evaluation_count", 0) + 1,
            }
            self._save()

    def clear_repo(self, repo: str) -> None:
        """Remove all domain records for a repo (e.g. when deleted from KB)."""
        with self._lock:
            removed = self._data.pop(repo, None)
            if removed is not None:
                self._save()
                log.info(f"Reputation: cleared all records for repo '{repo}'")

    def clear_all(self) -> None:
        """Wipe the entire registry.  Used when --clear-kb is passed."""
        with self._lock:
            self._data = {}
            self._save()
        log.warning("Reputation registry cleared (full reset)")


# ── Module-level singleton (lazy) ────────────────────────────────────────────

_STORE: ReputationStore | None = None


def get_reputation_store() -> ReputationStore:
    global _STORE
    if _STORE is None:
        _STORE = ReputationStore()
    return _STORE
