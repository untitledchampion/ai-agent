"""Синк номенклатуры из 1С УНФ в локальную products.

Стратегия:
- Тянем ВСЕ товары одним запросом (пагинация $skip в 1С битая).
- Фильтруем папки, дедупим по Ref_Key.
- Апсерт в products по нормализованному name:
  - если есть — проставляем ref_key, обновляем code.
  - если нет — вставляем как новый, эмбеддим, добавляем в vec_products.
- Существующих НЕ в 1С — помечаем legacy (is_legacy=1). Не удаляем.
"""
from __future__ import annotations

import logging
import os
import re
import sqlite3
import struct
import time
from pathlib import Path

import requests

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "data" / "chatapp_data_prod.db"

ODATA_URL = os.environ.get(
    "ODATA_URL", "http://1c.optceiling.ru/unf_potolki/odata/standard.odata"
)
ODATA_USER = os.environ.get("ODATA_USER", "odatauser")
ODATA_PASS = os.environ.get("ODATA_PASS", "rty4546")


def _norm(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").lower().replace("ё", "е").strip())


def _ensure_columns(conn: sqlite3.Connection) -> None:
    cols = {r[1] for r in conn.execute("PRAGMA table_info(products)")}
    if "ref_key" not in cols:
        conn.execute("ALTER TABLE products ADD COLUMN ref_key TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS ix_products_refkey ON products(ref_key)")
    if "is_legacy" not in cols:
        conn.execute("ALTER TABLE products ADD COLUMN is_legacy INTEGER DEFAULT 0")
    conn.commit()


def _fetch_1c() -> list[dict]:
    s = requests.Session()
    s.auth = (ODATA_USER, ODATA_PASS)
    r = s.get(
        f"{ODATA_URL}/Catalog_Номенклатура",
        params={
            "$top": 10000,
            "$select": "Ref_Key,Code,Description,IsFolder,DeletionMark",
            "$format": "json",
        },
        timeout=300,
    )
    r.raise_for_status()
    items = r.json().get("value", [])
    seen = set()
    out = []
    for x in items:
        if x.get("IsFolder") or x.get("DeletionMark"):
            continue
        rk = x.get("Ref_Key")
        if not rk or rk in seen:
            continue
        seen.add(rk)
        out.append(x)
    return out


def _embed(model, text: str) -> bytes:
    vec = model.encode([text], normalize_embeddings=True)[0]
    return struct.pack(f"{len(vec)}f", *vec)


def run_sync() -> dict:
    """Выполняет синк. Возвращает отчёт."""
    t0 = time.time()
    logger.info("sync_1c: fetching from 1C...")
    items_1c = _fetch_1c()
    logger.info("sync_1c: got %d products from 1C", len(items_1c))

    # Открываем БД
    import sqlite_vec

    conn = sqlite3.connect(str(DB_PATH), timeout=60)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=60000")
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    _ensure_columns(conn)

    # Локальные по name_norm
    local = {}
    for r in conn.execute("SELECT id, code, name, ref_key FROM products"):
        local.setdefault(_norm(r["name"]), r)

    # Загружаем модель эмбеддингов
    from agent.core.product_search import _get_model

    model = _get_model()

    updated = 0
    added = 0
    matched_refs: set[str] = set()

    for x in items_1c:
        name = x.get("Description") or ""
        if not name:
            continue
        n = _norm(name)
        ref = x["Ref_Key"]
        code = x.get("Code") or None
        matched_refs.add(ref)

        row = local.get(n)
        if row:
            if row["ref_key"] != ref or row["code"] != code:
                conn.execute(
                    "UPDATE products SET ref_key=?, code=?, is_legacy=0 WHERE id=?",
                    (ref, code, row["id"]),
                )
                updated += 1
            else:
                conn.execute(
                    "UPDATE products SET is_legacy=0 WHERE id=?", (row["id"],)
                )
        else:
            # Новый — вставляем и эмбеддим
            cur = conn.execute(
                "INSERT INTO products(sheet, code, name, ref_key, is_legacy) VALUES (?,?,?,?,0)",
                ("1c", code, name, ref),
            )
            pid = cur.lastrowid
            try:
                blob = _embed(model, name)
                conn.execute(
                    "INSERT INTO vec_products(id, embedding) VALUES (?, ?)",
                    (pid, blob),
                )
            except Exception as e:
                logger.warning("embed failed for %s: %s", name, e)
            added += 1

    # Осиротевшие — есть у нас с ref_key, нет в 1C; + те что без ref_key после синка
    conn.execute("UPDATE products SET is_legacy=1 WHERE ref_key IS NULL OR ref_key=''")
    if matched_refs:
        placeholders = ",".join("?" * len(matched_refs))
        conn.execute(
            f"UPDATE products SET is_legacy=0 WHERE ref_key IN ({placeholders})",
            tuple(matched_refs),
        )
    orphaned = conn.execute(
        "SELECT COUNT(*) FROM products WHERE is_legacy=1"
    ).fetchone()[0]

    # Алиасы к осиротевшим
    orphaned_aliases = conn.execute("""
        SELECT COUNT(*) FROM product_aliases pa
        WHERE NOT EXISTS (
            SELECT 1 FROM products p
            WHERE p.name = pa.product_name AND (p.is_legacy = 0 OR p.is_legacy IS NULL)
        )
    """).fetchone()[0]

    conn.commit()
    conn.close()

    dur = round(time.time() - t0, 1)
    report = {
        "total_1c": len(items_1c),
        "updated": updated,
        "added": added,
        "orphaned": orphaned,
        "orphaned_aliases": orphaned_aliases,
        "duration_sec": dur,
    }
    logger.info("sync_1c: done %s", report)
    return report
