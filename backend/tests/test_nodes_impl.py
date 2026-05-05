"""Tests for the filled-in nodes (discover, shortlist, pick_dish,
compose_proposal, build_cart, review_cart) — covers the happy path and the
key failure classifications for each.

Each fake MCP response uses the **enveloped** `{success, data}` shape that
real Swiggy MCP returns, so the unwrap helper is exercised end-to-end.
"""

from __future__ import annotations

from typing import Any
from unittest.mock import AsyncMock

import pytest

from meal_agent.agent.nodes import (
    build_cart,
    compose_proposal,
    discover,
    pick_dish,
    place_order,
    review_cart,
    shortlist,
)
from meal_agent.agent.state import (
    AgentStatus,
    FailureReason,
    ParsedCriteria,
    Restaurant,
)

pytestmark = pytest.mark.asyncio


# Helpers ─────────────────────────────────────────────────────────────────────


def _envelope(payload: dict[str, Any], success: bool = True) -> dict[str, Any]:
    if not success:
        return {"success": False, "error": {"message": payload.get("message", "boom")}}
    return {"success": True, "data": payload}


def _state_with_parsed(initial_state, **overrides):
    parsed = ParsedCriteria(
        intent_summary="Light Asian lunch",
        cuisine_lean=["thai", "asian"],
        max_price_inr=400,
        max_eta_min=45,
        confidence=0.7,
        **overrides,
    )
    return initial_state.model_copy(update={"parsed": parsed})


# ── discover ────────────────────────────────────────────────────────────────


async def test_discover_happy_path(initial_state, deps) -> None:
    state = _state_with_parsed(initial_state)
    deps.swiggy.food["search_restaurants"].ainvoke.return_value = _envelope({
        "restaurants": [
            {"id": "r1", "name": "Thai Express", "rating": 4.4,
             "distanceKm": 2.1, "etaMin": 25, "availabilityStatus": "OPEN"},
            {"id": "r2", "name": "Asian Bowl", "rating": 4.0,
             "distanceKm": 5.0, "etaMin": 40, "availabilityStatus": "OPEN"},
            {"id": "r3", "name": "Closed Co", "rating": 4.8,
             "distanceKm": 1.0, "etaMin": 20, "availabilityStatus": "CLOSED"},
        ],
    })

    update = await discover.run(state, deps)

    assert "candidates" in update
    ids = [r.id for r in update["candidates"]]
    assert "r3" not in ids
    assert ids[0] == "r1"  # higher score wins


async def test_discover_no_candidates(initial_state, deps) -> None:
    state = _state_with_parsed(initial_state)
    deps.swiggy.food["search_restaurants"].ainvoke.return_value = _envelope({"restaurants": []})

    update = await discover.run(state, deps)
    assert update["status"] == AgentStatus.FAILED
    assert update["error"].reason == FailureReason.NO_CANDIDATES


async def test_discover_address_not_serviceable(initial_state, deps) -> None:
    state = _state_with_parsed(initial_state)
    deps.swiggy.food["search_restaurants"].ainvoke.return_value = {
        "success": False,
        "error": {"message": "ADDRESS_NOT_SERVICEABLE: address out of zone"},
    }
    update = await discover.run(state, deps)
    assert update["error"].reason == FailureReason.ADDRESS_NOT_SERVICEABLE


# ── shortlist ───────────────────────────────────────────────────────────────


async def test_shortlist_skips_llm_when_under_cap(initial_state, deps) -> None:
    state = _state_with_parsed(initial_state).model_copy(update={
        "candidates": [
            Restaurant(id="r1", name="A", rating=4.5),
            Restaurant(id="r2", name="B", rating=4.4),
        ],
    })
    update = await shortlist.run(state, deps)
    assert len(update["shortlisted"]) == 2


async def test_shortlist_uses_llm_to_rank(initial_state, deps) -> None:
    cands = [Restaurant(id=f"r{i}", name=f"R{i}", rating=4.5) for i in range(5)]
    state = _state_with_parsed(initial_state).model_copy(update={"candidates": cands})

    from meal_agent.agent.nodes.shortlist import _ShortlistPick
    deps.llms.router.next_response = _ShortlistPick(
        ordered_restaurant_ids=["r4", "r2", "r0"]
    )
    update = await shortlist.run(state, deps)
    assert [r.id for r in update["shortlisted"]] == ["r4", "r2", "r0"]


# ── pick_dish ───────────────────────────────────────────────────────────────


async def test_pick_dish_happy_path(initial_state, deps) -> None:
    cands = [Restaurant(id="r1", name="Thai Express", rating=4.5)]
    state = _state_with_parsed(initial_state).model_copy(update={
        "candidates": cands, "shortlisted": cands,
    })
    deps.swiggy.food["search_menu"].ainvoke.return_value = _envelope({
        "items": [
            {"id": "i1", "name": "Pad Thai", "price": 320, "isVeg": True},
            {"id": "i2", "name": "Green Curry", "price": 380, "isVeg": False},
        ],
    })
    from meal_agent.agent.nodes.pick_dish import _Pick
    deps.llms.picker.next_response = _Pick(
        item_id="i1", restaurant_id="r1", reason_summary="Light, savoury, hits the protein nudge.",
    )

    update = await pick_dish.run(state, deps)
    assert update["dish_candidates"][0].item_id == "i1"
    assert update["metadata"]["pick_reason_summary"].startswith("Light")


async def test_pick_dish_filters_price_and_excludes(initial_state, deps) -> None:
    cands = [Restaurant(id="r1", name="X", rating=4.5)]
    state = _state_with_parsed(initial_state, exclude_dishes=["biryani"]).model_copy(update={
        "candidates": cands, "shortlisted": cands,
    })
    deps.swiggy.food["search_menu"].ainvoke.return_value = _envelope({
        "items": [
            {"id": "i1", "name": "Veg Biryani", "price": 200},  # excluded
            {"id": "i2", "name": "Bowl", "price": 999},          # over price
        ],
    })
    update = await pick_dish.run(state, deps)
    assert update["status"] == AgentStatus.FAILED
    assert update["error"].reason == FailureReason.NOTHING_ORDERABLE


async def test_pick_dish_falls_back_when_llm_picks_unknown(initial_state, deps) -> None:
    cands = [Restaurant(id="r1", name="X", rating=4.5)]
    state = _state_with_parsed(initial_state).model_copy(update={
        "candidates": cands, "shortlisted": cands,
    })
    deps.swiggy.food["search_menu"].ainvoke.return_value = _envelope({
        "items": [{"id": "i1", "name": "Cheap", "price": 100},
                  {"id": "i2", "name": "Pricey", "price": 350}],
    })
    from meal_agent.agent.nodes.pick_dish import _Pick
    deps.llms.picker.next_response = _Pick(
        item_id="bogus", restaurant_id="bogus", reason_summary="x",
    )
    update = await pick_dish.run(state, deps)
    assert update["dish_candidates"][0].item_id == "i1"  # cheapest fallback


# ── compose_proposal ────────────────────────────────────────────────────────


async def test_compose_proposal_renders_voice(initial_state, deps, sample_dish) -> None:
    state = _state_with_parsed(initial_state).model_copy(update={
        "dish_candidates": [sample_dish],
        "metadata": {"pick_reason_summary": "Protein-heavy. Hits the nudge."},
    })
    update = await compose_proposal.run(state, deps)
    p = update["proposal"]
    assert p.voice_heading == "Aaj ke liye, this one."
    assert "Protein-heavy" in p.voice_reason
    assert update["status"] == AgentStatus.AWAITING_PROPOSAL


# ── build_cart ──────────────────────────────────────────────────────────────


async def test_build_cart_calls_update_with_correct_shape(
    initial_state, deps, sample_dish
) -> None:
    from meal_agent.agent.state import Proposal
    state = initial_state.model_copy(update={
        "proposal": Proposal(
            dish=sample_dish, reason_summary="r",
            voice_heading="h", voice_reason="r", voice_cta_yes="y", voice_cta_swap="s",
        ),
    })
    deps.swiggy.food["update_food_cart"].ainvoke.return_value = _envelope({"ok": True})

    update = await build_cart.run(state, deps)
    assert "status" not in update or update.get("status") != AgentStatus.FAILED

    args = deps.swiggy.food["update_food_cart"].ainvoke.await_args.args[0]
    assert args["restaurantId"] == sample_dish.restaurant_id
    assert args["addressId"] == initial_state.input.address_id
    assert args["cartItems"] == [{"menu_item_id": sample_dish.item_id, "quantity": 1}]


async def test_build_cart_classifies_mcp_error(initial_state, deps, sample_dish) -> None:
    from meal_agent.agent.state import Proposal
    state = initial_state.model_copy(update={
        "proposal": Proposal(
            dish=sample_dish, reason_summary="r",
            voice_heading="h", voice_reason="r", voice_cta_yes="y", voice_cta_swap="s",
        ),
    })
    deps.swiggy.food["update_food_cart"].ainvoke.side_effect = RuntimeError("kaboom")
    update = await build_cart.run(state, deps)
    assert update["status"] == AgentStatus.FAILED
    assert update["error"].reason == FailureReason.MCP_ERROR


# ── review_cart ─────────────────────────────────────────────────────────────


async def test_review_cart_happy_path(initial_state, deps) -> None:
    deps.swiggy.food["get_food_cart"].ainvoke.return_value = _envelope({
        "items": [
            {"id": "i1", "name": "Pad Thai", "quantity": 1, "price": 320},
        ],
        "bill": {"subTotal": 320, "deliveryFee": 30, "discount": 0, "totalAmount": 350},
        "availablePaymentMethods": ["upi"],
        "address": {"displayText": "Home"},
    })
    update = await review_cart.run(initial_state, deps)
    assert update["status"] == AgentStatus.AWAITING_CONFIRM
    assert update["cart"].total_inr == 350
    assert update["cart"].cart_hash  # populated


async def test_review_cart_total_over_cap(initial_state, deps) -> None:
    deps.swiggy.food["get_food_cart"].ainvoke.return_value = _envelope({
        "items": [{"id": "i1", "name": "Truffle Risotto", "quantity": 1, "price": 1500}],
        "bill": {"totalAmount": 1500},
    })
    update = await review_cart.run(initial_state, deps)
    assert update["status"] == AgentStatus.FAILED
    assert update["error"].reason == FailureReason.NOTHING_ORDERABLE


async def test_review_cart_empty(initial_state, deps) -> None:
    deps.swiggy.food["get_food_cart"].ainvoke.return_value = _envelope({"items": [], "bill": {}})
    update = await review_cart.run(initial_state, deps)
    assert update["status"] == AgentStatus.FAILED


async def test_review_cart_hash_is_stable(initial_state, deps) -> None:
    """Two calls with same response → same hash. One field changed → different hash."""
    payload = {
        "items": [{"id": "i1", "name": "Pad Thai", "quantity": 1, "price": 320}],
        "bill": {"totalAmount": 320},
    }
    deps.swiggy.food["get_food_cart"].ainvoke = AsyncMock(return_value=_envelope(payload))

    h1 = (await review_cart.run(initial_state, deps))["cart"].cart_hash
    h2 = (await review_cart.run(initial_state, deps))["cart"].cart_hash
    assert h1 == h2

    payload2 = {**payload, "items": [{**payload["items"][0], "quantity": 2, "price": 160}],
                "bill": {"totalAmount": 320}}
    deps.swiggy.food["get_food_cart"].ainvoke = AsyncMock(return_value=_envelope(payload2))
    h3 = (await review_cart.run(initial_state, deps))["cart"].cart_hash
    assert h3 != h1


# ── place_order with envelope ────────────────────────────────────────────────


async def test_place_order_with_real_envelope(initial_state, deps, monkeypatch) -> None:
    """place_order now unwraps envelopes too — verify against the real shape.

    The live-orders safety rail (settings.agent.live_orders_enabled) defaults
    to False; tests must explicitly enable it to exercise the MCP code path.
    """
    from meal_agent.agent.state import CartLine, CartSnapshot
    from meal_agent.settings import get_settings

    monkeypatch.setenv("AGENT_LIVE_ORDERS_ENABLED", "true")
    get_settings.cache_clear()

    state = initial_state.model_copy(update={
        "cart": CartSnapshot(
            lines=[CartLine(name="x", qty=1, price_inr=300)],
            subtotal_inr=300, delivery_fee_inr=30, discount_inr=0,
            total_inr=330, payment_methods=["upi"],
            address_label="Home", cart_hash="h_envelope_test",
        ),
    })
    deps.swiggy.food["place_food_order"].ainvoke.return_value = _envelope({
        "order_id": "ORD_REAL_42", "eta_min": 28,
    })

    update = await place_order.run(state, deps)
    assert update["status"] == AgentStatus.PLACED
    assert update["order"].order_id == "ORD_REAL_42"

    args = deps.swiggy.food["place_food_order"].ainvoke.await_args.args[0]
    assert args == {"addressId": initial_state.input.address_id}

    get_settings.cache_clear()


async def test_place_order_dry_run_by_default(initial_state, deps, monkeypatch) -> None:
    """Without AGENT_LIVE_ORDERS_ENABLED=true, place_order MUST NOT call MCP."""
    from meal_agent.agent.state import CartLine, CartSnapshot
    from meal_agent.settings import get_settings

    monkeypatch.delenv("AGENT_LIVE_ORDERS_ENABLED", raising=False)
    get_settings.cache_clear()

    state = initial_state.model_copy(update={
        "cart": CartSnapshot(
            lines=[CartLine(name="x", qty=1, price_inr=300)],
            subtotal_inr=300, delivery_fee_inr=30, discount_inr=0,
            total_inr=330, payment_methods=["upi"],
            address_label="Home", cart_hash="h_dryrun_test",
        ),
    })

    update = await place_order.run(state, deps)

    assert update["status"] == AgentStatus.PLACED
    assert update["order"].order_id.startswith("DRYRUN_"), update["order"].order_id
    deps.swiggy.food["place_food_order"].ainvoke.assert_not_awaited()

    get_settings.cache_clear()


async def test_review_cart_blocks_cod_only_carts(initial_state, deps) -> None:
    """If the only payment method is Cash, review_cart MUST refuse the cart."""
    from meal_agent.agent.state import FailureReason
    from meal_agent.settings import get_settings

    get_settings.cache_clear()

    deps.swiggy.food["get_food_cart"].ainvoke = AsyncMock(return_value=_envelope({
        "items": [{"name": "Paneer", "quantity": 1, "price": 200}],
        "bill": {"totalAmount": 200},
        "availablePaymentMethods": ["Cash"],
    }))

    update = await review_cart.run(initial_state, deps)

    assert update["status"] == AgentStatus.FAILED
    assert update["error"].reason == FailureReason.PAYMENT_NOT_SUPPORTED


async def test_review_cart_strips_cod_keeps_other(initial_state, deps) -> None:
    """If Cash + other methods are offered, Cash is stripped but cart proceeds."""
    from meal_agent.settings import get_settings

    get_settings.cache_clear()

    deps.swiggy.food["get_food_cart"].ainvoke = AsyncMock(return_value=_envelope({
        "items": [{"name": "Paneer", "quantity": 1, "price": 200}],
        "bill": {"totalAmount": 200},
        "availablePaymentMethods": ["Cash", "UPI", "Credit Card"],
    }))

    update = await review_cart.run(initial_state, deps)

    cart = update["cart"]
    assert "Cash" not in cart.payment_methods
    assert "UPI" in cart.payment_methods
    assert "Credit Card" in cart.payment_methods
