"""Encode products and customer terms with BGE-M3, store in sqlite-vec tables.

Creates (in chatapp_data.db):
  - vec_products     (virtual table, sqlite-vec): id INTEGER, embedding float[1024]
  - vec_customer_terms (virtual table): id INTEGER, embedding float[1024]

Each row's id matches the primary key in `products` / `customer_terms`.
"""
from __future__ import annotations

import sqlite3
import struct
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")

import sqlite_vec  # noqa: E402
import torch  # noqa: E402
from sentence_transformers import SentenceTransformer  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "chatapp_data.db"
MODEL_NAME = "BAAI/bge-m3"
DIM = 1024


def _pack(vec) -> bytes:
    return struct.pack(f"{DIM}f", *vec)


def _build_text_for_product(row: sqlite3.Row) -> str:
    """Assemble one line of text from product fields for embedding."""
    parts: list[str] = []
    if row["category"]:
        parts.append(row["category"])
    parts.append(row["name"])
    if row["color"]:
        parts.append(row["color"])
    if row["width"]:
        parts.append(f"ширина {row['width']}")
    return " | ".join(parts)


def _build_text_for_group(row: sqlite3.Row) -> str:
    """For customer groups we embed the surface forms users actually typed."""
    if row["surface_forms"]:
        return row["surface_forms"]
    return row["group_key"]


def main() -> int:
    device = "mps" if torch.backends.mps.is_available() else "cpu"
    print(f"device: {device}")
    model = SentenceTransformer(MODEL_NAME, device=device)

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    # Fresh vector tables
    conn.execute("DROP TABLE IF EXISTS vec_products")
    conn.execute("DROP TABLE IF EXISTS vec_customer_terms")
    conn.execute(
        f"CREATE VIRTUAL TABLE vec_products USING vec0("
        f"id INTEGER PRIMARY KEY, embedding float[{DIM}])"
    )
    conn.execute(
        f"CREATE VIRTUAL TABLE vec_customer_terms USING vec0("
        f"id INTEGER PRIMARY KEY, embedding float[{DIM}])"
    )

    # ---- products ----
    prod_rows = conn.execute(
        "SELECT id, category, name, color, width FROM products ORDER BY id"
    ).fetchall()
    prod_ids = [r["id"] for r in prod_rows]
    prod_texts = [_build_text_for_product(r) for r in prod_rows]
    print(f"encoding {len(prod_texts)} products...")
    prod_vecs = model.encode(
        prod_texts, normalize_embeddings=True, batch_size=32, show_progress_bar=True
    )
    conn.executemany(
        "INSERT INTO vec_products(id, embedding) VALUES (?, ?)",
        [(pid, _pack(v)) for pid, v in zip(prod_ids, prod_vecs)],
    )

    # ---- customer terms ----
    term_rows = conn.execute(
        "SELECT id, group_key, surface_forms FROM customer_terms ORDER BY id"
    ).fetchall()
    term_ids = [r["id"] for r in term_rows]
    term_texts = [_build_text_for_group(r) for r in term_rows]
    print(f"encoding {len(term_texts)} customer groups...")
    term_vecs = model.encode(
        term_texts, normalize_embeddings=True, batch_size=64, show_progress_bar=True
    )
    conn.executemany(
        "INSERT INTO vec_customer_terms(id, embedding) VALUES (?, ?)",
        [(tid, _pack(v)) for tid, v in zip(term_ids, term_vecs)],
    )

    conn.commit()
    print("done.")
    print(
        "vec_products:",
        conn.execute("SELECT COUNT(*) FROM vec_products").fetchone()[0],
    )
    print(
        "vec_customer_terms:",
        conn.execute("SELECT COUNT(*) FROM vec_customer_terms").fetchone()[0],
    )
    conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
