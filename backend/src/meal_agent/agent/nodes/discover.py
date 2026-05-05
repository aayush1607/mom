"""Node 2: `discover` — search Swiggy for restaurants at the user's address.

Calls `search_restaurants` with the parsed query, filters to OPEN status,
applies a deterministic blend of rating/distance/eta as the sort key, and
returns the top N as `Restaurant` objects.

Failure classification:
  * Empty result               → FailureReason.NO_CANDIDATES
  * "ADDRESS_NOT_SERVICEABLE"  → FailureReason.ADDRESS_NOT_SERVICEABLE
  * Any MCP exception          → FailureReason.MCP_ERROR
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
    Restaurant,
)
from meal_agent.settings import get_settings
from meal_agent.tools.mcp_envelope import unwrap

NODE_NAME = "discover"


async def run(state: AgentState, deps: Deps) -> dict[str, Any]:
    parsed = state.parsed
    if parsed is None:
        return _fail(FailureReason.MCP_ERROR, "discover called before interpret_prompt")

    query = _build_query(parsed)
    args = {"addressId": state.input.address_id, "query": query}
    await deps.audit.write_event(
        run_id=deps.run_id, node=NODE_NAME, event="enter", payload=args
    )

    try:
        raw = await deps.swiggy.food_tool("search_restaurants").ainvoke(args)
    except Exception as e:
        return _fail(FailureReason.MCP_ERROR, str(e))

    data, err = unwrap(raw)
    if err:
        reason = (
            FailureReason.ADDRESS_NOT_SERVICEABLE
            if "ADDRESS_NOT_SERVICEABLE" in err.upper()
            else FailureReason.MCP_ERROR
        )
        return _fail(reason, err)

    restaurants_raw = data.get("restaurants") or data.get("results") or []
    open_restaurants = [r for r in restaurants_raw if _is_open(r)]
    if not open_restaurants:
        return _fail(
            FailureReason.NO_CANDIDATES,
            f"no OPEN restaurants for query={query!r}",
        )

    # Deterministic blended score; LLM gets to re-rank in shortlist
    open_restaurants.sort(key=_score, reverse=True)
    top_n = get_settings().agent.discover_top_n
    candidates = [_to_restaurant(r) for r in open_restaurants[:top_n]]

    await deps.audit.write_event(
        run_id=deps.run_id,
        node=NODE_NAME,
        event="exit",
        payload={"count": len(candidates), "query": query},
    )
    return {"candidates": candidates}


# ── helpers ──────────────────────────────────────────────────────────────────


def _build_query(parsed) -> str:
    """Build the search query from parsed criteria; broad terms get better recall."""
    if parsed.cuisine_lean:
        return ", ".join(parsed.cuisine_lean[:3])
    if parsed.bias_toward:
        return ", ".join(parsed.bias_toward[:3])
    return parsed.intent_summary[:80]


def _is_open(r: dict) -> bool:
    status = (r.get("availabilityStatus") or r.get("availability_status") or "").upper()
    return status == "OPEN" or status == ""  # absent → assume open (conservative)


def _score(r: dict) -> float:
    """rating·10 - distanceKm - eta_penalty. Tunable; intentionally simple."""
    rating = float(r.get("rating") or r.get("avgRating") or 0.0)
    distance = float(r.get("distanceKm") or r.get("distance_km") or 0.0)
    eta = float(
        r.get("etaMin")
        or r.get("eta_min")
        or r.get("deliveryTimeMinutes")
        or r.get("sla", {}).get("deliveryTime")
        or 30
    )
    return rating * 10.0 - distance - (eta / 10.0)


def _to_restaurant(r: dict) -> Restaurant:
    return Restaurant(
        id=str(r.get("id") or r.get("restaurantId") or r.get("rest_id") or ""),
        name=str(r.get("name") or r.get("restaurantName") or "Unknown"),
        cuisines=list(r.get("cuisines") or r.get("cuisine") or []),
        rating=_maybe_float(r.get("rating") or r.get("avgRating")),
        rating_count=_maybe_int(r.get("ratingCount") or r.get("totalRatings")),
        distance_km=_maybe_float(r.get("distanceKm") or r.get("distance_km")),
        eta_min=_maybe_int(
            r.get("etaMin")
            or r.get("eta_min")
            or r.get("deliveryTimeMinutes")
            or r.get("sla", {}).get("deliveryTime")
        ),
        cost_for_two_inr=_maybe_int(r.get("costForTwo") or r.get("costForTwoInr")),
        availability_status=r.get("availabilityStatus") or r.get("availability_status"),
    )


def _maybe_int(v) -> int | None:
    try:
        return int(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _maybe_float(v) -> float | None:
    try:
        return float(v) if v is not None else None
    except (TypeError, ValueError):
        return None


def _fail(reason: FailureReason, detail: str) -> dict[str, Any]:
    return {
        "status": AgentStatus.FAILED,
        "candidates": [],
        "error": AgentError(
            reason=reason,
            detail=detail,
            occurred_at=datetime.now(UTC),
            node=NODE_NAME,
        ),
    }


__all__ = ["NODE_NAME", "run"]
