"""Voice-pack schema.

A voice pack is a YAML file containing all user-facing strings for one brand.
Each section maps to a place in the agent flow. Templates use Jinja-style
`{{ variable }}` placeholders rendered server-side at emit time.

Adding a new brand = drop a new YAML in `persona/packs/<id>.yaml`.
The agent code never imports brand strings.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ProposalVoice(BaseModel):
    """Strings used when the agent emits a proposal to the user."""

    heading: str                                # "Aaj ke liye, this one."
    reason_template: str                        # "{{ reason_summary }}"
    cta_yes: str                                # "Okay, mom"
    cta_swap: str                               # "Something else"


class ConfirmVoice(BaseModel):
    """Strings on the confirm-cart screen."""

    heading: str                                # "Confirm before I place it"
    cta_confirm: str                            # "Confirm — place order"
    cta_cancel: str                             # "Not now"


class PlacedVoice(BaseModel):
    """Strings shown after the order is placed."""

    heading: str                                # "Pakka."
    subline_template: str                       # "On the way · {{ eta_min }} min"


class GiveUpVoice(BaseModel):
    """One string per FailureReason. Frontend looks up by status/reason."""

    swap_exhausted: str
    no_candidates: str
    nothing_orderable: str
    mcp_error: str
    address_not_serviceable: str
    interrupt_timeout: str


class PushVoice(BaseModel):
    """Strings used in the Web Push payload."""

    proposal_title: str                         # "mom's calling 📞"
    proposal_body_template: str                 # "I have a pick for tonight. {{ dish }}."
    placed_title: str                           # "Pakka."
    placed_body_template: str                   # "{{ dish }} on the way · {{ eta_min }} min"


class VoicePack(BaseModel):
    """The entire user-facing voice for one brand."""

    id: str = Field(..., description="Stable identifier — used in PersonaInput.voice_pack_id")
    name: str = Field(..., description="Brand name — used in templates as {{ name }}")
    locale: str = Field("en-IN", description="BCP-47 locale; used by future i18n logic")

    proposal: ProposalVoice
    confirm: ConfirmVoice
    placed: PlacedVoice
    give_up: GiveUpVoice
    push: PushVoice


__all__ = [
    "ConfirmVoice",
    "GiveUpVoice",
    "PlacedVoice",
    "ProposalVoice",
    "PushVoice",
    "VoicePack",
]
