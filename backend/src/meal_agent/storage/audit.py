"""Agent audit log.

Two tables:

  * `agent_runs` — one row per run; status, who, when, final outcome.
  * `agent_audit` — append-only log of every node entry/exit + tool call.

Used for:
  - Debugging "why did the agent pick that?"
  - Re-running a node with the same inputs in tests
  - Compliance / reproducibility (we replay LLM inputs, not outputs)
  - Idempotency checks (e.g. `place_order` looks up prior placements by
    `(thread_id, cart_hash)` to avoid double-charging).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

import asyncpg
from pydantic import BaseModel

from meal_agent.agent.state import AgentStatus, FailureReason
from meal_agent.settings import get_settings

# ──────────────────────────────────────────────────────────────────────────────
# DDL — bundled here for the scaffold; production should manage via Alembic
# ──────────────────────────────────────────────────────────────────────────────

DDL = """
CREATE TABLE IF NOT EXISTS agent_runs (
    run_id            TEXT PRIMARY KEY,
    user_id           TEXT NOT NULL,
    thread_id         TEXT NOT NULL,
    voice_pack_id     TEXT NOT NULL,
    prompt            TEXT,
    status            TEXT NOT NULL,
    failure_reason    TEXT,
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    final_order_id    TEXT
);

CREATE INDEX IF NOT EXISTS agent_runs_user_idx ON agent_runs (user_id, created_at DESC);
CREATE INDEX IF NOT EXISTS agent_runs_thread_idx ON agent_runs (thread_id);

CREATE TABLE IF NOT EXISTS agent_audit (
    id                BIGSERIAL PRIMARY KEY,
    run_id            TEXT NOT NULL REFERENCES agent_runs(run_id) ON DELETE CASCADE,
    node              TEXT NOT NULL,
    event             TEXT NOT NULL,        -- 'enter' | 'exit' | 'tool_call' | 'llm_call' | 'error'
    payload           JSONB NOT NULL,
    occurred_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS agent_audit_run_idx ON agent_audit (run_id, occurred_at);

-- Used by place_order idempotency guard
CREATE TABLE IF NOT EXISTS agent_placed_orders (
    thread_id         TEXT NOT NULL,
    cart_hash         TEXT NOT NULL,
    order_id          TEXT NOT NULL,
    placed_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (thread_id, cart_hash)
);
"""


# ──────────────────────────────────────────────────────────────────────────────
# Writer
# ──────────────────────────────────────────────────────────────────────────────


class AuditWriter:
    """Async writer for the audit + run + idempotency tables.

    Holds a pooled connection. One instance lives across the app lifespan;
    each handler call grabs a connection from the pool.
    """

    def __init__(self, pool: asyncpg.Pool) -> None:
        self._pool = pool

    @classmethod
    async def connect(cls) -> AuditWriter:
        s = get_settings().storage
        pool = await asyncpg.create_pool(
            dsn=s.dsn,
            min_size=s.pool_min,
            max_size=s.pool_max,
        )
        if pool is None:
            raise RuntimeError("Failed to create asyncpg pool")
        await cls.ensure_schema(pool)
        return cls(pool)

    @staticmethod
    async def ensure_schema(pool: asyncpg.Pool) -> None:
        async with pool.acquire() as conn:
            await conn.execute(DDL)

    async def close(self) -> None:
        await self._pool.close()

    # ── runs ────────────────────────────────────────────────────────────────

    async def create_run(
        self,
        *,
        run_id: str,
        user_id: str,
        thread_id: str,
        voice_pack_id: str,
        prompt: str | None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_runs (run_id, user_id, thread_id, voice_pack_id, prompt, status)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (run_id) DO NOTHING
                """,
                run_id, user_id, thread_id, voice_pack_id, prompt, AgentStatus.RUNNING.value,
            )

    async def update_run_status(
        self,
        *,
        run_id: str,
        status: AgentStatus,
        failure_reason: FailureReason | None = None,
        final_order_id: str | None = None,
    ) -> None:
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                UPDATE agent_runs
                   SET status = $2,
                       failure_reason = $3,
                       final_order_id = COALESCE($4, final_order_id),
                       updated_at = now()
                 WHERE run_id = $1
                """,
                run_id,
                status.value,
                failure_reason.value if failure_reason else None,
                final_order_id,
            )

    # ── audit log ───────────────────────────────────────────────────────────

    async def write_event(
        self,
        *,
        run_id: str,
        node: str,
        event: str,
        payload: dict[str, Any] | BaseModel,
    ) -> None:
        if isinstance(payload, BaseModel):
            payload = payload.model_dump(mode="json")
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_audit (run_id, node, event, payload)
                VALUES ($1, $2, $3, $4::jsonb)
                """,
                run_id, node, event, json.dumps(payload, default=str),
            )

    # ── idempotency guard for place_order ──────────────────────────────────

    async def get_placed_order(self, *, thread_id: str, cart_hash: str) -> str | None:
        """Return order_id if this (thread, cart_hash) has already been placed."""
        async with self._pool.acquire() as conn:
            row = await conn.fetchrow(
                """
                SELECT order_id FROM agent_placed_orders
                 WHERE thread_id = $1 AND cart_hash = $2
                """,
                thread_id, cart_hash,
            )
            return row["order_id"] if row else None

    async def record_placed_order(
        self, *, thread_id: str, cart_hash: str, order_id: str
    ) -> None:
        """Record a successful placement. Raises asyncpg.UniqueViolationError on duplicate."""
        async with self._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO agent_placed_orders (thread_id, cart_hash, order_id, placed_at)
                VALUES ($1, $2, $3, $4)
                """,
                thread_id, cart_hash, order_id, datetime.now(UTC),
            )


__all__ = ["DDL", "AuditWriter"]
