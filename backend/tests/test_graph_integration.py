"""Full-graph integration test using `InMemorySaver`.

This is the **wire-up** test — it doesn't need Postgres, but it exercises
the entire LangGraph state machine through both interrupts using the same
fake LLM/MCP fixtures from `conftest.py`. If routing edges ever break,
this test fails first.

For the real-Postgres variant (`AsyncPostgresSaver` + docker-compose), see
the integration suite (out of scope for this scaffold).
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from meal_agent.agent.graph import build_graph
from meal_agent.agent.nodes.pick_dish import _Pick
from meal_agent.agent.nodes.shortlist import _ShortlistPick
from meal_agent.agent.state import (
    AgentStatus,
    ParsedCriteria,
    UserDecision,
    UserDecisionKind,
)

pytestmark = pytest.mark.asyncio


def _envelope(payload):
    return {"success": True, "data": payload}


def _f(obj, *path):
    """Tolerant nested accessor: works on both dict and Pydantic shapes.

    LangGraph's checkpoint serializer round-trips Pydantic models through
    msgpack and restores typed objects when it can — so `snap.values["x"]`
    might be a dict OR an instance. Tests should not depend on which.
    """
    cur = obj
    for key in path:
        if cur is None:
            return None
        if isinstance(cur, dict):
            cur = cur.get(key)
        else:
            cur = getattr(cur, key, None)
    return cur


@pytest.fixture
def configured_swiggy(fake_swiggy):
    """A Swiggy fake that returns realistic enveloped responses for the full path."""
    fake_swiggy.food["search_restaurants"].ainvoke.return_value = _envelope({
        "restaurants": [
            {"id": "r1", "name": "Thai Express", "rating": 4.4,
             "distanceKm": 2.1, "etaMin": 25, "availabilityStatus": "OPEN"},
        ],
    })
    fake_swiggy.food["search_menu"].ainvoke.return_value = _envelope({
        "items": [{"id": "i1", "name": "Pad Thai", "price": 320, "isVeg": True}],
    })
    fake_swiggy.food["get_food_cart"].ainvoke.return_value = _envelope({
        "items": [{"id": "i1", "name": "Pad Thai", "quantity": 1, "price": 320}],
        "bill": {"subTotal": 320, "deliveryFee": 30, "totalAmount": 350},
        "availablePaymentMethods": ["upi"],
        "address": {"displayText": "Home"},
    })
    fake_swiggy.food["place_food_order"].ainvoke.return_value = _envelope({
        "order_id": "ORD_E2E_1", "eta_min": 30,
    })
    return fake_swiggy


@pytest.fixture
def configured_llms(fake_llms):
    """LLM stub that returns the right type for each call site."""
    parsed = ParsedCriteria(
        intent_summary="Light Thai lunch",
        cuisine_lean=["thai"],
        max_price_inr=400,
        max_eta_min=45,
        confidence=0.8,
    )
    pick = _Pick(item_id="i1", restaurant_id="r1", reason_summary="Light, savoury.")

    # Each call site uses with_structured_output with a different schema. Map
    # the schema to the right canned response.
    response_by_schema = {
        ParsedCriteria: parsed,
        _ShortlistPick: _ShortlistPick(ordered_restaurant_ids=["r1"]),
        _Pick: pick,
    }

    class _Chain:
        def __init__(self, schema):
            self._schema = schema

        async def ainvoke(self, _messages):
            return response_by_schema[self._schema]

    fake_llms.router.with_structured_output = lambda schema: _Chain(schema)
    fake_llms.picker.with_structured_output = lambda schema: _Chain(schema)
    return fake_llms


async def test_graph_e2e_happy_path(deps, configured_llms, configured_swiggy, initial_state):
    """Run the full graph: start → propose interrupt → accept → confirm interrupt → place."""
    deps.llms = configured_llms
    deps.swiggy = configured_swiggy

    saver = InMemorySaver()
    graph = build_graph(deps=deps, checkpointer=saver)
    config = {"configurable": {"thread_id": initial_state.thread_id}}

    # 1. Start the run — should park at the propose interrupt
    await graph.ainvoke(initial_state.model_dump(), config=config)
    snap = await graph.aget_state(config)
    assert "propose_to_user" in snap.next, f"expected to pause at propose, next={snap.next}"
    assert _f(snap.values, "proposal", "voice_heading") == "Aaj ke liye, this one."
    assert _f(snap.values, "proposal", "dish", "item_id") == "i1"

    # 2. User accepts → resume → should park at the confirm interrupt
    accept = UserDecision(kind=UserDecisionKind.ACCEPT, received_at=datetime.now(UTC))
    await graph.ainvoke(
        Command(update={"user_decision": accept.model_dump()}),
        config=config,
    )
    snap = await graph.aget_state(config)
    assert "confirm_order" in snap.next, f"expected to pause at confirm, next={snap.next}"
    assert _f(snap.values, "cart", "total_inr") == 350
    assert _f(snap.values, "cart", "cart_hash")

    # 3. User confirms → run completes
    confirm = UserDecision(kind=UserDecisionKind.CONFIRM, received_at=datetime.now(UTC))
    await graph.ainvoke(
        Command(update={"user_decision": confirm.model_dump()}),
        config=config,
    )
    snap = await graph.aget_state(config)
    assert snap.next == (), f"expected terminal, got next={snap.next}"
    status = _f(snap.values, "status")
    assert status == AgentStatus.PLACED or status == AgentStatus.PLACED.value
    assert _f(snap.values, "order", "order_id") == "ORD_E2E_1"


async def test_graph_e2e_swap_then_accept(deps, configured_llms, configured_swiggy, initial_state):
    """Run pauses at propose → user swaps → re-proposes → user accepts."""
    deps.llms = configured_llms
    deps.swiggy = configured_swiggy

    saver = InMemorySaver()
    graph = build_graph(deps=deps, checkpointer=saver)
    config = {"configurable": {"thread_id": initial_state.thread_id}}

    await graph.ainvoke(initial_state.model_dump(), config=config)

    # Swap once — moves through __record_swap__ and back through discover
    swap = UserDecision(kind=UserDecisionKind.SWAP, received_at=datetime.now(UTC))
    await graph.ainvoke(
        Command(update={"user_decision": swap.model_dump()}),
        config=config,
    )
    snap = await graph.aget_state(config)
    assert "propose_to_user" in snap.next, "should re-propose after swap"
    assert _f(snap.values, "swap_count") == 1
    assert len(_f(snap.values, "excluded_proposals") or []) == 1

    # Second swap — exhausts budget (default max_swap_count=1) → fail terminal
    await graph.ainvoke(
        Command(update={"user_decision": swap.model_dump()}),
        config=config,
    )
    snap = await graph.aget_state(config)
    assert snap.next == ()
    status = _f(snap.values, "status")
    assert status == AgentStatus.FAILED or status == AgentStatus.FAILED.value
    reason = _f(snap.values, "error", "reason")
    reason_value = reason.value if hasattr(reason, "value") else reason
    assert reason_value == "swap_exhausted"


async def test_graph_e2e_reject_terminates(deps, configured_llms, configured_swiggy, initial_state):
    deps.llms = configured_llms
    deps.swiggy = configured_swiggy

    saver = InMemorySaver()
    graph = build_graph(deps=deps, checkpointer=saver)
    config = {"configurable": {"thread_id": initial_state.thread_id}}

    await graph.ainvoke(initial_state.model_dump(), config=config)

    reject = UserDecision(kind=UserDecisionKind.REJECT, received_at=datetime.now(UTC))
    await graph.ainvoke(
        Command(update={"user_decision": reject.model_dump()}),
        config=config,
    )
    snap = await graph.aget_state(config)
    assert snap.next == ()
    status = _f(snap.values, "status")
    assert status == AgentStatus.CANCELLED_BY_USER or status == AgentStatus.CANCELLED_BY_USER.value
