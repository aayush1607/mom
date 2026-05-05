"""Persistence layer.

Two concerns live here:

  1. **LangGraph checkpointer** — provided by `langgraph-checkpoint-postgres`.
     The state machine snapshots every state transition so a run can resume
     across process restarts. See `checkpointer.py`.

  2. **Agent audit log** — application-level append-only log of node entries,
     LLM calls, MCP calls, and final outcomes. See `audit.py`.

The LangGraph table is managed by the checkpointer library. The audit table
DDL is in `audit.py` (run via Alembic in production; bundled here for the
scaffold).
"""
