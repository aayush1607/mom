"""Swiggy MCP OAuth helper — get a bearer token via PKCE+phone+OTP.

Usage:
    cd backend
    uv run python scripts/swiggy_login.py

Flow:
  1. Generate PKCE verifier + challenge (S256)
  2. Dynamically register client (RFC 7591) at /auth/register
  3. Spin up a tiny aiohttp server on http://localhost:{PORT}/oauth/callback
  4. Open the user's browser to /auth/authorize — they enter phone + OTP
  5. Capture the auth code from the callback
  6. Exchange code → bearer access_token at /auth/token
  7. Print the token + write it back into backend/.env (SWIGGY_OAUTH_TOKEN)

Token lifetime is 5 days per Swiggy docs. Re-run when it expires.
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import secrets
import sys
import urllib.parse
import webbrowser
from pathlib import Path

import httpx
from aiohttp import web

PORT = 8787
REDIRECT_URI = f"http://localhost:{PORT}/oauth/callback"
BASE = "https://mcp.swiggy.com"
SCOPE = "mcp:tools mcp:resources mcp:prompts"
ENV_PATH = Path(__file__).resolve().parent.parent / ".env"


def _b64url(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).rstrip(b"=").decode("ascii")


def _make_pkce() -> tuple[str, str]:
    verifier = _b64url(secrets.token_bytes(32))
    challenge = _b64url(hashlib.sha256(verifier.encode()).digest())
    return verifier, challenge


async def _register_client(http: httpx.AsyncClient) -> str:
    print("[1/5] Registering dynamic client ...")
    r = await http.post(
        f"{BASE}/auth/register",
        json={
            "client_name": "mom Local Dev",
            "redirect_uris": [REDIRECT_URI],
            "grant_types": ["authorization_code"],
            "response_types": ["code"],
            "token_endpoint_auth_method": "none",
            "scope": SCOPE,
        },
    )
    r.raise_for_status()
    data = r.json()
    print(f"      client_id = {data['client_id']}")
    return data["client_id"]


async def _wait_for_code() -> tuple[str, str]:
    """Run aiohttp server, return (code, state) from callback."""
    fut: asyncio.Future[tuple[str, str]] = asyncio.get_event_loop().create_future()

    async def handler(req: web.Request) -> web.Response:
        code = req.query.get("code")
        state = req.query.get("state", "")
        err = req.query.get("error")
        if err:
            if not fut.done():
                fut.set_exception(RuntimeError(f"OAuth error: {err}"))
            return web.Response(text=f"OAuth error: {err}", status=400)
        if not code:
            return web.Response(text="Missing ?code", status=400)
        if not fut.done():
            fut.set_result((code, state))
        return web.Response(
            text="<h2>Login complete. You can close this tab.</h2>",
            content_type="text/html",
        )

    app = web.Application()
    app.router.add_get("/oauth/callback", handler)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, "127.0.0.1", PORT)
    await site.start()
    try:
        return await asyncio.wait_for(fut, timeout=300)
    finally:
        await runner.cleanup()


def _patch_env_token(token: str) -> None:
    """Update SWIGGY_OAUTH_TOKEN= line in backend/.env (or append if missing)."""
    if not ENV_PATH.exists():
        print(f"  (no .env at {ENV_PATH} — skipping write-back)")
        return
    lines = ENV_PATH.read_text().splitlines()
    new_lines = []
    found = False
    for line in lines:
        if line.startswith("SWIGGY_OAUTH_TOKEN="):
            new_lines.append(f"SWIGGY_OAUTH_TOKEN={token}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"SWIGGY_OAUTH_TOKEN={token}")
    ENV_PATH.write_text("\n".join(new_lines) + "\n")
    print(f"      ✓ wrote SWIGGY_OAUTH_TOKEN to {ENV_PATH}")


async def main() -> int:
    async with httpx.AsyncClient(timeout=30.0) as http:
        client_id = await _register_client(http)

        verifier, challenge = _make_pkce()
        state = _b64url(secrets.token_bytes(16))

        print("[2/5] Opening browser for phone + OTP consent ...")
        params = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": REDIRECT_URI,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
            "state": state,
            "scope": SCOPE,
        }
        url = f"{BASE}/auth/authorize?" + urllib.parse.urlencode(params)
        print(f"      {url}")
        webbrowser.open(url)

        print(f"[3/5] Waiting for callback on {REDIRECT_URI} (5 min timeout) ...")
        code, returned_state = await _wait_for_code()
        if returned_state != state:
            raise RuntimeError(
                f"State mismatch — possible CSRF. expected={state} got={returned_state}"
            )
        print(f"      ✓ got auth code ({len(code)} chars)")

        print("[4/5] Exchanging code for access token ...")
        r = await http.post(
            f"{BASE}/auth/token",
            json={
                "grant_type": "authorization_code",
                "code": code,
                "code_verifier": verifier,
                "client_id": client_id,
                "redirect_uri": REDIRECT_URI,
            },
        )
        if r.status_code != 200:
            print(f"      ✗ token exchange failed ({r.status_code}): {r.text}")
            return 1
        tok = r.json()
        token = tok["access_token"]
        print(f"      ✓ access_token issued ({len(token)} chars)")
        print(f"      expires_in={tok.get('expires_in')}s")
        print(f"      scope={tok.get('scope')}")

        print("[5/5] Writing to backend/.env ...")
        _patch_env_token(token)

        print("\n✓ Done. Token is live for ~5 days.")
        print("  Run:  uv run python scripts/probe_mcp.py")
        return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\n(cancelled)")
        sys.exit(130)
