"""FastAPI app + lifespan.

Owns the long-lived singletons:
  * Postgres pool for `agent_runs` / `agent_audit` (asyncpg)
  * Postgres pool for LangGraph checkpointer (psycopg3)
  * Azure OpenAI client wrappers (LLMs)
  * Voice-pack loader cache (lazy, in `persona.loader`)

Per-request resources are built fresh in `routes.py`:
  * Swiggy MCP client (per-user OAuth token; cannot be cached globally)
  * `Deps` container assembled from app state + the per-request MCP client
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from meal_agent.api import routes
from meal_agent.storage.audit import AuditWriter
from meal_agent.storage.checkpointer import checkpointer_pool
from meal_agent.tools.llm import build_llms


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Initialise singletons on startup; tear them down on shutdown."""
    # LLMs are pure clients — no connection to manage
    app.state.llms = build_llms()

    # Audit writer (asyncpg pool); also runs DDL
    app.state.audit = await AuditWriter.connect()

    # Checkpointer (psycopg pool, separate from the audit pool by design —
    # different drivers, different concurrency profiles)
    async with checkpointer_pool() as saver:
        await saver.setup()  # idempotent: creates langgraph_checkpoints if missing
        app.state.checkpointer = saver
        try:
            yield
        finally:
            await app.state.audit.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="meal-agent",
        version="0.1.0",
        description="Brand-agnostic meal-decision agent. Persona injected per request.",
        lifespan=lifespan,
    )
    app.include_router(routes.router, prefix="/agent")
    return app


app = create_app()


__all__ = ["app", "create_app"]
