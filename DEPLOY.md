# Деплой

Прод: `root@<IP>:/opt/ai-agent`

## Обычный деплой (30 секунд)

```bash
git push
ssh root@64.188.60.206 'cd /opt/ai-agent && git pull && docker compose up -d --build agent'
```

- Фронт собирается внутри контейнера (multi-stage Dockerfile.agent)
- Python-зависимости (torch, transformers и т.д.) кэшируются пока `requirements.txt` не менялся
- Типичное время: 20–60 секунд

## Когда нужен `--no-cache`

**Почти никогда.** Использовать только если:
- Испортился base-образ
- Нужно форсировать перескачивание системных пакетов
- Подозрение на битый кэш-слой

`--no-cache` пересобирает всё с нуля, включая установку torch (~1.5 ГБ) — это 5–10 минут и трафик. Не делать «на всякий случай».

## Если кончился диск

```bash
ssh root@64.188.60.206 'docker system prune -a -f --volumes'
```

## Разворачивание на новом сервере

Эталонный бэкап прод-базы лежит в репо: `data/backups/chatapp_data_prod_2026-04-15.db`.

```bash
# 1. Клонируем репо
git clone <repo-url> /opt/ai-agent && cd /opt/ai-agent

# 2. Копируем .env (секреты — не в git, скопировать вручную)
cp .env.example .env
# Заполнить: ANTHROPIC_API_KEY, CHATAPP_TOKEN, OC_1C_USER, OC_1C_PASS и т.д.

# 3. Восстанавливаем БД из бэкапа
cp data/backups/chatapp_data_prod_2026-04-15.db data/chatapp_data_prod.db

# 4. Запускаем миграции БЗ (эмбеддинги + сценарии)
#    import_ceiling_knowledge пересоздаёт vec_knowledge (эмбеддинги)
#    seed_consultation_scene создаёт сценарий product_consultation
docker compose up -d --build agent
docker compose exec agent python scripts/import_ceiling_knowledge.py
docker compose exec agent python scripts/seed_consultation_scene.py

# 5. (Опционально) Синхронизировать свежие данные из 1С
#    Через UI: вкладка «Синхронизация» → кнопка «Синхронизировать»
```

### Что лежит в бэкапе

| Данные | Строк | Восстанавливается |
|---|---|---|
| Товары (`products`) | 2431 | Из бэкапа + актуализируется синком 1С |
| Обогащённые описания (`products_meta`) | 1705 | Из бэкапа |
| Алиасы (`product_aliases`) | 2709 | Из бэкапа (ручная работа, не пересобирается) |
| База знаний (`knowledge_chunks`) | 21 | Из бэкапа + скрипт import_ceiling_knowledge |
| Сценарии (`scenes`) | 12 | Из бэкапа + скрипт seed_consultation_scene |
| Векторные индексы (`vec_*`) | — | Пересобираются скриптами миграции |

**Важно:** алиасы (`product_aliases`, `knowledge_product_aliases`) — **ручная работа**, наполнялись через UI. Без бэкапа их не восстановить. Это главная причина хранить бэкап в репо.

### Обновление бэкапа

Перед сносом сервера или при значительных изменениях в данных:

```bash
scp root@<IP>:/opt/ai-agent/data/chatapp_data_prod.db \
    data/backups/chatapp_data_prod_$(date +%F).db
git add data/backups/
git commit -m "backup: свежий бэкап прод-базы $(date +%F)"
```

## Не делать

- `rsync` кода на прод — только через git
- Ручной `npm run build` на проде — фронт теперь собирается в Dockerfile
- `--no-verify` при коммите
