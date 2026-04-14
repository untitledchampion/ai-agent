"""Knowledge base (product aliases) API."""

from __future__ import annotations

import re
from typing import Optional

from pydantic import BaseModel
from fastapi import APIRouter, HTTPException
from sqlalchemy import text

from agent.models import async_session

router = APIRouter(prefix="/api/knowledge", tags=["knowledge"])


def _normalize(s: str) -> str:
    q = (s or "").lower().replace("ё", "е").strip()
    q = re.sub(r"\s*№\s*", " ", q)
    q = re.sub(r"\s+", " ", q).strip()
    return q


class AliasIn(BaseModel):
    alias: str
    product_name: str


class AliasOut(BaseModel):
    id: int
    alias: str
    product_name: str
    created_at: Optional[str] = None
    product_exists: bool = True


@router.get("/aliases")
async def list_aliases(q: str = "", limit: int = 500, offset: int = 0):
    """List aliases with optional search. Marks aliases whose target name no longer exists in products."""
    async with async_session() as session:
        where = ""
        params = {"limit": limit, "offset": offset}
        if q:
            where = "WHERE pa.alias LIKE :q OR pa.product_name LIKE :q"
            params["q"] = f"%{q.lower()}%"
        rows = await session.execute(text(f"""
            SELECT pa.id, pa.alias, pa.product_name, pa.created_at,
                   EXISTS(SELECT 1 FROM products p WHERE p.name = pa.product_name) AS product_exists
              FROM product_aliases pa
              {where}
          ORDER BY pa.id DESC
             LIMIT :limit OFFSET :offset
        """), params)
        items = [dict(r._mapping) for r in rows]
        total = (await session.execute(text(
            f"SELECT COUNT(*) FROM product_aliases pa {where}"
        ), params)).scalar()
        return {"items": items, "total": total}


@router.post("/aliases", status_code=201)
async def create_alias(body: AliasIn):
    alias = _normalize(body.alias)
    name = (body.product_name or "").strip()
    if not alias or not name:
        raise HTTPException(400, "alias and product_name required")
    async with async_session() as session:
        # Dedup
        existing = (await session.execute(text(
            "SELECT id FROM product_aliases WHERE alias=:a AND product_name=:n"
        ), {"a": alias, "n": name})).scalar()
        if existing:
            return {"id": existing, "alias": alias, "product_name": name, "created": False}
        await session.execute(text(
            "INSERT INTO product_aliases(alias, product_name) VALUES (:a, :n)"
        ), {"a": alias, "n": name})
        await session.commit()
        new_id = (await session.execute(text(
            "SELECT id FROM product_aliases WHERE alias=:a AND product_name=:n"
        ), {"a": alias, "n": name})).scalar()
        return {"id": new_id, "alias": alias, "product_name": name, "created": True}


@router.put("/aliases/{alias_id}")
async def update_alias(alias_id: int, body: AliasIn):
    alias = _normalize(body.alias)
    name = (body.product_name or "").strip()
    if not alias or not name:
        raise HTTPException(400, "alias and product_name required")
    async with async_session() as session:
        await session.execute(text(
            "UPDATE product_aliases SET alias=:a, product_name=:n WHERE id=:id"
        ), {"a": alias, "n": name, "id": alias_id})
        await session.commit()
        return {"id": alias_id, "alias": alias, "product_name": name}


@router.delete("/aliases/{alias_id}")
async def delete_alias(alias_id: int):
    async with async_session() as session:
        await session.execute(text("DELETE FROM product_aliases WHERE id=:id"), {"id": alias_id})
        await session.commit()
        return {"deleted": alias_id}


@router.get("/products/search")
async def search_products_for_select(q: str = "", limit: int = 20):
    """Autocomplete for product selector in UI."""
    q = (q or "").strip()
    if len(q) < 2:
        return {"items": []}
    async with async_session() as session:
        rows = await session.execute(text("""
            SELECT id, name, code, price_dealer
              FROM products
             WHERE name LIKE :q OR code LIKE :q
          ORDER BY name
             LIMIT :limit
        """), {"q": f"%{q}%", "limit": limit})
        return {"items": [dict(r._mapping) for r in rows]}
