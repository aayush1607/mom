# mom.

> *One nudge. One tap. Meals, handled.*

A meal-decision agent that calls you at meal time, picks **one** real, in-stock dish from Swiggy, and (after you tap *Pakka*) places the order. No infinite scroll, no menu, no decision fatigue.

---

## Run it locally

The repo has two pieces — a Python backend (FastAPI + LangGraph) and a Next.js PWA frontend. **Place-order is OFF by default**, so nothing reaches Swiggy unless you flip a single env flag.

### 1. Prerequisites

| Tool | Version | Install |
|---|---|---|
| Python | `3.12` | `brew install python@3.12` |
| `uv` | latest | `brew install uv` (Python pkg manager) |
| Node | `20+` | `brew install node` |
| `pnpm` | `9+` | `npm i -g pnpm` |
| PostgreSQL | `16` | `brew install postgresql@16 && brew services start postgresql@16` |
| Azure OpenAI | — | An endpoint + API key with two deployments (a small router model + a stronger picker model — e.g. `o4-mini` and `gpt-5.4`/`gpt-4o`) |
| Swiggy MCP token | — | Whitelist access at [mcp.swiggy.com/builders/access](https://mcp.swiggy.com/builders/access). Once approved, run the helper in step 4. |

### 2. Clone and create the database

```bash
git clone https://github.com/aayush1607/mom.git
cd mom
createdb meal_agent           # local Postgres, default OS user, no password
```

The schema (LangGraph checkpointer + `agent_runs`, `agent_audit`, `agent_placed_orders`) is created automatically on the first backend boot.

### 3. Configure the backend

```bash
cd backend
cp .env.example .env
```

Open `backend/.env` and fill in:

- `POSTGRES_DSN` — match your local user (e.g. `postgresql://$USER@localhost:5432/meal_agent`)
- `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`
- `AZURE_OPENAI_DEPLOYMENT_ROUTER` and `AZURE_OPENAI_DEPLOYMENT_PICKER` — your two deployment names
- Leave `SWIGGY_OAUTH_TOKEN=<REPLACE_ME_AFTER_OAUTH>` for now — step 4 fills it in
- Leave `AGENT_LIVE_ORDERS_ENABLED=false` (dry-run safety rail) and `AGENT_BLOCK_COD=true`

### 4. Get a Swiggy MCP token

Once your account is whitelisted by Swiggy, the helper script does the OAuth-PKCE + phone-OTP dance and writes the token straight back into `backend/.env`:

```bash
cd backend
uv run python scripts/swiggy_login.py
```

Tokens last ~5 days — re-run when expired.

### 5. Boot the backend

```bash
cd backend
uv sync                       # one-time
uv run uvicorn meal_agent.api.app:app --host 127.0.0.1 --port 8765
```

Sanity check: open [http://localhost:8765/docs](http://localhost:8765/docs) — you should see the FastAPI Swagger UI listing the `/agent/*` endpoints.

### 6. Boot the frontend

```bash
cd frontend
cp .env.local.example .env.local
pnpm install
pnpm dev
```

Open [http://localhost:3000](http://localhost:3000), pick a delivery address from the picker, and tap **Khila do** on Lunch or Dinner. The run progresses through `MomThinking → Suggestion → CartConfirm → Pakka` (or `GiveUp` on a graceful failure).

### 7. Going live (optional)

When you're truly ready to charge real money:

```bash
# in backend/.env
AGENT_LIVE_ORDERS_ENABLED=true
```

Restart the backend. Now `place_food_order` actually calls Swiggy. Until you flip this flag, every order returns a synthetic `DRYRUN_*` id and never touches Swiggy's API.

---

## What is mom.?

The "what do we eat?" loop eats 30 minutes most evenings — open Swiggy, scroll, second-guess, close, reopen, settle for something mediocre. The decision is small but the cost is paid daily.

**mom.** is what your mom would do if she had Swiggy: at the meal time you set, she nudges you with **one** suggestion — picked against your past accepts, rejects, and the soft goal you told her to keep in mind ("protein-heavy", "under ₹400", "light dinners"). You tap *Pakka* and she places the order. You tap *Something else* and she swaps once. That's the entire product surface.

Two non-negotiables under the hood:
- **Every dish she suggests is real and in stock right now** — validated through Swiggy MCP before you ever see it.
- **No order is placed without an explicit second confirmation** — the cart screen shows total, address, payment method, and only `Confirm — place order` actually charges.

---

## How it works

mom is a **LangGraph state machine** with two human-in-the-loop pauses (suggestion + cart confirm) and one optional swap loop. The entire run state lives in Postgres via the LangGraph checkpointer, so resume after the user tap is exact — same restaurant, same cart, same prices.

```
START
  ↓
interpret_prompt        ← router LLM parses nudge → ParsedCriteria
  ↓
discover                ← Swiggy MCP search_restaurants, filter OPEN
  ↓
shortlist               ← prefilter rating ≥ 3.5, router LLM ranks → top 3
  ↓
pick_dish               ← Swiggy MCP search_menu × 3, picker LLM picks ONE
  ↓
compose_proposal        ← render voice strings from YAML pack
  ↓
⏸ propose_to_user                                  [INTERRUPT 1]
  ↓ (accept | swap | cancel)
  ├ accept → build_cart → review_cart
  │           ↓
  │       ⏸ confirm_order                           [INTERRUPT 2]
  │           ↓ (confirm | cancel)
  │           ├ confirm → place_order → END (PLACED)
  │           └ cancel  → END (CANCELLED)
  ├ swap   → discover (with prior in excluded_proposals; max 1 swap)
  └ cancel → END (CANCELLED)
```

A run is launched by `POST /agent/runs` (currently from the **Khila do** button — a scheduler is on the roadmap). The frontend polls `/agent/runs/{id}` every 1.5s for status and `/agent/runs/{id}/activity` for the live audit trail surfaced in the loader.

### The screens

| Screen | Component | What you see |
|---|---|---|
| Today | `app/today/page.tsx` | Slot cards (breakfast/lunch/snack/dinner), address picker, **Khila do** trigger |
| Loading | `MomThinking` | Live trace of the agent's nodes — "scanning 47 places open", "kept the top 8", … |
| Suggestion | `Suggestion` | One dish, one reason, one price. *Pakka* or *Something else*. |
| Cart confirm | `CartConfirm` | Itemised total + address + payment. Last chance to bail. |
| Placed | `Pakka` | Order id, ETA, link to track in Swiggy |
| Failed / cancelled | `GiveUp` | Honest copy per failure reason (`swap_exhausted`, `nothing_orderable`, …) |

### The stack

| Layer | Choice |
|---|---|
| Frontend | Next.js 15 PWA (App Router), Tailwind, SWR |
| Backend | FastAPI on Python 3.12, async throughout |
| Agent | LangGraph with Postgres checkpointer, `interrupt_before` for user pauses |
| LLM | Azure OpenAI — small router (`o4-mini`) + stronger picker (`gpt-5.4`) |
| Tools | Swiggy MCP (Food + Dineout) via `langchain-mcp-adapters` |
| Storage | Postgres 16 — LangGraph checkpoints + `agent_runs`/`agent_audit`/`agent_placed_orders` |
| Voice | YAML packs server-rendered into `Proposal` strings — frontend stays brand-agnostic |
| Pkg mgmt | `uv` (backend), `pnpm` (frontend) |

### Safety rails

- **`AGENT_LIVE_ORDERS_ENABLED=false`** by default. `place_order` returns `DRYRUN_<hex>` and never calls Swiggy.
- **`AGENT_BLOCK_COD=true`** by default. Cash-on-Delivery is stripped from the cart — mom requires pre-payment so a confirmed order is actually committed.
- **`AGENT_MAX_SWAP_COUNT=1`**. Beyond one swap, fatigue dominates. mom gives up gracefully.
- **`AGENT_INTERRUPT_TIMEOUT_MIN=60`**. If you don't respond, the run ends with `interrupt_timeout` instead of hanging forever.

---

## What's next

- Server-side scheduler — currently the user has to tap **Khila do**; the cron + Web Push that nudges across closed-tab is the next milestone
- Cross-meal learning — context updates from accept/reject signals (the agent already writes the audit; reading it back into the prompt is pending)
- Dineout mode — the MCP tools are wired but the second graph branch is stubbed
- Pantry top-up — `your_go_to_items` + `get_orders` for one-tap Instamart restocks
- Group mode — two flatmates, one compromise

---

*Built with love, mild guilt, and a lot of dal.*
