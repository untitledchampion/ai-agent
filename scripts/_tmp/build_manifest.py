"""Строит manifest.md для ревью структуры базы знаний.

Один чанк = один крупный раздел PDF (по договорённости).
В manifest: заголовок, источник, привязанные картинки, связанные products, превью.
"""
from __future__ import annotations

import json
import re
import sqlite3
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
RAW = Path(__file__).resolve().parent / "raw"
DB = ROOT / "data" / "chatapp_data_prod.db"
OUT = Path(__file__).resolve().parent / "manifest.md"

db = sqlite3.connect(DB)
db.row_factory = sqlite3.Row


def find_products(patterns: list[str]) -> list[dict]:
    """Ищет products, имя которых содержит ВСЕ паттерны (регистронезависимо)."""
    if not patterns:
        return []
    sql = "SELECT id, name FROM products WHERE " + " AND ".join(
        ["LOWER(name) LIKE LOWER(?)"] * len(patterns)
    )
    rows = db.execute(sql, [f"%{p}%" for p in patterns]).fetchall()
    return [{"id": r["id"], "name": r["name"]} for r in rows]


def pick(patterns: list[str], limit: int = 6) -> list[dict]:
    return find_products(patterns)[:limit]


# ─── Структура чанков ────────────────────────────────────────────────
# Каждый чанк — крупный раздел. Картинки указаны с оригинальными именами
# из scripts/_tmp/raw/<doc>/img_pXX_Y.png + предлагаемое осмысленное имя.

CHUNKS = [
    # ── 1.2 Системы установки ──────────────────────────────────────
    {
        "id": "osnovy_natyazhnoy_potolok",
        "title": "Натяжной потолок: что это, плюсы/минусы, типы полотен",
        "topic": "osnovy",
        "source": "1_2, pages 1-2",
        "pages": [(1, 1), (1, 2)],
        "images": [],
        "products": [],  # общая теория
    },
    {
        "id": "sistema_garpunnaya",
        "title": "Гарпунная система монтажа (основная, ~90% ПВХ)",
        "topic": "sistema_montazha",
        "source": "1_2, pages 2-3",
        "pages": [(2, 2), (2, 3)],
        "images": [],
        "products": [],
    },
    {
        "id": "sistema_shtapikovaya",
        "title": "Штапиковая (клиновая) система монтажа",
        "topic": "sistema_montazha",
        "source": "1_2, pages 3-4",
        "pages": [(2, 3), (2, 4)],
        "images": [],
        "products": pick(["штапик"], 3),
    },
    {
        "id": "sistema_clipso",
        "title": "Система Clipso (клипсовая) — для тканевых потолков",
        "topic": "sistema_montazha",
        "source": "1_2, pages 4-5",
        "pages": [(2, 4), (2, 5)],
        "images": [],
        "products": pick(["прищепка"], 3),
    },
    {
        "id": "sistema_dempfernaya",
        "title": "Демпферная система — для сложных конструкций",
        "topic": "sistema_montazha",
        "source": "1_2, pages 5-6",
        "pages": [(2, 5), (2, 6)],
        "images": [],
        "products": pick(["демпфер"], 3),
    },
    # ── 1.1 Виды профилей ──────────────────────────────────────────
    {
        "id": "profili_standartnye",
        "title": "Стандартные профили: потолочный, стеновой, универсальный",
        "topic": "profili_standartnye",
        "source": "1_1, pages 1-2",
        "pages": [(1, 1), (1, 2)],
        "images": [
            ("1_1/img_p01_1.png", "standart_potolochny.png", "Стандартный потолочный профиль"),
            ("1_1/img_p01_2.png", "standart_stenovoy.png", "Стандартный стеновой профиль"),
            ("1_1/img_p02_1.png", "standart_universalny.png", "Стандартный универсальный профиль"),
        ],
        "products": pick(["гарпунный", "алюминиевый", "потолочный"], 3)
                    + pick(["гарпунный", "алюминиевый", "стеновой"], 3),
    },
    {
        "id": "profili_razdelitelnye",
        "title": "Разделительные профили: стандартный, бесщелевой, теневой",
        "topic": "profili_razdelitelnye",
        "source": "1_1, pages 2-5",
        "pages": [(1, 2), (1, 3), (1, 4), (1, 5)],
        "images": [
            ("1_1/img_p02_2.png", "razdelit_standart.png", "Разделительный профиль (стандартный)"),
            ("1_1/img_p03_1.png", "razdelit_standart_ugol_1.png", "Стандартный разделитель на прямом участке"),
            ("1_1/img_p03_2.png", "razdelit_standart_ugol_2.png", "Стандартный разделитель на криволинейном участке"),
            ("1_1/img_p04_1.png", "razdelit_besschelevoy_montazh.png", "Бесщелевой разделитель: внешний вид после монтажа"),
            ("1_1/img_p04_2.png", "razdelit_besschelevoy_profil.png", "Бесщелевой разделительный профиль"),
            ("1_1/img_p04_3.png", "razdelit_y_otboinik.png", "Y-образный отбойник"),
            ("1_1/img_p05_1.png", "razdelit_tenevoy.png", "Теневой разделительный профиль (чёрный внутри)"),
        ],
        "products": pick(["разделительный"], 10),
    },
    {
        "id": "profili_prischepka",
        "title": "Профиль «прищепка» для тканевых потолков",
        "topic": "profili_tkanevye",
        "source": "1_1, pages 6-7",
        "pages": [(1, 6), (1, 7)],
        "images": [
            ("1_1/img_p06_1.png", "prischepka_montazh_skhema.png", "Прищепка: схема монтажа"),
            ("1_1/img_p06_2.png", "prischepka_interior.png", "Тканевый потолок с прищепкой (интерьер)"),
            ("1_1/img_p07_1.png", "prischepka_potolochnaya.png", "Потолочная прищепка"),
            ("1_1/img_p07_2.png", "prischepka_stenovaya.png", "Стеновая прищепка"),
            ("1_1/img_p07_3.png", "prischepka_tkan_v_rabote.png", "Прищепка с заправленным тканевым полотном"),
        ],
        "products": pick(["прищепка"], 6),
    },
    # ── 1.3 Парящий потолок ────────────────────────────────────────
    {
        "id": "paryashchy_pravila",
        "title": "Парящий потолок: что это, правила выбора и замера",
        "topic": "paryashchy",
        "source": "1_3, pages 1-2",
        "pages": [(3, 1), (3, 2)],
        "images": [],
        "products": [],
    },
    {
        "id": "paryashchy_profili_flexy",
        "title": "Парящие профили Flexy: FLY 01, FLY 02",
        "topic": "paryashchy",
        "source": "1_3, page 2",
        "pages": [(3, 2)],
        "images": [
            ("1_3/img_p02_1.png", "flexy_fly_01.png", "FLEXY FLY 01 — парящий без рассеивателя"),
            ("1_3/img_p02_2.png", "flexy_fly_02.png", "FLEXY FLY 02 — парящий с креплением под рассеиватель"),
        ],
        "products": pick(["FLY 01"], 5) + pick(["FLY 02"], 5),
    },
    {
        "id": "paryashchy_profili_alform",
        "title": "Парящие профили Алформ: Contour-Pro, Contour Pro LED",
        "topic": "paryashchy",
        "source": "1_3, page 3",
        "pages": [(3, 3)],
        "images": [
            ("1_3/img_p03_1.png", "alform_contour_pro.png", "Алформ Contour-Pro — без рассеивателя"),
            ("1_3/img_p03_2.png", "alform_contour_pro_led.png", "Алформ Contour Pro LED — с креплением под рассеиватель"),
        ],
        "products": pick(["Contour-Pro"], 5) + pick(["Contour Pro LED"], 5),
    },
    # ── 1.4 Теневой потолок ────────────────────────────────────────
    {
        "id": "tenevoy_pravila",
        "title": "Теневой потолок: что это и критически важные требования",
        "topic": "tenevoy",
        "source": "1_4, page 1",
        "pages": [(4, 1)],
        "images": [],
        "products": [],
    },
    {
        "id": "tenevoy_budget",
        "title": "Бюджетные теневые профили (без спецраскроя)",
        "topic": "tenevoy",
        "source": "1_4, pages 2-3",
        "pages": [(4, 2), (4, 3)],
        "images": [
            ("1_4/img_p02_1.png", "uline_pro_mini.png", "U-LINE PRO mini, теневой зазор 7,4 мм"),
            ("1_4/img_p02_2.png", "alform_evro_stenovoy.png", "Алформ евро стеновой, зазор 7,4-7,6 мм"),
            ("1_4/img_p03_1.png", "flexy_klassika_140.png", "Flexy KLASSIKA 140, зазор 7,6 мм"),
        ],
        "products": pick(["U-LINE PRO mini"], 3) + pick(["KLASSIKA 140"], 3),
    },
    {
        "id": "tenevoy_srednie",
        "title": "Теневые профили средней сложности (спец. шпатель)",
        "topic": "tenevoy",
        "source": "1_4, pages 3-4",
        "pages": [(4, 3), (4, 4)],
        "images": [
            ("1_4/img_p03_2.png", "flexy_euro_01.png", "Flexy EURO 01 (ранее Flexy МИНИ), зазор 5 мм"),
            ("1_4/img_p04_1.png", "flexy_euro_02.png", "Flexy EURO 02 (ранее Flexy стандарт), зазор 5 мм"),
            ("1_4/img_p04_2.png", "eurolumfer.png", "EuroLumFer, зазор 5 мм"),
        ],
        "products": pick(["FLEXY EURO 01"], 3)
                    + pick(["FLEXY EURO 02"], 3)
                    + pick(["EuroLumFer"], 3),
    },
    {
        "id": "tenevoy_slozhnye",
        "title": "Теневые профили высокой сложности (угловая заправка)",
        "topic": "tenevoy",
        "source": "1_4, pages 4-5",
        "pages": [(4, 4), (4, 5)],
        "images": [
            ("1_4/img_p04_3.png", "eurokraab.png", "EUROKRAAB — первая угловая заправка, зазор 7 мм"),
            ("1_4/img_p05_1.png", "flexy_euro_05.png", "Flexy EURO 05 — аналог EUROKRAAB, зазор 7,7 мм"),
            # Alteza Delta — возможно отдельная картинка не извлеклась; проверим
        ],
        "products": pick(["EUROKRAAB", "стеновой"], 3)
                    + pick(["FLEXY EURO 05"], 3)
                    + pick(["ALTEZA DELTA", "стеновой"], 3),
    },
    # ── 1.5 Правила ────────────────────────────────────────────────
    {
        "id": "pravila_shva",
        "title": "Правила сварного шва на полотне",
        "topic": "pravila",
        "source": "1_5, page 1",
        "pages": [(5, 1)],
        "images": [],
        "products": [],
        "escalate": "шов ближе 10 см от угла; паяние шва на противопожарном полотне (КМ-1/2/3, тектум к1/евро, бауф фаер пруф)",
    },
    {
        "id": "pravila_keramogranit",
        "title": "Установка натяжного потолка на керамогранитной плитке",
        "topic": "pravila",
        "source": "1_5, page 1",
        "pages": [(5, 1)],
        "images": [],
        "products": pick(["Титан"], 3)
                    + pick(["Lotus"], 3)
                    + pick(["HILBERG"], 3),
    },
    # ── 1.7 Гардины ────────────────────────────────────────────────
    {
        "id": "gardiny_osnovy",
        "title": "Гардины: что это, монтаж, Г-образные vs П-образные, обход окна",
        "topic": "gardiny",
        "source": "1_7, pages 1-4",
        "pages": [(7, 1), (7, 2), (7, 3), (7, 4)],
        "images": [
            ("1_7/img_p01_1.png", "gardina_s_shtorami_interior.png", "Гардина со шторами (интерьер)"),
            ("1_7/img_p02_1.png", "gardina_kronshteyny_montazh.png", "Крепление гардины на кронштейны к черновому потолку"),
            ("1_7/img_p03_1.png", "gardina_skhema_g_obraznaya.png", "Схема Г-образной гардины (разные уровни)"),
            ("1_7/img_p03_2.png", "gardina_g_obraznaya_foto.png", "Г-образная гардина в интерьере"),
            ("1_7/img_p04_1.png", "gardina_zapil_45.png", "Запил под 45° → прямой угол 90°"),
            ("1_7/img_p04_2.png", "gardina_gotovyi_ugol.png", "Готовый угол для гардины"),
        ],
        "products": [],
    },
    {
        "id": "gardiny_g_obraznye",
        "title": "Г-образные гардины: ПК-5/12/15 и аналоги",
        "topic": "gardiny",
        "source": "1_7, pages 5-8",
        "pages": [(7, 5), (7, 6), (7, 7), (7, 8)],
        "images": [
            ("1_7/img_p05_1.png", "pk5_garidna.png", "ПК-5 — 3-рядная без соединительного гвоздика"),
            ("1_7/img_p05_2.png", "pk12_garidna.png", "ПК-12 — 3-рядная"),
            ("1_7/img_p05_3.png", "pk15_garidna.png", "ПК-15 — 2-рядная"),
            ("1_7/img_p06_1.png", "flexy_gardina3_03.png", "FLEXY GARDINA3 03 — боковая заправка, чёрный"),
            ("1_7/img_p06_2.png", "flexy_gardina3_04.png", "FLEXY GARDINA3 04 — нижняя заправка, белый"),
            ("1_7/img_p07_1.png", "flexy_gardina2_01_02.png", "FLEXY GARDINA2 01 (белый, нижн.) / 02 (чёрный, боковая)"),
            ("1_7/img_p08_1.png", "borzz_karniz_45_slott_parsek.png", "BORZZ KARNIZ 45 / SLOTT PARSEK"),
        ],
        "products": pick(["GARDINA3 03"], 4)
                    + pick(["GARDINA3 04"], 4)
                    + pick(["GARDINA2 01"], 4)
                    + pick(["GARDINA2 02"], 4)
                    + pick(["BORZZ KARNIZ 45", "Гардина"], 4)
                    + pick(["SLOTT-PARSEK", "карниз"], 4),
    },
    {
        "id": "gardiny_p_obraznye",
        "title": "П-образные гардины: ПК-14 и аналоги (до LumFer SK)",
        "topic": "gardiny",
        "source": "1_7, pages 9-15",
        "pages": [(7, 9), (7, 10), (7, 11), (7, 12), (7, 13), (7, 14), (7, 15)],
        "images": [
            ("1_7/img_p09_1.png", "pk14_skhema_otstupy.png", "П-образная гардина: схема с отступами от стен"),
            ("1_7/img_p09_2.png", "garid_vrezka_stena_stena.png", "Врезка гардины от стены до стены"),
            ("1_7/img_p10_1.png", "torcevye_zaglushki_skhema.png", "Торцевые заглушки: внутренняя и внешняя"),
            ("1_7/img_p11_1.png", "pk14_otstupy_interior.png", "ПК-14 с отступами в интерьере"),
            ("1_7/img_p11_2.png", "pk14_dvuhryadnaya.png", "ПК-14 — 2-рядная с соединительным гвоздиком"),
            ("1_7/img_p12_1.png", "flexy_gardina2_05_2_0.png", "FLEXY GARDINA2 05 2.0 — аналог ПК-14"),
            ("1_7/img_p13_1.png", "borzz_karniz_p45.png", "BORZZ KARNIZ P45 + сопутствующие (вставка, рассеиватель, гарпун)"),
            ("1_7/img_p14_1.png", "gardina_p50_p60_p70.png", "Gardina P 50 / P 60 / P 70"),
            ("1_7/img_p14_2.png", "lumfer_sk_novus.png", "LumFer SK Novus — БЕЗ места под ленту"),
            ("1_7/img_p15_1.png", "lumfer_sk_magnum.png", "LumFer SK Magnum — С местом под ленту"),
        ],
        "products": pick(["ПК-14"], 3)
                    + pick(["GARDINA2 05", "Гардина"], 4)
                    + pick(["BORZZ KARNIZ P45", "Гардина"], 4)
                    + pick(["Lumfer", "Novus"], 3)
                    + pick(["Lumfer", "Magnum"], 3),
    },
    {
        "id": "polosky_raskroy_easy_ceiling",
        "title": "Закарнизные полоски: усадка и раскрой для Easy Ceiling",
        "topic": "gardiny",
        "source": "1_7, pages 15-16",
        "pages": [(7, 15), (7, 16)],
        "images": [],
        "products": [],
        "escalate": "полоска длиннее 631 см без согласования; клиент не хочет шов — к руководителю",
    },
]


def read_pdf_text(doc_slug: str) -> str:
    p = RAW / doc_slug / "text.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def extract_preview(doc_slug: str, pages: list[tuple[int, int]], max_chars: int = 500) -> str:
    """Вытаскивает текст конкретных страниц (doc_num, page_num)."""
    text = read_pdf_text(doc_slug)
    if not text:
        return "(no text)"
    # Разбиваем по "## Page N"
    parts = re.split(r"^## Page (\d+)$", text, flags=re.M)
    # parts = [prefix, "1", page1_text, "2", page2_text, ...]
    pages_map: dict[int, str] = {}
    for i in range(1, len(parts), 2):
        try:
            pages_map[int(parts[i])] = parts[i + 1].strip()
        except Exception:
            pass
    target_pages = [pg for _, pg in pages]
    chunks_text = "\n\n".join(pages_map.get(p, "").strip() for p in target_pages).strip()
    # Убираем служебные маркеры [IMG: …]
    chunks_text = re.sub(r"\[IMG[^\]]*\]", "", chunks_text)
    chunks_text = re.sub(r"\n{3,}", "\n\n", chunks_text).strip()
    if len(chunks_text) > max_chars:
        return chunks_text[:max_chars].rstrip() + "  …(обрезано)"
    return chunks_text


# ─── Build manifest ───────────────────────────────────────────────
lines = ["# Manifest базы знаний (натяжные потолки) — ревью\n"]
lines.append(f"Всего чанков: **{len(CHUNKS)}**\n")
lines.append("Легенда: один чанк = крупный раздел PDF. В БД положим полный текст как в PDF (минимальная чистка).\n\n---\n")

for idx, ch in enumerate(CHUNKS, 1):
    # Doc slug из source
    doc_slug = ch["source"].split(",")[0].strip()  # "1_1"
    lines.append(f"\n## [{idx}] `{ch['id']}` — {ch['title']}\n")
    lines.append(f"- **Topic:** `{ch['topic']}`")
    lines.append(f"- **Source:** {ch['source']}")
    if ch.get("escalate"):
        lines.append(f"- **Эскалация:** {ch['escalate']}")

    # Images
    if ch["images"]:
        lines.append(f"- **Картинок:** {len(ch['images'])}")
        lines.append("  | # | исходник | предлагаемое имя | описание |")
        lines.append("  |---|---|---|---|")
        for i, (src, new, desc) in enumerate(ch["images"], 1):
            lines.append(f"  | {i} | `{src}` | `{new}` | {desc} |")
    else:
        lines.append("- **Картинок:** нет")

    # Products
    uniq = {}
    for p in ch["products"]:
        uniq[p["id"]] = p
    if uniq:
        lines.append(f"- **Связанные товары ({len(uniq)}):**")
        for p in uniq.values():
            lines.append(f"  - [{p['id']}] {p['name']}")
    else:
        lines.append("- **Связанные товары:** — (общий теоретический раздел)")

    # Preview
    preview = extract_preview(doc_slug, ch["pages"], max_chars=400)
    lines.append("- **Превью текста:**")
    lines.append("  ```")
    for ln in preview.splitlines()[:12]:
        lines.append(f"  {ln}")
    lines.append("  ```")

OUT.write_text("\n".join(lines), encoding="utf-8")
print(f"✓ Написал {OUT} ({len(CHUNKS)} чанков, {OUT.stat().st_size} bytes)")
