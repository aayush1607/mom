"""Curated activity feed for an in-flight run.

The agent already writes a rich `agent_audit` log per node. Surfacing the
raw audit table to the browser would leak internals (LLM prompts, payload
shapes), so this module folds the audit rows into a small, ordered list of
**user-facing steps** that mom is doing right now — for the loader screen.

One step per *node* (not per audit row). Status is derived from the
event mix:

  * `done`    — node has emitted `event="exit"`
  * `active`  — at least one event recorded but no `exit` yet
  * `error`   — node emitted `event="error"` and never reached `exit`

Steps are ordered by first-seen-time so the FE can render the live trace
top-to-bottom as it grows. Detail strings are derived from the `exit`
payload when available (e.g. "47 places open") so the user sees real
agent output, not stock copy.
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel

# ──────────────────────────────────────────────────────────────────────────────
# Step labels — mom's voice, not engineering jargon
# ──────────────────────────────────────────────────────────────────────────────

# Active (still working) and done (finished) headlines. Active stays present-
# tense ("…ing"), done flips to past-tense so the trace reads like a story.
_LABELS: dict[str, dict[str, str]] = {
    "interpret_prompt": {
        "active": "Reading the room",
        "done": "Got the gist",
    },
    "discover": {
        "active": "Sniffing out food near you",
        "done": "Sniffed out the neighbourhood",
    },
    "shortlist": {
        "active": "Crossing off the rubbish",
        "done": "Trimmed to the shortlist",
    },
    "pick_dish": {
        "active": "Eyeing the menus",
        "done": "Picked a dish",
    },
    "compose_proposal": {
        "active": "Polishing the pitch",
        "done": "Pitch ready",
    },
    "build_cart": {
        "active": "Adding to your cart",
        "done": "Cart loaded",
    },
    "review_cart": {
        "active": "Double-checking the bill",
        "done": "Bill checks out",
    },
    "place_order": {
        "active": "Placing the order",
        "done": "Order in",
    },
}

# Order steps appear in. Anything not in this list is appended in
# first-seen order (defensive — we'd rather show an unknown node than
# silently drop it).
_ORDER = [
    "interpret_prompt",
    "discover",
    "shortlist",
    "pick_dish",
    "compose_proposal",
    "build_cart",
    "review_cart",
    "place_order",
]


# ──────────────────────────────────────────────────────────────────────────────
# Detail extractors — pulled from the `exit` payload when present
# ──────────────────────────────────────────────────────────────────────────────


def _detail(node: str, payload: dict[str, Any] | None) -> str | None:
    """Best-effort one-liner about what the node found. Nullable."""
    if not payload:
        return None
    if node == "interpret_prompt":
        intent = payload.get("intent_summary")
        return str(intent)[:80] if intent else None
    if node == "discover":
        c = payload.get("count")
        return f"{c} places open" if isinstance(c, int) else None
    if node == "shortlist":
        ids = payload.get("shortlisted_ids")
        if isinstance(ids, list):
            return f"kept the top {len(ids)}"
        c = payload.get("count")
        return f"kept all {c}" if isinstance(c, int) else None
    if node == "pick_dish":
        c = payload.get("candidate_count")
        return f"weighed {c} dishes" if isinstance(c, int) else None
    if node == "place_order":
        oid = payload.get("order_id")
        return f"id {oid}" if oid else None
    return None


# ──────────────────────────────────────────────────────────────────────────────
# Output schema
# ──────────────────────────────────────────────────────────────────────────────


class ActivityStep(BaseModel):
    """One curated step in the live trace."""

    node: str
    label: str
    detail: str | None = None
    status: str  # "done" | "active" | "error"
    started_at: str
    finished_at: str | None = None


class RunActivity(BaseModel):
    run_id: str
    steps: list[ActivityStep]


# ──────────────────────────────────────────────────────────────────────────────
# Folder
# ──────────────────────────────────────────────────────────────────────────────


def _coerce_payload(raw: Any) -> dict[str, Any] | None:
    """asyncpg returns JSONB as a Python dict already, but defensively
    handle the str fallback some drivers/versions emit."""
    if raw is None:
        return None
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            decoded = json.loads(raw)
        except Exception:  # noqa: BLE001
            return None
        return decoded if isinstance(decoded, dict) else None
    return None


def fold_audit_rows(run_id: str, rows: list[dict[str, Any]]) -> RunActivity:
    """Collapse `agent_audit` rows for one run into ordered ActivityStep.

    `rows` must be ordered by `occurred_at ASC` and contain keys:
      `node`, `event`, `payload`, `occurred_at` (datetime).
    Driver-internal entries (`__driver__`) are ignored.
    """
    by_node: dict[str, dict[str, Any]] = {}
    seen_order: list[str] = []

    for row in rows:
        node = row["node"]
        if node == "__driver__" or node not in _LABELS:
            continue
        event = row["event"]
        payload = _coerce_payload(row.get("payload"))
        at = row["occurred_at"]

        bucket = by_node.get(node)
        if bucket is None:
            bucket = {
                "started_at": at,
                "finished_at": None,
                "status": "active",
                "exit_payload": None,
                "errored": False,
            }
            by_node[node] = bucket
            seen_order.append(node)

        if event == "exit":
            bucket["finished_at"] = at
            bucket["status"] = "done"
            bucket["exit_payload"] = payload
        elif event == "error":
            # Keep the active/done state but flag — the run-level status
            # tells the FE if the whole thing failed; nodes can recover.
            bucket["errored"] = True

    # Stable order: known nodes by _ORDER, then any unknowns by seen order
    known = [n for n in _ORDER if n in by_node]
    unknown = [n for n in seen_order if n not in _ORDER]
    ordered_nodes = known + unknown

    steps: list[ActivityStep] = []
    for node in ordered_nodes:
        b = by_node[node]
        labels = _LABELS.get(node, {"active": node, "done": node})
        status = b["status"]
        # If finished but errored, downgrade to error — useful when a node
        # fails irrecoverably (the run-level status will be "failed" too).
        if status == "active" and b["errored"]:
            status = "error"
        label = labels["done"] if status == "done" else labels["active"]
        steps.append(
            ActivityStep(
                node=node,
                label=label,
                detail=_detail(node, b["exit_payload"]),
                status=status,
                started_at=b["started_at"].isoformat(),
                finished_at=(
                    b["finished_at"].isoformat() if b["finished_at"] else None
                ),
            )
        )
    return RunActivity(run_id=run_id, steps=steps)


__all__ = ["ActivityStep", "RunActivity", "fold_audit_rows"]
