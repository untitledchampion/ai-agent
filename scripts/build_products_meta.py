"""Inference of normalized sale unit and per-piece length for products.

Reads from data/chatapp_data.db.products and writes a separate analysis
table products_meta. Original products table is not modified.

unit_norm  : шт | м | м2 | кг | пачка | компл  (canonical)
pieces_length_m : NULL or float — length of one piece (for piece-sold profiles)

Heuristic:
  - unit='шт'/'упаковка'/'упак'/'рул'/'Упаковка 10 штук' → unit_norm='шт'
  - unit='м2' → 'м2'
  - unit='кг' → 'кг'
  - unit='пачка' → 'пачка'
  - unit='компл' → 'компл'
  - unit='пог. м':
      look in name for explicit piece length like "(3,2м)" / "2.0м" / " 3,5 м "
      → if found: unit_norm='шт', pieces_length_m=<length>
      → otherwise: unit_norm='м' (true linear meters, e.g. led tape)
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path

DB = Path(__file__).resolve().parent.parent / "data" / "chatapp_data.db"


# Match length-of-piece tokens. We want patterns where a number
# with comma/dot decimal sits next to "м" and is anchored by paren,
# whitespace or string boundary — but NOT followed by "/у" (per
# упаковка) or another digit.
_LENGTH_RX = re.compile(
    r"(?:\(|\s|^)"          # left boundary: paren / space / start
    r"(\d+[.,]\d+)\s*м"     # number + м
    r"(?!\d)"               # not part of a longer number
    r"(?!/у)"               # not "м/у" (per упаковка)
    r"(?:\)|\s|$|[+,])"     # right boundary
)


def normalize(unit: str | None, name: str) -> tuple[str | None, float | None]:
    if not unit:
        return None, None
    u = unit.strip().lower()
    if u in ("шт", "упаковка", "упак", "рул", "упаковка 10 штук"):
        return "шт", None
    if u == "м2":
        return "м2", None
    if u == "кг":
        return "кг", None
    if u == "пачка":
        return "пачка", None
    if u == "компл":
        return "компл", None
    if u == "пог. м":
        m = _LENGTH_RX.search(name)
        if m:
            try:
                return "шт", float(m.group(1).replace(",", "."))
            except ValueError:
                pass
        return "м", None
    return None, None


def main() -> None:
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products_meta (
            product_id      INTEGER PRIMARY KEY,
            unit_norm       TEXT,
            pieces_length_m REAL
        )
    """)
    conn.execute("DELETE FROM products_meta")

    rows = conn.execute("SELECT id, name, unit FROM products").fetchall()
    inferred = 0
    by_unit: dict[str | None, int] = {}
    pieces_count = 0

    for r in rows:
        unit_norm, plm = normalize(r["unit"], r["name"])
        conn.execute(
            "INSERT INTO products_meta (product_id, unit_norm, pieces_length_m) VALUES (?, ?, ?)",
            (r["id"], unit_norm, plm),
        )
        if unit_norm is not None:
            inferred += 1
        by_unit[unit_norm] = by_unit.get(unit_norm, 0) + 1
        if plm is not None:
            pieces_count += 1

    conn.commit()
    print(f"products: {len(rows)}  inferred: {inferred}  with pieces_length: {pieces_count}")
    print("--- distribution ---")
    for k, v in sorted(by_unit.items(), key=lambda kv: -kv[1]):
        print(f"  {v:5d}  {k}")
    conn.close()


if __name__ == "__main__":
    main()
