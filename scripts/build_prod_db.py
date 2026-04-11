"""Build a slim production DB containing only runtime-needed tables.

Source: data/chatapp_data.db (full development DB with chat history)
Output: data/chatapp_data_prod.db (only what the agent reads at runtime)

Kept:
  products, products_meta
  vec_products and its shadow tables
  fts_products and its shadow tables

Dropped: messages, chats, customer_terms, vec_customer_terms*,
vec_products_enriched*, extracted_order_items, order_candidates, etc.
"""
from __future__ import annotations

import shutil
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SRC = ROOT / "data" / "chatapp_data.db"
DST = ROOT / "data" / "chatapp_data_prod.db"

# Tables to keep. Virtual-table shadow tables are detected automatically.
KEEP_TABLES = {
    "products",
    "products_meta",
    "vec_products",
    "fts_products",
}


def main() -> None:
    if DST.exists():
        DST.unlink()

    # Full file copy is the simplest way — virtual tables and their shadow
    # tables, indexes, triggers all come along. Then we drop what we don't
    # want and VACUUM to reclaim space.
    shutil.copy2(SRC, DST)

    conn = sqlite3.connect(str(DST))
    conn.row_factory = sqlite3.Row

    # Discover the virtual-table shadow tables we MUST keep alongside
    # vec_products / fts_products. They share a name prefix.
    keep_prefixes = tuple(t + "_" for t in KEEP_TABLES)

    # Enumerate user tables (skip sqlite_*, skip ones we keep)
    tables = [
        r["name"]
        for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        )
    ]

    def keep(t: str) -> bool:
        if t in KEEP_TABLES:
            return True
        if t.startswith(keep_prefixes):
            return True
        return False

    drop = [t for t in tables if not keep(t)]

    # Drop in a loop because some tables depend on others; ignore errors
    # caused by FK/shadow ordering and just retry.
    remaining = drop[:]
    for _ in range(5):
        next_round = []
        for t in remaining:
            try:
                conn.execute(f'DROP TABLE IF EXISTS "{t}"')
            except sqlite3.OperationalError:
                next_round.append(t)
        remaining = next_round
        if not remaining:
            break
    conn.commit()

    # Drop user indexes that pointed at dropped tables (auto-dropped, but be safe)
    conn.commit()

    # Reclaim space
    conn.execute("VACUUM")
    conn.commit()
    conn.close()

    print(f"src: {SRC.stat().st_size/1024/1024:7.1f} MB")
    print(f"dst: {DST.stat().st_size/1024/1024:7.1f} MB  -> {DST}")

    # Sanity check (vec_products needs the sqlite-vec extension loaded)
    import sqlite_vec
    conn = sqlite3.connect(str(DST))
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    n_products = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    n_meta = conn.execute("SELECT COUNT(*) FROM products_meta").fetchone()[0]
    n_vec_chunks = conn.execute("SELECT COUNT(*) FROM vec_products_chunks").fetchone()[0]
    print(f"products: {n_products}  meta: {n_meta}  vec_chunks: {n_vec_chunks}")
    conn.close()


if __name__ == "__main__":
    main()
