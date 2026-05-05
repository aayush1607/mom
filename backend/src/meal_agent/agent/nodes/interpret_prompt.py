"""Node 1: `interpret_prompt`.

Turns the caller's `(prompt?, context, constraints)` into a structured
`ParsedCriteria`. This is the only node that reads raw user text. Every
downstream node consumes `ParsedCriteria` only.

The same node handles three input shapes uniformly:
  * scheduled nudge (no prompt) — synthesizes from context
  * chat query (prompt only) — honours explicit ask
  * both — explicit prompt wins on intent, context biases constraints
"""

from __future__ import annotations

from typing import Any

from meal_agent.agent.nodes import Deps
from meal_agent.agent.state import AgentState, ParsedCriteria
from meal_agent.agent.templates.interpret import (
    SYSTEM_PROMPT,
    render_interpret_user_prompt,
)

NODE_NAME = "interpret_prompt"


async def run(state: AgentState, deps: Deps) -> dict[str, Any]:
    """Parse caller intent into ParsedCriteria using the cheap router model."""
    await deps.audit.write_event(
        run_id=deps.run_id,
        node=NODE_NAME,
        event="enter",
        payload={
            "has_prompt": bool(state.input.prompt),
            "swap_count": state.swap_count,
        },
    )

    # Build the user prompt — pure function, snapshot-testable
    prev_dish = state.excluded_proposals[-1].dish.name if state.excluded_proposals else None
    user_prompt = render_interpret_user_prompt(state.input, previous_proposal_dish=prev_dish)

    # Bind the router LLM to the ParsedCriteria schema for typed output
    structured_llm = deps.llms.router.with_structured_output(ParsedCriteria)

    parsed: ParsedCriteria = await structured_llm.ainvoke(  # type: ignore[assignment]
        [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]
    )

    # Enforce hard caps from constraints regardless of LLM output
    parsed = parsed.model_copy(
        update={
            "max_price_inr": min(parsed.max_price_inr, state.input.constraints.max_price_inr),
            "max_eta_min": min(parsed.max_eta_min, state.input.constraints.max_eta_min),
        }
    )

    await deps.audit.write_event(
        run_id=deps.run_id,
        node=NODE_NAME,
        event="exit",
        payload=parsed,
    )

    return {"parsed": parsed}


__all__ = ["NODE_NAME", "run"]
