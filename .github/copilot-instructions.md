# Copilot Instructions — bawarchi.

## What This Project Is

**bawarchi.** is an AI agent that picks one meal suggestion at the user's configured nudge time — like a trusted Indian household cook (a *bawarchi*) deciding what they should eat. It connects to Swiggy at runtime, maintains its own food context from nudges and accept/reject signals, and applies a monthly "nudge" as a soft preference. The user sees one suggestion, taps "Okay, Bawarchi" to review and confirm the order, or "Something else" for one alternative.

## Architecture

- **Frontend**: Next.js 15 PWA (App Router) — installable on iOS + Android, hosted on Azure Static Web Apps
- **Backend**: FastAPI (Python 3.12) on Azure Container Apps — consumption tier, scale-to-zero, holds long-running agent runs in memory
- **Agent runtime**: LangGraph (Python) with Postgres checkpointer — the nudge flow is a state machine with two `interrupt_before` pauses (suggestion confirm + cart confirm)
- **Scheduler**: Azure Functions Timer Trigger (Python) — runs every minute, finds users due in next 60s, POSTs to the Container App's `/agent/run`
- **MCP integration**: `langchain-mcp-adapters` exposes Swiggy MCP tools (Food + Dineout) as LangChain tools the graph can call
- **LLM**: Azure OpenAI — GPT-4o-mini for routing, GPT-4o for the dish pick
- **Storage**: Azure Database for PostgreSQL Flexible Server — `users`, `food_context` (JSONB), `suggestions`, `push_subscriptions`, `langgraph_checkpoints`
- **Push notifications**: Web Push via `pywebpush` — VAPID keypair from Azure Key Vault. Works on iOS 16.4+ and Android. **No Notification Hubs / FCM / APNs.**
- **Secrets**: Azure Key Vault — Swiggy tokens (encrypted), VAPID, OpenAI key
- **Package mgmt**: `uv` for backend, `pnpm` for frontend
- **IaC**: Bicep / `azd`

## Key API Endpoints

FastAPI service on Container Apps:

- `POST /auth/swiggy/callback` — Swiggy OAuth callback, stores encrypted token
- `POST /onboarding/{step}` — schedule, address, goal, budget — write to `users` and `food_context`
- `POST /push/subscribe` — store the user's Web Push subscription (endpoint + p256dh + auth keys)
- `POST /agent/run` — invoked by the Timer Trigger; starts a LangGraph run for one user
- `POST /agent/resume` — invoked by the PWA when the user taps "Okay, Bawarchi" or "Confirm — place order"
- `GET /suggestions/latest` — what the PWA fetches when the notification is tapped

## Core Design Decisions

1. **One suggestion, not a list** — the entire product philosophy is removing choice
2. **Nudge = soft constraint** — injected into the LLM prompt as a bias, never a hard filter
3. **Onboarding is five steps** — Connect Swiggy → When → Address → Goal → Budget
4. **No historical Swiggy Food import** — current Food MCP docs do not expose long-term past Food orders; learn from Bawarchi-owned interactions instead
5. **No ML training** — learning loop is an append log in `food_context` JSONB; the LLM reads recent suggestions, nudges, and feedback directly in the prompt window
6. **MCP over REST wrappers** — the LangGraph agent orchestrates Swiggy Food + Dineout tool calls mid-reasoning; backend stays thin
7. **Food context is JSONB in Postgres** — human-readable, rebuilt from the app event log, queryable when needed but used as a flat blob most of the time
8. **PWA, not native** — single Next.js codebase, installable, Web Push covers nudges on iOS 16.4+ and Android. Onboarding ends with "Add Bawarchi to your home screen" (notifications no-op without it on iOS).
9. **LangGraph state machine, not single LLM call** — two `interrupt_before` pauses (suggestion confirm + cart confirm) make the flow durable: the Postgres checkpointer persists state so resume is exact and the user never sees a different dish on retry.
10. **Scheduler is dumb** — Azure Functions Timer is just a fan-out cron; all logic lives in the Container App graph.

## Swiggy MCP Reference

Before writing any Swiggy integration code, consult `swiggy-mcp-docs.md` in the repo root and fetch the linked `.md` docs for authoritative tool schemas. Do not invent Swiggy tool names. Key documented tools:

- Food: `get_addresses`, `search_restaurants`, `search_menu`, `get_restaurant_menu`, `update_food_cart`, `get_food_cart`, `place_food_order`, `track_food_order`
- Dineout: `get_saved_locations`, `search_restaurants_dineout`, `get_available_slots`, `book_table`, `get_booking_status`

Always call `get_food_cart` before `place_food_order`, show items/total/payment method/address, and require explicit user confirmation. Food Builders Club orders have a ₹1000 cap in current docs.

## Nudge Flow (LangGraph State Machine)

The agent is a single LangGraph compiled with a Postgres checkpointer and `interrupt_before=["confirm_suggestion", "place_order"]`.

```
load_context        → get_addresses → search_restaurants → search_menu
  ↓
pick_dish           ← LLM call (Azure OpenAI), context + nudge + open menu items
  ↓
propose_to_user     ← pywebpush sends "Bawarchi's calling 📞"
  ↓
[INTERRUPT confirm_suggestion]   ← graph state checkpointed to Postgres, Container App returns
  ↓ (user taps "Okay, Bawarchi" → POST /agent/resume)
update_food_cart → get_food_cart
  ↓
[INTERRUPT place_order]          ← cart confirmation screen rendered in PWA
  ↓ (user taps "Confirm — place order" → POST /agent/resume)
place_food_order → track_food_order (loop, ≥10s cadence)
  ↓
log_to_context     ← append accepted/swapped/skipped signal to food_context
```

Resume from interrupt is **exact** — same restaurant, same cart, same prices. No re-prompting the LLM. "Something else" jumps back to `pick_dish` with an excluded-dish list.

## Nudge Setup

Keep onboarding simple and preset-driven:

| Input | Presets | Stored as |
|---|---|---|
| Frequency | Everyday, Weekends, Custom days | `frequency` + `days` |
| Meal windows · multi-select | Breakfast, Lunch, Dinner, Custom — each with its own time | `meals[]` with per-meal `local_time` |
| Food goals · pick up to 3 | Protein-heavy, Light meal, High fiber, Spend less, Cook more, Vegetarian, Custom (exclusive) | `active_goals[]` (max 3) |
| Budget | No limit, Under ₹300, Under ₹400, Custom | `budget_cap_inr` or `null` |

Good default: Everyday Dinner at 7:00 PM with no budget cap. Multi-meal example: lunch at 1:30 + dinner at 7. Goals are capped at 3 to prevent conflicting nudges. **Custom goal is exclusive** — if selected, presets are disabled and the free-text becomes the entire `active_nudge`. Convert preset choices into a natural phrase like "protein-heavy lunch + light dinner under ₹400".

## Food Context Schema

```json
{
  "schedule": {
    "frequency": "everyday",
    "days": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
    "meals": [
      {"meal": "lunch", "local_time": "13:30"},
      {"meal": "dinner", "local_time": "19:00"}
    ]
  },
  "liked_dishes": ["dal khichdi", "paneer tikka"],
  "rejected_dishes": ["pasta"],
  "preferred_cuisines": ["north indian", "comfort"],
  "budget_cap_inr": 400,
  "recent_suggestions": [
    {"dish": "palak paneer", "signal": "accepted"},
    {"dish": "pasta", "signal": "rejected"}
  ],
  "active_goals": ["protein-heavy", "light meals", "high fiber"],
  "active_nudge": "Protein-heavy, light, high-fiber meals — lunch at 1:30 and dinner at 7. Under ₹400.",
  "notes": ["prefers lighter dinners on weekdays"]
}
```

## LLM Prompt Pattern

The system prompt uses a "trusted Indian household cook (bawarchi)" persona — warm, decisive, like family but not parental. The user prompt includes the food context, active nudge, day/time context, and available MCP tools. Output is structured JSON with: `suggestion`, `source` (`order_in` | `dine_out`), `restaurant`, `reason`, `eta_mins` when available, and `price`.

## Voice & Copy

Bawarchi is **family-staff, not family**. Voice is light Hinglish, food-host energy, decisive but warm. Never parental, never servile. The product is built for urban Indian millennials including non-Hindi-first users (Bangalore, Chennai, Hyderabad), so single-word Hindi anchors are fine but full Hindi clauses are not.

**Hinglish budget rule of thumb:**
- ✅ Single Hindi anchor + English clause (`"Bolo, what's the budget?"`, `"Aao."`, `"Pakka."`)
- ✅ Pan-India recognized particles (`na`, `aaj`, `bolo`, `pakka`, `achha`, `aao`)
- ❌ Full Hindi clauses with no English anchor (`"kitna kharch karna hai"`, `"yeh banaya"`)
- ❌ Hindi words a Tamil/Bengali user can't reverse-engineer from context

**Do:**
- Use Indian-language anchors for short emotional moments: `Aao` (welcome), `Bolo` (tell me), `Pakka` (confirmed), `Aaj ke liye` (for today)
- Frame the agent as the cook who *decides and feeds*: `"Aaj ke liye, this one."`, `"Pakka. On the way."`
- Keep CTAs short and action-y: `Okay, Bawarchi`, `Something else`, `All set, Bawarchi →`
- Use Hinglish in voice quotes (`"Bolo, when should I call?"`), plain English for instructional UI labels (`Your saved addresses`, `Total`)

**Don't:**
- Use `beta`, `bachcha`, or any child-coded address (parental, doesn't fit a cook)
- Use `sahab`, `saab`, `babu`, or any servile/colonial address
- Lean on guilt or nag mechanics ("you skipped breakfast again" — never)
- Use gendered pronouns (`she`/`he`) for the agent — bawarchi is gender-neutral, use `they/them`
- Write voice copy that requires Hindi to parse — full Hindi clauses go in a v2 voice-pack, not the default

**Reference voice samples (current mockup):**
- Splash: `Aao. Let's set you up.`
- When-screen quote: `"Bolo, when should I call?"`
- Days quote: `"Tell me your busy days, na."`
- Address quote: `"Bolo, where do I send food?"`
- Budget quote: `"Bolo, what's the budget?"`
- Suggestion hero: `Aaj ke liye, this one.`
- Order placed: `Pakka. On the way.`
- Weekly recap: `You ate well this week.`

## Code Conventions

### Backend (Python)

- **Python 3.12+**, managed with `uv` (`uv sync`, `uv add`, `uv run`)
- **FastAPI** with Pydantic v2 models for every request/response
- **SQLModel** (or SQLAlchemy 2.0 async) for DB access — never raw SQL strings
- **Async everywhere** — all FastAPI handlers, all DB calls, all MCP calls
- **LangGraph state** is a Pydantic model — declared once in `app/agent/state.py`
- **One node per file** under `app/agent/nodes/` — keeps the graph readable
- **MCP client** is created per-request with the user's Swiggy token; never cache across users
- **Logging**: structured logs (`structlog`), one log line per node entry/exit with the run ID

### Frontend (Next.js PWA)

- **Next.js 15** App Router, **React 19**, TypeScript strict mode
- **Tailwind** for styling — design tokens already defined in `frames/screens.html` (cream `#F4EBDB`, terracotta `#C8501F`, sage `#4A7C59`)
- **Fonts**: Fraunces serif for Bawarchi's voice / hero text; Inter for everything else
- **PWA wrapper**: `@serwist/next` for service worker + manifest
- **Push subscriptions** registered in the SW, sent to `/api/push/subscribe`
- **Server actions / route handlers** proxy to the FastAPI Container App; no business logic in Next.js
- **Type safety with backend**: generate TS types from Pydantic via `pydantic-to-typescript` into `shared/types/` — single source of truth lives in Python

### Shared rules

- **Never invent Swiggy MCP tool names** — see `swiggy-mcp-docs.md` and the live `.md` references
- **Never call `place_food_order` without an explicit user confirmation event** — must be triggered by `/agent/resume` after the cart-confirm interrupt, never from any other node
- **₹1000 cart cap** — validate before `place_food_order`, surface a clear error if exceeded
- **Address comes from `get_addresses`** — never collect a new address in our UI; redirect to Swiggy app
- **Push payloads stay under 4KB** — push wakes the user; the full suggestion is fetched from `/suggestions/latest` on tap
- **Nudge time is server-authoritative** — never trust the device clock; LangGraph runs are triggered server-side

## Cost Targets (MVP)

Keep monthly Azure spend under ~$20 at MVP scale (single-digit DAU):

- Static Web Apps Free tier (frontend) — $0
- Container Apps consumption with scale-to-zero — ~$0–5
- Functions Timer Trigger (free grant covers cron) — $0
- Postgres Flexible Burstable B1ms — ~$12
- Azure OpenAI (~1k nudges/mo @ ~3k tokens) — ~$3
- Key Vault — < $1
