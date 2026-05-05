"""MCP response envelope helpers.

All Swiggy MCP tools return a uniform envelope::

    { "success": true,  "data": <payload>, "message": "..." }
    { "success": false, "error": { "message": "..." } }

LangChain's `BaseTool.ainvoke` returns whatever the underlying client
returns, which can be any of:

  - the raw envelope dict
  - a JSON string (when the MCP response is content-typed text)
  - a list of MCP `Content` blocks the adapter has already JSON-decoded

`unwrap()` collapses all three into a `(payload_dict, error_message)` tuple
so node code can just say::

    payload, err = unwrap(await tool.ainvoke({...}))
    if err: ...
"""

from __future__ import annotations

import json
from typing import Any


def unwrap(raw: Any) -> tuple[dict[str, Any], str | None]:
    """Return (data, error_message). data is {} on error; error is None on success."""
    envelope = _coerce_envelope(raw)
    if envelope is None:
        return {}, f"unparseable MCP response: {raw!r}"

    if envelope.get("success") is False:
        err = envelope.get("error") or {}
        msg = err.get("message") if isinstance(err, dict) else str(err)
        return {}, str(msg or "unspecified MCP error")

    # Envelope-shaped response → use the `data` key
    if "success" in envelope or "data" in envelope:
        data = envelope.get("data")
        if data is None:
            return {}, None
        if not isinstance(data, dict):
            return {"_raw": data}, None
        return data, None

    # Bare dict (no envelope) → treat the dict itself as the payload.
    # Useful for tests and for any tool variant that returns raw payloads.
    return envelope, None


def _coerce_envelope(raw: Any) -> dict[str, Any] | None:
    """Best-effort: turn a tool response into the {success,data,...} dict."""
    if isinstance(raw, dict):
        return raw

    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
            return parsed if isinstance(parsed, dict) else None
        except json.JSONDecodeError:
            return None

    # langchain-mcp-adapters sometimes returns a list of content blocks
    if isinstance(raw, list) and raw:
        for block in raw:
            text = _extract_text(block)
            if text is None:
                continue
            try:
                parsed = json.loads(text)
                if isinstance(parsed, dict):
                    return parsed
            except json.JSONDecodeError:
                continue
    return None


def _extract_text(block: Any) -> str | None:
    if isinstance(block, dict):
        if block.get("type") == "text":
            return block.get("text")
        if "text" in block and isinstance(block["text"], str):
            return block["text"]
    text_attr = getattr(block, "text", None)
    return text_attr if isinstance(text_attr, str) else None


__all__ = ["unwrap"]
