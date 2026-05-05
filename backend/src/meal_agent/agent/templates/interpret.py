"""Prompt templates for `interpret_prompt` node.

Pure functions: given the agent input, produce the system + user strings the
LLM will see. No network, no clock reads, no randomness — fully deterministic
so they can be snapshot-tested.

The interpret step is the **only** node that handles raw caller input; every
downstream node consumes `ParsedCriteria`, never `prompt`/`context` directly.
This keeps the agent generic — works the same whether the caller passed an
explicit prompt or just a context bundle.
"""

from __future__ import annotations

import json
from textwrap import dedent

from meal_agent.agent.state import AgentRunInput, FeedbackEntry

SYSTEM_PROMPT = dedent("""
    You are the meal-decision agent's intent parser. Your job is to read the
    caller's ask and standing user context, then produce a structured
    `ParsedCriteria` JSON object that captures *what to look for*.

    Rules:

    1. **Hard constraints win.** The structured `constraints` block (price,
       eta, dietary) must always be reflected in your output and never
       overridden by softer signals.

    2. **Explicit prompt > context.** If the caller passed an explicit
       natural-language prompt, treat it as the primary intent. The context is
       background bias.

    3. **No prompt? Synthesize from context.** If `prompt` is null, derive the
       intent from `meal_slot`, `day_of_week`, `active_nudge`, and recent
       feedback.

    4. **Avoid recently rejected dishes.** Pull recent rejects into
       `exclude_dishes`. Add `previous_proposal` if present (set on a swap).

    5. **Lean toward the active nudge.** If `active_nudge` is set, add it as
       a `bias_toward` entry. Don't make it a hard rule.

    6. **Confidence.** If the user's ask is vague ("something good"), drop
       confidence. If they're specific ("paneer wrap, Bandra, ₹250"), boost
       it. Downstream nodes use this to decide how aggressively to filter.

    Respond with **only** the structured object. No prose, no markdown.
""").strip()


def render_interpret_user_prompt(
    inp: AgentRunInput,
    previous_proposal_dish: str | None = None,
) -> str:
    """Build the user-side prompt for the interpret_prompt LLM call.

    Pure function — same input always produces the same output.
    """
    blocks: list[str] = []

    # ── Section 1: the ask ──
    if inp.prompt and inp.prompt.strip():
        blocks.append(f"## Caller's explicit ask\n{inp.prompt.strip()}")
    else:
        blocks.append("## Caller's explicit ask\n(none — synthesize from context below)")

    # ── Section 2: standing context ──
    ctx = inp.context
    ctx_lines = []
    if ctx.meal_slot:
        ctx_lines.append(f"- Meal slot: **{ctx.meal_slot.value}**")
    if ctx.day_of_week:
        ctx_lines.append(f"- Day: {ctx.day_of_week}")
    if ctx.local_time:
        ctx_lines.append(f"- Local time: {ctx.local_time.isoformat()}")
    if ctx.active_nudge:
        ctx_lines.append(f"- Active nudge (soft bias): **{ctx.active_nudge}**")
    if ctx.recent_accepts:
        ctx_lines.append(f"- Recent accepts: {_summarise(ctx.recent_accepts)}")
    if ctx.recent_rejects:
        ctx_lines.append(f"- Recent rejects (avoid): {_summarise(ctx.recent_rejects)}")
    if ctx.recent_failures:
        reasons = ", ".join(f.reason.value for f in ctx.recent_failures[-3:])
        ctx_lines.append(f"- Recent agent failures: {reasons}")

    blocks.append(
        "## Standing user context\n" + ("\n".join(ctx_lines) if ctx_lines else "(empty)")
    )

    # ── Section 3: hard constraints ──
    c = inp.constraints
    c_lines = [
        f"- max_price_inr: {c.max_price_inr}",
        f"- max_eta_min: {c.max_eta_min}",
        f"- vegetarian: {c.vegetarian}",
        f"- jain: {c.jain}",
        f"- egg_ok: {c.egg_ok}",
    ]
    blocks.append("## Hard constraints (never override)\n" + "\n".join(c_lines))

    # ── Section 4: swap context (if present) ──
    if previous_proposal_dish:
        blocks.append(
            "## Swap context\n"
            f"The user already saw and rejected: **{previous_proposal_dish}**.\n"
            "Add it to `exclude_dishes` and pivot — different cuisine or different mood."
        )

    # ── Section 5: address (so LLM knows the location matters) ──
    if inp.address_label:
        blocks.append(f"## Delivery address\n{inp.address_label}")

    blocks.append(
        "## Output\n"
        "Return a `ParsedCriteria` JSON matching the schema you've been bound to."
    )

    return "\n\n".join(blocks)


def _summarise(entries: list[FeedbackEntry], limit: int = 5) -> str:
    """Render a list of feedback entries as a compact string."""
    head = entries[-limit:]
    items = []
    for e in head:
        bit = e.dish
        if e.cuisine:
            bit = f"{e.dish} ({e.cuisine})"
        if e.note:
            bit = f"{bit} — {e.note}"
        items.append(bit)
    return ", ".join(items)


__all__ = ["SYSTEM_PROMPT", "render_interpret_user_prompt"]


# ── debug helper ─────────────────────────────────────────────────────────────


def debug_dump(inp: AgentRunInput, previous_proposal_dish: str | None = None) -> str:
    """For ad-hoc local debugging — print the full prompt the LLM would see."""
    return (
        f"=== SYSTEM ===\n{SYSTEM_PROMPT}\n\n"
        f"=== USER ===\n{render_interpret_user_prompt(inp, previous_proposal_dish)}\n\n"
        f"=== INPUT JSON ===\n{json.dumps(inp.model_dump(mode='json'), indent=2, default=str)}"
    )
