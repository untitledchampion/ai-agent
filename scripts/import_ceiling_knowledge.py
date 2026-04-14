"""Импортирует базу знаний о натяжных потолках из PDF в БД.

Действия:
  1. Режет raw-текст PDF по логическим заголовкам → 21 чанк.
  2. Копирует картинки raw/*/img_pXX_Y.png → data/knowledge_images/<semantic>.png
  3. Создаёт таблицы knowledge_chunks + vec_knowledge.
  4. Инсертит чанки, строит BGE-M3 эмбеддинги.

Запуск:
    source .venv/bin/activate && python scripts/import_ceiling_knowledge.py
"""
from __future__ import annotations

import json
import re
import shutil
import sqlite3
import struct
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
RAW = ROOT / "scripts" / "_tmp" / "raw"
DB = ROOT / "data" / "chatapp_data_prod.db"
IMG_OUT = ROOT / "data" / "knowledge_images"
DIM = 1024
MODEL_NAME = "BAAI/bge-m3"


# ─── Определения чанков ──────────────────────────────────────────────
# start_marker / end_marker — regex или литерал, который ищется в raw text.
# Если end_marker отсутствует — берём до конца файла.
# images: [(raw_relpath, new_filename, caption)]
# products: query patterns (все должны быть в name) — финальный матч делается в импорте.
# categories: slugs of product categories to link (по префиксу)

CHUNKS: list[dict] = [
    {
        "id": "osnovy_natyazhnoy_potolok",
        "title": "Натяжной потолок: что это, преимущества/недостатки, типы полотен и фактуры",
        "topic": "osnovy",
        "doc": "1_2",
        "start": r"Натяжной потолок представляет собой",
        "end": r"СИСТЕМЫ УСТАНОВКИ НАТЯЖНОГО ПОТОЛКА",
        "images": [],
        "products": [],
        "categories": [],
    },
    {
        "id": "sistema_garpunnaya",
        "title": "Гарпунная система монтажа — основная (~90% ПВХ-потолков)",
        "topic": "sistema_montazha",
        "doc": "1_2",
        "start": r"1\. Гарпунная система",
        "end": r"2\. Штапиковая система",
        "images": [],
        "products": [],
        "categories": ["2.01.01", "2.01.02", "2.01.03"],
    },
    {
        "id": "sistema_shtapikovaya",
        "title": "Штапиковая (клиновая) система монтажа",
        "topic": "sistema_montazha",
        "doc": "1_2",
        "start": r"2\. Штапиковая система",
        "end": r"3\. Система Clipso",
        "images": [],
        "products": [],
        "categories": ["2.01.08"],
    },
    {
        "id": "sistema_clipso",
        "title": "Система Clipso (клипсовая) — для тканевых потолков",
        "topic": "sistema_montazha",
        "doc": "1_2",
        "start": r"3\. Система Clipso",
        "end": r"4\. Демпферная система",
        "images": [],
        "products": [],
        "categories": ["2.01.05"],
    },
    {
        "id": "sistema_dempfernaya",
        "title": "Демпферная система — для сложных потолочных конструкций",
        "topic": "sistema_montazha",
        "doc": "1_2",
        "start": r"4\. Демпферная система",
        "end": None,
        "images": [],
        "products": [],
        "categories": ["1.15"],
    },
    {
        "id": "profili_standartnye",
        "title": "Стандартные профили: потолочный, стеновой, универсальный",
        "topic": "profili_standartnye",
        "doc": "1_1",
        "start": r"Виды профилей для установки натяжного потолка",
        "end": r"Разделительный профиль в натяжных",
        "images": [
            ("1_1/img_p01_1.png", "standart_potolochny.png", "Стандартный потолочный профиль"),
            ("1_1/img_p01_2.png", "standart_stenovoy.png", "Стандартный стеновой профиль"),
            ("1_1/img_p02_1.png", "standart_universalny.png", "Стандартный универсальный профиль"),
        ],
        "products": [],
        "categories": ["2.01.01", "2.01.02", "2.01.03"],
    },
    {
        "id": "profili_razdelitelnye",
        "title": "Разделительные профили: стандартный, бесщелевой, теневой",
        "topic": "profili_razdelitelnye",
        "doc": "1_1",
        "start": r"Разделительный профиль в натяжных",
        "end": r"Профиль «прищепка» для тканевых потолков",
        "images": [
            ("1_1/img_p02_2.png", "razdelit_standart.png", "Разделительный профиль (стандартный)"),
            ("1_1/img_p03_1.png", "razdelit_standart_ugol_1.png", "Стандартный разделитель на прямом участке"),
            ("1_1/img_p03_2.png", "razdelit_standart_ugol_2.png", "Стандартный разделитель на криволинейном участке"),
            ("1_1/img_p04_1.png", "razdelit_besschelevoy_montazh.png", "Бесщелевой разделитель после монтажа"),
            ("1_1/img_p04_2.png", "razdelit_besschelevoy_profil.png", "Бесщелевой разделительный профиль"),
            ("1_1/img_p04_3.png", "razdelit_y_otboinik.png", "Y-образный отбойник"),
            ("1_1/img_p05_1.png", "razdelit_tenevoy.png", "Теневой разделительный профиль"),
        ],
        "products": [["разделительный"]],
        "categories": ["2.01.02"],
    },
    {
        "id": "profili_prischepka",
        "title": "Профиль «прищепка» для тканевых потолков",
        "topic": "profili_tkanevye",
        "doc": "1_1",
        "start": r"Профиль «прищепка» для тканевых потолков",
        "end": None,
        "images": [
            ("1_1/img_p06_1.png", "prischepka_montazh_skhema.png", "Прищепка: схема монтажа"),
            ("1_1/img_p06_2.png", "prischepka_interior.png", "Тканевый потолок с прищепкой (интерьер)"),
            ("1_1/img_p07_1.png", "prischepka_potolochnaya.png", "Потолочная прищепка"),
            ("1_1/img_p07_2.png", "prischepka_stenovaya.png", "Стеновая прищепка"),
            ("1_1/img_p07_3.png", "prischepka_tkan_v_rabote.png", "Прищепка с заправленным полотном"),
        ],
        "products": [["прищепка"]],
        "categories": ["2.01.05"],
    },
    {
        "id": "paryashchy_pravila",
        "title": "Парящий потолок: что это, правила выбора и замера",
        "topic": "paryashchy",
        "doc": "1_3",
        "start": r"Парящий потолок",
        "end": r"Ниже представлены одни из самых бюджетных",
        "images": [],
        "products": [],
        "categories": ["2.04", "2.05"],  # парящие/световые линии
    },
    {
        "id": "paryashchy_profili_flexy",
        "title": "Парящие профили Flexy: FLY 01 и FLY 02",
        "topic": "paryashchy",
        "doc": "1_3",
        "start": r"Стеновой парящий профиль Flexy FLY 01",
        "end": r"Стеновой парящий профиль \nАлформ Contour-Pro",
        "images": [
            ("1_3/img_p02_1.png", "flexy_fly_01.png", "FLEXY FLY 01 — парящий без рассеивателя"),
            ("1_3/img_p02_2.png", "flexy_fly_02.png", "FLEXY FLY 02 — парящий с креплением под рассеиватель"),
        ],
        "products": [["FLY 01"], ["FLY 02"]],
        "categories": [],
    },
    {
        "id": "paryashchy_profili_alform",
        "title": "Парящие профили Алформ: Contour-Pro и Contour Pro LED",
        "topic": "paryashchy",
        "doc": "1_3",
        "start": r"Стеновой парящий профиль \nАлформ Contour-Pro",
        "end": None,
        "images": [
            ("1_3/img_p03_1.png", "alform_contour_pro.png", "Алформ Contour-Pro — без рассеивателя"),
            ("1_3/img_p03_2.png", "alform_contour_pro_led.png", "Алформ Contour Pro LED — с креплением под рассеиватель"),
        ],
        "products": [["Contour-Pro"], ["Contour Pro LED"]],
        "categories": [],
    },
    {
        "id": "tenevoy_pravila",
        "title": "Теневой потолок: эстетика и критически важные требования монтажа",
        "topic": "tenevoy",
        "doc": "1_4",
        "start": r"Теневой потолок",
        "end": r"Бюджетные теневые профили",
        "images": [],
        "products": [],
        "categories": ["2.03"],
    },
    {
        "id": "tenevoy_budget",
        "title": "Бюджетные теневые профили (простой монтаж, без спецраскроя)",
        "topic": "tenevoy",
        "doc": "1_4",
        "start": r"Бюджетные теневые профили",
        "end": r"Теневые профили относящиеся к системам",
        "images": [
            ("1_4/img_p02_1.png", "uline_pro_mini.png", "U-LINE PRO mini, теневой зазор 7,4 мм"),
            ("1_4/img_p02_2.png", "alform_evro_stenovoy.png", "Алформ евро стеновой, зазор 7,4–7,6 мм"),
            ("1_4/img_p03_1.png", "flexy_klassika_140.png", "Flexy KLASSIKA 140, зазор 7,6 мм"),
        ],
        "products": [["U-LINE PRO mini"], ["KLASSIKA 140"]],
        "categories": ["2.03.04", "2.03.03"],
    },
    {
        "id": "tenevoy_srednie",
        "title": "Теневые профили средней сложности (нужен спец. шпатель)",
        "topic": "tenevoy",
        "doc": "1_4",
        "start": r"Теневые профили относящиеся к системам\s+средней сложности",
        "end": r"Данная категория профилей требует особой",
        "images": [
            ("1_4/img_p03_2.png", "flexy_euro_01.png", "Flexy EURO 01 (ранее Flexy МИНИ), зазор 5 мм"),
            ("1_4/img_p04_1.png", "flexy_euro_02.png", "Flexy EURO 02 (ранее Flexy стандарт), зазор 5 мм"),
            ("1_4/img_p04_2.png", "eurolumfer.png", "EuroLumFer, зазор 5 мм"),
        ],
        "products": [["FLEXY EURO 01"], ["FLEXY EURO 02"], ["EuroLumFer"]],
        "categories": ["2.03.01", "2.03.06"],
    },
    {
        "id": "tenevoy_slozhnye",
        "title": "Теневые профили высокой сложности: угловая заправка (EUROKRAAB и аналоги)",
        "topic": "tenevoy",
        "doc": "1_4",
        "start": r"Данная категория профилей требует особой",
        "end": None,
        "images": [
            ("1_4/img_p04_3.png", "eurokraab.png", "EUROKRAAB — первая угловая заправка, зазор 7 мм"),
            ("1_4/img_p05_1.png", "flexy_euro_05.png", "Flexy EURO 05 — аналог EUROKRAAB, зазор 7,7 мм"),
        ],
        "products": [["EUROKRAAB", "стеновой"], ["FLEXY EURO 05"], ["ALTEZA DELTA", "стеновой"]],
        "categories": ["2.03.02"],
    },
    {
        "id": "pravila_shva",
        "title": "Правила сварного шва на полотне (10 см от угла, противопожарное полотно)",
        "topic": "pravila",
        "doc": "1_5",
        "start": r"Правила шва",
        "end": r"Установка натяжного потолка в помещениях с керамогранитной",
        "images": [],
        "products": [],
        "categories": [],
        "escalate": "шов ближе 10 см от угла; паяние шва на противопожарном полотне",
    },
    {
        "id": "pravila_keramogranit",
        "title": "Монтаж натяжного потолка на керамогранитной плитке",
        "topic": "pravila",
        "doc": "1_5",
        "start": r"Установка натяжного потолка в помещениях с керамогранитной",
        "end": None,
        "images": [],
        "products": [["Титан"], ["Lotus"], ["HILBERG"]],
        "categories": ["4.07.03"],  # алмазные коронки/воск
    },
    {
        "id": "gardiny_osnovy",
        "title": "Гардины: общие сведения, монтаж, Г-образные vs П-образные, обход окна",
        "topic": "gardiny",
        "doc": "1_7",
        "start": r"Мы называем Гардиной алюминиевый",
        "end": r"Виды Г-образных гардин",
        "images": [
            ("1_7/img_p01_1.png", "gardina_s_shtorami_interior.png", "Гардина со шторами (интерьер)"),
            ("1_7/img_p02_1.png", "gardina_kronshteyny_montazh.png", "Крепление гардины на кронштейны"),
            ("1_7/img_p03_1.png", "gardina_skhema_g_obraznaya.png", "Схема Г-образной гардины"),
            ("1_7/img_p03_2.png", "gardina_g_obraznaya_foto.png", "Г-образная гардина в интерьере"),
            ("1_7/img_p04_1.png", "gardina_zapil_45.png", "Запил под 45° → прямой угол 90°"),
            ("1_7/img_p04_2.png", "gardina_gotovyi_ugol.png", "Готовый угол для гардины"),
        ],
        "products": [],
        "categories": ["1.11.02"],
    },
    {
        "id": "gardiny_g_obraznye",
        "title": "Г-образные гардины: ПК-5, ПК-12, ПК-15 и их аналоги",
        "topic": "gardiny",
        "doc": "1_7",
        "start": r"Виды Г-образных гардин",
        "end": r"П-образные гардины устанавливаются",
        "images": [
            ("1_7/img_p05_1.png", "pk5_gardina.png", "ПК-5 — 3-рядная без соединительного гвоздика"),
            ("1_7/img_p05_2.png", "pk12_gardina.png", "ПК-12 — 3-рядная"),
            ("1_7/img_p05_3.png", "pk15_gardina.png", "ПК-15 — 2-рядная"),
            ("1_7/img_p06_1.png", "flexy_gardina3_03.png", "FLEXY GARDINA3 03 — боковая заправка"),
            ("1_7/img_p06_2.png", "flexy_gardina3_04.png", "FLEXY GARDINA3 04 — нижняя заправка"),
            ("1_7/img_p07_1.png", "flexy_gardina2_01_02.png", "FLEXY GARDINA2 01 / 02"),
            ("1_7/img_p08_1.png", "borzz_karniz_45_slott_parsek.png", "BORZZ KARNIZ 45 / SLOTT PARSEK"),
        ],
        "products": [
            ["GARDINA3 03"], ["GARDINA3 04"],
            ["GARDINA2 01"], ["GARDINA2 02"],
            ["BORZZ KARNIZ 45", "Гардина"],
            ["SLOTT-PARSEK", "карниз"],
        ],
        "categories": ["2.07.02", "2.08.02", "2.07.05"],
    },
    {
        "id": "gardiny_p_obraznye",
        "title": "П-образные гардины: ПК-14 и аналоги (вплоть до LumFer SK)",
        "topic": "gardiny",
        "doc": "1_7",
        "start": r"П-образные гардины устанавливаются",
        "end": r"ДЛЯ ПОСТРОЕНИЯ В EASY CEILING",
        "images": [
            ("1_7/img_p09_1.png", "pk14_skhema_otstupy.png", "П-образная: схема с отступами"),
            ("1_7/img_p09_2.png", "gardina_vrezka_stena_stena.png", "Врезка гардины от стены до стены"),
            ("1_7/img_p10_1.png", "torcevye_zaglushki_skhema.png", "Торцевые заглушки"),
            ("1_7/img_p11_1.png", "pk14_otstupy_interior.png", "ПК-14 с отступами в интерьере"),
            ("1_7/img_p11_2.png", "pk14_dvuhryadnaya.png", "ПК-14 — 2-рядная"),
            ("1_7/img_p12_1.png", "flexy_gardina2_05_2_0.png", "FLEXY GARDINA2 05 2.0"),
            ("1_7/img_p13_1.png", "borzz_karniz_p45.png", "BORZZ KARNIZ P45"),
            ("1_7/img_p14_1.png", "gardina_p50_p60_p70.png", "Gardina P 50 / P 60 / P 70"),
            ("1_7/img_p14_2.png", "lumfer_sk_novus.png", "LumFer SK Novus — БЕЗ ленты"),
            ("1_7/img_p15_1.png", "lumfer_sk_magnum.png", "LumFer SK Magnum — С лентой"),
        ],
        "products": [
            ["ПК-14"],
            ["GARDINA2 05", "Гардина"],
            ["BORZZ KARNIZ P45", "Гардина"],
            ["Lumfer", "Novus"], ["Lumfer", "Magnum"],
        ],
        "categories": ["2.07.02", "2.07.04"],
    },
    {
        "id": "polosky_raskroy_easy_ceiling",
        "title": "Закарнизные полоски: усадка и раскрой для Easy Ceiling",
        "topic": "gardiny",
        "doc": "1_7",
        "start": r"ДЛЯ ПОСТРОЕНИЯ В EASY CEILING",
        "end": None,
        "images": [],
        "products": [],
        "categories": [],
        "escalate": "полоска длиннее 631 см без согласования; клиент не хочет шов — к руководителю",
    },
]


def load_text(doc: str) -> str:
    return (RAW / doc / "text.md").read_text(encoding="utf-8")


def slice_text(raw: str, start_re: str, end_re: str | None) -> str:
    """Вырезает кусок от start_re до end_re (не включительно). Чистит [IMG: ...]."""
    start_match = re.search(start_re, raw)
    if not start_match:
        raise RuntimeError(f"start_re not found: {start_re!r}")
    start = start_match.start()
    if end_re:
        end_match = re.search(end_re, raw[start:])
        if not end_match:
            raise RuntimeError(f"end_re not found: {end_re!r} (after start)")
        end = start + end_match.start()
    else:
        end = len(raw)
    chunk = raw[start:end]
    # Убираем маркеры "## Page N" и "[IMG: ...]"
    chunk = re.sub(r"^## Page \d+\s*$", "", chunk, flags=re.M)
    chunk = re.sub(r"\[IMG[^\]]*\]", "", chunk)
    chunk = re.sub(r"^---\s*$", "", chunk, flags=re.M)
    # Схлопываем множественные пустые строки
    chunk = re.sub(r"\n{3,}", "\n\n", chunk)
    return chunk.strip()


def find_products(patterns: list[str], conn) -> list[int]:
    """Возвращает id products, имя которых содержит ВСЕ patterns (регистронезависимо)."""
    if not patterns:
        return []
    sql = "SELECT id FROM products WHERE " + " AND ".join(["LOWER(name) LIKE LOWER(?)"] * len(patterns))
    rows = conn.execute(sql, [f"%{p}%" for p in patterns]).fetchall()
    return [r[0] for r in rows]


def products_by_category_prefix(prefix: str, conn) -> list[int]:
    rows = conn.execute(
        "SELECT id FROM products WHERE category LIKE ?",
        (f"{prefix}%",),
    ).fetchall()
    return [r[0] for r in rows]


def resolve_products(ch: dict, conn) -> list[int]:
    ids: set[int] = set()
    for pat_list in ch.get("products", []):
        ids.update(find_products(pat_list, conn))
    for cat_prefix in ch.get("categories", []):
        ids.update(products_by_category_prefix(cat_prefix, conn))
    return sorted(ids)


def copy_images(ch: dict) -> list[dict]:
    """Копирует картинки в data/knowledge_images/. Возвращает метаданные."""
    IMG_OUT.mkdir(parents=True, exist_ok=True)
    out = []
    for src_rel, new_name, caption in ch.get("images", []):
        src = RAW / src_rel
        if not src.exists():
            print(f"  ! missing image: {src}")
            continue
        dst = IMG_OUT / new_name
        shutil.copyfile(src, dst)
        out.append({"path": f"/static/knowledge_images/{new_name}", "caption": caption})
    return out


def build_embedding_text(title: str, content: str, product_names: list[str]) -> str:
    """Компонуем текст для эмбеддинга: заголовок + первые 600 символов + имена товаров."""
    head = title
    body = content[:600]
    names = " | ".join(product_names[:10]) if product_names else ""
    return f"{head}\n\n{body}\n\n{names}".strip()


def main() -> int:
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    # Загружаем sqlite-vec
    import sqlite_vec  # type: ignore

    conn.enable_load_extension(True)
    sqlite_vec.load(conn)
    conn.enable_load_extension(False)

    # ── DDL: knowledge_chunks ──
    conn.execute("DROP TABLE IF EXISTS knowledge_chunks")
    conn.execute("""
        CREATE TABLE knowledge_chunks (
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
    conn.execute("CREATE INDEX ix_kc_topic ON knowledge_chunks(topic)")

    conn.execute("DROP TABLE IF EXISTS vec_knowledge")
    conn.execute(
        f"CREATE VIRTUAL TABLE vec_knowledge USING vec0("
        f"id INTEGER PRIMARY KEY, embedding float[{DIM}])"
    )

    # ── Читаем raw-тексты ──
    raw_cache: dict[str, str] = {}
    for ch in CHUNKS:
        raw_cache.setdefault(ch["doc"], load_text(ch["doc"]))

    # ── Режем и резолвим ──
    prepared: list[dict] = []
    for ch in CHUNKS:
        raw = raw_cache[ch["doc"]]
        try:
            content = slice_text(raw, ch["start"], ch["end"])
        except RuntimeError as e:
            print(f"  !! {ch['id']}: {e}")
            content = "(TEXT EXTRACTION FAILED)"
        imgs = copy_images(ch)
        pids = resolve_products(ch, conn)
        prepared.append({
            "id": ch["id"],
            "title": ch["title"],
            "topic": ch["topic"],
            "content": content,
            "images": imgs,
            "product_ids": pids,
            "escalate": ch.get("escalate"),
            "doc": ch["doc"],
        })
        print(f"  ✓ {ch['id']:40s} text={len(content):5d}  imgs={len(imgs):2d}  products={len(pids):3d}")

    # ── Инсертим чанки ──
    chunk_rows: list[tuple[int, str, str]] = []  # (pk, title, content_preview) для эмбеддинга
    for p in prepared:
        # Тянем имена товаров для эмбеддинг-текста
        names: list[str] = []
        if p["product_ids"]:
            placeholders = ",".join("?" * len(p["product_ids"]))
            rs = conn.execute(
                f"SELECT name FROM products WHERE id IN ({placeholders}) LIMIT 15",
                p["product_ids"],
            ).fetchall()
            names = [r[0] for r in rs]
        cur = conn.execute(
            """INSERT INTO knowledge_chunks
                (slug, title, topic, content, images_json, product_ids_json, escalate, source_doc)
                VALUES (?,?,?,?,?,?,?,?)""",
            (
                p["id"], p["title"], p["topic"], p["content"],
                json.dumps(p["images"], ensure_ascii=False),
                json.dumps(p["product_ids"]),
                p["escalate"],
                p["doc"],
            ),
        )
        pk = cur.lastrowid
        emb_text = build_embedding_text(p["title"], p["content"], names)
        chunk_rows.append((pk, p["id"], emb_text))

    conn.commit()

    # ── Строим эмбеддинги ──
    print("\nLoading BGE-M3...")
    import torch  # type: ignore
    from sentence_transformers import SentenceTransformer  # type: ignore

    device = "mps" if torch.backends.mps.is_available() else "cpu"
    model = SentenceTransformer(MODEL_NAME, device=device)

    texts = [t for _, _, t in chunk_rows]
    print(f"encoding {len(texts)} chunks on {device}...")
    vecs = model.encode(texts, normalize_embeddings=True, batch_size=8, show_progress_bar=True)

    conn.executemany(
        "INSERT INTO vec_knowledge(id, embedding) VALUES (?, ?)",
        [(pk, struct.pack(f"{DIM}f", *v)) for (pk, _, _), v in zip(chunk_rows, vecs)],
    )
    conn.commit()

    # ── Проверка ──
    n_chunks = conn.execute("SELECT COUNT(*) FROM knowledge_chunks").fetchone()[0]
    n_vec = conn.execute("SELECT COUNT(*) FROM vec_knowledge").fetchone()[0]
    print(f"\n✓ knowledge_chunks: {n_chunks}, vec_knowledge: {n_vec}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
