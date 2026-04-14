"""Разведка: тянем номенклатуру из 1С и сравниваем с локальной products.

Ничего не пишет в БД. Только отчёт.

Usage:
    python scripts/recon_1c.py [db_path]
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import time
from collections import Counter

import requests

ODATA_URL = "http://1c.optceiling.ru/unf_potolki/odata/standard.odata"
ODATA_USER = os.environ.get("ODATA_USER", "odatauser")
ODATA_PASS = os.environ.get("ODATA_PASS", "rty4546")

PAGE_SIZE = 1000


def _norm(s: str) -> str:
    if not s:
        return ""
    q = s.lower().replace("ё", "е").strip()
    q = re.sub(r"\s+", " ", q)
    return q


def fetch_all_nomenclature() -> list[dict]:
    """Paginate Catalog_Номенклатура in full, client-side filter folders."""
    session = requests.Session()
    session.auth = (ODATA_USER, ODATA_PASS)
    session.headers["Accept"] = "application/json"

    results = []
    skip = 0
    t0 = time.time()
    while True:
        params = {
            "$select": "Ref_Key,Code,Артикул,Description,DeletionMark,IsFolder,Parent_Key,ЕдиницаИзмерения_Key",
            "$top": PAGE_SIZE,
            "$skip": skip,
            "$format": "json",
        }
        r = session.get(f"{ODATA_URL}/Catalog_Номенклатура", params=params, timeout=120)
        r.raise_for_status()
        batch = r.json().get("value", [])
        if not batch:
            break
        results.extend(batch)
        print(f"  fetched {len(results)} total in {time.time()-t0:.1f}s", flush=True)
        if len(batch) < PAGE_SIZE:
            break
        skip += PAGE_SIZE
    return results


def main(db_path: str) -> None:
    print(f"[recon] DB: {db_path}")
    print(f"[recon] pulling Catalog_Номенклатура from 1C...")
    try:
        items_1c = fetch_all_nomenclature()
    except Exception as e:
        print(f"[recon] ERROR fetching from 1C: {e}")
        return

    all_count = len(items_1c)
    folders = [x for x in items_1c if x.get("IsFolder")]
    deleted = [x for x in items_1c if x.get("DeletionMark")]
    items_1c = [x for x in items_1c if not x.get("IsFolder") and not x.get("DeletionMark")]

    print(f"[recon] 1C total raw:        {all_count}")
    print(f"[recon] 1C folders:          {len(folders)}")
    print(f"[recon] 1C marked deleted:   {len(deleted)}")
    print(f"[recon] 1C real products:    {len(items_1c)}")

    with_code = sum(1 for x in items_1c if x.get("Code"))
    with_article = sum(1 for x in items_1c if x.get("Артикул"))
    print(f"[recon] of those, with Code: {with_code}")
    print(f"[recon] of those, with Арт.: {with_article}")

    # Build lookup by normalized name
    by_name_1c: dict[str, list[dict]] = {}
    for x in items_1c:
        n = _norm(x.get("Description") or "")
        if not n:
            continue
        by_name_1c.setdefault(n, []).append(x)

    dup_names = sum(1 for vs in by_name_1c.values() if len(vs) > 1)
    print(f"[recon] 1C distinct normalized names: {len(by_name_1c)}")
    print(f"[recon] 1C names with dups: {dup_names}")

    # Local products
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    local = [dict(r) for r in conn.execute("SELECT id, code, name FROM products")]
    print(f"[recon] local products: {len(local)}")

    # Match
    matched = 0
    ambiguous = 0
    not_found = []
    for p in local:
        n = _norm(p["name"])
        hits = by_name_1c.get(n, [])
        if len(hits) == 1:
            matched += 1
        elif len(hits) > 1:
            ambiguous += 1
        else:
            not_found.append(p)

    print()
    print("=" * 60)
    print(f"RESULT:")
    print(f"  matched 1-to-1:   {matched} / {len(local)}")
    print(f"  ambiguous (>1):   {ambiguous}")
    print(f"  not found in 1C:  {len(not_found)}")
    print(f"  only in 1C:       {len(by_name_1c) - matched - ambiguous}")
    print("=" * 60)

    if not_found:
        print("\n[sample] 10 local products NOT FOUND in 1C:")
        for p in not_found[:10]:
            print(f"  - {p['name']!r} (code={p['code']})")

    # Sample "only in 1C"
    local_names = {_norm(p["name"]) for p in local}
    only_1c = [x for n, vs in by_name_1c.items() for x in vs if n not in local_names]
    if only_1c:
        print(f"\n[sample] 10 products only in 1C (of {len(only_1c)}):")
        for x in only_1c[:10]:
            print(f"  - {x.get('Description')!r} "
                  f"(ref={x.get('Ref_Key')[:8]}… code={x.get('Code')!r} art={x.get('Артикул')!r})")

    # Near-matches для not_found (первые 5)
    if not_found:
        print("\n[fuzzy] near-matches for first 5 not-found local:")
        from difflib import get_close_matches
        names_1c_list = list(by_name_1c.keys())
        for p in not_found[:5]:
            n = _norm(p["name"])
            close = get_close_matches(n, names_1c_list, n=3, cutoff=0.8)
            print(f"  LOCAL: {p['name']!r}")
            for c in close:
                print(f"    ~ {c!r}")
            if not close:
                print("    (нет близких совпадений)")


if __name__ == "__main__":
    db = sys.argv[1] if len(sys.argv) > 1 else "/app/data/chatapp_data_prod.db"
    main(db)
