"""Node 4: `pick_dish` — fetch menus for shortlisted restaurants, LLM picks ONE.

Steps:

  1. For each shortlisted restaurant, call `search_menu` scoped to that
     restaurant id with the user's intent as the query.
  2. Aggregate all returned items into a flat list.
  3. Apply deterministic filters:
       - drop items above `parsed.max_price_inr`
       - drop items in `parsed.exclude_dishes` (case-insensitive substring)
       - if vegetarian/jain constraint, drop non-veg
  4. Picker LLM picks ONE `DishCandidate` + a one-line `reason_summary`.
  5. The remaining filtered candidates are kept as `state.dish_candidates`
     so a future swap loop can use them without another menu fetch.

Failure classification:
  * No filtered candidates → FailureReason.NOTHING_ORDERABLE
  * MCP exception          → FailureReason.MCP_ERROR
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from pydantic import BaseModel, Field

from meal_agent.agent.nodes import Deps
from meal_agent.agent.state import (
    AddonGroup,
    AgentError,
    AgentState,
    AgentStatus,
    DishCandidate,
    FailureReason,
)
from meal_agent.tools.mcp_envelope import unwrap

NODE_NAME = "pick_dish"


class _Pick(BaseModel):
    """Picker LLM output schema."""

    item_id: str = Field(..., description="The chosen item_id from the candidate list")
    restaurant_id: str = Field(..., description="The restaurant_id matching the item")
    reason_summary: str = Field(
        ...,
        description="One short sentence (<140 chars) for the user's voice card. No emojis.",
        max_length=140,
    )


async def run(state: AgentState, deps: Deps) -> dict[str, Any]:
    parsed = state.parsed
    if parsed is None or not state.shortlisted:
        return _fail(
            FailureReason.NOTHING_ORDERABLE,
            "pick_dish called without parsed + shortlisted",
        )

    # search_menu searches DISH NAMES (e.g. "paneer", "biryani"), NOT cuisines.
    # Prefer bias_toward (dish keywords from nudge), then a noun-y first word
    # of intent_summary; cuisine_lean is intentionally not used here.
    if parsed.bias_toward:
        query = parsed.bias_toward[0]
    elif parsed.cuisine_lean:
        # Use only the first cuisine token; some cuisines double as dish keywords
        query = parsed.cuisine_lean[0]
    else:
        query = parsed.intent_summary.split()[0] if parsed.intent_summary else "popular"
    address_id = state.input.address_id

    try:
        menus = await asyncio.gather(
            *[
                deps.swiggy.food_tool("search_menu").ainvoke(
                    {"addressId": address_id, "query": query, "restaurantIdOfAddedItem": r.id}
                )
                for r in state.shortlisted
            ],
            return_exceptions=True,
        )
    except Exception as e:
        return _fail(FailureReason.MCP_ERROR, f"search_menu failed: {e}")

    all_candidates: list[DishCandidate] = []
    for r, raw in zip(state.shortlisted, menus, strict=True):
        if isinstance(raw, Exception):
            await deps.audit.write_event(
                run_id=deps.run_id,
                node=NODE_NAME,
                event="error",
                payload={"restaurant_id": r.id, "detail": str(raw)},
            )
            continue
        data, err = unwrap(raw)
        if err:
            continue
        for item in _iter_items(data):
            cand = _to_candidate(item, r.id, r.name)
            if cand:
                all_candidates.append(cand)

    filtered = _apply_filters(all_candidates, parsed, state)
    if not filtered:
        return _fail(
            FailureReason.NOTHING_ORDERABLE,
            f"no items survived filters (raw={len(all_candidates)})",
        )

    user_msg = _render_user_prompt(state, filtered)
    chain = deps.llms.picker.with_structured_output(_Pick)
    pick: _Pick = await chain.ainvoke(  # type: ignore[assignment]
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
    )

    chosen, others = _split_chosen(filtered, pick)
    if chosen is None:
        # LLM returned an unknown id — fall back to cheapest
        chosen = min(filtered, key=lambda c: c.price_inr)
        others = [c for c in filtered if c is not chosen]

    await deps.audit.write_event(
        run_id=deps.run_id,
        node=NODE_NAME,
        event="exit",
        payload={
            "chosen_item_id": chosen.item_id,
            "candidate_count": len(filtered),
            "reason": pick.reason_summary,
        },
    )

    # We carry the reason via state.metadata so compose_proposal can read it.
    return {
        "dish_candidates": [chosen, *others],
        "metadata": {"pick_reason_summary": pick.reason_summary},
    }


# ── menu parsing helpers ─────────────────────────────────────────────────────


def _iter_items(data: dict):
    """Yield item dicts from various search_menu response shapes."""
    for key in ("items", "menu_items", "results", "menuItems"):
        seq = data.get(key)
        if isinstance(seq, list):
            yield from seq
            return
    # Some shapes nest under restaurants[].items
    for r in data.get("restaurants") or []:
        yield from (r.get("items") or [])


def _to_candidate(item: dict, restaurant_id: str, restaurant_name: str) -> DishCandidate | None:
    item_id = (
        item.get("id")
        or item.get("itemId")
        or item.get("item_id")
        or item.get("menu_item_id")
        or item.get("menuItemId")
    )
    name = item.get("name") or item.get("itemName")
    price = (
        item.get("price")
        or item.get("finalPrice")
        or item.get("defaultPrice")
        or item.get("price_inr")
    )
    if not (item_id and name and price is not None):
        return None
    try:
        price_inr = int(float(price))
    except (TypeError, ValueError):
        return None
    # Swiggy reports paise sometimes — normalise if obviously paise
    if price_inr > 50_000:
        price_inr = price_inr // 100

    veg_flag = item.get("isVeg") or item.get("veg") or item.get("vegClassifier")
    veg = bool(veg_flag) if veg_flag is not None else None

    addon_groups = _parse_addon_groups(item.get("addons") or [])
    has_variants = bool(item.get("variantsV2") or item.get("variations") or item.get("hasVariants"))
    addons_required = bool(
        item.get("addons_required")
        or item.get("hasAddons")
        or has_variants
        or any(g.min_addons > 0 for g in addon_groups)
    )

    return DishCandidate(
        restaurant_id=restaurant_id,
        restaurant_name=restaurant_name,
        item_id=str(item_id),
        name=str(name),
        description=item.get("description") or item.get("shortDescription"),
        price_inr=price_inr,
        veg=veg,
        addons_required=addons_required,
        addon_groups=addon_groups,
    )


def _parse_addon_groups(raw_groups: list) -> list[AddonGroup]:
    """Convert search_menu addon shape into AddonGroup list."""
    out: list[AddonGroup] = []
    for g in raw_groups:
        if not isinstance(g, dict):
            continue
        group_id = g.get("groupId") or g.get("group_id") or g.get("id")
        if not group_id:
            continue
        # Swiggy reports maxAddons=-1 for unlimited; minAddons absent or 0 for optional
        max_addons = int(g.get("maxAddons") or g.get("max_addons") or 0)
        min_addons = int(g.get("minAddons") or g.get("min_addons") or 0)
        choices_raw = g.get("choices") or g.get("addons") or []
        choices = [
            {
                "id": str(c.get("id") or c.get("choice_id") or c.get("choiceId") or ""),
                "name": str(c.get("name") or ""),
                "price": float(c.get("price") or 0),
            }
            for c in choices_raw
            if isinstance(c, dict) and (c.get("id") or c.get("choice_id") or c.get("choiceId"))
        ]
        if not choices:
            continue
        out.append(
            AddonGroup(
                group_id=str(group_id),
                name=g.get("groupName") or g.get("name"),
                max_addons=max_addons,
                min_addons=min_addons,
                choices=choices,
            )
        )
    return out


def _apply_filters(
    candidates: list[DishCandidate], parsed, state: AgentState
) -> list[DishCandidate]:
    excluded = {x.lower() for x in parsed.exclude_dishes}
    constraints = state.input.constraints

    out: list[DishCandidate] = []
    for c in candidates:
        if c.price_inr > parsed.max_price_inr:
            continue
        if any(ex in c.name.lower() for ex in excluded):
            continue
        if constraints.vegetarian and c.veg is False:
            continue
        if constraints.jain and c.veg is False:
            continue
        out.append(c)
    return out


def _split_chosen(
    candidates: list[DishCandidate], pick: _Pick
) -> tuple[DishCandidate | None, list[DishCandidate]]:
    chosen = next(
        (
            c
            for c in candidates
            if c.item_id == pick.item_id and c.restaurant_id == pick.restaurant_id
        ),
        None,
    )
    if chosen is None:
        return None, candidates
    others = [c for c in candidates if c is not chosen]
    return chosen, others


# ── prompt ───────────────────────────────────────────────────────────────────


_SYSTEM_PROMPT = (
    "You pick ONE dish for the user from the provided candidates. "
    "Respect the user's intent and constraints. The reason_summary is a "
    "single short sentence the user will see — no emojis, no brand names, "
    "no Hindi. Choose only from the listed item ids."
)


def _render_user_prompt(state: AgentState, candidates: list[DishCandidate]) -> str:
    p = state.parsed
    assert p is not None
    lines = [
        f"Intent: {p.intent_summary}",
        f"Mood: {', '.join(p.mood_tags) or '—'}",
        f"Bias toward: {', '.join(p.bias_toward) or '—'}",
        f"Cuisine lean: {', '.join(p.cuisine_lean) or '—'}",
        f"Max price ₹: {p.max_price_inr}",
        "",
        "Candidates:",
    ]
    for c in candidates[:30]:  # cap to keep prompt small
        lines.append(
            f"- item_id={c.item_id} restaurant_id={c.restaurant_id} "
            f"name={c.name!r} price=Rs{c.price_inr} veg={c.veg}"
            + (f" desc={c.description!r}" if c.description else "")
        )
    return "\n".join(lines)


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
