"""Knowledge-base search — top-k lookup in vec_knowledge via BGE-M3.

Ищет релевантные чанки базы знаний по натяжным потолкам. Реюзит тот же
embedder и то же соединение, что и product_search.
"""
from __future__ import annotations

import json
import logging
import sqlite3
import struct
from pathlib import Path

from agent.core import product_search as _ps  # reuse BGE-M3 model + DB_PATH

logger = logging.getLogger(__name__)

DIM = 1024


def _open_conn() -> sqlite3.Connection:
    import sqlite_vec

    conn = sqlite3.connect(str(_ps.DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def search_knowledge(query: str, k: int = 3) -> list[dict]:
    """Возвращает top-k чанков базы знаний для свободного запроса.

    Каждый результат: {
        id, slug, title, topic, content, escalate,
        images: [{path, caption}],
        products: [{id, name, price_dealer, category}],  # первые 6
        distance
    }
    """
    q = (query or "").strip()
    if not q:
        return []

    model = _ps._get_model()
    vec = model.encode([q], normalize_embeddings=True)[0]
    blob = struct.pack(f"{DIM}f", *vec)

    conn = _open_conn()
    try:
        rows = conn.execute(
            """
            SELECT c.id, c.slug, c.title, c.topic, c.content, c.escalate,
                   c.images_json, c.product_ids_json, v.distance
            FROM vec_knowledge v
            JOIN knowledge_chunks c ON c.id = v.id
            WHERE v.embedding MATCH ? AND v.k = ?
            ORDER BY v.distance
            """,
            (blob, k),
        ).fetchall()

        out: list[dict] = []
        for r in rows:
            product_ids = json.loads(r["product_ids_json"] or "[]")[:6]
            products: list[dict] = []
            if product_ids:
                placeholders = ",".join("?" * len(product_ids))
                p_rows = conn.execute(
                    f"""SELECT id, name, category, price_dealer
                        FROM products WHERE id IN ({placeholders})""",
                    product_ids,
                ).fetchall()
                products = [dict(pr) for pr in p_rows]
            out.append({
                "id": r["id"],
                "slug": r["slug"],
                "title": r["title"],
                "topic": r["topic"],
                "content": r["content"],
                "escalate": r["escalate"],
                "images": json.loads(r["images_json"] or "[]"),
                "products": products,
                "distance": r["distance"],
            })
        return out
    finally:
        conn.close()
