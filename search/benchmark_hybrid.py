"""Run same 100 queries through both vector-only and hybrid search,
write a side-by-side report for comparison.
"""
from __future__ import annotations

import random
import sqlite3
import struct
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import sqlite_vec  # noqa: E402
import torch  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

from hybrid import CAND_K, DIM, ensure_fts, hybrid_search  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "chatapp_data.db"
REPORT_PATH = ROOT / "search" / "benchmark_hybrid_report.md"
N_TOP = 50
N_TAIL = 50
RANDOM_SEED = 42


def sample_queries(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    top = conn.execute(
        """
        SELECT raw_name, COUNT(*) n
        FROM extracted_order_items
        WHERE raw_name IS NOT NULL AND LENGTH(TRIM(raw_name)) > 0
        GROUP BY raw_name ORDER BY n DESC LIMIT ?
        """,
        (N_TOP,),
    ).fetchall()
    tail_candidates = conn.execute(
        """
        SELECT raw_name, COUNT(*) n
        FROM extracted_order_items
        WHERE raw_name IS NOT NULL AND LENGTH(TRIM(raw_name)) > 2
        GROUP BY raw_name HAVING n BETWEEN 2 AND 10
        """
    ).fetchall()
    rng = random.Random(RANDOM_SEED)
    tail = rng.sample(tail_candidates, min(N_TAIL, len(tail_candidates)))
    return top + tail


def _vec_only_top1(conn, vec) -> int | None:
    blob = struct.pack(f"{DIM}f", *vec)
    row = conn.execute(
        """
        SELECT id FROM vec_products
        WHERE embedding MATCH ? AND k = 1
        ORDER BY distance
        """,
        (blob,),
    ).fetchone()
    return int(row[0]) if row else None


def main() -> int:
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"device: {device}", file=sys.stderr)
    model = SentenceTransformer("BAAI/bge-m3", device=device)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    ensure_fts(conn)

    queries = sample_queries(conn)
    print(f"sampled {len(queries)} queries", file=sys.stderr)

    vecs = model.encode(
        [q for q, _ in queries],
        normalize_embeddings=True,
        batch_size=64,
        show_progress_bar=True,
    )

    def product(pid: int) -> sqlite3.Row:
        return conn.execute(
            "SELECT id, name, code, price_dealer FROM products WHERE id = ?",
            (pid,),
        ).fetchone()

    lines: list[str] = []
    lines.append("# Benchmark: vector-only vs hybrid (BM25 + vec, RRF)\n\n")
    lines.append(f"Queries: {len(queries)} ({N_TOP} top + {N_TAIL} tail)\n\n")

    diff_count = 0
    for i, ((raw, freq), vec) in enumerate(zip(queries, vecs)):
        if i == N_TOP:
            lines.append("\n## Long-tail queries\n\n")
        elif i == 0:
            lines.append("## Top-frequency queries\n\n")

        vec_id = _vec_only_top1(conn, vec)
        hybrid_hits = hybrid_search(conn, raw, vec, k=3)
        hyb_id = hybrid_hits[0].id if hybrid_hits else None

        changed = vec_id != hyb_id
        if changed:
            diff_count += 1

        marker = " ⚡" if changed else ""
        lines.append(f"### `{raw}` (n={freq}){marker}\n\n")

        if vec_id:
            p = product(vec_id)
            price = f"{p['price_dealer']}р" if p["price_dealer"] is not None else "—"
            lines.append(f"- **vec** : [{p['code']}] {price}  {p['name']}\n")
        else:
            lines.append("- **vec** : —\n")

        if hybrid_hits:
            for j, h in enumerate(hybrid_hits):
                p = product(h.id)
                price = f"{p['price_dealer']}р" if p["price_dealer"] is not None else "—"
                tag = "**hyb**" if j == 0 else "  #" + str(j + 1)
                vrank = h.vec_rank if h.vec_rank is not None else "—"
                brank = h.bm25_rank if h.bm25_rank is not None else "—"
                lines.append(
                    f"- {tag} : [{p['code']}] {price}  {p['name']}  "
                    f"_(vec#{vrank}, bm25#{brank}, rrf={h.rrf_score:.4f})_\n"
                )
        else:
            lines.append("- **hyb** : —\n")
        lines.append("\n")

    lines.insert(2, f"**Hybrid changed top-1 on {diff_count}/{len(queries)} queries**\n\n")
    REPORT_PATH.write_text("".join(lines), encoding="utf-8")
    print(f"wrote {REPORT_PATH}", file=sys.stderr)
    print(f"hybrid changed top-1 on {diff_count}/{len(queries)} queries", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
