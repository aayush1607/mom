"""Node 6: `build_cart` — push the picked dish into the Swiggy Food cart.

  1. `flush_food_cart` first (defensive — the user may have stale items
     from another agent run or the Swiggy app itself).
  2. `update_food_cart` with `{restaurantId, cartItems:[{itemId, quantity:1}],
     addressId, restaurantName}`.
  3. If the item has `addons_required`, we currently log a warning and
     proceed without addons — addon handling is a known follow-up
     (full impl would inspect `valid_addons` from the response and pick
     the cheapest mandatory set).

Failure classification:
  * Any MCP exception or `success: false` → FailureReason.MCP_ERROR
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from meal_agent.agent.nodes import Deps
from meal_agent.agent.state import (
    AgentError,
    AgentState,
    AgentStatus,
    FailureReason,
)
from meal_agent.tools.mcp_envelope import unwrap

NODE_NAME = "build_cart"


async def run(state: AgentState, deps: Deps) -> dict[str, Any]:
    proposal = state.proposal
    if proposal is None:
        return _fail(FailureReason.MCP_ERROR, "build_cart called without a proposal")

    dish = proposal.dish
    address_id = state.input.address_id

    await deps.audit.write_event(
        run_id=deps.run_id,
        node=NODE_NAME,
        event="enter",
        payload={"item_id": dish.item_id, "restaurant_id": dish.restaurant_id},
    )

    # 1. Flush — best-effort; ignore errors (cart may already be empty)
    try:
        await deps.swiggy.food_tool("flush_food_cart").ainvoke({})
    except Exception as e:
        await deps.audit.write_event(
            run_id=deps.run_id,
            node=NODE_NAME,
            event="flush_warning",
            payload={"detail": str(e)},
        )

    # 2. Update cart — Swiggy schema uses snake_case `menu_item_id`, NOT `itemId`.
    # If the dish has addon groups, send the cheapest choice from each as a
    # safe default so mandatory groups (e.g. "Choice of Breads") don't reject
    # the cart silently. We rely on `min_addons` / `max_addons` heuristics from
    # search_menu rather than the (TODO) two-pass valid_addons handshake.
    cart_item: dict[str, Any] = {"menu_item_id": dish.item_id, "quantity": 1}

    if dish.addon_groups:
        chosen_addons: list[dict[str, Any]] = []
        for g in dish.addon_groups:
            if not g.choices:
                continue
            cheapest = min(g.choices, key=lambda c: c.get("price", 0))
            choice_id = cheapest.get("id")
            if not choice_id:
                continue
            chosen_addons.append(
                {
                    "group_id": g.group_id,
                    "choice_id": choice_id,
                    "name": cheapest.get("name"),
                    "price": cheapest.get("price"),
                }
            )
        if chosen_addons:
            cart_item["addons"] = chosen_addons
            await deps.audit.write_event(
                run_id=deps.run_id,
                node=NODE_NAME,
                event="addons_picked",
                payload={
                    "item_id": dish.item_id,
                    "addons": [
                        {"group_id": a["group_id"], "choice_id": a["choice_id"]}
                        for a in chosen_addons
                    ],
                },
            )
    elif dish.addons_required:
        await deps.audit.write_event(
            run_id=deps.run_id,
            node=NODE_NAME,
            event="addons_warning",
            payload={
                "item_id": dish.item_id,
                "detail": "addons required but no addon_groups captured",
            },
        )

    args: dict[str, Any] = {
        "restaurantId": dish.restaurant_id,
        "addressId": address_id,
        "cartItems": [cart_item],
        "restaurantName": dish.restaurant_name,
    }

    try:
        raw = await deps.swiggy.food_tool("update_food_cart").ainvoke(args)
    except Exception as e:
        return _fail(FailureReason.MCP_ERROR, f"update_food_cart raised: {e}")

    _, err = unwrap(raw)
    if err:
        return _fail(FailureReason.MCP_ERROR, f"update_food_cart failed: {err}")

    await deps.audit.write_event(
        run_id=deps.run_id, node=NODE_NAME, event="exit", payload={"ok": True}
    )
    return {}


def _fail(reason: FailureReason, detail: str) -> dict[str, Any]:
    return {
        "status": AgentStatus.FAILED,
        "error": AgentError(
            reason=reason,
            detail=detail,
            occurred_at=datetime.now(UTC),
            node=NODE_NAME,
        ),
    }


__all__ = ["NODE_NAME", "run"]
