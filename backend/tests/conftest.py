"""Shared pytest fixtures.

Goals:
  * No external network — Azure OpenAI + Swiggy MCP are mocked.
  * Real Pydantic schemas exercised end-to-end.
  * Settings are populated with throwaway env vars before any module imports
    so `get_settings()` doesn't fail at import time.
"""

from __future__ import annotations

import os
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest

# ── Populate required env vars BEFORE meal_agent imports ─────────────────────
os.environ.setdefault("AZURE_OPENAI_ENDPOINT", "https://test.openai.azure.com")
os.environ.setdefault("AZURE_OPENAI_API_KEY", "test-key")
os.environ.setdefault("POSTGRES_DSN", "postgresql://test:test@localhost:5432/test")
# Tests use mocked Swiggy clients — no real money is at risk. Enable the
# live-orders code path so we cover the MCP `place_food_order` branch end to
# end. The default in real environments stays False (see settings.py).
os.environ.setdefault("AGENT_LIVE_ORDERS_ENABLED", "true")

from meal_agent.agent.nodes import Deps  # noqa: E402
from meal_agent.agent.state import (  # noqa: E402
    AgentRunInput,
    AgentState,
    Constraints,
    DishCandidate,
    PersonaInput,
    UserContext,
)
from meal_agent.persona import loader as persona_loader  # noqa: E402
from meal_agent.persona.schema import (  # noqa: E402
    ConfirmVoice,
    GiveUpVoice,
    PlacedVoice,
    ProposalVoice,
    PushVoice,
    VoicePack,
)
from meal_agent.tools.swiggy_mcp import SwiggyTools  # noqa: E402

# ── Voice pack ────────────────────────────────────────────────────────────────


@pytest.fixture
def fake_voice_pack() -> VoicePack:
    return VoicePack(
        id="test-v1",
        name="Test",
        locale="en-IN",
        proposal=ProposalVoice(
            heading="Aaj ke liye, this one.",
            reason_template="{{ reason_summary }}",
            cta_yes="Okay",
            cta_swap="Swap",
        ),
        confirm=ConfirmVoice(
            heading="Confirm.",
            cta_confirm="Confirm",
            cta_cancel="Cancel",
        ),
        placed=PlacedVoice(
            heading="Pakka.",
            subline_template="On the way · {{ eta_min }} min",
        ),
        give_up=GiveUpVoice(
            swap_exhausted="Skipped.",
            no_candidates="Nothing open.",
            nothing_orderable="Out of stock.",
            mcp_error="Try again later.",
            address_not_serviceable="Not deliverable here.",
            interrupt_timeout="Took too long.",
        ),
        push=PushVoice(
            proposal_title="Pick ready",
            proposal_body_template="{{ dish }}",
            placed_title="Pakka.",
            placed_body_template="{{ dish }}",
        ),
    )


@pytest.fixture(autouse=True)
def _patch_voice_loader(monkeypatch: pytest.MonkeyPatch, fake_voice_pack: VoicePack) -> None:
    """Make `load_pack(any_id)` return the fake pack — no YAML needed."""
    persona_loader.clear_cache()
    monkeypatch.setattr(persona_loader, "load_pack", lambda _id: fake_voice_pack)


# ── Inputs ────────────────────────────────────────────────────────────────────


@pytest.fixture
def persona_input() -> PersonaInput:
    return PersonaInput(
        system_prompt="You are a meal-decision assistant. Pick one dish.",
        voice_pack_id="test-v1",
        name="Test",
    )


@pytest.fixture
def run_input(persona_input: PersonaInput) -> AgentRunInput:
    return AgentRunInput(
        user_id="user_test",
        address_id="addr_test",
        address_label="Home",
        prompt="Quick lunch, light, under 400",
        context=UserContext(),
        constraints=Constraints(max_price_inr=400, max_eta_min=45),
        persona=persona_input,
    )


@pytest.fixture
def initial_state(run_input: AgentRunInput) -> AgentState:
    return AgentState(input=run_input, thread_id="th_test")


# ── LLM ───────────────────────────────────────────────────────────────────────


@pytest.fixture
def fake_llms() -> Any:
    """An LLM that returns whatever is set on `.next_response`.

    Tests can do::

        fake_llms.router.next_response = ParsedCriteria(...)
        await node.run(state, deps)
    """

    class _FakeChain:
        def __init__(self, parent: _FakeLLM) -> None:
            self._parent = parent

        async def ainvoke(self, _messages: list) -> Any:
            return self._parent.next_response

    class _FakeLLM:
        def __init__(self) -> None:
            self.next_response: Any = None

        def with_structured_output(self, _schema: Any) -> _FakeChain:
            return _FakeChain(self)

        async def ainvoke(self, _messages: list) -> Any:
            return self.next_response

    container = MagicMock()
    container.router = _FakeLLM()
    container.picker = _FakeLLM()
    return container


# ── Swiggy MCP ────────────────────────────────────────────────────────────────


@pytest.fixture
def fake_swiggy() -> SwiggyTools:
    """Stubbed Swiggy tools; per-tool responses can be set on `.tool.return_value`."""

    def _mk_tool(name: str, default: Any) -> MagicMock:
        t = MagicMock()
        t.name = name
        t.ainvoke = AsyncMock(return_value=default)
        return t

    food = {
        "search_restaurants": _mk_tool("search_restaurants", {"restaurants": []}),
        "search_menu": _mk_tool("search_menu", {"items": []}),
        "update_food_cart": _mk_tool("update_food_cart", {"ok": True}),
        "get_food_cart": _mk_tool("get_food_cart", {"lines": [], "total": 0}),
        "place_food_order": _mk_tool(
            "place_food_order",
            {"order_id": "ORD123", "eta_min": 30},
        ),
        "flush_food_cart": _mk_tool("flush_food_cart", {"ok": True}),
    }
    return SwiggyTools(food=food, dineout={})


# ── Audit writer ──────────────────────────────────────────────────────────────


@pytest.fixture
def fake_audit() -> Any:
    """In-memory audit writer — records calls; supports the idempotency lookup."""

    class _Audit:
        def __init__(self) -> None:
            self.events: list[dict[str, Any]] = []
            self.placed: dict[tuple[str, str], str] = {}

        async def write_event(self, **kwargs: Any) -> None:
            self.events.append(kwargs)

        async def get_placed_order(self, *, thread_id: str, cart_hash: str) -> str | None:
            return self.placed.get((thread_id, cart_hash))

        async def record_placed_order(
            self, *, thread_id: str, cart_hash: str, order_id: str
        ) -> None:
            key = (thread_id, cart_hash)
            if key in self.placed:
                import asyncpg
                raise asyncpg.UniqueViolationError("duplicate placement")
            self.placed[key] = order_id

        async def create_run(self, **_: Any) -> None:
            pass

        async def update_run_status(self, **_: Any) -> None:
            pass

    return _Audit()


# ── Deps container ────────────────────────────────────────────────────────────


@pytest.fixture
def deps(fake_llms, fake_swiggy, fake_audit, fake_voice_pack) -> Deps:
    return Deps(
        llms=fake_llms,
        swiggy=fake_swiggy,
        audit=fake_audit,
        voice=fake_voice_pack,
        run_id="run_test",
    )


# ── Misc ──────────────────────────────────────────────────────────────────────


@pytest.fixture
def now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
def sample_dish() -> DishCandidate:
    return DishCandidate(
        restaurant_id="r1",
        restaurant_name="Test Restaurant",
        item_id="i1",
        name="Grilled Chicken Bowl",
        description="Lean protein bowl",
        price_inr=349,
        veg=False,
    )
