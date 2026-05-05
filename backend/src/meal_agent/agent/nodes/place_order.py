"""Node 8 (final): `place_order`.

Calls Swiggy MCP `place_food_order`. This tool is **non-idempotent** — a
naive retry will charge the user twice. We guard with a
`(thread_id, cart_hash)` lookup against `agent_placed_orders`.

**Real-money safety rail:** the actual MCP call is gated behind
`settings.agent.live_orders_enabled` (env: `AGENT_LIVE_ORDERS_ENABLED`).
Default is **False**, in which case we record a synthetic `DRYRUN_*`
order id, persist it the same way (so idempotency still works), and
never spend money. Tests, smoke runs, and dev environments must keep
this False; only flip to True in the production deployment that you're
willing to charge.

Sequence:
  1. Re-check our placement table — if already placed, return that order_id.
  2. If `live_orders_enabled`, call MCP. Else, generate a DRYRUN id.
  3. On success, atomically insert into `agent_placed_orders`. If a concurrent
     placement happened (UniqueViolationError), trust the prior placement.
  4. Update run status to PLACED.

Failures classified into AgentError with a FailureReason for the give-up path.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

import asyncpg

from meal_agent.agent.nodes import Deps
from meal_agent.agent.state import (
    AgentError,
    AgentState,
    AgentStatus,
    FailureReason,
    OrderResult,
)
from meal_agent.settings import get_settings

NODE_NAME = "place_order"


async def run(state: AgentState, deps: Deps) -> dict[str, Any]:
    """Place the order via Swiggy Food MCP, with idempotency guard."""
    if state.cart is None:
        return _fail(
            state,
            FailureReason.MCP_ERROR,
            "place_order called without a cart snapshot",
        )

    cart_hash = state.cart.cart_hash
    thread_id = state.thread_id

    await deps.audit.write_event(
        run_id=deps.run_id,
        node=NODE_NAME,
        event="enter",
        payload={"thread_id": thread_id, "cart_hash": cart_hash},
    )

    # ── 1. Idempotency check ──
    existing = await deps.audit.get_placed_order(thread_id=thread_id, cart_hash=cart_hash)
    if existing:
        await deps.audit.write_event(
            run_id=deps.run_id,
            node=NODE_NAME,
            event="idempotent_hit",
            payload={"order_id": existing},
        )
        order = OrderResult(order_id=existing, placed_at=datetime.now(UTC))
        return _success(deps, state, order)

    # ── 2. Call MCP (gated by safety rail) ──
    settings = get_settings()
    if not settings.agent.live_orders_enabled:
        # DRY RUN — never call Swiggy. Generate a deterministic-looking but
        # obviously-fake id so it shows up clearly in logs / dashboards.
        order_id = f"DRYRUN_{secrets.token_hex(8)}"
        eta_min: int | None = None
        await deps.audit.write_event(
            run_id=deps.run_id,
            node=NODE_NAME,
            event="dry_run",
            payload={
                "order_id": order_id,
                "cart_hash": cart_hash,
                "detail": (
                    "AGENT_LIVE_ORDERS_ENABLED is false; no real order placed. "
                    "Set the env flag to True in production to enable real placement."
                ),
            },
        )
    else:
        try:
            tool = deps.swiggy.food_tool("place_food_order")
            raw = await tool.ainvoke({"addressId": state.input.address_id})
        except Exception as e:
            await deps.audit.write_event(
                run_id=deps.run_id,
                node=NODE_NAME,
                event="error",
                payload={"detail": str(e)},
            )
            return _fail(state, FailureReason.MCP_ERROR, str(e))

        from meal_agent.tools.mcp_envelope import unwrap as _unwrap

        result, err = _unwrap(raw)
        if err:
            return _fail(state, FailureReason.MCP_ERROR, err)

        order_id = _extract_order_id(result)
        if not order_id:
            return _fail(
                state,
                FailureReason.MCP_ERROR,
                f"place_food_order returned no order id: {result!r}",
            )
        eta_min = _extract_eta(result)

    # ── 3. Record placement (race-safe) ──
    try:
        await deps.audit.record_placed_order(
            thread_id=thread_id, cart_hash=cart_hash, order_id=order_id
        )
    except asyncpg.UniqueViolationError:
        # A concurrent placement already recorded this. Trust it.
        prior = await deps.audit.get_placed_order(thread_id=thread_id, cart_hash=cart_hash)
        if prior and prior != order_id:
            await deps.audit.write_event(
                run_id=deps.run_id,
                node=NODE_NAME,
                event="concurrent_placement",
                payload={"new": order_id, "prior": prior},
            )
            order_id = prior

    order = OrderResult(
        order_id=order_id,
        placed_at=datetime.now(UTC),
        eta_min=eta_min,
    )
    return _success(deps, state, order)


# ── helpers ──────────────────────────────────────────────────────────────────


def _success(deps: Deps, state: AgentState, order: OrderResult) -> dict[str, Any]:
    """Mark run as PLACED and return state update."""
    # Fire-and-forget audit + run-status update via background task on the
    # caller side; here we just include them in the returned state for the
    # API layer to persist.
    return {
        "order": order,
        "status": AgentStatus.PLACED,
    }


def _fail(state: AgentState, reason: FailureReason, detail: str) -> dict[str, Any]:
    return {
        "status": AgentStatus.FAILED,
        "error": AgentError(
            reason=reason,
            detail=detail,
            occurred_at=datetime.now(UTC),
            node=NODE_NAME,
        ),
    }


def _extract_order_id(result: Any) -> str | None:
    """Pull the order id out of the MCP response. Tolerant of shape changes."""
    if isinstance(result, dict):
        for key in ("order_id", "orderId", "id"):
            if key in result and result[key]:
                return str(result[key])
        data = result.get("data") if "data" in result else None
        if isinstance(data, dict):
            return _extract_order_id(data)
    return None


def _extract_eta(result: Any) -> int | None:
    if isinstance(result, dict):
        for key in ("eta_min", "etaMin", "eta", "delivery_eta"):
            if key in result and result[key] is not None:
                try:
                    return int(result[key])
                except (TypeError, ValueError):
                    return None
        data = result.get("data") if "data" in result else None
        if isinstance(data, dict):
            return _extract_eta(data)
    return None


__all__ = ["NODE_NAME", "run"]
