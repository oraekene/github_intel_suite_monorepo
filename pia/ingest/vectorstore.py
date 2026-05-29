"""
pia/ingest/vectorstore.py

ChromaDB-backed vector store.
• Embeds chunks using sentence-transformers (CPU, ~90 MB model)
• Persists to disk — survives between runs
• Supports incremental upsert (won't re-embed unchanged content)
• Exposes semantic_search() for the analysis phase
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import Sequence

from utils import cfg, ensure_dir, log
from ingest.chunker import Chunk

# ── Lazy imports (heavy; only loaded when needed) ────────────────────────────

def _get_chroma():
    import chromadb
    return chromadb

def _get_ef(model_name: str):
    from chromadb.utils import embedding_functions
    return embedding_functions.SentenceTransformerEmbeddingFunction(
        model_name=model_name,
        device="cpu",          # Core i3 — always CPU
        normalize_embeddings=True,
    )


# ── Constants ────────────────────────────────────────────────────────────────

COLLECTION_NAME    = "pia_knowledge_base"
BATCH_SIZE         = 32        # Embed in small batches to stay memory-safe


# ── Hash helper ──────────────────────────────────────────────────────────────

def _content_hash(text: str) -> str:
    return hashlib.md5(text.encode("utf-8", errors="replace")).hexdigest()


# ── VectorStore class ────────────────────────────────────────────────────────

class VectorStore:
    """
    Thin wrapper around a persistent ChromaDB collection.

    Usage:
        vs = VectorStore()
        vs.upsert_chunks(chunks)               # ingest phase
        results = vs.semantic_search(query, k=6)  # analysis phase
    """

    def __init__(
        self,
        persist_dir:    str | Path | None = None,
        embedding_model: str | None       = None,
    ):
        chroma_dir  = Path(persist_dir or cfg("knowledge_base.chroma_dir"))
        model_name  = embedding_model  or cfg(
            "knowledge_base.embedding_model", "all-MiniLM-L6-v2"
        )

        ensure_dir(chroma_dir)
        log.info(f"ChromaDB persist dir: {chroma_dir}")

        chromadb = _get_chroma()
        self._client = chromadb.PersistentClient(path=str(chroma_dir))
        self._ef     = _get_ef(model_name)
        self._col    = self._client.get_or_create_collection(
            name               = COLLECTION_NAME,
            embedding_function = self._ef,
            metadata           = {"hnsw:space": "cosine"},
        )
        log.info(
            f"Collection '{COLLECTION_NAME}' ready — "
            f"{self._col.count()} existing chunks"
        )

    # ── Ingest ───────────────────────────────────────────────────────────────

    def upsert_chunks(self, chunks: Sequence[Chunk]) -> dict[str, int]:
        """
        Upsert chunks into ChromaDB.  Only re-embeds chunks whose
        content hash has changed, making subsequent runs fast.

        Returns stats: {"added": n, "skipped": n, "total": n}
        """
        if not chunks:
            log.warning("upsert_chunks called with empty list — nothing to do.")
            return {"added": 0, "skipped": 0, "total": 0}

        # Fetch existing IDs + their stored hashes
        existing: dict[str, str] = {}   # chunk_id → stored_hash
        try:
            stored = self._col.get(include=["metadatas"])
            for cid, meta in zip(stored["ids"], stored["metadatas"]):
                existing[cid] = meta.get("content_hash", "")
        except Exception as e:
            log.debug(f"Could not fetch existing hashes: {e}")

        # Filter to new / changed chunks
        to_upsert = [
            c for c in chunks
            if existing.get(c.chunk_id) != _content_hash(c.content)
        ]

        skipped = len(chunks) - len(to_upsert)
        if skipped:
            log.info(f"Skipping {skipped} unchanged chunks (incremental update)")

        # Collect which repos are changing — returned for benchmarker
        new_repos: list[str] = sorted({
            c.metadata.get("repo", "unknown") for c in to_upsert
        })

        if not to_upsert:
            log.info("Knowledge base is up to date — nothing to embed.")
            return {"added": 0, "skipped": skipped, "total": len(chunks), "new_repos": []}

        log.info(f"Embedding {len(to_upsert)} chunks in batches of {BATCH_SIZE}…")

        added = 0
        from tqdm import tqdm
        for i in tqdm(range(0, len(to_upsert), BATCH_SIZE), desc="Embedding"):
            batch = to_upsert[i : i + BATCH_SIZE]
            ids      = [c.chunk_id for c in batch]
            contents = [c.content  for c in batch]
            metas    = [
                {**c.metadata, "content_hash": _content_hash(c.content)}
                for c in batch
            ]

            self._col.upsert(
                ids       = ids,
                documents = contents,
                metadatas = metas,
            )
            added += len(batch)

        log.info(
            f"Upsert complete — added/updated: {added}, "
            f"skipped: {skipped}, "
            f"collection total: {self._col.count()}"
        )
        return {"added": added, "skipped": skipped, "total": len(chunks), "new_repos": new_repos}

    # ── Query ────────────────────────────────────────────────────────────────

    def semantic_search(
        self,
        query:      str,
        k:          int | None = None,
        min_score:  float | None = None,
        where:      dict | None = None,
    ) -> list[dict]:
        """
        Semantic search over the knowledge base.

        Returns a list of result dicts:
        {
          "id":         chunk_id,
          "content":    text,
          "score":      similarity (0–1, higher = better),
          "metadata":   {...}
        }
        """
        top_k   = k         or cfg("knowledge_base.top_k_results",      6)
        min_sim = min_score or cfg("knowledge_base.similarity_threshold", 0.35)

        if self._col.count() == 0:
            log.warning("Vector store is empty — run the ingest phase first.")
            return []

        query_params: dict = dict(
            query_texts    = [query],
            n_results      = min(top_k * 2, self._col.count()),  # fetch extra, then filter
            include        = ["documents", "metadatas", "distances"],
        )
        if where:
            query_params["where"] = where

        try:
            results = self._col.query(**query_params)
        except Exception as e:
            log.error(f"ChromaDB query failed: {e}")
            return []

        hits = []
        for doc, meta, dist in zip(
            results["documents"][0],
            results["metadatas"][0],
            results["distances"][0],
        ):
            # ChromaDB cosine distance → similarity
            score = 1.0 - dist
            if score < min_sim:
                continue
            hits.append({
                "content":  doc,
                "score":    round(score, 4),
                "metadata": meta,
            })

        # Return top_k after filtering
        hits.sort(key=lambda x: x["score"], reverse=True)
        return hits[:top_k]

    # ── Utility ──────────────────────────────────────────────────────────────

    def count(self) -> int:
        return self._col.count()

    def clear(self) -> None:
        """Delete and recreate the collection. Use carefully."""
        log.warning("Clearing vector store — all embeddings will be lost.")
        self._client.delete_collection(COLLECTION_NAME)
        self._col = self._client.get_or_create_collection(
            name               = COLLECTION_NAME,
            embedding_function = self._ef,
            metadata           = {"hnsw:space": "cosine"},
        )


# ── Module-level singleton (lazy) ────────────────────────────────────────────

_STORE: VectorStore | None = None

def get_store() -> VectorStore:
    global _STORE
    if _STORE is None:
        _STORE = VectorStore()
    return _STORE
