"""Импортирует/обновляет базу знаний о натяжных потолках в прод-БД.

ИСТОЧНИК ДАННЫХ: data/ceiling_knowledge/chunks.json (в гите).
Картинки: data/knowledge_images/*.png (в гите).

БЕЗОПАСНО ДЛЯ ПРОДА:
  - Таблицы создаются через CREATE TABLE IF NOT EXISTS.
  - Существующие таблицы (products, vec_products, scenes и т.д.) НЕ ТРОГАЮТСЯ.
  - Чанки обновляются по slug через UPSERT — ручные правки НЕ ТЕРЯЮТСЯ
    для полей, которых нет в json (таких полей нет, но принцип заложен).
  - --dry-run: показать что будет сделано, без записи в БД.
  - --rebuild: DROP+CREATE (только для локальной разработки!).

Использование:
  # боевой импорт
  python scripts/import_ceiling_knowledge.py

  # предпросмотр без записи
  python scripts/import_ceiling_knowledge.py --dry-run

  # полная пересборка (локально)
  python scripts/import_ceiling_knowledge.py --rebuild
"""
from __future__ import annotations

import argparse
import json
import sqlite3
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "chatapp_data_prod.db"
CHUNKS_JSON = ROOT / "data" / "ceiling_knowledge" / "chunks.json"
IMG_DIR = ROOT / "data" / "knowledge_images"

DIM = 1024
MODEL_NAME = "BAAI/bge-m3"


def ensure_tables(conn: sqlite3.Connection, rebuild: bool) -> None:
    if rebuild:
        print("  ⚠ --rebuild: DROP TABLE knowledge_chunks, vec_knowledge")
        conn.execute("DROP TABLE IF EXISTS knowledge_chunks")
        conn.execute("DROP TABLE IF EXISTS vec_knowledge")

    conn.execute("""
        CREATE TABLE IF NOT EXISTS knowledge_chunks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            slug TEXT NOT NULL UNIQUE,
            title TEXT NOT NULL,
            topic TEXT NOT NULL,
            content TEXT NOT NULL,
            images_json TEXT NOT NULL DEFAULT '[]',
            product_ids_json TEXT NOT NULL DEFAULT '[]',
            escalate TEXT DEFAULT NULL,
            source_doc TEXT NOT NULL,
            created_at TEXT NOT NULL DEFAULT (datetime('now')),
            updated_at TEXT NOT NULL DEFAULT (datetime('now'))
        )
    """)
    conn.execute("CREATE INDEX IF NOT EXISTS ix_kc_topic ON knowledge_chunks(topic)")

    # vec_knowledge — виртуальная таблица sqlite-vec.
    # Проверяем её существование через sqlite_master, т.к. для virtual-таблиц
    # IF NOT EXISTS в CREATE VIRTUAL не всегда поддерживается корректно.
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='vec_knowledge'"
    ).fetchone()
    if not exists:
        conn.execute(
            f"CREATE VIRTUAL TABLE vec_knowledge USING vec0("
            f"id INTEGER PRIMARY KEY, embedding float[{DIM}])"
        )


def load_chunks() -> list[dict]:
    if not CHUNKS_JSON.exists():
        raise FileNotFoundError(
            f"{CHUNKS_JSON} not found. Это файл БЗ, должен быть в репозитории."
        )
    return json.loads(CHUNKS_JSON.read_text(encoding="utf-8"))


def verify_images(chunks: list[dict]) -> list[str]:
    """Проверяет что все картинки из chunks.json существуют на диске."""
    missing: list[str] = []
    for ch in chunks:
        for img in ch.get("images", []):
            path = img.get("path", "")
            # path вида "/static/knowledge_images/foo.png"
            name = path.split("/")[-1]
            if not (IMG_DIR / name).exists():
                missing.append(f"{ch['slug']} → {name}")
    return missing


def upsert_chunk(conn: sqlite3.Connection, ch: dict) -> tuple[int, str]:
    """Возвращает (chunk_id, action: 'inserted'|'updated')."""
    existing = conn.execute(
        "SELECT id FROM knowledge_chunks WHERE slug = ?", (ch["slug"],)
    ).fetchone()

    images_j = json.dumps(ch.get("images", []), ensure_ascii=False)
    pids_j = json.dumps(ch.get("product_ids", []))

    if existing:
        conn.execute(
            """UPDATE knowledge_chunks SET
                title=?, topic=?, content=?,
                images_json=?, product_ids_json=?,
                escalate=?, source_doc=?, updated_at=datetime('now')
               WHERE slug=?""",
            (
                ch["title"], ch["topic"], ch["content"],
                images_j, pids_j,
                ch.get("escalate"), ch.get("source_doc", ""),
                ch["slug"],
            ),
        )
        return existing[0], "updated"

    cur = conn.execute(
        """INSERT INTO knowledge_chunks
            (slug, title, topic, content, images_json, product_ids_json,
             escalate, source_doc)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            ch["slug"], ch["title"], ch["topic"], ch["content"],
            images_j, pids_j,
            ch.get("escalate"), ch.get("source_doc", ""),
        ),
    )
    return cur.lastrowid, "inserted"


def build_embedding_text(ch: dict, product_names: list[str]) -> str:
    head = ch["title"]
    body = ch["content"][:600]
    names = " | ".join(product_names[:10]) if product_names else ""
    return f"{head}\n\n{body}\n\n{names}".strip()


def fetch_product_names(conn: sqlite3.Connection, pids: list[int]) -> list[str]:
    if not pids:
        return []
    placeholders = ",".join("?" * len(pids))
    rows = conn.execute(
        f"SELECT name FROM products WHERE id IN ({placeholders}) LIMIT 15",
        pids,
    ).fetchall()
    return [r[0] for r in rows]


def update_vec(conn: sqlite3.Connection, id_: int, vec_blob: bytes) -> None:
    """sqlite-vec не поддерживает UPSERT; делаем DELETE+INSERT."""
    conn.execute("DELETE FROM vec_knowledge WHERE id = ?", (id_,))
    conn.execute("INSERT INTO vec_knowledge(id, embedding) VALUES (?, ?)", (id_, vec_blob))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dry-run", action="store_true",
                        help="Показать что будет сделано, не писать в БД")
    parser.add_argument("--rebuild", action="store_true",
                        help="ОПАСНО: DROP+CREATE таблиц БЗ (только для локалки)")
    args = parser.parse_args(argv)

    if not DB.exists():
        print(f"✗ {DB} не существует", file=sys.stderr)
        return 1

    chunks = load_chunks()
    print(f"Загружено {len(chunks)} чанков из {CHUNKS_JSON.name}")

    missing = verify_images(chunks)
    if missing:
        print(f"⚠ Отсутствуют {len(missing)} картинок:")
        for m in missing[:10]:
            print(f"    {m}")
        if not args.dry_run:
            print("  Продолжаем импорт, но ответы агента будут ссылаться на битые картинки.")

    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    # sqlite-vec extension
    import sqlite_vec  # type: ignore

    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    ensure_tables(conn, rebuild=args.rebuild)

    # ── Фаза 1: апсерт чанков (без эмбеддингов) ──
    plan: list[tuple[int, str, dict]] = []  # (chunk_id, action, chunk)
    for ch in chunks:
        chunk_id, action = upsert_chunk(conn, ch)
        plan.append((chunk_id, action, ch))

    inserted = sum(1 for _, a, _ in plan if a == "inserted")
    updated = sum(1 for _, a, _ in plan if a == "updated")
    print(f"  chunks: {inserted} inserted, {updated} updated")

    if args.dry_run:
        print("\n--dry-run: откатываю транзакцию, БД не изменена.")
        conn.rollback()
        conn.close()
        return 0

    conn.commit()

    # ── Фаза 2: эмбеддинги ──
    print("\nЗагружаю BGE-M3...")
    import torch  # type: ignore
    from sentence_transformers import SentenceTransformer  # type: ignore

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = SentenceTransformer(MODEL_NAME, device=device)

    texts: list[str] = []
    for chunk_id, _, ch in plan:
        pnames = fetch_product_names(conn, ch.get("product_ids", []))
        texts.append(build_embedding_text(ch, pnames))

    print(f"Кодирую {len(texts)} чанков на {device}...")
    vecs = model.encode(texts, normalize_embeddings=True, batch_size=8, show_progress_bar=True)

    for (chunk_id, _, _), v in zip(plan, vecs):
        update_vec(conn, chunk_id, struct.pack(f"{DIM}f", *v))

    conn.commit()

    n_chunks = conn.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0]
    n_vec = conn.execute("SELECT COUNT(*) FROM vec_knowledge").fetchone()[0]
    print(f"\n✓ knowledge_chunks: {n_chunks}, vec_knowledge: {n_vec}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
