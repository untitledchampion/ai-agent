"""Hybrid search: BM25 (SQLite FTS5) + vector (sqlite-vec) merged with RRF.

Exposes:
  - ensure_fts(conn): builds fts_products if missing.
  - hybrid_search(conn, model, query, k=10): returns list of (product_row, score).
"""
from __future__ import annotations

import re
import sqlite3
import struct
from dataclasses import dataclass

DIM = 1024
RRF_K = 60
CAND_K = 50  # per-ranker candidate depth
VEC_WEIGHT = 2.0  # vector signal is more trustworthy on this data
BM25_WEIGHT = 1.0


def _normalize(text: str) -> str:
    """Normalize separators so 125*150, 125x150, 125 х 150 all match 125х150.

    - lowercase
    - collapse digit separators *, ×, latin x, '-' between digits → 'х'
    - drop spaces inside numeric groups (`2 * 1.5` -> `2х1.5`)
    - normalize decimal ',' -> '.' inside numbers
    """
    s = text.lower()
    # fold multiplication-ish separators between digits
    s = re.sub(
        r"(\d)\s*[\*x×х\-/]\s*(\d)",
        lambda m: m.group(1) + "х" + m.group(2),
        s,
    )
    # decimal comma inside number
    s = re.sub(r"(\d),(\d)", r"\1.\2", s)
    return s


def ensure_fts(conn: sqlite3.Connection) -> None:
    """Create FTS5 virtual table mirroring products with normalized text."""
    # Always rebuild so normalization rules are up-to-date.
    conn.execute("DROP TABLE IF EXISTS fts_products")
    conn.execute(
        """
        CREATE VIRTUAL TABLE fts_products USING fts5(
            name, category, code,
            content='',
            tokenize='unicode61 remove_diacritics 2'
        )
        """
    )
    rows = conn.execute(
        "SELECT id, name, category, code FROM products"
    ).fetchall()
    conn.executemany(
        "INSERT INTO fts_products(rowid, name, category, code) VALUES (?, ?, ?, ?)",
        [
            (r[0], _normalize(r[1] or ""), _normalize(r[2] or ""), r[3] or "")
            for r in rows
        ],
    )
    conn.commit()


_TOKEN_RE = re.compile(r"[\w.]+", re.UNICODE)


def _tokens(raw: str) -> list[str]:
    norm = _normalize(raw)
    out: list[str] = []
    for t in _TOKEN_RE.findall(norm):
        if len(t) == 1 and not t.isdigit():
            continue
        out.append(t)
    return out


def _fts_and(tokens: list[str]) -> str:
    return " AND ".join('"' + t.replace('"', '""') + '"' for t in tokens)


def _fts_or(tokens: list[str]) -> str:
    return " OR ".join('"' + t.replace('"', '""') + '"' for t in tokens)


def _vector_search(
    conn: sqlite3.Connection, query_vec, k: int
) -> list[tuple[int, float]]:
    blob = struct.pack(f"{DIM}f", *query_vec)
    rows = conn.execute(
        """
        SELECT id, distance
        FROM vec_products
        WHERE embedding MATCH ? AND k = ?
        ORDER BY distance
        """,
        (blob, k),
    ).fetchall()
    return [(int(r[0]), float(r[1])) for r in rows]


def _run_fts(conn: sqlite3.Connection, fts_q: str, k: int) -> list[tuple[int, float]]:
    try:
        rows = conn.execute(
            """
            SELECT rowid, bm25(fts_products)
            FROM fts_products
            WHERE fts_products MATCH ?
            ORDER BY bm25(fts_products)
            LIMIT ?
            """,
            (fts_q, k),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [(int(r[0]), float(r[1])) for r in rows]


def _bm25_search(
    conn: sqlite3.Connection, query_text: str, k: int
) -> list[tuple[int, float]]:
    toks = _tokens(query_text)
    if not toks:
        return []
    # Try strict AND first; fall back to OR only if AND yields nothing.
    if len(toks) >= 2:
        hits = _run_fts(conn, _fts_and(toks), k)
        if hits:
            return hits
    return _run_fts(conn, _fts_or(toks), k)


@dataclass
class HybridHit:
    id: int
    rrf_score: float
    vec_rank: int | None
    bm25_rank: int | None
    vec_distance: float | None
    bm25_score: float | None


def hybrid_search(
    conn: sqlite3.Connection,
    query_text: str,
    query_vec,
    k: int = 10,
) -> list[HybridHit]:
    """Run both rankers, merge with Reciprocal Rank Fusion."""
    vec_hits = _vector_search(conn, query_vec, CAND_K)
    bm25_hits = _bm25_search(conn, query_text, CAND_K)

    scores: dict[int, HybridHit] = {}
    for rank, (pid, dist) in enumerate(vec_hits):
        scores[pid] = HybridHit(
            id=pid,
            rrf_score=VEC_WEIGHT / (RRF_K + rank + 1),
            vec_rank=rank + 1,
            bm25_rank=None,
            vec_distance=dist,
            bm25_score=None,
        )
    for rank, (pid, bm) in enumerate(bm25_hits):
        add = BM25_WEIGHT / (RRF_K + rank + 1)
        if pid in scores:
            h = scores[pid]
            h.rrf_score += add
            h.bm25_rank = rank + 1
            h.bm25_score = bm
        else:
            scores[pid] = HybridHit(
                id=pid,
                rrf_score=add,
                vec_rank=None,
                bm25_rank=rank + 1,
                vec_distance=None,
                bm25_score=bm,
            )

    ranked = sorted(scores.values(), key=lambda h: h.rrf_score, reverse=True)
    return ranked[:k]
