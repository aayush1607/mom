"""Swiggy MCP client wrapper.

Opens a real `mcp.ClientSession` (via streamable-HTTP or SSE transport) per
agent run and exposes a thin `_McpToolProxy.ainvoke(args)` surface that mirrors
the langchain `BaseTool.ainvoke` signature used by the rest of the code.

We do NOT use `langchain-mcp-adapters` here because that wrapper drops the
`structuredContent` field of `CallToolResult` — the only place real Swiggy
returns structured JSON. Going to the raw MCP session lets us pass the
structured payload straight through.

Auth model: each user has a Swiggy OAuth token. The MCP client is built **per
agent run** with that user's token in the request header. We deliberately do
NOT cache an MCP client globally — token scope is per-user.

For tests, see `tests/conftest.py` for a fake MCP fixture that uses MagicMock.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import AsyncExitStack, asynccontextmanager
from dataclasses import dataclass
from typing import Any

from mcp import ClientSession
from mcp.client.sse import sse_client
from mcp.client.streamable_http import streamablehttp_client

from meal_agent.settings import get_settings

# ──────────────────────────────────────────────────────────────────────────────
# Tool proxy — duck-types the langchain BaseTool surface used by node code
# ──────────────────────────────────────────────────────────────────────────────


class _McpToolProxy:
    """Async-callable proxy for a single MCP tool.

    Exposes `.name` and `.ainvoke(args)` matching the langchain BaseTool
    surface so node code (and the FakeSwiggy MagicMock fixture) can be
    swapped in without changes.

    Returns a `{success, data, ...}` envelope so `unwrap()` works on both
    real MCP responses and test stubs.
    """

    def __init__(self, session: ClientSession, name: str) -> None:
        self._session = session
        self.name = name

    async def ainvoke(self, args: dict[str, Any] | None = None) -> dict[str, Any]:
        result = await self._session.call_tool(self.name, args or {})
        if result.isError:
            return {
                "success": False,
                "error": {"message": _first_text(result.content) or "MCP tool error"},
            }
        if result.structuredContent is not None:
            return {"success": True, "data": result.structuredContent}
        # No structured payload — return the text under a `_text` field so
        # nodes that don't strictly need structured data can still see it.
        text = _first_text(result.content)
        return {"success": True, "data": {"_text": text} if text else {}}


def _first_text(blocks: Any) -> str | None:
    if not blocks:
        return None
    for b in blocks:
        text = getattr(b, "text", None)
        if isinstance(text, str):
            return text
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Tool collection
# ──────────────────────────────────────────────────────────────────────────────


@dataclass
class SwiggyTools:
    """Resolved set of Swiggy MCP tools for one agent run."""

    food: dict[str, Any]                            # name → _McpToolProxy or MagicMock
    dineout: dict[str, Any]

    def all(self) -> list[Any]:
        return [*self.food.values(), *self.dineout.values()]

    def food_tool(self, name: str) -> Any:
        try:
            return self.food[name]
        except KeyError as e:
            raise KeyError(f"Swiggy Food MCP tool '{name}' not exposed") from e

    def dineout_tool(self, name: str) -> Any:
        try:
            return self.dineout[name]
        except KeyError as e:
            raise KeyError(f"Swiggy Dineout MCP tool '{name}' not exposed") from e


# ──────────────────────────────────────────────────────────────────────────────
# Session lifecycle
# ──────────────────────────────────────────────────────────────────────────────


async def _open_session(
    stack: AsyncExitStack,
    *,
    url: str,
    transport: str,
    headers: dict[str, str],
) -> ClientSession:
    if transport in {"streamable_http", "streamable-http", "http"}:
        ctx = streamablehttp_client(url, headers=headers)
        read, write, _ = await stack.enter_async_context(ctx)
    elif transport == "sse":
        ctx = sse_client(url, headers=headers)
        read, write = await stack.enter_async_context(ctx)
    else:
        raise ValueError(f"Unsupported MCP transport: {transport!r}")

    session = await stack.enter_async_context(ClientSession(read, write))
    await session.initialize()
    return session


@asynccontextmanager
async def swiggy_tools(user_token: str) -> AsyncIterator[SwiggyTools]:
    """Context-managed MCP sessions + resolved tools for one user.

    Usage::

        async with swiggy_tools(token) as tools:
            envelope = await tools.food_tool("search_restaurants").ainvoke(
                {"addressId": "...", "query": "biryani"}
            )
            data, err = unwrap(envelope)

    Both `food` and `dineout` sessions are opened on enter and closed on exit.
    `dineout` is opened only if `swiggy.dineout_enabled` is True (default False
    in v1 — most client_ids are not allowlisted for it).
    """
    s = get_settings().swiggy
    headers = {"Authorization": f"Bearer {user_token}"}

    food: dict[str, _McpToolProxy] = {}
    dineout: dict[str, _McpToolProxy] = {}

    async with AsyncExitStack() as stack:
        try:
            food_session = await _open_session(
                stack, url=s.food_url, transport=s.transport, headers=headers
            )
            food_tools_list = await food_session.list_tools()
            for t in food_tools_list.tools:
                food[t.name] = _McpToolProxy(food_session, t.name)

            if s.dineout_enabled:
                dineout_session = await _open_session(
                    stack, url=s.dineout_url, transport=s.transport, headers=headers
                )
                dineout_tools_list = await dineout_session.list_tools()
                for t in dineout_tools_list.tools:
                    dineout[t.name] = _McpToolProxy(dineout_session, t.name)
        except Exception as e:
            raise RuntimeError(f"Failed to initialise Swiggy MCP client: {e}") from e

        yield SwiggyTools(food=food, dineout=dineout)


__all__ = ["SwiggyTools", "swiggy_tools"]
