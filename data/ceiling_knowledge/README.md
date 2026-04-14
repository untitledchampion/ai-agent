# База знаний: натяжные потолки

Знания для сценария `product_consultation` — агент отвечает на технические вопросы клиентов о натяжных потолках, профилях, системах монтажа, гардинах.

## Файлы

- `chunks.json` — 21 чанк с текстом, картинками, связанными товарами. **Источник правды.** Редактируется вручную.
- `../knowledge_images/` — 50 PNG-картинок, упоминаемых в чанках.
- Скрипты в `../../scripts/`:
  - `import_ceiling_knowledge.py` — импортирует `chunks.json` в прод-БД (`knowledge_chunks` + `vec_knowledge`).
  - `seed_consultation_scene.py` — создаёт сценарий `product_consultation` (если его ещё нет).

## Что кладётся в БД

Скрипты **никогда не трогают существующие таблицы** (`products`, `vec_products`, `scenes` в остальном). Только:

1. Создают/наполняют **новые** таблицы `knowledge_chunks` и `vec_knowledge` (через `CREATE IF NOT EXISTS`, апсерт по `slug`).
2. Добавляют **одну новую строку** в `scenes` со `slug='product_consultation'` — только если такого сценария ещё нет (по умолчанию). Ручные правки через UI сохраняются.

## Деплой на прод

Предполагается, что код уже подтянут через `git pull`, картинки в `data/knowledge_images/` поехали вместе с репозиторием.

```bash
# 1. Бэкап прод-БД (страховка)
cp data/chatapp_data_prod.db data/chatapp_data_prod.db.backup-$(date +%F)

# 2. Предпросмотр — что будет сделано
python scripts/import_ceiling_knowledge.py --dry-run
python scripts/seed_consultation_scene.py --dry-run

# 3. Реальный импорт
python scripts/import_ceiling_knowledge.py          # ~20с на BGE-M3
python scripts/seed_consultation_scene.py           # <1с

# 4. Рестарт контейнера агента (чтобы подхватил новый tool search_knowledge)
docker compose restart agent     # или эквивалент вашему стеку
```

Оба скрипта идемпотентны — можно запускать повторно без риска задублировать данные.

## Обновление контента

Редактируем `chunks.json` (текст, картинки, product_ids, escalate), затем:

```bash
python scripts/import_ceiling_knowledge.py   # upsert по slug + ре-эмбеддинг
```

Сценарий обновляется вручную:
```bash
python scripts/seed_consultation_scene.py --force   # перезапишет все поля сценария
```

## Откат

Если что-то пошло не так — новая БЗ полностью изолирована от боевых данных:

```sql
DROP TABLE knowledge_chunks;
DROP TABLE vec_knowledge;
DELETE FROM scenes WHERE slug = 'product_consultation';
```

Существующие продукты/цены/остатки/сценарии не затронуты.
