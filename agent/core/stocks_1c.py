"""Live-остатки из 1С УНФ по Ref_Key.

Батч-запрос к AccumulationRegister_ЗапасыНаСкладах/Balance().
Показываем только клиентские склады: «Склад», СЕВЕР, ВОСТОК, ЗАПАД, ЮГ.
Скрываем: брак, производство, стенды, подразделения.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import threading
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

ODATA_URL = os.environ.get(
    "ODATA_URL", "http://1c.optceiling.ru/unf_potolki/odata/standard.odata"
)
ODATA_USER = os.environ.get("ODATA_USER", "odatauser")
ODATA_PASS = os.environ.get("ODATA_PASS", "rty4546")

BATCH_SIZE = 40
TIMEOUT = 15

# Клиентские склады — показываем. Всё остальное (брак, производство, стенды,
# подразделения) — прячем от клиента.
_CLIENT_WAREHOUSE_RE = re.compile(
    r"^склад(\s+(север|восток|запад|юг))?$", re.IGNORECASE
)

_warehouses_cache: dict[str, dict] | None = None
_warehouses_lock = threading.Lock()


def _auth_header() -> str:
    return "Basic " + base64.b64encode(
        f"{ODATA_USER}:{ODATA_PASS}".encode()
    ).decode()


def _get(url: str) -> dict:
    req = urllib.request.Request(url)
    req.add_header("Authorization", _auth_header())
    with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
        return json.loads(r.read())


def _warehouses() -> dict[str, dict]:
    """Возвращает {ref_key: {name, is_client}} для всех складов. Кэшируется."""
    global _warehouses_cache
    if _warehouses_cache is not None:
        return _warehouses_cache
    with _warehouses_lock:
        if _warehouses_cache is not None:
            return _warehouses_cache
        base = f"{ODATA_URL}/Catalog_СтруктурныеЕдиницы"
        qs = urllib.parse.urlencode(
            {
                "$select": "Ref_Key,Description,ТипСтруктурнойЕдиницы",
                "$format": "json",
            },
            quote_via=urllib.parse.quote,
        )
        url = urllib.parse.quote(base, safe=":/") + "?" + qs
        try:
            data = _get(url)
        except Exception as e:
            logger.warning("warehouses fetch failed: %s", e)
            _warehouses_cache = {}
            return _warehouses_cache

        out: dict[str, dict] = {}
        for x in data.get("value", []):
            name = (x.get("Description") or "").strip()
            is_client = bool(_CLIENT_WAREHOUSE_RE.match(name))
            out[x["Ref_Key"]] = {"name": name, "is_client": is_client}
        _warehouses_cache = out
        return out


def _fetch_batch(refs: list[str]) -> list[dict]:
    or_part = " or ".join(f"Номенклатура_Key eq guid'{r}'" for r in refs)
    base = f"{ODATA_URL}/AccumulationRegister_ЗапасыНаСкладах/Balance()"
    qs = urllib.parse.urlencode(
        {"$filter": or_part, "$format": "json"}, quote_via=urllib.parse.quote
    )
    url = urllib.parse.quote(base, safe=":/()") + "?" + qs
    try:
        data = _get(url)
    except Exception as e:
        logger.warning("stocks fetch failed: %s", e)
        return []
    return data.get("value", [])


def fetch_stocks(ref_keys: list[str]) -> dict[str, list[dict]]:
    """Возвращает {ref_key: [{warehouse, qty}, ...]} по клиентским складам.

    Суммирует по складу (разные партии/характеристики в одну строку на склад).
    Пустой список = нет на клиентских складах (может быть на производстве, но
    это клиенту не показываем).
    """
    uniq = [r for r in dict.fromkeys(ref_keys) if r]
    if not uniq:
        return {}

    wh = _warehouses()
    result: dict[str, dict[str, float]] = {}  # ref_key -> {warehouse_name: qty}

    for i in range(0, len(uniq), BATCH_SIZE):
        for row in _fetch_batch(uniq[i : i + BATCH_SIZE]):
            rk = row.get("Номенклатура_Key")
            wh_key = row.get("СтруктурнаяЕдиница_Key")
            qty = row.get("КоличествоBalance") or 0
            if not rk or not wh_key or qty <= 0:
                continue
            info = wh.get(wh_key)
            if not info or not info["is_client"]:
                continue
            result.setdefault(rk, {}).setdefault(info["name"], 0)
            result[rk][info["name"]] += float(qty)

    return {
        rk: [{"warehouse": w, "qty": q} for w, q in sorted(whs.items())]
        for rk, whs in result.items()
    }
