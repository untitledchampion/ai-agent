"""Live-цены из 1С УНФ по Ref_Key.

Батч-запрос к InformationRegister_ЦеныНоменклатуры, фильтр по виду цен «БП2».
Один HTTP-запрос на N товаров (пока N <= ~50 — ограничение длины URL).
"""
from __future__ import annotations

import base64
import json
import logging
import os
import urllib.parse
import urllib.request

logger = logging.getLogger(__name__)

ODATA_URL = os.environ.get(
    "ODATA_URL", "http://1c.optceiling.ru/unf_potolki/odata/standard.odata"
)
ODATA_USER = os.environ.get("ODATA_USER", "odatauser")
ODATA_PASS = os.environ.get("ODATA_PASS", "rty4546")

# Вид цены "БП2" — фактически используемый для номенклатуры
PRICE_TYPE_KEY = os.environ.get(
    "PRICE_TYPE_KEY", "224fb0e2-7cd8-11f0-9071-005056aaefed"
)

BATCH_SIZE = 40
TIMEOUT = 15


def _auth_header() -> str:
    return "Basic " + base64.b64encode(
        f"{ODATA_USER}:{ODATA_PASS}".encode()
    ).decode()


def _fetch_batch(refs: list[str]) -> dict[str, float]:
    """Запрос в 1С: возвращает {ref_key: price} для указанных refs по виду БП2."""
    if not refs:
        return {}
    or_part = " or ".join(f"Номенклатура_Key eq guid'{r}'" for r in refs)
    flt = f"({or_part}) and ВидЦен_Key eq guid'{PRICE_TYPE_KEY}'"
    qs = urllib.parse.urlencode(
        {"$filter": flt, "$format": "json"}, quote_via=urllib.parse.quote
    )
    url = (
        urllib.parse.quote(
            f"{ODATA_URL}/InformationRegister_ЦеныНоменклатуры", safe=":/"
        )
        + "?"
        + qs
    )
    req = urllib.request.Request(url)
    req.add_header("Authorization", _auth_header())
    out: dict[str, float] = {}
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            data = json.loads(r.read())
    except Exception as e:
        logger.warning("1C price fetch failed: %s", e)
        return {}

    # В регистре может быть несколько записей на один Ref_Key (история) —
    # берём с максимальным Period.
    latest: dict[str, tuple[str, float]] = {}
    for row in data.get("value", []):
        rk = row.get("Номенклатура_Key")
        period = row.get("Period", "")
        price = row.get("Цена")
        if rk is None or price is None:
            continue
        cur = latest.get(rk)
        if not cur or period > cur[0]:
            latest[rk] = (period, float(price))
    for rk, (_, price) in latest.items():
        out[rk] = price
    return out


def fetch_prices(ref_keys: list[str]) -> dict[str, float]:
    """Возвращает {ref_key: price} для всех указанных. Батчит по BATCH_SIZE."""
    uniq = [r for r in dict.fromkeys(ref_keys) if r]
    result: dict[str, float] = {}
    for i in range(0, len(uniq), BATCH_SIZE):
        result.update(_fetch_batch(uniq[i : i + BATCH_SIZE]))
    return result
