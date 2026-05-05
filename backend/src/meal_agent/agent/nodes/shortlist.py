"""Node 3: `shortlist` — LLM ranks the discover output down to N restaurants.

Two-stage filter:

  1. **Deterministic prefilter** — drop everything below `min_rating`. This
     guarantees the LLM never sees obviously bad picks and reduces token cost.
  2. **LLM rerank** — router model returns ordered restaurant ids; we keep
     top `settings.agent.shortlist_top_n` (default 3).

Short-circuits if candidates already <= cap.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from meal_agent.agent.nodes import Deps
from meal_agent.agent.state import AgentState
from meal_agent.settings import get_settings

NODE_NAME = "shortlist"
MIN_RATING = 3.5


class _ShortlistPick(BaseModel):
    """LLM output schema for shortlist."""

    ordered_restaurant_ids: list[str] = Field(
        ..., description="Restaurant ids ordered best-first (subset of input)"
    )


async def run(state: AgentState, deps: Deps) -> dict[str, Any]:
    cap = get_settings().agent.shortlist_top_n

    prefiltered = [r for r in state.candidates if (r.rating or 0.0) >= MIN_RATING]
    if not prefiltered:
        # All sub-3.5 — keep top by score so the run continues, picker LLM
        # has to deal with mediocre options downstream
        prefiltered = state.candidates

    if len(prefiltered) <= cap:
        await deps.audit.write_event(
            run_id=deps.run_id,
            node=NODE_NAME,
            event="exit",
            payload={"count": len(prefiltered), "skipped_llm": True},
        )
        return {"shortlisted": prefiltered}

    user_msg = _render_user_prompt(state, prefiltered)
    chain = deps.llms.router.with_structured_output(_ShortlistPick)
    pick: _ShortlistPick = await chain.ainvoke(  # type: ignore[assignment]
        [
            {"role": "system", "content": _SYSTEM_PROMPT},
            {"role": "user", "content": user_msg},
        ]
    )

    by_id = {r.id: r for r in prefiltered}
    shortlisted = [by_id[i] for i in pick.ordered_restaurant_ids if i in by_id][:cap]
    if not shortlisted:
        # LLM returned ids we don't have — fall back to top-by-score
        shortlisted = prefiltered[:cap]

    await deps.audit.write_event(
        run_id=deps.run_id,
        node=NODE_NAME,
        event="exit",
        payload={"shortlisted_ids": [r.id for r in shortlisted]},
    )
    return {"shortlisted": shortlisted}


_SYSTEM_PROMPT = (
    "You rank restaurants for a meal-decision agent. Return restaurant ids "
    "ordered best-first based on the user's stated intent and the candidate "
    "metadata. Use only ids from the input. Prefer fit-to-intent over rating "
    "alone. Never invent ids."
)


def _render_user_prompt(state: AgentState, restaurants) -> str:
    parsed = state.parsed
    intent = parsed.intent_summary if parsed else "Pick a meal."
    bias = ", ".join(parsed.bias_toward) if parsed and parsed.bias_toward else "—"
    avoid = ", ".join(parsed.cuisine_avoid) if parsed and parsed.cuisine_avoid else "—"
    lines = [
        f"Intent: {intent}",
        f"Bias toward: {bias}",
        f"Avoid: {avoid}",
        "",
        "Candidates:",
    ]
    for r in restaurants:
        lines.append(
            f"- id={r.id} name={r.name!r} cuisines={r.cuisines} "
            f"rating={r.rating} eta={r.eta_min}min distance={r.distance_km}km"
        )
    return "\n".join(lines)


__all__ = ["NODE_NAME", "run"]
