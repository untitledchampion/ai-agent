"""Customer-alias enrichment.

For each product, find the closest customer_terms (real phrases from chats)
and attach them to the product's text, then re-encode and replace vec_products.

Strategy:
  1. Load all product vectors and all customer_term vectors into numpy.
  2. Cosine-sim matrix (1705 x 8888) in one matmul (vectors are normalized).
  3. For each product pick top-N aliases with sim >= THRESHOLD.
  4. Save aliases to products.aliases column (new).
  5. Build enriched text per product, re-encode with BGE-M3, replace vec_products.
"""
from __future__ import annotations

import sqlite3
import struct
import sys
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np  # noqa: E402
import sqlite_vec  # noqa: E402
import torch  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "chatapp_data.db"
DIM = 1024
TOP_N_ALIASES = 5
MIN_COSINE = 0.55   # keep only reasonably close aliases
MIN_TERM_TOTAL = 2  # ignore customer groups seen only once


def _unpack(blob: bytes) -> np.ndarray:
    return np.array(struct.unpack(f"{DIM}f", blob), dtype=np.float32)


def _pack(vec: np.ndarray) -> bytes:
    return struct.pack(f"{DIM}f", *vec.astype(np.float32).tolist())


def main() -> int:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    # Ensure aliases column exists
    cols = {r[1] for r in conn.execute("PRAGMA table_info(products)").fetchall()}
    if "aliases" not in cols:
        conn.execute("ALTER TABLE products ADD COLUMN aliases TEXT")

    # ---- load product vectors ----
    print("loading product vectors...", file=sys.stderr)
    prod_rows = conn.execute(
        "SELECT p.id, p.category, p.name, p.color, p.width, v.embedding "
        "FROM products p JOIN vec_products v ON v.id = p.id ORDER BY p.id"
    ).fetchall()
    prod_ids = np.array([r["id"] for r in prod_rows], dtype=np.int64)
    prod_vecs = np.stack([_unpack(r["embedding"]) for r in prod_rows])
    print(f"  products: {prod_vecs.shape}", file=sys.stderr)

    # ---- load customer_term vectors ----
    print("loading customer_term vectors...", file=sys.stderr)
    term_rows = conn.execute(
        "SELECT c.id, c.group_key, c.surface_forms, c.total, v.embedding "
        "FROM customer_terms c JOIN vec_customer_terms v ON v.id = c.id "
        "WHERE c.total >= ? ORDER BY c.id",
        (MIN_TERM_TOTAL,),
    ).fetchall()
    term_vecs = np.stack([_unpack(r["embedding"]) for r in term_rows])
    term_texts = [r["surface_forms"] or r["group_key"] for r in term_rows]
    print(f"  terms: {term_vecs.shape}", file=sys.stderr)

    # ---- cosine sim matrix ----
    print("computing cosine matrix...", file=sys.stderr)
    sims = prod_vecs @ term_vecs.T  # (P, T)
    print(f"  matrix: {sims.shape}", file=sys.stderr)

    # ---- top-N per product ----
    print("selecting top-N aliases per product...", file=sys.stderr)
    top_idx = np.argpartition(-sims, TOP_N_ALIASES, axis=1)[:, :TOP_N_ALIASES]

    aliases_per_product: dict[int, list[str]] = {}
    total_with_aliases = 0
    for row_i, pid in enumerate(prod_ids):
        cand = top_idx[row_i]
        # sort the small slice by actual similarity desc
        cand = cand[np.argsort(-sims[row_i, cand])]
        picked: list[str] = []
        seen: set[str] = set()
        for j in cand:
            s = float(sims[row_i, j])
            if s < MIN_COSINE:
                break
            t = term_texts[j].strip()
            if not t or t in seen:
                continue
            seen.add(t)
            picked.append(t)
        if picked:
            aliases_per_product[int(pid)] = picked
            total_with_aliases += 1
    print(
        f"  products with at least one alias: {total_with_aliases}/{len(prod_ids)}",
        file=sys.stderr,
    )

    # ---- save aliases ----
    upd = [
        (" | ".join(aliases_per_product.get(int(pid), [])), int(pid))
        for pid in prod_ids
    ]
    conn.executemany("UPDATE products SET aliases = ? WHERE id = ?", upd)
    conn.commit()

    # ---- re-encode with enriched text ----
    print("encoding enriched product texts...", file=sys.stderr)
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = SentenceTransformer("BAAI/bge-m3", device=device)

    enriched_texts: list[str] = []
    for r in prod_rows:
        parts: list[str] = []
        if r["category"]:
            parts.append(r["category"])
        parts.append(r["name"])
        if r["color"]:
            parts.append(r["color"])
        if r["width"]:
            parts.append(f"ширина {r['width']}")
        aliases = aliases_per_product.get(int(r["id"]))
        if aliases:
            parts.append("|| " + " | ".join(aliases))
        enriched_texts.append(" | ".join(parts))

    new_vecs = model.encode(
        enriched_texts,
        normalize_embeddings=True,
        batch_size=32,
        show_progress_bar=True,
    )

    # ---- replace vec_products ----
    print("replacing vec_products...", file=sys.stderr)
    conn.execute("DROP TABLE IF EXISTS vec_products")
    conn.execute(
        f"CREATE VIRTUAL TABLE vec_products USING vec0("
        f"id INTEGER PRIMARY KEY, embedding float[{DIM}])"
    )
    conn.executemany(
        "INSERT INTO vec_products(id, embedding) VALUES (?, ?)",
        [(int(pid), _pack(v)) for pid, v in zip(prod_ids, new_vecs)],
    )
    conn.commit()
    print("done.", file=sys.stderr)

    # ---- spot-check ----
    print("\nSample enrichments:", file=sys.stderr)
    for sample_id in prod_ids[:0]:
        pass
    for row in conn.execute(
        "SELECT name, aliases FROM products WHERE aliases != '' ORDER BY RANDOM() LIMIT 8"
    ):
        print(f"  [{row[0][:50]}]  →  {row[1][:80]}", file=sys.stderr)

    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
