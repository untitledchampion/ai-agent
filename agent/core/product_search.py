"""Product search — top-k lookup in vec_products via BGE-M3.

Lazy-loads the embedding model and a shared sqlite connection on first call.
Returns plain dicts so results can be JSON-serialized into tool outputs.
"""
from __future__ import annotations

import logging
import sqlite3
import struct
import threading
from pathlib import Path

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parent.parent.parent
DB_PATH = ROOT / "data" / "chatapp_data_prod.db"
MODEL_NAME = "BAAI/bge-m3"
DIM = 1024

_model = None
_model_lock = threading.Lock()


def _get_model():
    global _model
    if _model is not None:
        return _model
    with _model_lock:
        if _model is not None:
            return _model
        import warnings
        warnings.filterwarnings("ignore")
        import torch
        from sentence_transformers import SentenceTransformer

        device = "mps" if torch.backends.mps.is_available() else "cpu"
        logger.info(f"Loading BGE-M3 on {device}...")
        _model = SentenceTransformer(MODEL_NAME, device=device)
        logger.info("BGE-M3 loaded")
        return _model


def _open_conn() -> sqlite3.Connection:
    import sqlite_vec

    conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)
    return conn


def search_products(query: str, k: int = 10) -> list[dict]:
    """Return top-k product candidates for a free-form query.

    Each result: {id, code, name, category, color, width, price_dealer, distance}.
    """
    q = (query or "").strip()
    if not q:
        return []

    model = _get_model()
    vec = model.encode([q], normalize_embeddings=True)[0]
    blob = struct.pack(f"{DIM}f", *vec)

    conn = _open_conn()
    try:
        rows = conn.execute(
            """
            SELECT p.id, p.code, p.name, p.category, p.color, p.width,
                   p.price_dealer, p.unit AS unit_raw,
                   m.unit_norm, m.pieces_length_m,
                   v.distance
            FROM vec_products v
            JOIN products p ON p.id = v.id
            LEFT JOIN products_meta m ON m.product_id = p.id
            WHERE v.embedding MATCH ? AND v.k = ?
            ORDER BY v.distance
            """,
            (blob, k),
        ).fetchall()
    finally:
        conn.close()

    return [dict(r) for r in rows]


if __name__ == "__main__":
    import json
    import sys

    query = " ".join(sys.argv[1:]) or "краб стеновой 2 метра"
    for hit in search_products(query, k=10):
        print(json.dumps(hit, ensure_ascii=False))
