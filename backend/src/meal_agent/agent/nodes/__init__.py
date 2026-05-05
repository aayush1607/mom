"""Per-node async functions.

Each node has the same signature::

    async def run(state: AgentState, deps: Deps) -> dict[str, Any]

It returns a dict of state-field updates; LangGraph reduces those into the
next state.

`Deps` is a small container of injected dependencies (LLMs, audit writer,
voice pack, persona, user-token-bound MCP tools). Built fresh per run by
the API layer; never reach for module-level singletons inside a node.
"""

from __future__ import annotations

from dataclasses import dataclass

from meal_agent.persona.schema import VoicePack
from meal_agent.storage.audit import AuditWriter
from meal_agent.tools.llm import LLMs
from meal_agent.tools.swiggy_mcp import SwiggyTools


@dataclass
class Deps:
    """Per-run injected dependencies, passed alongside the state into each node."""

    llms: LLMs
    swiggy: SwiggyTools
    audit: AuditWriter
    voice: VoicePack
    run_id: str


__all__ = ["Deps"]
