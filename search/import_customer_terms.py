"""Import customer groups from yesterday's dictionary work into chatapp_data.db.

Creates new table `customer_terms`. Each row = a fuzzy-clustered group of how
real customers referred to products in chats (group_key + all surface forms).
"""
from __future__ import annotations

import csv
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CSV_PATH = ROOT / "data" / "order_extraction" / "order_items_groups.csv"
DB_PATH = ROOT / "data" / "chatapp_data.db"


def _parse_top_members(raw: str) -> tuple[str, list[str]]:
    """'еврокраб(79) | еврокрааб(15) | ...' -> ('еврокраб еврокрааб ...', [...])"""
    if not raw:
        return "", []
    forms: list[str] = []
    for chunk in raw.split("|"):
        chunk = chunk.strip()
        if not chunk:
            continue
        # strip trailing '(N)'
        if chunk.endswith(")") and "(" in chunk:
            chunk = chunk[: chunk.rindex("(")].strip()
        if chunk:
            forms.append(chunk)
    return " ".join(forms), forms


def main() -> int:
    rows: list[dict] = []
    with CSV_PATH.open(encoding="utf-8") as f:
        reader = csv.DictReader(f)
        # first column may have BOM
        key_col = reader.fieldnames[0]
        for r in reader:
            group_key = (r[key_col] or "").strip()
            if not group_key:
                continue
            total = int(r.get("total") or 0)
            variants = int(r.get("variants") or 0)
            unique_msgs = int(r.get("unique_msgs") or 0)
            surface_joined, surface_list = _parse_top_members(r.get("top_members") or "")
            rows.append({
                "group_key": group_key,
                "total": total,
                "variants": variants,
                "unique_msgs": unique_msgs,
                "top_members": r.get("top_members") or "",
                "surface_forms": surface_joined,
                "sizes": r.get("sizes") or "",
                "colors": r.get("colors") or "",
                "units": r.get("units") or "",
            })

    print(f"parsed {len(rows)} customer groups")

    conn = sqlite3.connect(DB_PATH)
    try:
        conn.execute("DROP TABLE IF EXISTS customer_terms")
        conn.execute(
            """
            CREATE TABLE customer_terms (
                id             INTEGER PRIMARY KEY AUTOINCREMENT,
                group_key      TEXT NOT NULL,
                total          INTEGER NOT NULL,
                variants       INTEGER NOT NULL,
                unique_msgs    INTEGER NOT NULL,
                top_members    TEXT,
                surface_forms  TEXT,
                sizes          TEXT,
                colors         TEXT,
                units          TEXT
            )
            """
        )
        conn.execute("CREATE INDEX idx_customer_terms_key ON customer_terms(group_key)")
        conn.execute("CREATE INDEX idx_customer_terms_total ON customer_terms(total)")
        conn.executemany(
            """
            INSERT INTO customer_terms
              (group_key, total, variants, unique_msgs, top_members,
               surface_forms, sizes, colors, units)
            VALUES
              (:group_key, :total, :variants, :unique_msgs, :top_members,
               :surface_forms, :sizes, :colors, :units)
            """,
            rows,
        )
        conn.commit()
    finally:
        conn.close()

    print(f"wrote {len(rows)} rows to {DB_PATH}:customer_terms")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
