"""Live connectivity smoke test.

Run AFTER you've pasted real values into backend/.env:

    cd backend
    uv run python scripts/smoke_live.py

Checks (in order):
  1. Settings load (so you know all env vars are visible)
  2. Postgres connection + DDL run
  3. Azure OpenAI router model (cheap)
  4. Azure OpenAI picker model (smart)

Each check prints either OK or a precise failure cause.
Exits non-zero on the first failure so CI can use it too.
"""

from __future__ import annotations

import asyncio
import sys
import traceback
from textwrap import shorten


async def check_settings() -> bool:
    print("\n[1/4] Loading settings from .env ...")
    try:
        from meal_agent.settings import get_settings

        s = get_settings()
        print(f"  endpoint    : {s.azure_openai.endpoint}")
        print(f"  api_version : {s.azure_openai.api_version}")
        print(f"  router      : {s.azure_openai.deployment_router}")
        print(f"  picker      : {s.azure_openai.deployment_picker}")
        print(f"  postgres    : {s.storage.dsn.split('@')[-1]}")
        print(f"  swiggy_url  : {s.swiggy.food_url}")
        if s.azure_openai.api_key.startswith("<"):
            print("  ✗ AZURE_OPENAI_API_KEY is still a placeholder")
            return False
        print("  ✓ OK")
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        traceback.print_exc()
        return False


async def check_postgres() -> bool:
    print("\n[2/4] Connecting to Postgres ...")
    try:
        import psycopg

        from meal_agent.settings import get_settings

        dsn = get_settings().storage.dsn
        async with await psycopg.AsyncConnection.connect(dsn) as conn:
            async with conn.cursor() as cur:
                await cur.execute("SELECT version();")
                row = await cur.fetchone()
                print(f"  connected to: {shorten(row[0], 70)}")

        # Now apply audit DDL
        from meal_agent.storage.audit import AuditWriter

        writer = await AuditWriter.connect()
        await writer.close()
        print("  ✓ audit DDL applied")
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {e}")
        return False


async def check_router_llm() -> bool:
    print("\n[3/4] Calling Azure router model ...")
    try:
        from meal_agent.tools.llm import build_llms

        llm = build_llms().router
        resp = await llm.ainvoke("Reply with just: pong")
        print(f"  response: {shorten(str(resp.content), 80)}")
        print("  ✓ OK")
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {type(e).__name__}: {e}")
        return False


async def check_picker_llm() -> bool:
    print("\n[4/4] Calling Azure picker model ...")
    try:
        from meal_agent.tools.llm import build_llms

        llm = build_llms().picker
        resp = await llm.ainvoke("Reply with just: pong")
        print(f"  response: {shorten(str(resp.content), 80)}")
        print("  ✓ OK")
        return True
    except Exception as e:
        print(f"  ✗ FAILED: {type(e).__name__}: {e}")
        return False


async def main() -> int:
    print("=" * 60)
    print("Bawarchi backend — live connectivity smoke")
    print("=" * 60)

    checks = [
        check_settings,
        check_postgres,
        check_router_llm,
        check_picker_llm,
    ]
    for check in checks:
        ok = await check()
        if not ok:
            print("\n✗ Aborting on first failure.")
            return 1

    print("\n" + "=" * 60)
    print("✓ All 4 checks passed. You're ready to boot the FastAPI app.")
    print("=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
