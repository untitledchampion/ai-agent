"""Benchmark pure-vector search on real customer phrases.

Strategy:
  - Sample 100 raw_names from extracted_order_items, stratified:
      50 from the top-frequency ones (most common real customer phrases),
      50 random from the long tail.
  - For each, run vector search on vec_products, take top-3.
  - Output a readable report: query, top-1 distance, top-1 product, top-2, top-3.
  - Flag weak results (top-1 distance > 1.0) for manual review.
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

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "chatapp_data.db"
REPORT_PATH = ROOT / "search" / "benchmark_report.md"
DIM = 1024
N_TOP = 50
N_TAIL = 50
RANDOM_SEED = 42


def sample_queries(conn: sqlite3.Connection) -> list[tuple[str, int]]:
    """Return list of (raw_name, frequency) pairs, 100 items."""
    top = conn.execute(
        """
        SELECT raw_name, COUNT(*) n
        FROM extracted_order_items
        WHERE raw_name IS NOT NULL AND LENGTH(TRIM(raw_name)) > 0
        GROUP BY raw_name
        ORDER BY n DESC
        LIMIT ?
        """,
        (N_TOP,),
    ).fetchall()

    # Long-tail: frequency between 2 and 10 (genuine phrases, not one-off typos)
    tail_candidates = conn.execute(
        """
        SELECT raw_name, COUNT(*) n
        FROM extracted_order_items
        WHERE raw_name IS NOT NULL AND LENGTH(TRIM(raw_name)) > 2
        GROUP BY raw_name
        HAVING n BETWEEN 2 AND 10
        """
    ).fetchall()

    rng = random.Random(RANDOM_SEED)
    tail = rng.sample(tail_candidates, min(N_TAIL, len(tail_candidates)))

    return top + tail


def main() -> int:
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"device: {device}", file=sys.stderr)
    model = SentenceTransformer("BAAI/bge-m3", device=device)

    conn = sqlite3.connect(DB_PATH)
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    queries = sample_queries(conn)
    print(f"sampled {len(queries)} queries", file=sys.stderr)

    texts = [q for q, _ in queries]
    vecs = model.encode(
        texts, normalize_embeddings=True, batch_size=64, show_progress_bar=True
    )

    results: list[dict] = []
    for (raw, freq), v in zip(queries, vecs):
        blob = struct.pack(f"{DIM}f", *v)
        rows = conn.execute(
            """
            SELECT p.name, p.code, p.price_dealer, p.sheet, v.distance
            FROM vec_products v JOIN products p ON p.id = v.id
            WHERE v.embedding MATCH ? AND k = 3
            ORDER BY v.distance
            """,
            (blob,),
        ).fetchall()
        results.append({"raw": raw, "freq": freq, "hits": rows})

    # Build report
    lines: list[str] = []
    lines.append("# Benchmark: pure-vector search on real customer phrases\n")
    lines.append(f"- Model: BGE-M3 (local, MPS)\n")
    lines.append(f"- Products indexed: 1705\n")
    lines.append(f"- Queries: {len(queries)} "
                 f"({N_TOP} top-frequency + {N_TAIL} long-tail)\n\n")

    # Summary stats
    d1s = [r["hits"][0][4] for r in results if r["hits"]]
    import statistics
    lines.append("## Distance stats (top-1)\n")
    lines.append(f"- min: {min(d1s):.3f}\n")
    lines.append(f"- median: {statistics.median(d1s):.3f}\n")
    lines.append(f"- mean: {statistics.mean(d1s):.3f}\n")
    lines.append(f"- max: {max(d1s):.3f}\n")
    buckets = {"<0.5": 0, "0.5-0.7": 0, "0.7-0.9": 0, "0.9-1.1": 0, ">1.1": 0}
    for d in d1s:
        if d < 0.5: buckets["<0.5"] += 1
        elif d < 0.7: buckets["0.5-0.7"] += 1
        elif d < 0.9: buckets["0.7-0.9"] += 1
        elif d < 1.1: buckets["0.9-1.1"] += 1
        else: buckets[">1.1"] += 1
    lines.append("\n### Buckets\n")
    for k, v in buckets.items():
        lines.append(f"- {k}: {v}\n")
    lines.append("\n---\n\n")

    # Per-query results
    lines.append("## Top-frequency queries\n\n")
    for i, r in enumerate(results):
        if i == N_TOP:
            lines.append("\n## Long-tail queries\n\n")
        raw, freq, hits = r["raw"], r["freq"], r["hits"]
        lines.append(f"**`{raw}`** (n={freq})\n\n")
        for j, (name, code, price, sheet, d) in enumerate(hits):
            marker = "→" if j == 0 else " "
            price_s = f"{price}р" if price is not None else "—"
            lines.append(f"- {marker} `{d:.3f}`  [{code}] {price_s}  {name}\n")
        lines.append("\n")

    REPORT_PATH.write_text("".join(lines), encoding="utf-8")
    print(f"wrote report: {REPORT_PATH}", file=sys.stderr)
    print(f"\nDistance buckets: {buckets}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
