"""HTTP routes.

Four endpoints, all async::

    POST /agent/runs                 → 202 + run_id; schedules background work
    POST /agent/runs/{id}/resume     → 202; injects user_decision + resumes graph
    GET  /agent/runs/{id}            → current status + last interrupt payload
    POST /agent/runs/{id}/cancel     → 202; aborts the run

The graph is invoked via `BackgroundTasks` for the v1 scaffold. Production
should switch to a durable queue (Postgres LISTEN/NOTIFY, Azure Service
Bus, etc.) so process restarts don't drop in-flight runs.
"""

from __future__ import annotations

import secrets
from datetime import UTC, datetime
from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request, status
from langgraph.types import Command
from pydantic import BaseModel, Field

from meal_agent.agent.graph import build_graph
from meal_agent.agent.nodes import Deps
from meal_agent.agent.state import (
    AgentRunInput,
    AgentState,
    AgentStatus,
    UserDecision,
    UserDecisionKind,
)
from meal_agent.persona.loader import load_pack
from meal_agent.tools.swiggy_mcp import swiggy_tools

router = APIRouter()


# ──────────────────────────────────────────────────────────────────────────────
# Request / response shapes
# ──────────────────────────────────────────────────────────────────────────────


class CreateRunRequest(BaseModel):
    """Caller-assembled run input + the per-user OAuth token for Swiggy MCP.

    The token is passed in the body (not a header) so the agent layer is
    transport-agnostic and can be invoked from a queue worker too.
    """

    input: AgentRunInput
    user_token: str = Field(..., description="Per-user OAuth token for Swiggy MCP")


class CreateRunResponse(BaseModel):
    run_id: str
    thread_id: str
    status: AgentStatus = AgentStatus.RUNNING


class ResumeRequest(BaseModel):
    decision: UserDecisionKind
    note: str | None = None
    user_token: str = Field(..., description="Per-user OAuth token for Swiggy MCP")


class RunSnapshot(BaseModel):
    run_id: str
    thread_id: str
    status: AgentStatus
    state: dict[str, Any]


# ──────────────────────────────────────────────────────────────────────────────
# Endpoints
# ──────────────────────────────────────────────────────────────────────────────


@router.post(
    "/runs",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CreateRunResponse,
)
async def create_run(
    body: CreateRunRequest,
    background: BackgroundTasks,
    request: Request,
) -> CreateRunResponse:
    """Start a new agent run. Returns immediately with the run_id."""
    run_id = _new_id("run")
    thread_id = _new_id("th")

    await request.app.state.audit.create_run(
        run_id=run_id,
        user_id=body.input.user_id,
        thread_id=thread_id,
        voice_pack_id=body.input.persona.voice_pack_id,
        prompt=body.input.prompt,
    )

    background.add_task(
        _drive_run_to_next_pause,
        request.app,
        run_id=run_id,
        thread_id=thread_id,
        run_input=body.input,
        user_token=body.user_token,
        resume_value=None,
    )

    return CreateRunResponse(run_id=run_id, thread_id=thread_id)


@router.post(
    "/runs/{run_id}/resume",
    status_code=status.HTTP_202_ACCEPTED,
    response_model=CreateRunResponse,
)
async def resume_run(
    run_id: str,
    body: ResumeRequest,
    background: BackgroundTasks,
    request: Request,
) -> CreateRunResponse:
    """Resume a paused run by injecting a UserDecision."""
    thread_id = await _lookup_thread_id(request.app, run_id)

    decision = UserDecision(
        kind=body.decision,
        note=body.note,
        received_at=datetime.now(UTC),
    )

    background.add_task(
        _drive_run_to_next_pause,
        request.app,
        run_id=run_id,
        thread_id=thread_id,
        run_input=None,
        user_token=body.user_token,
        resume_value={"user_decision": decision},
    )

    return CreateRunResponse(run_id=run_id, thread_id=thread_id)


@router.get("/runs/{run_id}", response_model=RunSnapshot)
async def get_run(run_id: str, request: Request) -> RunSnapshot:
    """Return the latest checkpointed state for a run."""
    thread_id = await _lookup_thread_id(request.app, run_id)
    config = {"configurable": {"thread_id": thread_id}}

    # We need a graph to query state — but it can be a no-deps graph since
    # we're only reading. We build a stub deps purely for the API surface;
    # nodes won't run for a get_state call.
    saver = request.app.state.checkpointer
    from meal_agent.agent.graph import build_graph as _build  # local import to avoid cycle
    graph = _build(deps=_stub_deps(request.app, run_id, user_token=""), checkpointer=saver)

    snap = await graph.aget_state(config)
    state_dict = snap.values if hasattr(snap, "values") else {}
    current_status = (
        state_dict.get("status") if isinstance(state_dict, dict) else AgentStatus.RUNNING
    )
    return RunSnapshot(
        run_id=run_id,
        thread_id=thread_id,
        status=AgentStatus(current_status) if current_status else AgentStatus.RUNNING,
        state=_safe_dump(state_dict),
    )


@router.post("/runs/{run_id}/cancel", status_code=status.HTTP_202_ACCEPTED)
async def cancel_run(run_id: str, request: Request) -> dict[str, str]:
    """Mark the run as cancelled. Does NOT interrupt an in-flight node."""
    await request.app.state.audit.update_run_status(
        run_id=run_id, status=AgentStatus.CANCELLED_BY_USER
    )
    return {"run_id": run_id, "status": AgentStatus.CANCELLED_BY_USER.value}


# ──────────────────────────────────────────────────────────────────────────────
# Background driver
# ──────────────────────────────────────────────────────────────────────────────


async def _drive_run_to_next_pause(
    app,
    *,
    run_id: str,
    thread_id: str,
    run_input: AgentRunInput | None,
    user_token: str,
    resume_value: dict[str, Any] | None,
) -> None:
    """Run the graph until the next interrupt or terminal state.

    For new runs, `run_input` is provided and `resume_value` is None.
    For resumes, `resume_value` carries the UserDecision and `run_input`
    is None (the graph reads its frozen input from the checkpoint).
    """
    audit = app.state.audit
    config = {"configurable": {"thread_id": thread_id}}

    try:
        async with swiggy_tools(user_token=user_token) as swiggy:
            voice_pack_id = await _resolve_voice_pack_id(
                app, run_id, run_input, thread_id
            )
            voice = load_pack(voice_pack_id)

            deps = Deps(
                llms=app.state.llms,
                swiggy=swiggy,
                audit=audit,
                voice=voice,
                run_id=run_id,
            )
            graph = build_graph(deps=deps, checkpointer=app.state.checkpointer)

            if resume_value is None:
                # New run — seed initial state
                assert run_input is not None
                init_state = AgentState(input=run_input, thread_id=thread_id)
                await graph.ainvoke(init_state.model_dump(), config=config)
            else:
                # Resume — inject the decision via Command(update=...)
                await graph.ainvoke(Command(update=resume_value), config=config)

        # Read final state, sync run-status table
        final = await graph.aget_state(config)
        final_values = final.values if hasattr(final, "values") else {}
        if isinstance(final_values, dict):
            new_status = final_values.get("status")
            order = final_values.get("order")
            error = final_values.get("error")
            if new_status:
                await audit.update_run_status(
                    run_id=run_id,
                    status=AgentStatus(new_status),
                    failure_reason=error.get("reason") if isinstance(error, dict) else None,
                    final_order_id=order.get("order_id") if isinstance(order, dict) else None,
                )

    except Exception as e:  # noqa: BLE001 — top-level driver, must not crash silently
        await audit.write_event(
            run_id=run_id, node="__driver__", event="error", payload={"detail": str(e)}
        )
        await audit.update_run_status(run_id=run_id, status=AgentStatus.FAILED)


# ──────────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────────


def _new_id(prefix: str) -> str:
    return f"{prefix}_{secrets.token_urlsafe(12)}"


async def _lookup_thread_id(app, run_id: str) -> str:
    pool = app.state.audit._pool  # noqa: SLF001 — internal helper
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT thread_id FROM agent_runs WHERE run_id = $1", run_id
        )
        if row is None:
            raise HTTPException(status_code=404, detail="run not found")
        return row["thread_id"]


async def _resolve_voice_pack_id(
    app, run_id: str, run_input: AgentRunInput | None, thread_id: str
) -> str:
    """Get the voice_pack_id from either the live input or the runs table."""
    if run_input is not None:
        return run_input.persona.voice_pack_id
    pool = app.state.audit._pool  # noqa: SLF001
    async with pool.acquire() as conn:
        row = await conn.fetchrow(
            "SELECT voice_pack_id FROM agent_runs WHERE run_id = $1", run_id
        )
        if row is None:
            raise HTTPException(status_code=404, detail="run not found")
        return row["voice_pack_id"]


def _stub_deps(app, run_id: str, user_token: str) -> Deps:
    """Deps for read-only graph operations (aget_state).

    Construction must not require Swiggy MCP, so we pass None and assert in
    a runtime check upstream that no node actually runs.
    """
    return Deps(
        llms=app.state.llms,
        swiggy=None,  # type: ignore[arg-type]
        audit=app.state.audit,
        voice=None,  # type: ignore[arg-type]
        run_id=run_id,
    )


def _safe_dump(state: Any) -> dict[str, Any]:
    """Best-effort JSON-friendly dump of the state values."""
    if hasattr(state, "model_dump"):
        return state.model_dump(mode="json")
    if isinstance(state, dict):
        return state
    return {"raw": str(state)}


__all__ = ["router"]
