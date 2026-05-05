"""Tests for the `interpret_prompt` node.

Covers the four canonical input shapes:
  1. Prompt only — caller passes free-text "I want light Thai tonight"
  2. Context only — scheduled nudge with no prompt; agent synthesises
  3. Both — prompt is dominant, context biases
  4. Swap loop — previous proposal must end up in `exclude_dishes`

Plus: hard-cap enforcement (max_price_inr / max_eta_min) — LLM cannot exceed
constraint values.
"""

from __future__ import annotations

import pytest

from meal_agent.agent.nodes import interpret_prompt
from meal_agent.agent.state import (
    AgentRunInput,
    Constraints,
    MealSlot,
    ParsedCriteria,
    PersonaInput,
    Proposal,
    UserContext,
)
from meal_agent.agent.templates import interpret as tmpl

# Async tests get the marker individually below. The pure-function template
# tests above must NOT be marked async, so we don't apply pytestmark module-wide.


# ── Pure-function template tests (no LLM) ────────────────────────────────────


def test_render_prompt_only(run_input: AgentRunInput) -> None:
    out = tmpl.render_interpret_user_prompt(run_input)
    assert "Quick lunch" in out
    assert "Home" in out


def test_render_includes_swap_context(run_input: AgentRunInput) -> None:
    out = tmpl.render_interpret_user_prompt(run_input, previous_proposal_dish="Veg Biryani")
    assert "Veg Biryani" in out


def test_render_with_no_prompt(persona_input: PersonaInput) -> None:
    inp = AgentRunInput(
        user_id="u",
        address_id="a",
        prompt=None,
        context=UserContext(meal_slot=MealSlot.LUNCH, day_of_week="Thursday"),
        constraints=Constraints(),
        persona=persona_input,
    )
    out = tmpl.render_interpret_user_prompt(inp)
    # The template should still produce *something* — synthesise from context
    assert out and len(out) > 20


# ── Node-level tests (with fake LLM) ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_node_returns_parsed_criteria(initial_state, deps) -> None:
    deps.llms.router.next_response = ParsedCriteria(
        intent_summary="Light lunch",
        cuisine_lean=["asian"],
        dietary=["non-veg"],
        max_price_inr=400,
        max_eta_min=45,
        confidence=0.8,
    )

    update = await interpret_prompt.run(initial_state, deps)

    assert "parsed" in update
    assert update["parsed"].intent_summary == "Light lunch"
    assert update["parsed"].cuisine_lean == ["asian"]


@pytest.mark.asyncio
async def test_node_enforces_price_cap(initial_state, deps) -> None:
    """LLM tries to set max_price=999, constraint says 400 — constraint wins."""
    deps.llms.router.next_response = ParsedCriteria(
        intent_summary="Anything",
        max_price_inr=999,  # tries to exceed
        max_eta_min=999,
        confidence=0.5,
    )

    update = await interpret_prompt.run(initial_state, deps)

    assert update["parsed"].max_price_inr == 400  # clamped to constraint
    assert update["parsed"].max_eta_min == 45


@pytest.mark.asyncio
async def test_node_writes_audit(initial_state, deps) -> None:
    deps.llms.router.next_response = ParsedCriteria(
        intent_summary="x", max_price_inr=100, max_eta_min=30, confidence=0.5
    )
    await interpret_prompt.run(initial_state, deps)
    nodes = [e["node"] for e in deps.audit.events]
    assert nodes.count("interpret_prompt") >= 2  # enter + exit


@pytest.mark.asyncio
async def test_swap_passes_previous_dish(initial_state, deps, sample_dish) -> None:
    """When excluded_proposals has entries, the rendered prompt must mention them."""
    state = initial_state.model_copy(
        update={
            "excluded_proposals": [
                Proposal(
                    dish=sample_dish,
                    reason_summary="prior",
                    voice_heading="h",
                    voice_reason="r",
                    voice_cta_yes="y",
                    voice_cta_swap="s",
                )
            ],
            "swap_count": 1,
        }
    )
    captured = {}

    async def capture_invoke(messages):
        captured["user_msg"] = messages[1]["content"]
        return ParsedCriteria(
            intent_summary="Swapping", max_price_inr=400, max_eta_min=45, confidence=0.6
        )

    deps.llms.router.with_structured_output = lambda _schema: type(
        "C", (), {"ainvoke": staticmethod(capture_invoke)}
    )()

    await interpret_prompt.run(state, deps)
    assert "Grilled Chicken Bowl" in captured["user_msg"]
