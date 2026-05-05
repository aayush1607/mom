# mom. — frontend

Next.js 15 PWA that exercises the meal-decision moment of the
[mom. agent](../backend). Mobile-first, hardcoded test user/address, no
auth in v1.

```
home  →  Wake mom  →  /run/{id}  →  Suggestion → CartConfirm → Pakka
                                  ↘ GiveUp (failed | cancelled)
```

## Run end-to-end against local backend

1. **Boot the backend** (in `../backend`):
   ```bash
   cd ../backend
   uv run uvicorn meal_agent.api.app:app --host 127.0.0.1 --port 8765
   ```
   Defaults: `AGENT_LIVE_ORDERS_ENABLED=false` (dry-run) +
   `AGENT_BLOCK_COD=true`. **Place orders never reach Swiggy** unless you
   flip the env flag — verify before testing real flows.

2. **Boot the frontend:**
   ```bash
   cp .env.local.example .env.local   # one-time
   pnpm install
   pnpm dev
   ```
   → http://localhost:3000

3. Tap **Wake mom** on Lunch or Dinner. The page navigates to
   `/run/{run_id}` and polls every 1.5 s until a terminal status.

## Env

| Var | Default | Purpose |
|---|---|---|
| `NEXT_PUBLIC_API_BASE` | `http://localhost:8765` | meal-agent FastAPI base |
| `NEXT_PUBLIC_USER_ID` | `u_dev` | passed as `input.user_id` |
| `NEXT_PUBLIC_TEST_ADDRESS_ID` | `d2t62h7va4r6aip36a50` | Swiggy address id |

## Files

```
src/
├─ app/
│  ├─ layout.tsx            html shell + service-worker registrar
│  ├─ page.tsx              Home — slots + Wake mom
│  ├─ run/[runId]/page.tsx  state-machine dispatcher (polls /agent/runs/{id})
│  ├─ settings/page.tsx     local-only nudge config
│  ├─ debug/page.tsx        raw run snapshot viewer
│  └─ globals.css           tokens (cream / ink / saffron / brand)
├─ components/
│  ├─ Phone.tsx             desktop phone-frame chrome
│  ├─ Suggestion.tsx        awaiting_proposal renderer
│  ├─ CartConfirm.tsx       awaiting_confirm renderer
│  ├─ Pakka.tsx             placed renderer (detects DRYRUN_ prefix)
│  ├─ GiveUp.tsx            failed | cancelled_by_user renderer
│  └─ ui/{Button,Spinner}.tsx
├─ lib/
│  ├─ api.ts                typed wrapper over the 4 endpoints
│  ├─ useRun.ts             SWR hook — polls until terminal
│  ├─ slots.ts              localStorage nudge config + useSlots()
│  └─ persona.ts            persona stub sent on POST /agent/runs
└─ types/agent.ts           mirrors backend AgentState pieces
```

## State machine the FE tracks

```
running ─┬─> awaiting_proposal ──(accept)──> running ──> awaiting_confirm ──(confirm)──> placed
         │                  └──(swap)──> running ──> awaiting_proposal      (cancel)──> cancelled
         └─> failed (terminal — GiveUp screen with voice strings)
```

Voice copy (`voice_heading`, `voice_reason`, `voice_cta_yes`, `voice_cta_swap`,
give-up reason templates) comes server-side from the persona pack
(`mom-v1`). The FE never re-templates — it only renders what the backend
sends.

## Conventions

- TypeScript strict, ESLint via `pnpm lint`.
- All client components start with `"use client"` and live alongside the
  route or in `components/`.
- Tailwind v4 design tokens live in `globals.css` (`--bg`, `--brand`,
  `--ink-*` etc.) and mirror `frames/screens.html`.
- No state libraries; SWR is the only async/data dependency.
- Brand metaphor rules (locked in repo plan): "mom" is what the brand
  calls **itself**, never the user. Never use `beta`, `dear`, `son`, etc.
  See `.github/copilot-instructions.md` for the full voice rules.

## Out of v1

Swiggy OAuth, real push, splash/onboarding, multi-user auth, address picker,
Kitchen weekly view, analytics, deployment.
