"""LangGraph graph builder.

Topology::

    START
      ↓
    interpret_prompt
      ↓
    discover ──► (no candidates) ──► END (status=FAILED, NO_CANDIDATES)
      ↓
    shortlist
      ↓
    pick_dish
      ↓
    compose_proposal
      ↓
    ⏸ propose_to_user                      [INTERRUPT 1]
      ↓ (user_decision branches)
      ├─ accept  → build_cart → review_cart → ⏸ confirm_order [INTERRUPT 2]
      │                                        ↓ (user_decision branches)
      │                                        ├─ confirm → place_order → END
      │                                        └─ cancel  → END (status=CANCELLED_BY_USER)
      ├─ swap    → (swap_count < max?) → discover (with previous proposal in excluded)
      │           └─ else → END (status=FAILED, SWAP_EXHAUSTED)
      └─ reject  → END (status=CANCELLED_BY_USER)
      └─ cancel  → END (status=CANCELLED_BY_USER)

`propose_to_user` and `confirm_order` are **passthrough nodes** that exist
only as hooks for `interrupt_before` to attach to. The actual user input
arrives via the API `/resume` endpoint, which writes `state.user_decision`
before the graph resumes execution past the interrupt.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph

from meal_agent.agent.nodes import (
    Deps,
    build_cart,
    compose_proposal,
    discover,
    interpret_prompt,
    pick_dish,
    place_order,
    review_cart,
    shortlist,
)
from meal_agent.agent.state import (
    AgentError,
    AgentState,
    AgentStatus,
    FailureReason,
    UserDecisionKind,
)
from meal_agent.settings import get_settings

# Node names — also the dict keys returned by graph state snapshots
N_INTERPRET = "interpret_prompt"
N_DISCOVER = "discover"
N_SHORTLIST = "shortlist"
N_PICK = "pick_dish"
N_COMPOSE = "compose_proposal"
N_PROPOSE = "propose_to_user"     # interrupt-only passthrough
N_BUILD = "build_cart"
N_REVIEW = "review_cart"
N_CONFIRM = "confirm_order"       # interrupt-only passthrough
N_PLACE = "place_order"


# ──────────────────────────────────────────────────────────────────────────────
# Passthrough nodes for interrupts
# ──────────────────────────────────────────────────────────────────────────────


async def _propose_passthrough(state: AgentState) -> dict[str, Any]:
    """Hook for `interrupt_before` — never runs body before interrupt.

    After resume, sets status back to RUNNING so downstream nodes can branch
    on user_decision without seeing the stale AWAITING_PROPOSAL flag.
    """
    return {"status": AgentStatus.RUNNING}


async def _confirm_passthrough(state: AgentState) -> dict[str, Any]:
    return {"status": AgentStatus.RUNNING}


# ──────────────────────────────────────────────────────────────────────────────
# Conditional edge routers
# ──────────────────────────────────────────────────────────────────────────────


def _after_discover(state: AgentState) -> Literal["shortlist", "__end_no_candidates__"]:
    """Short-circuit if discover found nothing."""
    if not state.candidates:
        return "__end_no_candidates__"
    return N_SHORTLIST


async def _no_candidates_terminal(state: AgentState) -> dict[str, Any]:
    return {
        "status": AgentStatus.FAILED,
        "error": AgentError(
            reason=FailureReason.NO_CANDIDATES,
            detail="discover returned no open restaurants for this address",
            occurred_at=datetime.now(UTC),
            node=N_DISCOVER,
        ),
    }


def _after_propose(
    state: AgentState,
) -> Literal["build_cart", "discover", "__end_swap_exhausted__", "__end_cancelled__"]:
    """Branch on the user's tap from the propose interrupt."""
    decision = state.user_decision
    if decision is None:
        # Should not happen — defensive
        return "__end_cancelled__"

    if decision.kind == UserDecisionKind.ACCEPT:
        return N_BUILD

    if decision.kind == UserDecisionKind.SWAP:
        max_swaps = get_settings().agent.max_swap_count
        if state.swap_count >= max_swaps:
            return "__end_swap_exhausted__"
        return N_DISCOVER

    # REJECT or CANCEL → cancelled
    return "__end_cancelled__"


async def _record_swap(state: AgentState) -> dict[str, Any]:
    """Inserted between propose and discover on the swap branch.

    Pushes the rejected proposal into excluded_proposals (so interpret_prompt
    can tell pick_dish to avoid it) and bumps the swap counter.
    """
    excluded = list(state.excluded_proposals)
    if state.proposal is not None:
        excluded.append(state.proposal)
    return {
        "excluded_proposals": excluded,
        "swap_count": state.swap_count + 1,
        "proposal": None,
        "candidates": [],
        "shortlisted": [],
        "dish_candidates": [],
        "user_decision": None,
    }


async def _swap_exhausted_terminal(state: AgentState) -> dict[str, Any]:
    return {
        "status": AgentStatus.FAILED,
        "error": AgentError(
            reason=FailureReason.SWAP_EXHAUSTED,
            detail=f"swap budget of {get_settings().agent.max_swap_count} exhausted",
            occurred_at=datetime.now(UTC),
            node=N_PROPOSE,
        ),
    }


async def _cancelled_terminal(state: AgentState) -> dict[str, Any]:
    return {"status": AgentStatus.CANCELLED_BY_USER}


def _after_confirm(state: AgentState) -> Literal["place_order", "__end_cancelled__"]:
    decision = state.user_decision
    if decision is None or decision.kind != UserDecisionKind.CONFIRM:
        return "__end_cancelled__"
    return N_PLACE


# ──────────────────────────────────────────────────────────────────────────────
# Builder
# ──────────────────────────────────────────────────────────────────────────────


def build_graph(*, deps: Deps, checkpointer: BaseCheckpointSaver):
    """Compile the agent graph with `deps` bound to every node call.

    LangGraph node functions take only `state`; we close over `deps` here so
    each node module can stay a clean `async def run(state, deps)` for unit
    testing.
    """

    g: StateGraph = StateGraph(AgentState)

    # ── core path nodes ──
    g.add_node(N_INTERPRET, _bind(interpret_prompt.run, deps))
    g.add_node(N_DISCOVER, _bind(discover.run, deps))
    g.add_node(N_SHORTLIST, _bind(shortlist.run, deps))
    g.add_node(N_PICK, _bind(pick_dish.run, deps))
    g.add_node(N_COMPOSE, _bind(compose_proposal.run, deps))
    g.add_node(N_PROPOSE, _propose_passthrough)
    g.add_node(N_BUILD, _bind(build_cart.run, deps))
    g.add_node(N_REVIEW, _bind(review_cart.run, deps))
    g.add_node(N_CONFIRM, _confirm_passthrough)
    g.add_node(N_PLACE, _bind(place_order.run, deps))

    # ── helper terminal/transition nodes ──
    g.add_node("__end_no_candidates__", _no_candidates_terminal)
    g.add_node("__end_swap_exhausted__", _swap_exhausted_terminal)
    g.add_node("__end_cancelled__", _cancelled_terminal)
    g.add_node("__record_swap__", _record_swap)

    # ── linear edges ──
    g.add_edge(START, N_INTERPRET)
    g.add_edge(N_INTERPRET, N_DISCOVER)
    g.add_conditional_edges(
        N_DISCOVER,
        _after_discover,
        {N_SHORTLIST: N_SHORTLIST, "__end_no_candidates__": "__end_no_candidates__"},
    )
    g.add_edge(N_SHORTLIST, N_PICK)
    g.add_edge(N_PICK, N_COMPOSE)
    g.add_edge(N_COMPOSE, N_PROPOSE)

    # propose → branch
    g.add_conditional_edges(
        N_PROPOSE,
        _after_propose,
        {
            N_BUILD: N_BUILD,
            N_DISCOVER: "__record_swap__",
            "__end_swap_exhausted__": "__end_swap_exhausted__",
            "__end_cancelled__": "__end_cancelled__",
        },
    )
    g.add_edge("__record_swap__", N_DISCOVER)

    # accept path
    g.add_edge(N_BUILD, N_REVIEW)
    g.add_edge(N_REVIEW, N_CONFIRM)
    g.add_conditional_edges(
        N_CONFIRM,
        _after_confirm,
        {N_PLACE: N_PLACE, "__end_cancelled__": "__end_cancelled__"},
    )
    g.add_edge(N_PLACE, END)

    # terminal → END
    g.add_edge("__end_no_candidates__", END)
    g.add_edge("__end_swap_exhausted__", END)
    g.add_edge("__end_cancelled__", END)

    return g.compile(
        checkpointer=checkpointer,
        interrupt_before=[N_PROPOSE, N_CONFIRM],
    )


def _bind(node_fn, deps: Deps):
    """Adapt a `(state, deps)` node into the LangGraph `(state)` shape."""

    async def _wrapped(state: AgentState) -> dict[str, Any]:
        return await node_fn(state, deps)

    _wrapped.__name__ = getattr(node_fn, "__name__", "node")
    return _wrapped


__all__ = ["build_graph"]
