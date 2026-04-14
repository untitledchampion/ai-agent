"""API синхронизации с 1С."""
from __future__ import annotations

import asyncio
import logging

from fastapi import APIRouter, HTTPException

from agent.core.sync_1c import run_sync

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/sync", tags=["sync"])


@router.post("/products")
async def sync_products():
    try:
        report = await asyncio.to_thread(run_sync)
        return report
    except Exception as e:
        logger.exception("sync failed")
        raise HTTPException(500, f"Sync failed: {e}")
