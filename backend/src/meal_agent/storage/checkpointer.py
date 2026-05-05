"""LangGraph Postgres checkpointer factory.

The checkpointer is the durability boundary for the state machine. Every
state transition is persisted; a run can be paused at an interrupt and
resumed days later from a different process.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from psycopg_pool import AsyncConnectionPool

from meal_agent.settings import get_settings


@asynccontextmanager
async def checkpointer_pool() -> AsyncIterator[AsyncPostgresSaver]:
    """Yield an AsyncPostgresSaver backed by a pooled connection.

    Use as a single long-lived context across the FastAPI lifespan:

        async with checkpointer_pool() as saver:
            graph = build_graph(checkpointer=saver, ...)
            ...

    The first time it runs against an empty schema, call `await saver.setup()`
    to create the LangGraph tables. We do that in app startup explicitly.
    """
    s = get_settings().storage
    pool = AsyncConnectionPool(
        conninfo=s.dsn,
        min_size=s.pool_min,
        max_size=s.pool_max,
        kwargs={"autocommit": True, "prepare_threshold": 0},
    )
    try:
        await pool.open()
        saver = AsyncPostgresSaver(pool)
        yield saver
    finally:
        await pool.close()


__all__ = ["checkpointer_pool"]
