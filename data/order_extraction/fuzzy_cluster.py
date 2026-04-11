#!/usr/bin/env python3
"""Fuzzy clustering of raw_name values.

Strategy:
  1. Extract content words (letters only, no digits), drop stopwords+colors+units
  2. Stem each word (strip common Russian endings)
  3. Key = sorted stems joined (numbers/colors are attributes, not part of key)
  4. Fuzzy merge single-word keys with Levenshtein ≤ 2 (handles typos)
  5. Collect sizes (numbers) and colors as attribute columns per group
"""
import re
import sqlite3
from collections import defaultdict, Counter

DB = "/Users/klim/Desktop/ai-agent/data/chatapp_data.db"

# --- Levenshtein ---
def lev(a: str, b: str) -> int:
    if a == b:
        return 0
    if len(a) < len(b):
        a, b = b, a
    if len(b) == 0:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        curr = [i] + [0] * len(b)
        for j, cb in enumerate(b, 1):
            curr[j] = min(curr[j-1] + 1, prev[j] + 1, prev[j-1] + (0 if ca == cb else 1))
        prev = curr
    return prev[-1]

# --- Simple Russian stemmer ---
ENDINGS = sorted([
    "ами","ями","иях","иях","ях","ах","ов","ев","ей","ем","ом","ых","их",
    "ай","ей","ой","ый","ий","ая","яя","ое","ее","ую","юю","ою","ею",
    "ам","ям","ой","ей","ию","ью","ее","ии",
    "а","я","ы","и","у","ю","о","е","ь","й",
], key=len, reverse=True)

def stem(word: str) -> str:
    w = word
    for e in ENDINGS:
        if len(w) > len(e) + 2 and w.endswith(e):
            return w[: -len(e)]
    return w

# --- Tokenization ---
LETTERS_RE = re.compile(r"[a-zа-яё]+", re.IGNORECASE)
DIGITS_RE = re.compile(r"\d+(?:[.,]\d+)?")
SIZE_RE = re.compile(r"\d+[./x×хЧ*]\d+", re.IGNORECASE)

# Stopwords + units + colors (treated as attributes, not part of key)
UNITS = {"шт","штук","штуки","штука","штучек","штучка","м","мм","см","кг","гр","мл","л","уп","упаковка",
         "пачка","пачку","палка","палок","палки","коробка","коробку","коробок","компл","комплект",
         "пара","пары","пар","метр","метра","метров","мп","пм","мп"}

COLORS = {"белый","белая","белое","белых","белым","белую",
          "чёрный","черный","черная","чёрная","чёрное","черное","чёрных","черных","чёрного","черного","черную","чёрную",
          "серый","серая","серое","серых","серого",
          "красный","красная","синий","синяя","синие","синих",
          "мат","матовый","матовая","матовое","матовых","матов","мата",
          "сатин","сатиновый","глянец","глянцевый","глянцевая","прозрачный","прозрачная",
          "рыжий","рыжая","рыжие","оранжевый","оранжевая","оранжевые",
          "зелёный","зелёная","жёлтый","жёлтая","золотой","золотая","бежевый","бежевая",
          "коричневый","коричневая","фиолетовый","розовый","голубой"}

FILLER = {"и","или","а","но","же","ну","на","в","во","от","до","по","с","со","у","к","за","из","о","об",
          "нужно","нужен","нужна","нужны","хочу","заказ","заказать","заказываю","пожалуйста","добавьте",
          "добавь","примите","привезите","если","есть","нет","можно","надо","как","тоже","ещё","еще",
          "для","под","над","про",
          "там","тут","это","этот","эта","эти","то","тот","та","те","они","он","она","оно","мы","вы",
          "день","утро","вечер","завтра","сегодня","через","минут","минуты","часов","час",
          "добрый","доброе","добрая","здравствуйте","привет","спасибо","ок","хорошо","принято",
          "большой","большая","маленький","маленькая","новый","новая","много","мало","чуть",
          "пл","пл.","ст","ст.","мм.","см.","шт.","м.","кг.",
          "г","гр","год","лет"}

STOP = UNITS | COLORS | FILLER

def extract(raw: str):
    """Return (key, sizes, colors, full_words) for a raw_name."""
    raw = raw.lower().strip()
    # Extract sizes (like "125/150", "30x40", "3,2")
    sizes = SIZE_RE.findall(raw) + [d for d in DIGITS_RE.findall(raw) if not any(d in s for s in SIZE_RE.findall(raw))]
    # dedup sizes preserving order
    seen = set(); sizes_u = []
    for s in sizes:
        if s not in seen:
            seen.add(s); sizes_u.append(s)
    # Extract content words (letters only)
    all_words = LETTERS_RE.findall(raw)
    colors_found = [w for w in all_words if w in COLORS]
    content = [w for w in all_words if w not in STOP and len(w) >= 2]
    if not content:
        content = all_words[:1]
    stems = [stem(w) for w in content]
    # Key: all sorted unique stems (preserves modifiers like "двойной", "тандем")
    key_stems = sorted(set(stems))
    key = " ".join(key_stems[:4])  # cap at 4 stems
    return key, sizes_u, list(set(colors_found)), all_words

# --- Load ---
conn = sqlite3.connect(DB)
cur = conn.cursor()
cur.execute("""
    SELECT LOWER(TRIM(raw_name)) as name, COUNT(*) as cnt
    FROM extracted_order_items
    WHERE raw_name IS NOT NULL AND TRIM(raw_name) <> ''
    GROUP BY LOWER(TRIM(raw_name))
""")
rows = cur.fetchall()
print(f"Loaded {len(rows)} unique raw_names")

# --- Initial grouping ---
groups = defaultdict(lambda: {"items": [], "sizes": Counter(), "colors": Counter(), "total": 0})
for name, cnt in rows:
    key, sizes, colors, _ = extract(name)
    if not key:
        key = "(empty)"
    g = groups[key]
    g["items"].append((name, cnt))
    g["total"] += cnt
    for s in sizes:
        g["sizes"][s] += cnt
    for c in colors:
        g["colors"][c] += cnt

print(f"Groups by stem: {len(groups)}")

# --- Direct-pair fuzzy merge (no chaining): smallest absorbs into nearest larger ---
# For each small group, find if there's a much larger group within Lev ≤ 1 and merge into it.
# This avoids chain effects because we only merge UP to larger groups.
merge_map = {}  # small_key -> absorbing_large_key
all_keys = sorted(groups.keys(), key=lambda k: -groups[k]["total"])
single = [k for k in all_keys if " " not in k and len(k) >= 5]

for i, small in enumerate(single):
    small_total = groups[small]["total"]
    # Find a LARGER group within Lev ≤ 1 (only looking at larger groups earlier in sorted list)
    best = None
    for big in single[:i]:
        big_total = groups[big]["total"]
        if big_total < small_total * 3:  # must be significantly larger to absorb
            continue
        if abs(len(big) - len(small)) > 1:
            continue
        d = lev(big, small)
        if d <= 1:
            best = big
            break
    if best:
        merge_map[small] = best

merged = defaultdict(lambda: {"items": [], "sizes": Counter(), "colors": Counter(), "total": 0, "keys": set()})
for k, g in groups.items():
    root = merge_map.get(k, k)
    m = merged[root]
    m["items"].extend(g["items"])
    m["total"] += g["total"]
    m["sizes"].update(g["sizes"])
    m["colors"].update(g["colors"])
    m["keys"].add(k)

print(f"After fuzzy merge: {len(merged)} groups (merged {len(merge_map)} typo-variants)")

# --- Top groups ---
ranked = sorted(merged.items(), key=lambda x: -x[1]["total"])

print("\n=== ТОП-25 КЛАСТЕРОВ ===\n")
for key, g in ranked[:25]:
    sizes_str = ", ".join(f"{s}:{c}" for s, c in g["sizes"].most_common(5))
    colors_str = ", ".join(f"{c}:{n}" for c, n in g["colors"].most_common(3))
    print(f"[{key}]  всего={g['total']}  вариантов={len(g['items'])}  ключей={len(g['keys'])}")
    if sizes_str: print(f"   размеры: {sizes_str}")
    if colors_str: print(f"   цвета:   {colors_str}")
    for name, cnt in sorted(g["items"], key=lambda x: -x[1])[:5]:
        print(f"   {cnt:>5}  {name}")
    if len(g["items"]) > 5:
        print(f"   ... и ещё {len(g['items'])-5} вариантов")
    print()

# --- Check дюбель group ---
print("\n=== ПРОВЕРКА: группы с дюбель/дюпель/дюбиль ===")
for key, g in ranked:
    if any(x in key for x in ["дюбел","дюпел","дюбил"]):
        print(f"[{key}] всего={g['total']} вариантов={len(g['items'])} keys={g['keys']}")
        for name, cnt in sorted(g["items"], key=lambda x: -x[1])[:8]:
            print(f"   {cnt:>4}  {name}")
        print()

# --- Check пк group ---
print("\n=== ПРОВЕРКА: группа пк ===")
for key, g in ranked:
    if key == "пк" or key.startswith("пк "):
        print(f"[{key}] всего={g['total']} вариантов={len(g['items'])} keys={g['keys']}")
        sizes = ", ".join(f"{s}:{c}" for s, c in g["sizes"].most_common(10))
        print(f"   размеры: {sizes}")
        for name, cnt in sorted(g["items"], key=lambda x: -x[1])[:10]:
            print(f"   {cnt:>4}  {name}")
        print()
        break

conn.close()
