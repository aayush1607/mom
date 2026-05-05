"""End-to-end test for `place_order` with idempotency guard.

The full graph e2e (with real LangGraph compile + checkpointer) requires a
live Postgres and exceeds the scope of an in-memory unit test. We test the
critical idempotency contract here directly.
"""

from __future__ import annotations

import pytest

from meal_agent.agent.nodes import place_order
from meal_agent.agent.state import AgentStatus, CartLine, CartSnapshot

pytestmark = pytest.mark.asyncio


def _state_with_cart(initial_state, cart_hash: str = "h_abc123"):
    """Helper: attach a cart snapshot to the initial state."""
    cart = CartSnapshot(
        lines=[CartLine(name="Bowl", qty=1, price_inr=349)],
        subtotal_inr=349,
        delivery_fee_inr=29,
        discount_inr=0,
        total_inr=378,
        payment_methods=["cod"],
        address_label="Home",
        cart_hash=cart_hash,
    )
    return initial_state.model_copy(update={"cart": cart})


async def test_place_order_happy_path(initial_state, deps) -> None:
    state = _state_with_cart(initial_state)
    update = await place_order.run(state, deps)

    assert update["status"] == AgentStatus.PLACED
    assert update["order"].order_id == "ORD123"
    assert update["order"].eta_min == 30
    # Idempotency record was written
    assert deps.audit.placed[("th_test", "h_abc123")] == "ORD123"


async def test_place_order_idempotent_replay(initial_state, deps) -> None:
    """Second run with same cart_hash must NOT call MCP again."""
    state = _state_with_cart(initial_state)

    # First call — places the order
    await place_order.run(state, deps)
    first_call_count = deps.swiggy.food["place_food_order"].ainvoke.await_count

    # Second call — should hit the idempotency cache
    update = await place_order.run(state, deps)
    second_call_count = deps.swiggy.food["place_food_order"].ainvoke.await_count

    assert second_call_count == first_call_count, "MCP must not be called twice"
    assert update["status"] == AgentStatus.PLACED
    assert update["order"].order_id == "ORD123"


async def test_place_order_fails_without_cart(initial_state, deps) -> None:
    """Defensive: graph misconfiguration shouldn't silently succeed."""
    update = await place_order.run(initial_state, deps)
    assert update["status"] == AgentStatus.FAILED
    assert update["error"].reason.value == "mcp_error"


async def test_place_order_classifies_mcp_error(initial_state, deps) -> None:
    state = _state_with_cart(initial_state)
    deps.swiggy.food["place_food_order"].ainvoke.side_effect = RuntimeError("boom")

    update = await place_order.run(state, deps)
    assert update["status"] == AgentStatus.FAILED
    assert update["error"].reason.value == "mcp_error"
    assert "boom" in update["error"].detail


async def test_place_order_handles_missing_order_id(initial_state, deps) -> None:
    state = _state_with_cart(initial_state)
    deps.swiggy.food["place_food_order"].ainvoke.return_value = {"unexpected": "shape"}

    update = await place_order.run(state, deps)
    assert update["status"] == AgentStatus.FAILED
    assert update["error"].reason.value == "mcp_error"
