# meal-agent backend

The brand-agnostic meal-decision agent that powers **mom.** (and any
future brand layered on top of it). A FastAPI service wrapping a LangGraph
agent that takes a prompt + user context, finds real Swiggy restaurants/
dishes via MCP, proposes one suggestion, and (after two human-in-the-loop
confirmations) places the order.

> Zero brand strings live in agent code. Persona is injected per request,
> voice strings are server-rendered from YAML packs.

---

## Architecture at a glance

```
┌────────────────────┐    POST /agent/runs      ┌───────────────────┐
│  Caller (FE / cron)│ ───────────────────────▶ │  FastAPI routes   │
└────────────────────┘ ◀──── 202 + run_id ───── └─────────┬─────────┘
         ▲                                                │
         │ web push                                       ▼ BackgroundTasks
         │                                       ┌───────────────────┐
         │                                       │  LangGraph agent  │
         │                                       │  (8 nodes,        │
         │   POST /agent/runs/{id}/resume        │   2 interrupts)   │
         └────────────────────────────────────── └─────────┬─────────┘
                                                           │
                            ┌──────────────┬───────────────┼───────────────┐
                            ▼              ▼               ▼               ▼
                      ┌──────────┐  ┌────────────┐  ┌────────────┐  ┌──────────┐
                      │ Azure    │  │ Swiggy MCP │  │ Postgres   │  │ Voice    │
                      │ OpenAI   │  │ (Food +    │  │ (LG ckpt + │  │ packs    │
                      │ (router+ │  │  Dineout)  │  │  audit)    │  │ (YAML)   │
                      │  picker) │  │            │  │            │  │          │
                      └──────────┘  └────────────┘  └────────────┘  └──────────┘
```

### Node graph

```
START
  ↓
interpret_prompt   ★  full LLM (router model, structured output → ParsedCriteria)
  ↓
discover           ★  search_restaurants → filter OPEN → score → Restaurant[]
  ↓
shortlist          ★  prefilter (rating>=3.5) → router LLM ranks → top 3
  ↓
pick_dish          ★  search_menu × 3, picker LLM picks ONE DishCandidate
  ↓
compose_proposal   ★  render Proposal voice strings from VoicePack templates
  ↓
⏸ propose_to_user                                   [INTERRUPT 1]
  ↓ (accept | swap | reject | cancel)
  ├ accept → build_cart → review_cart → ⏸ confirm_order [INTERRUPT 2]
  │                                       ↓ (confirm | cancel)
  │                                       ├ confirm → place_order ★ → END
  │                                       └ cancel  → END (CANCELLED_BY_USER)
  ├ swap   → (swap_count < max?) → discover (with prior in excluded_proposals)
  │           else → END (FAILED, SWAP_EXHAUSTED)
  └ reject/cancel → END (CANCELLED_BY_USER)
```

★ = full implementation • ◯ = stub with TODO. As of this revision, **all 8 functional nodes are full implementations.**

### Locked design decisions

| Decision | Choice | Why |
|---|---|---|
| Thread model | one LangGraph thread per **nudge** | swap loop + 2 interrupts fit cleanly per ask |
| Swap budget | **1** | beyond that, fatigue dominates user satisfaction |
| API mode | fully **async** (202 + push) | scheduled nudges arrive while user is offline |
| Voice strings | **server-rendered** from YAML packs | FE stays brand-agnostic; copy churns server-side |
| Prompt input | optional NL + structured `context` | one node handles scheduled and chat cases uniformly |
| Persona | injected per request via `PersonaInput` | brand renamable from frontend, no agent redeploy |
| Failure modes | 5 distinct `FailureReason` enums | each maps 1:1 to a voice key for honest copy |
| Idempotency | `(thread_id, cart_hash)` in Postgres | Food MCP `place_food_order` is non-idempotent |

---

## Layout

```
src/meal_agent/
  settings.py           # pydantic-settings — single env var entrypoint
  agent/
    state.py            # AgentState + all enums + Pydantic models
    graph.py            # build_graph() — wires 8 nodes + 2 interrupts
    nodes/
      __init__.py       # Deps container
      interpret_prompt.py  ★
      discover.py          ★
      shortlist.py         ★
      pick_dish.py         ★
      compose_proposal.py  ★
      build_cart.py        ★
      review_cart.py       ★
      place_order.py       ★
    templates/
      interpret.py      # pure-function prompt builder for interpret_prompt
  persona/
    schema.py           # VoicePack + sub-models
    loader.py           # load_pack(id) — YAML reader, lru_cached
    packs/
      mom-v1.yaml       # first concrete brand pack
  tools/
    llm.py              # AzureChatOpenAI factory (router + picker)
    swiggy_mcp.py       # MultiServerMCPClient wrapper, per-user OAuth
  storage/
    checkpointer.py     # AsyncPostgresSaver factory
    audit.py            # agent_runs + agent_audit + idempotency tables
  tools/{llm, swiggy_mcp, mcp_envelope}.py
  api/
    app.py              # FastAPI app + lifespan
    routes.py           # 4 endpoints
scripts/
  probe_mcp.py          # live MCP shape probe (gated on SWIGGY_OAUTH_TOKEN)
tests/
  conftest.py           # fake LLM, fake MCP, in-memory audit, sample voice
  test_interpret_prompt.py
  test_nodes_impl.py    # all 6 implemented nodes — happy + failure paths
  test_agent_e2e.py     # place_order idempotency contract
  test_graph_integration.py  # full graph through both interrupts (InMemorySaver)
```

---

## Run locally

```bash
cd backend
uv sync                                     # install deps
cp .env.example .env                        # then fill values
uv run pytest -q                            # run tests
uv run uvicorn meal_agent.api.app:app --reload
```

### Required env vars

| Var | Purpose |
|---|---|
| `AZURE_OPENAI_ENDPOINT` | Azure OpenAI endpoint URL |
| `AZURE_OPENAI_API_KEY` | Azure OpenAI key |
| `AZURE_OPENAI_DEPLOYMENT_ROUTER` | cheap model, default `gpt-4o-mini` |
| `AZURE_OPENAI_DEPLOYMENT_PICKER` | stronger model, default `gpt-4o` |
| `POSTGRES_DSN` | `postgresql://user:pass@host:5432/db` |
| `SWIGGY_MCP_FOOD_URL` | default `https://mcp.swiggy.com/food/sse` |
| `SWIGGY_MCP_DINEOUT_URL` | default `https://mcp.swiggy.com/dineout/sse` |
| `AGENT_MAX_SWAP_COUNT` | default `1` |

The Swiggy OAuth token is **not** an env var — callers pass it in the
request body (per-user, per-run).

---

## API

### `POST /agent/runs` — start a run

```jsonc
{
  "input": {
    "user_id": "u_abc",
    "address_id": "addr_123",
    "address_label": "Home — Bandra W",
    "prompt": "Quick lunch, light, under 400",   // optional
    "context": {
      "active_nudge": "more protein",
      "meal_slot": "lunch",
      "recent_rejects": [{ "dish": "Veg Biryani", "ts": "2025-01-10T12:00:00Z" }]
    },
    "constraints": { "max_price_inr": 400, "max_eta_min": 45, "vegetarian": false },
    "persona": {
      "system_prompt": "You are mom, a meal-decision assistant...",
      "voice_pack_id": "mom-v1",
      "name": "mom"
    }
  },
  "user_token": "<swiggy oauth token>"
}
```

→ `202 Accepted` `{ "run_id": "run_xxx", "thread_id": "th_xxx", "status": "running" }`

The agent runs in the background until it hits the propose interrupt, then
parks. The caller subscribes via web push for the `proposal_ready` signal.

### `POST /agent/runs/{run_id}/resume` — feed a decision

```jsonc
{ "decision": "accept" | "swap" | "reject" | "confirm" | "cancel",
  "note": "optional free text",
  "user_token": "<swiggy oauth token>" }
```

→ `202 Accepted`

The graph resumes past the interrupt and runs to the next interrupt or
terminal state.

### `GET /agent/runs/{run_id}` — read latest state

→ `200 OK` `{ run_id, thread_id, status, state: { /* full AgentState dump */ } }`

### `POST /agent/runs/{run_id}/cancel` — abort

→ `202 Accepted`

---

## Adding a new brand / voice

1. Drop a new YAML at `src/meal_agent/persona/packs/<brand>-v1.yaml`.
2. Validate it loads: `python -c "from meal_agent.persona.loader import load_pack; print(load_pack('brand-v1'))"`.
3. The caller now passes `persona.voice_pack_id = "brand-v1"`. No agent
   redeploy needed.

The `VoicePack` schema (`src/meal_agent/persona/schema.py`) is the contract.
A pack must populate every key — there are no fallbacks, by design (a
half-localised brand is worse than an obviously-missing one).

---

## Extending a stub node

Each `◯` node currently returns a no-op state update. The full implementation
notes are inlined in each file's docstring. Pattern:

```python
async def run(state: AgentState, deps: Deps) -> dict[str, Any]:
    await deps.audit.write_event(run_id=deps.run_id, node=NODE_NAME, event="enter", payload={...})
    # ... LLM / MCP work ...
    await deps.audit.write_event(run_id=deps.run_id, node=NODE_NAME, event="exit", payload={...})
    return {"<state_field>": <new_value>}
```

The `Deps` container holds: `llms` (router + picker), `swiggy` (food + dineout
tool dicts), `audit`, `voice` (resolved VoicePack), `run_id`.

---

## Testing strategy

| Layer | Approach |
|---|---|
| Pure templates | snapshot-style assertions on `render_interpret_user_prompt` |
| Nodes | inject fake `Deps` (fake LLM with `next_response`, fake MCP tools, in-memory audit). Real envelope shape `{success, data}` is exercised end-to-end. |
| Graph wiring | `tests/test_graph_integration.py` runs the full graph with `InMemorySaver` through both interrupts (happy path / swap loop / reject) — no Postgres required |
| Real Postgres | future: same suite under `@pytest.mark.integration` with `AsyncPostgresSaver` against docker-compose |
| Idempotency | `test_agent_e2e.py::test_place_order_idempotent_replay` |

Real LLM/MCP integration tests live behind a `@pytest.mark.live` marker so
they don't run on every push.

---

## Out of scope (this scaffold)

- Web Push sender (separate `/push/send` endpoint, future PR)
- Onboarding endpoints (separate service)
- Real DB migrations (DDL is bundled in `storage/audit.py` for v1)
- Bicep / azd files
- Pantry / Instamart support (parked for v2)
