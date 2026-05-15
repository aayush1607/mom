"""Address listing — thin proxy over Swiggy MCP `get_addresses`.

The frontend needs a way to let users pick which saved Swiggy address the
agent should order to. We don't want raw Swiggy payloads in the browser
(API drift, leaky internals), so this module:

  * calls `get_addresses` via the per-request MCP client
  * normalises each row into a small, FE-friendly shape
  * never persists; Swiggy already owns the source of truth

If the user has a favourite (e.g. addressTag="Home"), it will appear in
the list — the FE picks the default (first one or last-selected from
localStorage). Backend stays stateless.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel

from meal_agent.tools.mcp_envelope import unwrap
from meal_agent.tools.swiggy_mcp import SwiggyTools


class Address(BaseModel):
    """One Swiggy address, FE-shaped."""

    id: str
    label: str           # short name to show in the picker pill
    address_line: str    # full one-line address (may be long)
    category: str | None = None  # "Home" | "Work" | "Other" | "Friends & Family"
    phone_masked: str | None = None  # eg "****1417"


class ListAddressesResponse(BaseModel):
    addresses: list[Address]


def _label_for(raw: dict[str, Any]) -> str:
    """Pick the most user-recognisable label for the picker pill.

    Preference order:
      1. addressTag (user-set free text — "Home", "Goa Airbnb - Tripti")
      2. addressCategory (Swiggy bucket — "Home", "Work", "Other")
      3. first segment of addressLine
      4. id, as a last resort
    """
    tag = (raw.get("addressTag") or "").strip()
    if tag:
        return tag
    cat = (raw.get("addressCategory") or "").strip()
    if cat:
        return cat
    line = (raw.get("addressLine") or "").strip()
    if line:
        # "Aayush: Flat 206, Bengaluru, …" → "Flat 206, Bengaluru"
        head = line.split(":", 1)[-1].strip()
        return head.split(",", 2)[0].strip() or head[:40]
    return str(raw.get("id", "Address"))


def _normalise(raw: dict[str, Any]) -> Address | None:
    aid = raw.get("id")
    if not aid:
        return None
    return Address(
        id=str(aid),
        label=_label_for(raw),
        address_line=str(raw.get("addressLine") or "").strip(),
        category=(str(raw["addressCategory"]).strip()
                  if raw.get("addressCategory") else None),
        phone_masked=(str(raw["phoneNumber"]).strip()
                      if raw.get("phoneNumber") else None),
    )


async def fetch_addresses(swiggy: SwiggyTools) -> ListAddressesResponse:
    """Call MCP, normalise, return. Empty list on error so the FE can
    fall back to its env-default address rather than crashing."""
    raw = await swiggy.food_tool("get_addresses").ainvoke({})
    data, err = unwrap(raw)
    if err or not isinstance(data, dict):
        return ListAddressesResponse(addresses=[])
    rows = data.get("addresses") or []
    out: list[Address] = []
    for r in rows:
        if isinstance(r, dict):
            n = _normalise(r)
            if n is not None:
                out.append(n)
    return ListAddressesResponse(addresses=out)


__all__ = ["Address", "ListAddressesResponse", "fetch_addresses"]
