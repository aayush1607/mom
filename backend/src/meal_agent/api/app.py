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

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from meal_agent.api import routes
from meal_agent.storage.audit import AuditWriter
from meal_agent.storage.checkpointer import checkpointer_pool
from meal_agent.tools.llm import build_llms

# Load backend/.env into process env *before* anything reads os.environ
# (pydantic-settings classes already read .env via SettingsConfigDict, but
# routes.py also reads SWIGGY_OAUTH_TOKEN directly to fall back when the
# caller doesn't ship a per-user OAuth token — see _resolve_user_token).
_ENV_FILE = Path(__file__).resolve().parents[3] / ".env"
if _ENV_FILE.exists():
    load_dotenv(_ENV_FILE, override=False)


# Browser-facing origins. Defaults cover local Next.js dev (`pnpm dev` on
# :3000). For prod, set CORS_ALLOW_ORIGINS to a comma-separated list, e.g.
# "https://mom.example.com,https://www.mom.example.com".
_DEFAULT_ORIGINS = [
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]
_origins_env = os.environ.get("CORS_ALLOW_ORIGINS", "").strip()
ALLOWED_ORIGINS = (
    [o.strip() for o in _origins_env.split(",") if o.strip()]
    if _origins_env
    else _DEFAULT_ORIGINS
)


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
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ALLOWED_ORIGINS,
        allow_credentials=False,  # we send no cookies; Authorization (later) will be in body
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["*"],
    )
    app.include_router(routes.router, prefix="/agent")
    return app


app = create_app()


__all__ = ["app", "create_app"]
