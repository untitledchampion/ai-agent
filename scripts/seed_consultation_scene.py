"""Создаёт/обновляет сценарий `product_consultation` в agent.db.

Сценарий отвечает на технические вопросы клиентов о натяжных потолках:
профили, системы монтажа, теневые/парящие, гардины, правила монтажа.

Использует tool `search_knowledge` (+ опционально `search_products` для
цен упомянутых моделей).
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "data" / "agent.db"

SCENE_SLUG = "product_consultation"

TRIGGER = {
    "description": (
        "Клиент задаёт ТЕХНИЧЕСКИЙ / КОНСУЛЬТАЦИОННЫЙ вопрос о натяжных потолках: "
        "что такое теневой/парящий потолок, чем отличаются системы монтажа (гарпунная, "
        "штапиковая, Clipso, демпферная), какой профиль выбрать для конкретной задачи, "
        "как правильно монтировать (шов, керамогранит), виды гардин (ПК-5/12/14/15, "
        "FLEXY GARDINA, BORZZ KARNIZ, LumFer SK), разделительные профили, прищепки, "
        "правила усадки и раскроя полосок. Важно: это НЕ оформление заказа и НЕ проверка "
        "остатков — тут клиент хочет ПОНЯТЬ, а не купить."
    ),
    "examples": [
        "Чем отличается теневой от парящего?",
        "Какой профиль для теневого потолка с угловой заправкой?",
        "Что такое EUROKRAAB?",
        "Какой профиль на керамогранитную плитку?",
        "Можно ли делать шов рядом с углом?",
        "Расскажите про FLEXY FLY 02",
        "Гардина ПК-14 и ПК-15 — в чём разница?",
        "Какая система монтажа лучше для ванной?",
        "Покажите парящие профили",
        "Что такое прищепка?",
        "Какая усадка у закарнизной полоски шириной 18 см?",
    ],
}

FIELDS = [
    {
        "name": "topic_query",
        "required": True,
        "prompt": "Сформулируй суть вопроса клиента 1-2 фразами (это будет запрос к базе знаний)",
    },
]

TOOLS = [
    {
        "tool": "search_knowledge",
        "when": "topic_query заполнено",
        "args": {"query": "$topic_query", "k": 3},
    },
]

RESPONSE_TEMPLATE = (
    "Отвечай на технический вопрос клиента ТОЛЬКО на основании данных из tool "
    "`search_knowledge` (раздел 'РЕЗУЛЬТАТЫ ИНСТРУМЕНТОВ' → chunks). "
    "Правила:\n"
    "1. Пиши коротко, как живой менеджер в чате. Не копируй текст PDF дословно — "
    "пересказывай своими словами, сохраняя все цифры, названия моделей и факты.\n"
    "2. Если chunk содержит картинки (поле images), в конце ответа отдельной строкой "
    "напиши: `IMAGES: путь1.png, путь2.png` — только те, которые прямо иллюстрируют "
    "ответ на вопрос клиента. НЕ более 3 картинок. Картинки берутся из image.path "
    "внутри chunks.\n"
    "3. Если клиент спрашивает про конкретную модель и она есть в chunks[].products — "
    "упомяни её точное название (например 'FLEXY FLY 02') и коротко — основные параметры.\n"
    "4. Если в chunks есть поле `escalate` и вопрос клиента подпадает под это условие — "
    "ОБЯЗАТЕЛЬНО добавь в ответ строку '##ESCALATE: <причина>'. Не пытайся сам решать такие "
    "вопросы — передавай руководителю.\n"
    "5. Не выдумывай модели, цифры или правила, которых нет в chunks. Если в базе знаний "
    "нет прямого ответа — скажи честно: 'Уточню у руководителя' и эскалируй."
)

ESCALATE_WHEN = [
    "Клиент просит сделать шов ближе 10 см от угла",
    "Клиент хочет паять шов на противопожарном полотне (КМ-1/2/3, тектум к1/евро, бауф фаер пруф)",
    "Клиент хочет закарнизную полоску длиннее 631 см без шва",
    "Клиент просит нестандартную усадку полотна",
    "Вопрос клиента не покрывается базой знаний (в chunks нет подходящего раздела)",
]


def main() -> int:
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row

    existing = conn.execute(
        "SELECT id FROM scenes WHERE slug = ?", (SCENE_SLUG,)
    ).fetchone()

    trigger_j = json.dumps(TRIGGER, ensure_ascii=False)
    fields_j = json.dumps(FIELDS, ensure_ascii=False)
    tools_j = json.dumps(TOOLS, ensure_ascii=False)
    escalate_j = json.dumps(ESCALATE_WHEN, ensure_ascii=False)
    knowledge_j = json.dumps([], ensure_ascii=False)

    if existing:
        conn.execute(
            """UPDATE scenes SET
                name=?, active=1, sort_order=?, auto_reply=1,
                trigger_json=?, fields_json=?, tools_json=?,
                response_template=?, escalate_when_json=?,
                knowledge_json=?, updated_at=datetime('now')
               WHERE slug=?""",
            (
                "Консультация по продукту (натяжные потолки)",
                50,
                trigger_j, fields_j, tools_j,
                RESPONSE_TEMPLATE, escalate_j, knowledge_j,
                SCENE_SLUG,
            ),
        )
        print(f"✓ Updated scene '{SCENE_SLUG}' (id={existing['id']})")
    else:
        conn.execute(
            """INSERT INTO scenes
                (slug, name, active, sort_order, auto_reply,
                 trigger_json, fields_json, tools_json,
                 response_template, escalate_when_json, knowledge_json,
                 created_at, updated_at)
               VALUES (?, ?, 1, ?, 1, ?, ?, ?, ?, ?, ?, datetime('now'), datetime('now'))""",
            (
                SCENE_SLUG, "Консультация по продукту (натяжные потолки)",
                50, trigger_j, fields_j, tools_j,
                RESPONSE_TEMPLATE, escalate_j, knowledge_j,
            ),
        )
        print(f"✓ Created scene '{SCENE_SLUG}'")

    conn.commit()
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
