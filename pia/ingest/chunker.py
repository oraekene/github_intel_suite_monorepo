"""
pia/ingest/chunker.py

Splits RawDocuments into overlapping text chunks suitable for
embedding. Uses token-aware splitting so chunk sizes stay consistent
regardless of file type.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Sequence

from utils import cfg, count_tokens, log
from ingest.loader import RawDocument


# ── Data model ───────────────────────────────────────────────────────────────

@dataclass
class Chunk:
    chunk_id:    str          # unique: "{source_path}::chunk_{n}"
    content:     str
    token_count: int
    metadata:    dict         # carries all fields from parent RawDocument


# ── Splitter logic ───────────────────────────────────────────────────────────

def _split_by_tokens(
    text:         str,
    chunk_size:   int,
    chunk_overlap: int,
) -> list[str]:
    """
    Split text into chunks of at most `chunk_size` tokens with
    `chunk_overlap` token overlap between consecutive chunks.

    Strategy:
    1. First split on natural boundaries (double-newlines → paragraphs,
       then single newlines, then sentences).
    2. Pack sentences into chunks respecting the token limit.
    3. Apply overlap by prepending the tail of the previous chunk.
    """
    # ── Sentence / paragraph segmentation ────────────────────────────
    # Split on paragraph breaks first, then sentences within paragraphs
    paragraphs = re.split(r"\n{2,}", text.strip())
    sentences: list[str] = []
    for para in paragraphs:
        # Split on line endings or ". " boundaries
        sents = re.split(r"(?<=[.!?])\s+|\n", para)
        sents = [s.strip() for s in sents if s.strip()]
        sentences.extend(sents)
        sentences.append("")    # blank acts as paragraph separator

    # ── Pack into chunks ──────────────────────────────────────────────
    chunks:  list[str]  = []
    current: list[str]  = []
    current_tokens       = 0

    for sent in sentences:
        sent_tokens = count_tokens(sent) if sent else 0

        # If a single sentence exceeds chunk_size, hard-split it
        if sent_tokens > chunk_size:
            words = sent.split()
            mini  = []
            mini_t = 0
            for w in words:
                wt = count_tokens(w)
                if mini_t + wt > chunk_size and mini:
                    chunks.append(" ".join(mini))
                    # overlap: keep last ~chunk_overlap tokens worth of words
                    overlap_words: list[str] = []
                    ot = 0
                    for mw in reversed(mini):
                        mt = count_tokens(mw)
                        if ot + mt > chunk_overlap:
                            break
                        overlap_words.insert(0, mw)
                        ot += mt
                    mini  = overlap_words + [w]
                    mini_t = ot + wt
                else:
                    mini.append(w)
                    mini_t += wt
            if mini:
                current.extend(mini)
                current_tokens += mini_t
            continue

        if current_tokens + sent_tokens > chunk_size and current:
            chunk_text = " ".join(current).strip()
            if chunk_text:
                chunks.append(chunk_text)

            # Build overlap: walk backwards through current sentences
            overlap_sents: list[str] = []
            ot = 0
            for s in reversed(current):
                st = count_tokens(s) if s else 0
                if ot + st > chunk_overlap:
                    break
                overlap_sents.insert(0, s)
                ot += st

            current       = overlap_sents + ([sent] if sent else [])
            current_tokens = ot + sent_tokens
        else:
            current.append(sent) if sent else None
            current_tokens += sent_tokens

    # Flush remainder
    if current:
        chunk_text = " ".join(current).strip()
        if chunk_text:
            chunks.append(chunk_text)

    return [c for c in chunks if c.strip()]


# ── Public API ───────────────────────────────────────────────────────────────

def chunk_documents(
    docs:          Sequence[RawDocument],
    chunk_size:    int | None = None,
    chunk_overlap: int | None = None,
) -> list[Chunk]:
    """
    Chunk a list of RawDocuments.  Returns a flat list of Chunk objects.
    """
    c_size    = chunk_size    or cfg("knowledge_base.chunk_size",    800)
    c_overlap = chunk_overlap or cfg("knowledge_base.chunk_overlap", 100)

    all_chunks: list[Chunk] = []
    total_tokens = 0

    for doc in docs:
        raw_chunks = _split_by_tokens(doc.content, c_size, c_overlap)

        for i, text in enumerate(raw_chunks):
            tc = count_tokens(text)
            total_tokens += tc
            all_chunks.append(Chunk(
                chunk_id    = f"{doc.source_path}::chunk_{i}",
                content     = text,
                token_count = tc,
                metadata    = {
                    **doc.metadata,
                    "chunk_index":  i,
                    "chunk_total":  len(raw_chunks),
                    "chunk_tokens": tc,
                },
            ))

    log.info(
        f"Chunked {len(docs)} docs → {len(all_chunks)} chunks "
        f"({total_tokens:,} total tokens, "
        f"avg {total_tokens // max(len(all_chunks), 1)} tok/chunk)"
    )
    return all_chunks


# ── CLI helper ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    sys.path.insert(0, str(__import__("pathlib").Path(__file__).parent.parent))
    from ingest.loader import load_knowledge_base

    docs   = load_knowledge_base()
    chunks = chunk_documents(docs)
    print(f"\nSample chunks from first doc ({docs[0].filename}):")
    doc_chunks = [c for c in chunks if docs[0].source_path in c.chunk_id]
    for c in doc_chunks[:3]:
        print(f"  chunk_id={c.chunk_id.split('::')[1]}  tokens={c.token_count}")
        print(f"  {c.content[:120]}...\n")
