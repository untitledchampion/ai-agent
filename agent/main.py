"""FastAPI application — entry point for the agent server."""

from __future__ import annotations

import logging

from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from agent.config import settings
from agent.models import init_db
from agent.api.chat import router as chat_router
from agent.api.scenes import router as scenes_router
from agent.api.tools import router as tools_router
from agent.api.tone import router as tone_router
from agent.api.knowledge import router as knowledge_router

logging.basicConfig(
    level=logging.DEBUG if settings.debug else logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup and shutdown events."""
    # Startup
    logger.info("Initializing database...")
    await init_db()

    # Warm up BGE-M3 so the first client request doesn't pay the ~20s load cost
    import asyncio as _asyncio
    from agent.core import product_search as _ps

    async def _warm():
        try:
            await _asyncio.to_thread(_ps.search_products, "прогрев", 1)
            logger.info("BGE-M3 warmed up")
        except Exception as e:
            logger.warning(f"BGE-M3 warmup failed: {e}")

    _asyncio.create_task(_warm())

    if not settings.anthropic_api_key:
        logger.warning(
            "⚠️  ANTHROPIC_API_KEY not set! Chat will not work. "
            "Set it in .env file."
        )

    logger.info(f"Agent server starting on {settings.host}:{settings.port}")
    yield
    # Shutdown
    logger.info("Agent server shutting down")


app = FastAPI(
    title="OptCeiling AI Agent",
    description="AI Sales Agent for OptCeiling — B2B ceiling materials",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS — allow frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# API routes
app.include_router(chat_router)
app.include_router(scenes_router)
app.include_router(tools_router)
app.include_router(tone_router)
app.include_router(knowledge_router)


@app.get("/api/health")
async def health():
    return {
        "status": "ok",
        "version": "0.1.0",
        "anthropic_key_set": bool(settings.anthropic_api_key),
    }


# Serve frontend static files (built React app)
# Static assets (JS, CSS, images) served directly, SPA routes fall back to index.html
import os
from fastapi.responses import FileResponse

frontend_dist = os.path.join(os.path.dirname(__file__), "..", "frontend", "dist")
if os.path.isdir(frontend_dist):
    app.mount("/assets", StaticFiles(directory=os.path.join(frontend_dist, "assets")), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        file_path = os.path.join(frontend_dist, full_path)
        if full_path and os.path.isfile(file_path):
            return FileResponse(file_path)
        return FileResponse(os.path.join(frontend_dist, "index.html"))
