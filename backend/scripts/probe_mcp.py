"""Probe Swiggy MCP — print live tool list + sample response shapes.

Usage::

    SWIGGY_OAUTH_TOKEN=<token> ADDRESS_ID=<id> uv run python scripts/probe_mcp.py

Walks the canonical Food journey and dumps the JSON shape of each response
so node code can be coded against the real shape (not the docs alone).

Skipped if SWIGGY_OAUTH_TOKEN is not set — safe to commit + run in CI.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parent.parent / ".env")

from meal_agent.tools.mcp_envelope import unwrap  # noqa: E402
from meal_agent.tools.swiggy_mcp import swiggy_tools  # noqa: E402


async def main() -> int:
    token = os.environ.get("SWIGGY_OAUTH_TOKEN")
    if not token:
        print("SWIGGY_OAUTH_TOKEN not set — skipping probe.", file=sys.stderr)
        return 0
    address_id = os.environ.get("ADDRESS_ID")

    async with swiggy_tools(user_token=token) as tools:
        print(f"=== {len(tools.food)} Food tools ===")
        for name in sorted(tools.food):
            print(f"  • {name}")

        print("\n=== get_addresses ===")
        raw = await tools.food_tool("get_addresses").ainvoke({})
        data, err = unwrap(raw)
        _dump(data, err)
        if not address_id:
            for addr in data.get("addresses", []) or []:
                if "id" in addr:
                    address_id = addr["id"]
                    print(f"\n[auto-picked addressId={address_id}]")
                    break

        if not address_id:
            print("\nNo ADDRESS_ID and could not infer one — stopping.")
            return 0

        for tool_name, args in [
            ("search_restaurants", {"addressId": address_id, "query": "biryani"}),
            ("search_menu", {"addressId": address_id, "query": "biryani"}),
            ("get_food_cart", {"addressId": address_id}),
        ]:
            print(f"\n=== {tool_name} ===")
            raw = await tools.food_tool(tool_name).ainvoke(args)
            data, err = unwrap(raw)
            _dump(data, err)

    return 0


def _dump(data: dict, err: str | None) -> None:
    if err:
        print(f"  ERROR: {err}")
        return
    print(json.dumps(_truncate(data), indent=2)[:2000])


def _truncate(obj, depth=0):
    """Trim arrays/strings so the dump is readable."""
    if depth > 6:
        return "…"
    if isinstance(obj, list):
        return [_truncate(x, depth + 1) for x in obj[:3]]
    if isinstance(obj, dict):
        return {k: _truncate(v, depth + 1) for k, v in obj.items()}
    if isinstance(obj, str) and len(obj) > 200:
        return obj[:200] + "…"
    return obj


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
