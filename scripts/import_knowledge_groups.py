#!/usr/bin/env python3
"""Import knowledge from ИИ.xlsx 'Группы' sheet into knowledge_product_aliases.

For each group row where 'в 1С' is filled:
  - Parse jargon variants from 'Топ члены' column (format: "слово(count) | слово2(count2)")
  - Parse product names from 'в 1С' column (newline-separated)
  - Match each 1С product name to products.id via Python-side case-insensitive match
  - Insert alias → product_id pairs into knowledge_product_aliases

Single-product groups:  each jargon variant → that one product_id
Multi-product groups:   each jargon variant → ALL product_ids (disambiguation via size/color filters at runtime)

Usage:
    python scripts/import_knowledge_groups.py --input path/to/ИИ.xlsx [--min-freq 2] [--dry-run]
"""
from __future__ import annotations

import argparse
import re
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DB_PATH = ROOT / "data" / "chatapp_data_prod.db"


def _norm(s: str) -> str:
    if not s:
        return ""
    s = s.lower().replace("ё", "е").strip()
    s = re.sub(r"\s*№\s*", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def _parse_top_members(s: str) -> list[tuple[str, int]]:
    """Parse 'подвесы(1141) | подвес(296)' → [('подвесы', 1141), ...]"""
    if not s:
        return []
    pairs = []
    for chunk in str(s).split("|"):
        chunk = chunk.strip()
        m = re.match(r"^(.+?)\((\d+)\)$", chunk)
        if m:
            alias = m.group(1).strip()
            # Skip junk: entries starting with digits+punctuation like "1)", "2."
            if re.match(r"^\d+[\.\)]\s*", alias):
                alias = re.sub(r"^\d+[\.\)]\s*", "", alias).strip()
            if alias and len(alias) >= 2:
                pairs.append((alias, int(m.group(2))))
    return pairs


def _load_products(conn: sqlite3.Connection) -> dict[str, int]:
    """Load products: normalized_name → id. For duplicates, keep first."""
    rows = conn.execute("SELECT id, name FROM products").fetchall()
    mapping: dict[str, int] = {}
    for pid, name in rows:
        n = _norm(name)
        if n not in mapping:
            mapping[n] = pid
    return mapping


def _clean_1c_name(name: str) -> str:
    """Strip price-list prefixes like '303, ', quotes, leading dashes."""
    s = name.strip()
    # Strip leading article "NNN, " or "NNN. "
    s = re.sub(r"^\d{2,4}[,\.]\s*", "", s)
    # Strip leading "- "
    s = re.sub(r"^[-–—]\s*", "", s)
    # Strip quotes
    s = s.replace('"', '').replace("'", '').replace('\u00ab', '').replace('\u00bb', '')
    # Strip stray dashes attached to words: "Мат- MSD" → "Мат MSD"
    s = re.sub(r"\s*[-–—]+\s*", " ", s)
    return s.strip()


def _match_1c_to_product_ids(
    product_names_1c: list[str],
    products_map: dict[str, int],
) -> list[int]:
    """Match 1C product names to product IDs via normalized exact/substring match."""
    ids = []
    for name in product_names_1c:
        cleaned = _clean_1c_name(name)
        n = _norm(cleaned)
        if not n or len(n) < 3:
            continue

        # 1. Exact match
        pid = products_map.get(n)
        if pid is not None:
            ids.append(pid)
            continue

        # 2. Substring match (either direction)
        found = False
        for pn, pi in products_map.items():
            if n in pn or pn in n:
                ids.append(pi)
                found = True
                break

        if found:
            continue

        # 3. Word-overlap match: if all significant words (len>=3) from 1C name
        #    appear in a product name, it's likely a match
        words = [w for w in n.split() if len(w) >= 3]
        if len(words) >= 2:
            best_score = 0
            best_pid = None
            for pn, pi in products_map.items():
                score = sum(1 for w in words if w in pn)
                if score > best_score and score >= len(words) * 0.7:
                    best_score = score
                    best_pid = pi
            if best_pid is not None:
                ids.append(best_pid)

    return list(set(ids))  # dedupe


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--input", required=True, help="Path to ИИ.xlsx")
    ap.add_argument("--min-freq", type=int, default=2,
                    help="Minimum frequency to import a jargon variant (default: 2)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    try:
        import pandas as pd
    except ImportError:
        sys.exit("pip install pandas openpyxl")

    df = pd.read_excel(args.input, sheet_name="Группы", header=0)
    print(f"Loaded {len(df)} rows from 'Группы'")

    # Filter rows with 'в 1С' filled
    col_1c = df.columns[1]  # 'в 1с'
    col_members = df.columns[6]  # 'Топ члены'

    mapped = df[df[col_1c].notna()]
    print(f"Rows with 'в 1С': {len(mapped)}")

    conn = sqlite3.connect(str(DB_PATH))
    products_map = _load_products(conn)
    print(f"Products in DB: {len(products_map)}")

    # Ensure table exists
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS knowledge_product_aliases (
            id               INTEGER PRIMARY KEY AUTOINCREMENT,
            alias            TEXT NOT NULL,
            alias_norm       TEXT NOT NULL,
            product_id       INTEGER NOT NULL REFERENCES products(id),
            match_type       TEXT NOT NULL,
            match_confidence REAL,
            source           TEXT NOT NULL,
            source_row_ref   TEXT,
            note             TEXT,
            created_at       TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at       TEXT NOT NULL DEFAULT (datetime('now'))
        );
        CREATE INDEX IF NOT EXISTS ix_kpa_alias_norm ON knowledge_product_aliases(alias_norm);
        CREATE INDEX IF NOT EXISTS ix_kpa_product_id ON knowledge_product_aliases(product_id);
        CREATE UNIQUE INDEX IF NOT EXISTS ux_kpa_alias_product ON knowledge_product_aliases(alias_norm, product_id);
    """)

    total_inserted = 0
    total_skipped = 0
    total_no_match = 0
    groups_matched = 0
    groups_no_match = 0

    for idx, (_, row) in enumerate(mapped.iterrows()):
        products_1c_raw = str(row[col_1c]).strip()
        product_names = [p.strip() for p in products_1c_raw.split("\n") if p.strip()]
        members = _parse_top_members(str(row[col_members]) if pd.notna(row[col_members]) else "")

        # Filter by min frequency
        members = [(alias, freq) for alias, freq in members if freq >= args.min_freq]
        if not members:
            continue

        # Match 1C names to product IDs
        product_ids = _match_1c_to_product_ids(product_names, products_map)
        if not product_ids:
            groups_no_match += 1
            if members and members[0][1] >= 10:  # only log frequent misses
                print(f"  NO MATCH: {product_names[0][:60]}... ({len(members)} aliases, top freq={members[0][1]})")
            total_no_match += len(members)
            continue

        groups_matched += 1

        for alias, freq in members:
            an = _norm(alias)
            if not an:
                continue
            for pid in product_ids:
                if args.dry_run:
                    total_inserted += 1
                    continue
                try:
                    conn.execute(
                        """INSERT INTO knowledge_product_aliases
                           (alias, alias_norm, product_id, match_type, match_confidence,
                            source, source_row_ref, note)
                           VALUES (?, ?, ?, 'kb_group', 1.0, 'xlsx:ИИ:Группы', ?, ?)
                           ON CONFLICT(alias_norm, product_id) DO UPDATE SET
                             -- don't overwrite manual entries
                             match_type = CASE
                               WHEN excluded.match_type = 'manual' THEN knowledge_product_aliases.match_type
                               ELSE CASE
                                 WHEN knowledge_product_aliases.match_type = 'manual' THEN 'manual'
                                 ELSE 'kb_group'
                               END
                             END,
                             updated_at = datetime('now')
                        """,
                        (alias, an, pid, f"row:{idx}", f"freq={freq}, products={len(product_ids)}"),
                    )
                    total_inserted += 1
                except Exception as e:
                    total_skipped += 1

    if not args.dry_run:
        conn.commit()

    # Stats
    total_rows = conn.execute("SELECT COUNT(*) FROM knowledge_product_aliases").fetchone()[0]
    by_type = conn.execute(
        "SELECT match_type, COUNT(*) FROM knowledge_product_aliases GROUP BY match_type"
    ).fetchall()

    print(f"\n{'DRY RUN — ' if args.dry_run else ''}Results:")
    print(f"  Groups matched to products: {groups_matched}")
    print(f"  Groups with no product match: {groups_no_match}")
    print(f"  Alias-product pairs inserted/updated: {total_inserted}")
    print(f"  Skipped (errors): {total_skipped}")
    print(f"  Aliases with no 1C match: {total_no_match}")
    print(f"\n  Total rows in knowledge_product_aliases: {total_rows}")
    for mt, cnt in by_type:
        print(f"    {mt}: {cnt}")

    if not args.dry_run:
        conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    conn.close()


if __name__ == "__main__":
    main()
