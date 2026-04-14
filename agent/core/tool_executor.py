"""Tool Executor — calls external APIs based on scene tool configs.

Executes HTTP-based tools from the tool registry.
No mock/stub data — tools only work through real API integrations.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field

import httpx

from agent.core import product_search
from agent.core import knowledge_search

logger = logging.getLogger(__name__)


# Local (in-process) tools — no HTTP, called directly.
# Map: slug → callable(args: dict) -> dict
def _top1_dist(hits: list[dict]) -> float:
    return hits[0]["distance"] if hits else float("inf")


# If several top candidates are within this distance from top-1,
# the choice is considered ambiguous and the Responder must ask the client.
AMBIGUITY_GAP = 0.025


# Deterministic post-filter: if the user query contains hard numeric
# constraints (dimension pair like "60/110" or "2*0.75", length in meters,
# article number), keep only candidates whose name contains the same
# constraint. BGE-M3 does not differentiate "(3,2м)" from "(3,0м)" or
# "2*1.5" from "2*0.75" reliably, so we do it ourselves.
#
# Separators in number pairs are normalized: "60/110", "060-110", "60x110",
# "60*110", "60×110" and "60х110" (Cyrillic х) all collapse to "60:110".
_NUM = r"\d+(?:[.,]\d+)?"
_SEP = r"[-/*xхX×]"
_PAIR_RX = re.compile(rf"(?<!\d){_NUM}\s*{_SEP}\s*{_NUM}(?!\d)")
# Space-separated pairs: "100 125" — both numbers must be ≥2 digits to avoid
# false positives like "кольцо 50 5шт".  Also reject if second number is
# followed by a unit-like letter (ш, м, к → шт/м/кг).
_SPACE_PAIR_RX = re.compile(r"(?<!\d)(\d{2,}(?:[.,]\d+)?)\s+(\d{2,}(?:[.,]\d+)?)(?!\d)(?![шмкa-яa-z])", re.IGNORECASE)
_LEN_M_RX = re.compile(r"(?<!\d)(\d+[.,]\d+)\s*м(?!м)(?!\w)")
_ARTICLE_RX = re.compile(r"№\s*(\d+)")


def _canon_num(s: str) -> str:
    """Strip leading zeros and trailing fraction zeros: '060' → '60', '2.0' → '2', '0.750' → '0.75'."""
    s = s.strip().replace(",", ".")
    if "." in s:
        i, f = s.split(".", 1)
        i = i.lstrip("0") or "0"
        f = f.rstrip("0")
        return f"{i}.{f}" if f else i
    return s.lstrip("0") or "0"


def _extract_size_tokens(text: str) -> list[str]:
    """Extract canonical dimension/size tokens from free text.

    Returns tokens like 'P60:110' for number pairs (any separator),
    'L3.2' for lengths in meters, '№22' for article numbers. The same
    semantic value produces the same token regardless of which
    separator was used ('/', '-', '*', 'x', 'х', '×').
    """
    if not text:
        return []
    n = text.lower()
    out: list[str] = []
    for m in _PAIR_RX.finditer(n):
        parts = re.split(_SEP, m.group(0))
        canon = ":".join(_canon_num(p) for p in parts if p.strip())
        out.append(f"P{canon}")
    # Space-separated pairs: "100 125" → P100:125
    for m in _SPACE_PAIR_RX.finditer(n):
        canon = f"{_canon_num(m.group(1))}:{_canon_num(m.group(2))}"
        token = f"P{canon}"
        if token not in out:  # avoid duplicates if already matched by _PAIR_RX
            out.append(token)
    for m in _LEN_M_RX.finditer(n):
        out.append(f"L{_canon_num(m.group(1))}")
    for m in _ARTICLE_RX.finditer(n):
        out.append(f"№{m.group(1)}")
    return out


# Common color stems used in product names. Match by substring after
# normalizing ё→е, so "чёрный" / "черный" / "ЧЕРНЫЙ" all collapse.
_COLOR_STEMS = [
    "бел", "черн", "красн", "син", "зелен", "желт",
    "коричн", "сер", "золот", "бронз", "беж",
]


def _extract_color_stems(name: str) -> list[str]:
    n = name.lower().replace("ё", "е")
    return [s for s in _COLOR_STEMS if s in n]


def _filter_by_color(query_name: str, hits: list[dict]) -> list[dict]:
    stems = _extract_color_stems(query_name)
    if not stems or not hits:
        return hits
    filtered: list[dict] = []
    for h in hits:
        n = h.get("name", "").lower().replace("ё", "е")
        if any(s in n for s in stems):
            filtered.append(h)
    return filtered if filtered else hits


_QTY_RX = re.compile(r"(\d+(?:[.,]\d+)?)\s*([а-яА-Яa-zA-Z²]+)?")

# Map customer-side qty units to canonical unit_norm tokens.
_QTY_UNIT_MAP = {
    # pieces
    "шт": "шт", "штук": "шт", "штука": "шт", "штуки": "шт", "штуку": "шт",
    "палка": "шт", "палки": "шт", "палок": "шт", "палку": "шт",
    "уп": "шт", "упак": "шт", "упаковка": "шт", "упаковки": "шт",
    # meters
    "м": "м", "метр": "м", "метра": "м", "метров": "м",
    "пог": "м", "пм": "м",
    # square meters
    "м2": "м2", "м²": "м2", "кв": "м2",
    # kg
    "кг": "кг", "килограмм": "кг",
    # packs
    "пачка": "пачка", "пачки": "пачка", "пачек": "пачка",
    # complects
    "комплект": "компл", "комплекта": "компл", "комплектов": "компл",
    "компл": "компл", "компалект": "компл",
}


def _parse_qty(qty: str | None) -> tuple[float | None, str | None]:
    """Parse '42 м' / '3 палки' / '1 пачка' → (42.0, 'м')."""
    if not qty:
        return None, None
    s = qty.strip().lower().replace(",", ".")
    m = _QTY_RX.search(s)
    if not m:
        return None, None
    try:
        value = float(m.group(1))
    except ValueError:
        return None, None
    raw_unit = (m.group(2) or "").strip()
    canon = _QTY_UNIT_MAP.get(raw_unit)
    if canon is None:
        # try prefix match (e.g. "метр" matches "метров"-stripped form)
        for k, v in _QTY_UNIT_MAP.items():
            if raw_unit.startswith(k):
                canon = v
                break
    return value, canon


import math


def _compute_total(qty: str | None, candidate: dict) -> dict | None:
    """If qty + candidate units are convertible, return totals.

    Returns dict with: pieces, unit_label, unit_price, total_price, note
    """
    if not candidate:
        return None
    price = candidate.get("price_dealer")
    if price is None:
        return None
    value, qty_unit = _parse_qty(qty)
    if value is None or qty_unit is None:
        return None
    cand_unit = candidate.get("unit_norm")
    if cand_unit is None:
        return None

    # qty_unit == cand_unit → straight multiplication
    if qty_unit == cand_unit:
        pieces = value
        # If pieces should be integer (шт/пачка/компл), don't round but
        # show as int when whole.
        return {
            "pieces": pieces,
            "unit_label": cand_unit,
            "unit_price": price,
            "total_price": round(pieces * price, 2),
            "note": "",
        }

    # client says meters, product is sold in pieces with known length
    if qty_unit == "м" and cand_unit == "шт" and candidate.get("pieces_length_m"):
        plm = float(candidate["pieces_length_m"])
        if plm <= 0:
            return None
        pieces = math.ceil(value / plm)
        return {
            "pieces": pieces,
            "unit_label": "шт",
            "unit_price": price,
            "total_price": round(pieces * price, 2),
            "note": f"{value:g} м ≈ {pieces} шт по {plm:g} м",
        }

    # client says pieces, product priced per meter — convert if length known
    if qty_unit == "шт" and cand_unit == "м" and candidate.get("pieces_length_m"):
        plm = float(candidate["pieces_length_m"])
        meters = value * plm
        return {
            "pieces": meters,
            "unit_label": "м",
            "unit_price": price,
            "total_price": round(meters * price, 2),
            "note": f"{value:g} шт × {plm:g} м = {meters:g} м",
        }

    # otherwise: cannot convert safely
    return None


def _filter_by_top_category(hits: list[dict]) -> list[dict]:
    """Keep only candidates whose category matches top-1's category.

    Categories in the price list (e.g. "2.03.02 KRAAB Теневые профили")
    are a strong structural signal for "same product family". This drops
    accessories/tools/different families that BGE-M3 mistakenly pulled
    in by keyword overlap.
    """
    if not hits:
        return hits
    top_cat = hits[0].get("category")
    if not top_cat:
        return hits
    filtered = [h for h in hits if h.get("category") == top_cat]
    return filtered if filtered else hits


def _filter_by_size(query_name: str, hits: list[dict]) -> list[dict]:
    q_tokens = _extract_size_tokens(query_name)
    if not q_tokens or not hits:
        return hits
    q_set = set(q_tokens)
    filtered: list[dict] = []
    for h in hits:
        name_tokens = set(_extract_size_tokens(h.get("name", "")))
        if q_set.issubset(name_tokens):
            filtered.append(h)
    # If hard filter wiped everything, fall back to original list
    return filtered if filtered else hits


def _search_products_tool(args: dict) -> dict:
    """Local tool: run vector search for one query or a list of items.

    For each item runs TWO searches — by `name` alone and by `name + " " + qty` —
    and keeps the variant whose top-1 distance is smaller. This helps when `qty`
    actually carries a size (e.g. '3.5*35') that the Triage misclassified as count.
    """
    k = int(args.get("k", 5))
    items = args.get("items")
    if isinstance(items, list) and items:
        out_items: list[dict] = []
        for it in items:
            if isinstance(it, dict):
                name = str(it.get("name", "")).strip()
                qty_raw = it.get("qty")
                qty = str(qty_raw).strip() if qty_raw else None
            elif isinstance(it, str):
                name = it.strip()
                qty = None
            else:
                continue
            if not name:
                continue

            # Knowledge-base alias: exact jargon → product_id lookup.
            # Returns a list: 1 item = direct match, N items = ambiguous
            # (e.g. "кольцо" → 63 rings), 0 = miss → fall back to BGE-M3.
            alias_hits = product_search.lookup_by_alias(name)
            if alias_hits:
                chosen_query = name
                # Apply same hard filters to narrow ambiguous KB hits
                chosen_hits = _filter_by_size(name, alias_hits)
                chosen_hits = _filter_by_color(name, chosen_hits)
            else:
                # По умолчанию ищем только по имени — количество (типа "10 м", "2 шт")
                # ложно совпадает с упаковкой в названии товара ("10 м/уп").
                chosen_query = name
                chosen_hits = product_search.search_products(name, k=k)

                # Исключение: если qty — это "голое" число без единиц ("320",
                # "50"), оно может быть на самом деле размером/шириной, который
                # Triage ошибочно засунул в qty. Тогда пробуем name+qty как
                # страховку — и берём только если результат заметно лучше.
                if qty and re.fullmatch(r"\d+([.,]\d+)?", qty.strip()):
                    hits_combined = product_search.search_products(f"{name} {qty}", k=k)
                    if _top1_dist(hits_combined) < _top1_dist(chosen_hits) - 0.03:
                        chosen_query = f"{name} {qty}"
                        chosen_hits = hits_combined

                # Hard filters: explicit numeric size, explicit color,
                # then collapse to top-1's product category.
                chosen_hits = _filter_by_size(name, chosen_hits)
                chosen_hits = _filter_by_color(name, chosen_hits)
                chosen_hits = _filter_by_top_category(chosen_hits)

            # Detect ambiguity: how many candidates sit within AMBIGUITY_GAP of top-1
            close_count = 0
            if chosen_hits:
                top_d = chosen_hits[0]["distance"]
                close_count = sum(
                    1 for h in chosen_hits if h["distance"] - top_d <= AMBIGUITY_GAP
                )
            ambiguous = close_count >= 2

            # If single candidate, try to compute total deterministically
            computed = None
            if len(chosen_hits) == 1:
                computed = _compute_total(qty, chosen_hits[0])

            out_items.append({
                "query_name": name,
                "qty": qty,
                "searched_as": chosen_query,
                "ambiguous": ambiguous,
                "close_count": close_count,
                "candidates": chosen_hits,
                "computed": computed,
            })
        return {"items": out_items}

    q = str(args.get("query", "")).strip()
    return {"results": product_search.search_products(q, k=int(args.get("k", 10)))}


def _search_knowledge_tool(args: dict) -> dict:
    """Local tool: top-k чанков базы знаний (профили, системы, правила).

    args: { query: str, k?: int=3 }
    returns: { chunks: [...] } — каждый чанк с title, content, images, products, escalate.
    """
    q = str(args.get("query", "")).strip()
    k = int(args.get("k", 3))
    chunks = knowledge_search.search_knowledge(q, k=k)
    return {"chunks": chunks}


LOCAL_TOOLS: dict = {
    "search_products": _search_products_tool,
    "search_knowledge": _search_knowledge_tool,
}


@dataclass
class ToolResult:
    tool_slug: str
    success: bool
    data: dict = field(default_factory=dict)
    error: str = ""
    latency_ms: int = 0


# ── Public API ───────────────────────────────────────────────────────


def determine_tools_to_call(scene_config: dict, extracted: dict) -> list[dict]:
    """Determine which scene tools should be called based on extracted data.

    Checks "when" conditions against available data.
    Returns list of tool configs to execute.
    """
    tools = scene_config.get("tools", [])
    result = []
    for tool_cfg in tools:
        when = tool_cfg.get("when", "")
        if _check_when_condition(when, extracted):
            result.append(tool_cfg)
    return result


def _check_when_condition(when: str, data: dict) -> bool:
    """Check if a tool's 'when' condition is satisfied by available data."""
    if not when:
        return True

    fields_in_condition = [key for key in data if key.lower() in when.lower()]

    if not fields_in_condition:
        return True

    return all(
        data.get(f) is not None and data.get(f) != ""
        for f in fields_in_condition
    )


def _resolve_args(args_template: dict, scene_data: dict) -> dict:
    """Resolve $-references in tool args using scene data."""
    resolved = {}
    for key, value in args_template.items():
        if isinstance(value, str) and value.startswith("$"):
            ref = value[1:]
            base_ref = ref.split("[")[0].split(".")[0]
            resolved[key] = scene_data.get(base_ref, value)
        else:
            resolved[key] = value
    return resolved


async def execute_tools(
    tools_to_call: list[dict],
    scene_data: dict,
    tool_configs: dict[str, dict] | None = None,
) -> list[ToolResult]:
    """Execute a list of tools, possibly in parallel."""
    tasks = []
    for tool_ref in tools_to_call:
        slug = tool_ref.get("tool", "")
        args_template = tool_ref.get("args", {})
        args = _resolve_args(args_template, scene_data)
        tasks.append(_execute_single(slug, args, tool_configs))

    return await asyncio.gather(*tasks)


async def _execute_single(
    slug: str,
    args: dict,
    tool_configs: dict[str, dict] | None = None,
) -> ToolResult:
    """Execute a single tool by slug."""
    start = time.monotonic()

    # Local in-process tool (e.g. vector search)
    if slug in LOCAL_TOOLS:
        try:
            data = await asyncio.to_thread(LOCAL_TOOLS[slug], args)
            return ToolResult(
                tool_slug=slug,
                success=True,
                data=data,
                latency_ms=int((time.monotonic() - start) * 1000),
            )
        except Exception as e:
            logger.exception(f"Local tool {slug} failed")
            return ToolResult(
                tool_slug=slug,
                success=False,
                error=str(e),
                latency_ms=int((time.monotonic() - start) * 1000),
            )

    # HTTP tool from config
    if tool_configs and slug in tool_configs:
        return await _execute_http_tool(slug, args, tool_configs[slug], start)

    return ToolResult(
        tool_slug=slug,
        success=False,
        error=f"Tool '{slug}' not found",
        latency_ms=int((time.monotonic() - start) * 1000),
    )


async def _execute_http_tool(
    slug: str, args: dict, config: dict, start: float,
) -> ToolResult:
    """Execute an HTTP-based tool from the tool registry."""
    req = config.get("request", {})
    method = req.get("method", "GET")
    url = req.get("url", "")
    headers = req.get("headers", {})
    timeout_ms = config.get("timeout_ms", 5000)

    url = _resolve_template(url, args)
    headers = {k: _resolve_template(v, args) for k, v in headers.items()}
    params = {k: _resolve_template(v, args) for k, v in req.get("params", {}).items()}

    try:
        async with httpx.AsyncClient(timeout=timeout_ms / 1000) as client:
            if method.upper() == "GET":
                resp = await client.get(url, headers=headers, params=params)
            else:
                body = req.get("body", {})
                body = {k: _resolve_template(v, args) for k, v in body.items()}
                resp = await client.request(method, url, headers=headers, json=body)

            resp.raise_for_status()
            data = resp.json()

            mapping = config.get("response_mapping", {})
            if mapping:
                data = _apply_mapping(data, mapping)

            return ToolResult(
                tool_slug=slug,
                success=True,
                data=data,
                latency_ms=int((time.monotonic() - start) * 1000),
            )

    except Exception as e:
        logger.error(f"HTTP tool {slug} failed: {e}")
        return ToolResult(
            tool_slug=slug,
            success=False,
            error=config.get("fallback_message", str(e)),
            latency_ms=int((time.monotonic() - start) * 1000),
        )


def _resolve_template(value: str, args: dict) -> str:
    """Replace ${args.xxx} placeholders in string."""
    if not isinstance(value, str):
        return value

    def replacer(match: re.Match) -> str:
        key = match.group(1)
        if key.startswith("args."):
            arg_name = key[5:]
            return str(args.get(arg_name, match.group(0)))
        if key.startswith("env."):
            import os
            env_name = key[4:]
            return os.environ.get(env_name, match.group(0))
        return match.group(0)

    return re.sub(r"\$\{(\w+\.\w+)\}", replacer, value)


def _apply_mapping(data: dict, mapping: dict) -> dict:
    """Simple JSONPath-like extraction from response data."""
    result = {}
    for out_key, path in mapping.items():
        if isinstance(path, str) and path.startswith("$."):
            parts = path[2:].split(".")
            val = data
            for p in parts:
                if isinstance(val, dict):
                    val = val.get(p)
                else:
                    val = None
                    break
            result[out_key] = val
        else:
            result[out_key] = path
    return result
