"""Migrate knowledge_product_aliases → simpler product_aliases (alias, product_name).

Run: python scripts/migrate_aliases.py <db_path>
Idempotent — safe to re-run.
"""
from __future__ import annotations

import sys
import sqlite3


def migrate(db_path: str) -> None:
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 1. Create new table
    cur.execute("""
    CREATE TABLE IF NOT EXISTS product_aliases (
        id           INTEGER PRIMARY KEY AUTOINCREMENT,
        alias        TEXT NOT NULL,
        product_name TEXT NOT NULL,
        created_at   TEXT NOT NULL DEFAULT (datetime('now')),
        UNIQUE(alias, product_name)
    )
    """)
    cur.execute("CREATE INDEX IF NOT EXISTS ix_pa_alias ON product_aliases(alias)")
    cur.execute("CREATE INDEX IF NOT EXISTS ix_pa_name  ON product_aliases(product_name)")

    # 2. Check if source table exists
    has_old = cur.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='knowledge_product_aliases'"
    ).fetchone()
    if not has_old:
        print("[migrate] no legacy table, skipping copy")
        conn.commit()
        return

    # 3. Copy data (INSERT OR IGNORE handles dedup via UNIQUE constraint)
    before = cur.execute("SELECT COUNT(*) FROM product_aliases").fetchone()[0]
    cur.execute("""
        INSERT OR IGNORE INTO product_aliases(alias, product_name, created_at)
        SELECT kpa.alias_norm, p.name, kpa.created_at
          FROM knowledge_product_aliases kpa
          JOIN products p ON p.id = kpa.product_id
         WHERE kpa.alias_norm IS NOT NULL
           AND kpa.alias_norm <> ''
           AND p.name IS NOT NULL
           AND p.name <> ''
    """)
    after = cur.execute("SELECT COUNT(*) FROM product_aliases").fetchone()[0]
    conn.commit()
    print(f"[migrate] copied: {after - before} new rows (total now {after})")

    # 4. Stats
    src = cur.execute("SELECT COUNT(*) FROM knowledge_product_aliases").fetchone()[0]
    print(f"[migrate] legacy rows: {src} → new rows: {after}")

    conn.close()


if __name__ == "__main__":
    path = sys.argv[1] if len(sys.argv) > 1 else "./data/chatapp_data_prod.db"
    migrate(path)
