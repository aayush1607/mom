"""Node 5: `compose_proposal` — pure render of the user-facing Proposal.

No LLM calls here. Brand voice comes from `deps.voice` (loaded by id from
the persona pack). The reason text comes from the picker LLM via
`state.metadata['pick_reason_summary']` (set by `pick_dish`).

Voice templates are tiny `{{ var }}` placeholders. We don't need a full
templating engine — `_render()` does single-pass substitution.
"""

from __future__ import annotations

import re
from typing import Any

from meal_agent.agent.nodes import Deps
from meal_agent.agent.state import AgentState, AgentStatus, Proposal

NODE_NAME = "compose_proposal"

_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")


async def run(state: AgentState, deps: Deps) -> dict[str, Any]:
    if not state.dish_candidates:
        # Defensive — pick_dish should have either succeeded or failed the run
        return {"status": AgentStatus.FAILED}

    dish = state.dish_candidates[0]
    reason_summary = state.metadata.get("pick_reason_summary") or _fallback_reason(state, dish)
    voice = deps.voice.proposal

    ctx = {
        "reason_summary": reason_summary,
        "dish": dish.name,
        "restaurant": dish.restaurant_name,
        "price": str(dish.price_inr),
        "name": deps.voice.name,
    }

    proposal = Proposal(
        dish=dish,
        reason_summary=reason_summary,
        voice_heading=_render(voice.heading, ctx),
        voice_reason=_render(voice.reason_template, ctx),
        voice_cta_yes=_render(voice.cta_yes, ctx),
        voice_cta_swap=_render(voice.cta_swap, ctx),
    )

    await deps.audit.write_event(
        run_id=deps.run_id,
        node=NODE_NAME,
        event="exit",
        payload={"item_id": dish.item_id, "restaurant_id": dish.restaurant_id},
    )

    return {"proposal": proposal, "status": AgentStatus.AWAITING_PROPOSAL}


def _render(template: str, ctx: dict[str, str]) -> str:
    """Single-pass {{ var }} substitution. Unknown vars become empty strings."""
    return _PLACEHOLDER.sub(lambda m: ctx.get(m.group(1), ""), template)


def _fallback_reason(state: AgentState, dish) -> str:
    """If picker didn't set a reason (test/skipped), synthesise a minimal one."""
    parsed = state.parsed
    if parsed and parsed.bias_toward:
        return f"{', '.join(parsed.bias_toward)}. {dish.name} fits."
    return f"{dish.name} from {dish.restaurant_name}."


__all__ = ["NODE_NAME", "run"]
