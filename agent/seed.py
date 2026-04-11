"""Seed default scenarios, tone config, and tools into the database."""

from __future__ import annotations

import json
import logging

from sqlalchemy import select

from agent.models import Scene, Tool, ToneConfig, async_session

logger = logging.getLogger(__name__)

DEFAULT_SCENES = [
    {
        "slug": "faq",
        "name": "Общие вопросы",
        "sort_order": 0,
        "auto_reply": True,
        "trigger": {
            "description": "Клиент здоровается, задаёт общий вопрос: адрес склада, режим работы, условия доставки, оплата, возврат, минимальный заказ",

            "examples": [
                "Добрый день",
                "Здравствуйте",
                "Привет",
                "Где у вас склад?",
                "Как оплатить?",
                "Какие условия доставки?",
                "Во сколько работаете?",
                "Какой минимальный заказ?",
            ],
        },
        "fields": [],
        "tools": [],
        "response_template": "Ответь на вопрос клиента, используя ТОЛЬКО данные из базы знаний ниже. Если ответа нет — скажи что уточнишь у коллег.",
        "escalate_when": [],
        "knowledge": [
            {
                "question": "Приветствие: добрый день, здравствуйте, привет",
                "answer": "Поздоровайся в ответ коротко и спроси чем помочь. Не нужно перечислять услуги.",
            },
            {
                "question": "Где находятся склады? Адрес склада?",
                "answer": "Склады ОптСилинг:\n• Восток — АДРЕС УТОЧНИТЬ У РУКОВОДСТВА\n• Юг — АДРЕС УТОЧНИТЬ У РУКОВОДСТВА\n• Север — АДРЕС УТОЧНИТЬ У РУКОВОДСТВА\n• Запад — АДРЕС УТОЧНИТЬ У РУКОВОДСТВА\nРежим работы: Пн-Пт 9:00-18:00, Сб 10:00-15:00",
            },
            {
                "question": "Сколько стоит доставка? Условия доставки?",
                "answer": "Доставка по Москве и МО.\nСтоимость от 1 500₽.\nПри заказе от 15 000₽ — бесплатно.\nСрок: как правило, на следующий рабочий день.",
            },
            {
                "question": "Как оплатить? Какие способы оплаты?",
                "answer": "Принимаем: наличные, карта, безнал (счёт), QR-код.\nДля юрлиц — оплата по счёту, отсрочка обсуждается индивидуально.",
            },
            {
                "question": "Можно вернуть товар? Условия возврата?",
                "answer": "Возврат в течение 14 дней при сохранении товарного вида. Раскрой возврату не подлежит.",
            },
            {
                "question": "Какой минимальный заказ?",
                "answer": "Минимальная сумма заказа — 3 000₽.",
            },
            {
                "question": "Когда работаете? График работы?",
                "answer": "Пн-Пт 9:00-18:00, Сб 10:00-15:00. Воскресенье — выходной.",
            },
        ],
    },
    {
        "slug": "order",
        "name": "Оформление заказа",
        "sort_order": 1,
        "auto_reply": True,
        "trigger": {
            "description": "Клиент присылает список товаров с количествами или просит оформить заказ",

            "examples": [
                "ПК14 3.2м, гарпун тандем 5м",
                "Запустите пожалуйста бауф черный",
                "Нужен профиль EuroKraab 80 метров",
            ],
        },
        "fields": [
            {"name": "items", "type": "product_list", "required": True, "prompt": "Какие позиции вам нужны?"},
            {"name": "warehouse", "type": "enum", "options": ["юг", "север", "восток", "запад"], "required": True, "prompt": "С какого склада забираете?"},
            {"name": "payment", "type": "enum", "options": ["карта", "наличные", "счёт", "QR"], "required": True, "prompt": "Как оплачиваете?"},
            {"name": "delivery", "type": "text", "required": False, "prompt": "Нужна доставка? Если да — укажите адрес"},
        ],
        "tools": [
            {"tool": "check_stock", "when": "items и warehouse заполнены", "args": {"items": "$items", "warehouse": "$warehouse"}},
            {"tool": "get_price", "when": "items заполнены", "args": {"items": "$items", "client_id": "$client_id"}},
        ],
        "response_template": "Подтверди каждую позицию с ценой и наличием. Назови итоговую сумму. Спроси способ оплаты если не указан.",
        "escalate_when": [
            "клиент просит скидку",
            "товара нет ни на одном складе",
            "спецраскрой или нестандартный размер",
            "клиент недоволен или конфликтует",
        ],
        "knowledge": [
            {
                "question": "Как оформить заказ?",
                "answer": "Для оформления нужно: список позиций с количеством, выбрать склад (Восток/Юг/Север/Запад), способ оплаты, и если нужна доставка — адрес.",
            },
        ],
    },
    {
        "slug": "stock_check",
        "name": "Проверка наличия",
        "sort_order": 2,
        "auto_reply": True,
        "trigger": {
            "description": "Клиент спрашивает есть ли товар в наличии, на каком складе, остатки",

            "examples": [
                "Есть белый Р50 в наличии?",
                "ST-95 30 м.п.?",
                "Что по остаткам ПК14?",
            ],
        },
        "fields": [
            {"name": "items", "type": "product_list", "required": True, "prompt": "Какой товар проверить?"},
            {"name": "warehouse", "type": "enum", "options": ["юг", "север", "восток", "запад", "все"], "required": False, "prompt": "На каком складе проверить?"},
        ],
        "tools": [
            {"tool": "check_stock", "when": "items заполнены", "args": {"items": "$items", "warehouse": "$warehouse"}},
        ],
        "response_template": "Сообщи наличие и количество по каждой позиции. Укажи на каком складе. Если клиент спросит адрес склада — бери ТОЛЬКО из базы знаний. НЕ ВЫДУМЫВАЙ адреса.",
        "escalate_when": [
            "не удалось идентифицировать товар",
        ],
        "knowledge": [
            {
                "question": "Где находятся склады?",
                "answer": "Склады: Восток, Юг, Север, Запад. Точные адреса — УТОЧНИТЬ У РУКОВОДСТВА. Режим работы: Пн-Пт 9:00-18:00, Сб 10:00-15:00.",
            },
        ],
    },
    {
        "slug": "price",
        "name": "Запрос цены",
        "sort_order": 3,
        "auto_reply": True,
        "trigger": {
            "description": "Клиент спрашивает стоимость товара, цену, прайс",

            "examples": [
                "ПК14 какая цена сейчас?",
                "Сколько стоит тандем?",
                "Это за м.пог?",
            ],
        },
        "fields": [
            {"name": "items", "type": "product_list", "required": True, "prompt": "На какой товар цену посмотреть?"},
        ],
        "tools": [
            {"tool": "get_price", "when": "items заполнены", "args": {"items": "$items", "client_id": "$client_id"}},
        ],
        "response_template": "Назови цену по каждой позиции с указанием единицы измерения (м.п., шт, рулон). Если есть скидка по категории — укажи.",
        "escalate_when": [
            "клиент просит индивидуальную скидку",
            "запрос на большой объём со спеццеой",
        ],
        "knowledge": [],
    },
    {
        "slug": "order_status",
        "name": "Статус заказа",
        "sort_order": 4,
        "auto_reply": True,
        "trigger": {
            "description": "Клиент спрашивает статус своего заказа, готовность, сроки",

            "examples": [
                "Готовы полотна?",
                "Когда отправите?",
                "Где мой заказ 450?",
            ],
        },
        "fields": [
            {"name": "order_id", "type": "text", "required": True, "prompt": "Подскажите номер заказа?"},
        ],
        "tools": [
            {"tool": "get_order_status", "when": "order_id заполнен", "args": {"order_id": "$order_id"}},
        ],
        "response_template": "Сообщи статус заказа и ориентировочные сроки готовности.",
        "escalate_when": [
            "заказ задерживается больше чем на день",
            "клиент настаивает на срочности",
        ],
        "knowledge": [],
    },
    {
        "slug": "delivery",
        "name": "Доставка",
        "sort_order": 5,
        "auto_reply": True,
        "trigger": {
            "description": "Клиент спрашивает про доставку, стоимость, сроки, адрес",

            "examples": [
                "Доставка до Троицк сколько?",
                "Завтра утро с Востока привезёте?",
                "Сколько будет доставка до Балашихи?",
            ],
        },
        "fields": [
            {"name": "address", "type": "text", "required": True, "prompt": "Куда доставить? Укажите адрес."},
            {"name": "time", "type": "text", "required": False, "prompt": "Когда удобно принять доставку?"},
        ],
        "tools": [
            {"tool": "calc_delivery", "when": "address заполнен", "args": {"address": "$address"}},
        ],
        "response_template": "Назови стоимость и срок доставки. Упомяни условия бесплатной доставки если они есть. Если адреса складов нет в базе знаний — скажи что уточнишь.",
        "escalate_when": [
            "сложный маршрут или другой регион",
        ],
        "knowledge": [
            {
                "question": "Условия доставки?",
                "answer": "Доставка по Москве и МО. Стоимость от 1 500₽. При заказе от 15 000₽ — бесплатно. Срок: следующий рабочий день.",
            },
            {
                "question": "Куда доставляете?",
                "answer": "Доставка по Москве и Московской области. Другие регионы — обсуждается индивидуально с менеджером.",
            },
        ],
    },
    {
        "slug": "payment",
        "name": "Оплата",
        "sort_order": 6,
        "auto_reply": True,
        "trigger": {
            "description": "Клиент спрашивает про способы оплаты, QR, счёт, безнал",

            "examples": [
                "QR код пришлёте?",
                "Оплачу при получении",
                "Можно на счёт выставить?",
            ],
        },
        "fields": [
            {"name": "payment_method", "type": "enum", "options": ["карта", "наличные", "счёт", "QR"], "required": True, "prompt": "Какой способ оплаты удобен?"},
        ],
        "tools": [],
        "response_template": "Подтверди способ оплаты. Если QR или счёт — скажи что подготовишь и пришлёшь.",
        "escalate_when": [
            "запрос отсрочки платежа",
            "вопрос по задолженности",
        ],
        "knowledge": [
            {
                "question": "Как оплатить?",
                "answer": "Принимаем: наличные, карта, безнал (счёт), QR-код. Для юрлиц — оплата по счёту, отсрочка обсуждается индивидуально.",
            },
        ],
    },
    {
        "slug": "new_client",
        "name": "Новый клиент",
        "sort_order": 7,
        "auto_reply": False,
        "trigger": {
            "description": "Новый клиент впервые обращается, просит прайс, спрашивает условия сотрудничества",

            "examples": [
                "Здравствуйте, хотел бы узнать о сотрудничестве",
                "Можно прайс на профиль?",
                "Меня зовут Александра, компания ТД Спецстрой",
            ],
        },
        "fields": [
            {"name": "name", "type": "text", "required": True, "prompt": "Как вас зовут?"},
            {"name": "company", "type": "text", "required": True, "prompt": "Название компании / ИП?"},
            {"name": "role", "type": "enum", "options": ["монтажник", "дилер", "подрядчик", "конечный заказчик"], "required": True, "prompt": "Вы монтажник, дилер или подрядчик?"},
            {"name": "region", "type": "text", "required": True, "prompt": "В каком регионе работаете?"},
            {"name": "volume", "type": "text", "required": False, "prompt": "Примерный объём закупок в месяц?"},
        ],
        "tools": [],
        "response_template": "Собери всю информацию о клиенте. Когда все обязательные поля заполнены — сформируй карточку для менеджера.",
        "escalate_when": [],
        "knowledge": [],
    },
    {
        "slug": "complaint",
        "name": "Рекламация / Брак",
        "sort_order": 8,
        "auto_reply": False,
        "trigger": {
            "description": "Клиент жалуется на брак, некачественный товар, хочет возврат или замену",

            "examples": [
                "На большом полотне брак какой-то",
                "Прислали не тот цвет",
                "Товар пришёл повреждённый",
            ],
        },
        "fields": [
            {"name": "order_id", "type": "text", "required": True, "prompt": "Подскажите номер заказа?"},
            {"name": "problem", "type": "text", "required": True, "prompt": "Что именно не так? Опишите проблему."},
            {"name": "photo", "type": "text", "required": False, "prompt": "Пришлите, пожалуйста, фото."},
        ],
        "tools": [],
        "response_template": "Извинись за неудобства. Собери информацию о проблеме. Передай менеджеру.",
        "escalate_when": [],
        "knowledge": [
            {
                "question": "Условия возврата?",
                "answer": "Возврат в течение 14 дней при сохранении товарного вида. Раскрой возврату не подлежит. Рекламация рассматривается в течение 3 рабочих дней.",
            },
        ],
    },
    {
        "slug": "escalation",
        "name": "Эскалация (fallback)",
        "sort_order": 99,
        "auto_reply": False,
        "trigger": {
            "description": "Не подошёл ни один другой сценарий, или сложный/нестандартный вопрос",
            "examples": [],
        },
        "fields": [],
        "tools": [],
        "response_template": "Передай вопрос менеджеру с полным контекстом.",
        "escalate_when": [],
        "knowledge": [],
    },
]

DEFAULT_TONE = {
    "persona": "Менеджер отдела продаж компании ОптСилинг",
    "parameters": {
        "formality": 2,
        "brevity": 4,
        "emoji": False,
        "address": "ты/вы по контексту",
        "signature": False,
    },
    "rules": [
        "Отвечай кратко и по делу, как опытный менеджер",
        "Не используй шаблонные фразы типа 'Чем могу помочь'",
        "Подтверждай каждую позицию заказа",
        "Если чего-то нет — сразу предлагай альтернативу",
        "Цены и остатки — ТОЛЬКО из инструментов, никогда не выдумывай",
        "Не говори что ты бот или ИИ",
    ],
    "examples": [
        {
            "client": "ПК14 3.2м есть на востоке?",
            "agent": "Да, ПК14 на Востоке есть, 45 шт. Цена 870₽/м.п. Оформляем?",
        },
        {
            "client": "Доставка до Балашихи сколько?",
            "agent": "Доставка до Балашихи — 1 500₽. При заказе от 15 000₽ бесплатно. Оформить?",
        },
        {
            "client": "Где мой заказ 450?",
            "agent": "Заказ 450 в производстве, готовность завтра к 10:00. Отпишусь когда будет готов.",
        },
    ],
    "forbidden_phrases": [
        "К сожалению, я всего лишь бот",
        "Я не могу гарантировать",
        "Обратитесь в поддержку",
        "Извините за неудобства",
        "Я — искусственный интеллект",
    ],
}

DEFAULT_TOOLS = [
    {
        "slug": "check_stock",
        "name": "Проверка остатков",
        "description": "Проверяет наличие товара на складе. MVP: мок-данные. Phase 2: 1С API.",
        "active": True,
    },
    {
        "slug": "get_price",
        "name": "Получение цены",
        "description": "Возвращает цену товара с учётом категории клиента. MVP: мок-данные. Phase 2: 1С API.",
        "active": True,
    },
    {
        "slug": "search_product",
        "name": "Поиск товара",
        "description": "Нечёткий поиск товара по названию/артикулу. MVP: мок-данные. Phase 2: SQLite FTS.",
        "active": True,
    },
    {
        "slug": "get_order_status",
        "name": "Статус заказа",
        "description": "Получение статуса заказа по номеру. MVP: мок-данные. Phase 2: 1С API.",
        "active": True,
    },
    {
        "slug": "calc_delivery",
        "name": "Расчёт доставки",
        "description": "Расчёт стоимости и сроков доставки. MVP: мок-данные. Phase 2: таблица/API.",
        "active": True,
    },
]


async def seed_defaults() -> dict[str, int]:
    """Seed default scenarios, tools, and tone config. Returns counts."""
    counts = {"scenes": 0, "tools": 0, "tone": 0}

    async with async_session() as session:
        # Scenes
        for scene_data in DEFAULT_SCENES:
            existing = await session.execute(
                select(Scene).where(Scene.slug == scene_data["slug"])
            )
            if existing.scalar_one_or_none():
                continue

            scene = Scene(
                slug=scene_data["slug"],
                name=scene_data["name"],
                sort_order=scene_data["sort_order"],
                auto_reply=scene_data["auto_reply"],
                response_template=scene_data["response_template"],
            )
            scene.trigger = scene_data["trigger"]
            scene.fields = scene_data["fields"]
            scene.tools = scene_data["tools"]
            scene.escalate_when = scene_data["escalate_when"]
            scene.knowledge = scene_data.get("knowledge", [])
            session.add(scene)
            counts["scenes"] += 1

        # Tools
        for tool_data in DEFAULT_TOOLS:
            existing = await session.execute(
                select(Tool).where(Tool.slug == tool_data["slug"])
            )
            if existing.scalar_one_or_none():
                continue

            tool = Tool(
                slug=tool_data["slug"],
                name=tool_data["name"],
                description=tool_data["description"],
                active=tool_data["active"],
            )
            session.add(tool)
            counts["tools"] += 1

        # Tone
        existing_tone = await session.execute(select(ToneConfig).limit(1))
        if not existing_tone.scalar_one_or_none():
            tone = ToneConfig(name="default", persona=DEFAULT_TONE["persona"])
            tone.parameters = DEFAULT_TONE["parameters"]
            tone.rules = DEFAULT_TONE["rules"]
            tone.examples = DEFAULT_TONE["examples"]
            tone.forbidden_phrases = DEFAULT_TONE["forbidden_phrases"]
            session.add(tone)
            counts["tone"] = 1

        await session.commit()

    return counts
