"""Side-by-side compare: plain vec_products vs vec_products_enriched on same 100 queries."""
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
REPORT = ROOT / "search" / "compare_plain_vs_enriched.md"
DIM = 1024
N_TOP, N_TAIL, SEED = 50, 50, 42


def sample(conn):
    top = conn.execute(
        """
        SELECT raw_name, COUNT(*) n FROM extracted_order_items
        WHERE raw_name IS NOT NULL AND LENGTH(TRIM(raw_name)) > 0
        GROUP BY raw_name ORDER BY n DESC LIMIT ?
        """,
        (N_TOP,),
    ).fetchall()
    tail_c = conn.execute(
        """
        SELECT raw_name, COUNT(*) n FROM extracted_order_items
        WHERE raw_name IS NOT NULL AND LENGTH(TRIM(raw_name)) > 2
        GROUP BY raw_name HAVING n BETWEEN 2 AND 10
        """
    ).fetchall()
    tail = random.Random(SEED).sample(tail_c, min(N_TAIL, len(tail_c)))
    return top + tail


def top1(conn, table, vec):
    blob = struct.pack(f"{DIM}f", *vec)
    row = conn.execute(
        f"SELECT id, distance FROM {table} WHERE embedding MATCH ? AND k = 1 ORDER BY distance",
        (blob,),
    ).fetchone()
    return row


def main():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    model = SentenceTransformer(
        "BAAI/bge-m3",
        device="mps" if torch.backends.mps.is_available() else "cpu",
    )
    queries = sample(conn)
    vecs = model.encode(
        [q for q, _ in queries],
        normalize_embeddings=True,
        batch_size=64,
        show_progress_bar=True,
    )

    def product(pid):
        return conn.execute(
            "SELECT name, code, price_dealer FROM products WHERE id = ?", (pid,)
        ).fetchone()

    lines = ["# Plain vs enriched (alias-augmented) index\n\n"]
    changed = 0
    for i, ((raw, freq), v) in enumerate(zip(queries, vecs)):
        if i == N_TOP:
            lines.append("\n## Long-tail\n\n")
        elif i == 0:
            lines.append("## Top-frequency\n\n")

        pr = top1(conn, "vec_products", v)
        en = top1(conn, "vec_products_enriched", v)
        pr_id = pr["id"] if pr else None
        en_id = en["id"] if en else None

        diff = pr_id != en_id
        if diff:
            changed += 1
        mark = " ⚡" if diff else ""
        lines.append(f"### `{raw}` (n={freq}){mark}\n\n")
        if pr:
            p = product(pr_id)
            price = f"{p['price_dealer']}р" if p["price_dealer"] is not None else "—"
            lines.append(f"- **plain** ({pr['distance']:.3f}) [{p['code']}] {price}  {p['name']}\n")
        if en:
            p = product(en_id)
            price = f"{p['price_dealer']}р" if p["price_dealer"] is not None else "—"
            lines.append(f"- **enrich** ({en['distance']:.3f}) [{p['code']}] {price}  {p['name']}\n")
        lines.append("\n")

    lines.insert(1, f"**Top-1 changed on {changed}/{len(queries)} queries**\n\n")
    REPORT.write_text("".join(lines), encoding="utf-8")
    print(f"changed: {changed}/{len(queries)}", file=sys.stderr)
    print(f"wrote {REPORT}", file=sys.stderr)


if __name__ == "__main__":
    main()
