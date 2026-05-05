"""Agent state schema.

Single Pydantic-based state object that flows through every LangGraph node.
Each node returns a partial update; LangGraph reduces them into the next state.

Naming is **deliberately generic** — no brand strings here.
"""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field

# ──────────────────────────────────────────────────────────────────────────────
# Enums
# ──────────────────────────────────────────────────────────────────────────────


class AgentStatus(StrEnum):
    RUNNING = "running"
    AWAITING_PROPOSAL = "awaiting_proposal"
    AWAITING_CONFIRM = "awaiting_confirm"
    PLACED = "placed"
    CANCELLED_BY_USER = "cancelled_by_user"
    FAILED = "failed"


class FailureReason(StrEnum):
    """One of these is set when status == FAILED."""

    SWAP_EXHAUSTED = "swap_exhausted"
    NO_CANDIDATES = "no_candidates"
    NOTHING_ORDERABLE = "nothing_orderable"
    MCP_ERROR = "mcp_error"
    ADDRESS_NOT_SERVICEABLE = "address_not_serviceable"
    INTERRUPT_TIMEOUT = "interrupt_timeout"
    PAYMENT_NOT_SUPPORTED = "payment_not_supported"


class UserDecisionKind(StrEnum):
    """What the user tapped on resume."""

    ACCEPT = "accept"          # Okay — proceed to cart
    SWAP = "swap"              # Show me something else
    REJECT = "reject"          # No, I don't want anything
    CONFIRM = "confirm"        # Final tap to place the order
    CANCEL = "cancel"          # Abort entire run


class MealSlot(StrEnum):
    BREAKFAST = "breakfast"
    LUNCH = "lunch"
    SNACK = "snack"
    DINNER = "dinner"


# ──────────────────────────────────────────────────────────────────────────────
# Inputs (frozen after run start)
# ──────────────────────────────────────────────────────────────────────────────


class FeedbackEntry(BaseModel):
    """A single past accept/reject signal — fed in by the caller from their DB."""

    dish: str
    cuisine: str | None = None
    ts: datetime
    note: str | None = None


class FailureMemory(BaseModel):
    """Recent failure reason + when, so the agent can avoid repeating it."""

    reason: FailureReason
    ts: datetime


class UserContext(BaseModel):
    """Standing facts about the user. Caller assembles this from their DB.

    Kept separate from `prompt` so the agent can synthesize an ask when the
    caller passes no explicit prompt (the scheduled-nudge case).
    """

    recent_accepts: list[FeedbackEntry] = []
    recent_rejects: list[FeedbackEntry] = []
    active_nudge: str | None = None             # e.g. "more protein", "less oily"
    meal_slot: MealSlot | None = None
    day_of_week: str | None = None              # "Thursday"
    local_time: datetime | None = None
    recent_failures: list[FailureMemory] = []


class Constraints(BaseModel):
    """Hard limits the agent must enforce deterministically (not LLM judgement)."""

    max_price_inr: int = 1000                   # Builders Club cap
    max_eta_min: int = 60
    vegetarian: bool = False
    jain: bool = False
    egg_ok: bool = True


class PersonaInput(BaseModel):
    """Persona injected per request. The agent code never references brand strings."""

    system_prompt: str                          # Full persona system prompt
    voice_pack_id: str                          # Loader resolves this to a VoicePack
    name: str                                   # Display name only — used by voice templates


class AgentRunInput(BaseModel):
    """Frozen input bundle. Stored on the state for the lifetime of the run."""

    user_id: str
    address_id: str
    address_label: str | None = None            # "Home — Bandra W"; for prompt readability
    prompt: str | None = None                   # OPTIONAL natural-language ask
    context: UserContext = Field(default_factory=UserContext)
    constraints: Constraints = Field(default_factory=Constraints)
    persona: PersonaInput


# ──────────────────────────────────────────────────────────────────────────────
# Working memory (filled by nodes)
# ──────────────────────────────────────────────────────────────────────────────


class ParsedCriteria(BaseModel):
    """`interpret_prompt` node output. The single source of truth for downstream nodes."""

    intent_summary: str                         # one-line distilled ask
    cuisine_lean: list[str] = []
    cuisine_avoid: list[str] = []
    dietary: list[str] = []                     # ["veg"] | ["non-veg"] | ["jain"] | etc.
    mood_tags: list[str] = []                   # ["light", "comfort", "protein-heavy"]
    max_price_inr: int                          # mirrors constraint, may be tightened by intent
    max_eta_min: int
    exclude_dishes: list[str] = []              # from recent rejects + previous proposal in swap
    bias_toward: list[str] = []                 # from active nudge
    confidence: float = Field(ge=0.0, le=1.0)


class Restaurant(BaseModel):
    """Slim restaurant record — only what we need across the graph."""

    id: str                                     # Swiggy restaurant id
    name: str
    cuisines: list[str] = []
    rating: float | None = None
    rating_count: int | None = None
    distance_km: float | None = None
    eta_min: int | None = None
    cost_for_two_inr: int | None = None
    availability_status: str | None = None      # OPEN / CLOSED / etc.


class AddonGroup(BaseModel):
    """One addon group from search_menu, with its choices.

    Used by build_cart to auto-pick the cheapest mandatory addon.
    """

    group_id: str
    name: str | None = None
    max_addons: int = 0                          # 0 / -1 = unlimited
    min_addons: int = 0                          # >0 = mandatory
    choices: list[dict[str, Any]] = []           # raw {id, name, price} dicts


class DishCandidate(BaseModel):
    """A specific dish-at-a-restaurant candidate — what `pick_dish` picks ONE of."""

    restaurant_id: str
    restaurant_name: str
    item_id: str                                # Swiggy menu item id
    name: str
    description: str | None = None
    price_inr: int
    veg: bool | None = None
    addons_required: bool = False               # if True, agent needs default addons
    addon_groups: list[AddonGroup] = []         # captured from search_menu, sent in build_cart


class Proposal(BaseModel):
    """The single suggestion shown to the user. Voice fields are server-rendered strings."""

    dish: DishCandidate
    reason_summary: str                         # raw LLM reason, used by voice templates
    voice_heading: str                          # e.g. "Aaj ke liye, this one."
    voice_reason: str                           # e.g. "Protein-heavy, hits the nudge."
    voice_cta_yes: str                          # e.g. "Okay, Bawarchi"
    voice_cta_swap: str                         # e.g. "Something else"


class CartLine(BaseModel):
    name: str
    qty: int
    price_inr: int


class CartSnapshot(BaseModel):
    """Result of `get_food_cart` — what we show on the confirm screen."""

    lines: list[CartLine]
    subtotal_inr: int
    delivery_fee_inr: int
    discount_inr: int
    total_inr: int
    payment_methods: list[str] = []
    address_label: str
    cart_hash: str                              # used as idempotency key for place_order


class OrderResult(BaseModel):
    order_id: str
    placed_at: datetime
    eta_min: int | None = None


class UserDecision(BaseModel):
    """What the user tapped on resume."""

    kind: UserDecisionKind
    note: str | None = None                     # optional free text (chat case)
    received_at: datetime


class AgentError(BaseModel):
    reason: FailureReason
    detail: str
    occurred_at: datetime
    node: str | None = None                     # which node raised it


# ──────────────────────────────────────────────────────────────────────────────
# The state itself
# ──────────────────────────────────────────────────────────────────────────────


def _merge_dict(left: dict | None, right: dict | None) -> dict:
    """Reducer for additive metadata dicts."""
    return {**(left or {}), **(right or {})}


class AgentState(BaseModel):
    """The single state object that flows through the graph.

    LangGraph reduces partial updates from each node into the next state.
    We rely on Pydantic's default merge (last-write-wins) for most fields,
    and use `Annotated` reducers only for the additive `metadata` blob.
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    # ── frozen inputs ─────────────────────────────────────────
    input: AgentRunInput
    thread_id: str

    # ── working memory ────────────────────────────────────────
    parsed: ParsedCriteria | None = None
    candidates: list[Restaurant] = []
    shortlisted: list[Restaurant] = []
    dish_candidates: list[DishCandidate] = []
    proposal: Proposal | None = None
    excluded_proposals: list[Proposal] = []     # for swap loop; first proposal goes here on swap
    cart: CartSnapshot | None = None
    order: OrderResult | None = None

    # ── control ───────────────────────────────────────────────
    status: AgentStatus = AgentStatus.RUNNING
    user_decision: UserDecision | None = None   # set by /resume, consumed by next node
    swap_count: int = 0
    error: AgentError | None = None

    # ── observability ─────────────────────────────────────────
    metadata: Annotated[dict[str, Any], _merge_dict] = Field(default_factory=dict)


# ──────────────────────────────────────────────────────────────────────────────
# Public re-exports
# ──────────────────────────────────────────────────────────────────────────────

__all__ = [
    "AgentError",
    "AgentRunInput",
    "AgentState",
    "AgentStatus",
    "CartLine",
    "CartSnapshot",
    "Constraints",
    "DishCandidate",
    "FailureMemory",
    "FailureReason",
    "FeedbackEntry",
    "MealSlot",
    "OrderResult",
    "ParsedCriteria",
    "PersonaInput",
    "Proposal",
    "Restaurant",
    "UserContext",
    "UserDecision",
    "UserDecisionKind",
]
