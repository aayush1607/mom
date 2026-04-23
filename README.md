# mom.

> *One call a day. One tap. Dinner, handled.*

---

## The Problem

I'm 24, living in Bangalore with friends. Most evenings — especially weekends or when the cook doesn't show up — the question *"what do we eat tonight?"* becomes a 30-minute rabbit hole of scrolling through Swiggy, opening menus, closing them, second-guessing, and eventually ordering something mediocre out of exhaustion.

The decision fatigue is real. I know roughly what I want — maybe something lighter this week, maybe more protein — but translating that vague feeling into an actual order across hundreds of restaurants is draining.

What I actually want is my mom. She knows what I've been eating. She knows when I'm being lazy vs. when I'm trying to be healthy. She'd just call and say: *"Beta, order this."* And I would. No friction.

---

## The Solution

**mom.** is an AI agent that acts like your mom deciding dinner for you.

It connects to your Swiggy history, learns your patterns, absorbs a single "nudge" you configure for the month, and every evening presents you with **one suggestion** — not a list, not a menu, just one thing. You tap *Okay, Mom* and it's ordered. If it's off, you tap *Something else* and get one alternative. That's it.

It works across:
- **Order In** — Swiggy food delivery
- **Pantry** — Instamart grocery order if you have ingredients at home
- **Dine Out** — a nearby restaurant suggestion if you're stepping out

Every choice (accept or reject) teaches it more. Mom gets smarter.

---

## Screens

| Screen | What it does |
|---|---|
| **Splash** | Connects with your Swiggy account. Reads last 6 months of orders. |
| **The Suggestion** | One meal recommendation, personalized reasoning, ETA + price. Accept or ask for something else. |
| **Done, beta.** | Order confirmed. Live tracking in Mom's voice. |
| **A Nudge** | Configure one dietary/lifestyle steer for the month (e.g. "more protein", "spending less"). Mom factors this in, doesn't obsess. |
| **The Kitchen** | Weekly history view. What Mom ordered, when you said something else, your patterns. |

### Preview

<table>
  <tr>
    <td align="center"><img src="frames/onboarding.jpg" width="180"/><br/><sub><b>Splash — Onboarding</b></sub></td>
    <td align="center"><img src="frames/daily-call.jpg" width="180"/><br/><sub><b>The Suggestion</b></sub></td>
    <td align="center"><img src="frames/order-screen.jpg" width="180"/><br/><sub><b>Done, beta.</b></sub></td>
    <td align="center"><img src="frames/nudge-config.jpg" width="180"/><br/><sub><b>A Nudge</b></sub></td>
    <td align="center"><img src="frames/kitchen.jpg" width="180"/><br/><sub><b>The Kitchen</b></sub></td>
  </tr>
</table>

---

## Technical Overview

The goal: feel like magic. Work on first principles. Stay embarrassingly simple under the hood.

### 1. Data Foundation — "What has this person actually been eating?"

**On signup**, pull the last 6 months of Swiggy order history via the Swiggy MCP connector:
- Dish names, cuisine types, restaurants
- Order timestamps (day of week, time of day)
- Order frequency and recency

Store this as a lightweight **user food profile** — a structured JSON blob, not a vector DB. Keep it human-readable.

```
{
  "frequent_dishes": ["dal khichdi", "paneer tikka", "pasta"],
  "preferred_cuisines": ["north indian", "comfort"],
  "avg_order_time": "7:30 PM",
  "price_range": "₹250–₹400",
  "last_7_days": ["pasta", "pasta", "palak paneer"],
  "active_nudge": "more protein"
}
```

This profile is rebuilt/refreshed once daily in the background.

---

### 2. The Recommendation Engine — "What should she eat tonight?"

At ~6:30 PM every day, a single LLM call is made. No retrieval, no embeddings, no RAG. Just a well-constructed prompt.

**System prompt** (the "Mom persona"):
> You are a caring Indian mom who knows exactly what your child has been eating. You want to pick one good dinner for them — practical, balanced, not repetitive. You have a soft nudge they've asked you to keep in mind. Don't overthink. Just decide.

**User prompt** (the food profile + context):
> Here's what Beta has been eating this week: [last 7 days]. Their active nudge is: more protein. It's a Thursday evening. What's one good dinner — ordered in, made at home from pantry, or dine out?

**LLM output** (structured JSON):
```json
{
  "suggestion": "Paneer tikka + dal",
  "source": "order_in",
  "restaurant": "Gulabs, Khar",
  "reason": "protein-heavy, dal for warmth",
  "eta_mins": 28,
  "price": 340
}
```

The LLM does two things in one pass:
- **Avoids repetition** — it sees the last 7 days and steers away
- **Steers toward the nudge** — it biases toward the configured goal without being rigid

This is the core magic. One prompt. One output. No multi-step pipeline.

---

### 3. The Nudge — "Steering, not obsessing"

The nudge is a single plain-text preference set by the user:
- Picked from presets: *more protein / keto-ish / lighter meals / vegetarian week / spending less / cook more at home*
- Or typed freely: *"less sugar, more greens"*

It's injected into the daily LLM prompt as a soft constraint. The model is instructed to *lean toward* it, not enforce it strictly. If the best match tonight happens to have some carbs, that's fine — Mom uses judgment, not rules.

Nudge resets or updates monthly. One nudge at a time.

---

### 4. Learning Loop — "Mom gets smarter"

Every interaction updates the food profile:

| User action | What it signals | Profile update |
|---|---|---|
| *Okay, Mom* | Good suggestion | Reinforce dish type, cuisine, price point |
| *Something else* | Mild miss | Note: user wasn't in the mood for this |
| Ignored the notification | No preference | Light signal, don't over-index |

This is a simple append log — no ML training, no fine-tuning. The profile JSON grows richer over time and the LLM naturally picks up on patterns because it can read the recent history directly in the prompt.

---

### 5. The Stack

| Layer | Choice | Why |
|---|---|---|
| **Backend** | Azure Functions (Python) | Serverless, pay-per-use, easy cron via Timer Trigger |
| **LLM** | Claude Sonnet (via Anthropic API) | Best-in-class instruction following, Indian food context |
| **Food data** | Swiggy MCP connector | Live order history + restaurant catalog + real ETAs |
| **Pantry** | Instamart MCP connector | Ingredient availability |
| **Dine Out** | Swiggy Dineout or Google Places | Nearby restaurant fallback |
| **Storage** | Azure Blob Storage (JSON per user) | No database needed at MVP scale |
| **Notifications** | Azure Notification Hubs → FCM / APNs | The daily "call from Mom" |

---

### 6. The Daily Flow

```
6:30 PM  →  Cron triggers for active users
             Pull fresh order history delta (last 24h)
             Update food profile JSON
             
6:31 PM  →  LLM call with profile + nudge + time context
             Get structured suggestion JSON
             
6:32 PM  →  Push notification: "Mom picked dinner 🍲"
             User opens app → sees The Suggestion screen
             
User taps "Okay, Mom"
             →  Swiggy API places order
             →  Show tracking (Done, beta. screen)
             →  Log: positive signal → update profile

User taps "Something else"
             →  Second LLM call: "Give one alternative, different from the first"
             →  Show alternative
             →  Log: mild negative → update profile
```

---

## Tech Stack & Architecture

### Stack at a Glance

| Layer | Choice |
|---|---|
| **Mobile app** | React Native (iOS-first MVP) |
| **Backend** | Azure Functions — Python |
| **Scheduler** | Azure Timer Trigger — 6:30 PM IST daily |
| **LLM** | Claude Sonnet via Anthropic API |
| **Food data** | Swiggy MCP connector |
| **Grocery data** | Instamart MCP connector |
| **Dine-out fallback** | Google Places API |
| **Storage** | Azure Blob Storage — `user_profile.json` per user |
| **Push notifications** | Azure Notification Hubs → FCM / APNs |

---

### Architecture Diagram

```
┌─────────────────────────────────────────────────────┐
│                   React Native App                  │
│   Onboarding → Suggestion → Order → Kitchen/Nudge   │
└───────────────────┬─────────────────────────────────┘
                    │ REST
┌───────────────────▼─────────────────────────────────┐
│           Azure Functions — Python (API)            │
│  • /auth/swiggy   • /suggestion   • /feedback       │
└───────┬───────────────────────┬─────────────────────┘
        │                       │
┌───────▼────────┐   ┌──────────▼──────────────────┐
│  Swiggy MCP    │   │     Anthropic API            │
│  Connector     │   │  Claude Sonnet               │
│                │   │  (profile + nudge → JSON)    │
│  • order_history    └─────────────────────────────┘
│  • place_order │
│  • restaurant  │   ┌─────────────────────────────┐
│    catalog     │   │  Azure Blob Storage          │
│  • live ETA    │   │  user_profile.json           │
└────────────────┘   │  { frequent_dishes,          │
                     │    active_nudge,             │
┌────────────────┐   │    last_7_days, ... }        │
│ Instamart MCP  │   └─────────────────────────────┘
│  • pantry stock│
│  • grocery cart│   ┌─────────────────────────────┐
└────────────────┘   │  Azure Timer Trigger         │
                     │  6:30 PM IST → Function      │
                     │  → profile refresh + LLM     │
                     │  → Notification Hubs push    │
                     └─────────────────────────────┘
```

---

### Swiggy MCP Integration

MCP (Model Context Protocol) lets Claude call Swiggy as a **tool** directly inside the LLM prompt cycle — no custom scraping, no brittle REST wrappers.

**What the Swiggy MCP connector exposes:**

| Tool | When mom. uses it |
|---|---|
| `swiggy.get_order_history(user_id, days=180)` | Onboarding — build the initial food profile |
| `swiggy.get_order_history(user_id, days=1)` | Daily cron delta refresh |
| `swiggy.search_restaurants(query, lat, lng)` | Validate the LLM's restaurant suggestion is real + open |
| `swiggy.get_restaurant_menu(restaurant_id)` | Confirm the suggested dish is on tonight's menu |
| `swiggy.get_eta(restaurant_id, address)` | Fetch live ETA to show on the Suggestion screen |
| `swiggy.place_order(cart)` | Execute the order when user taps *Okay, Mom* |
| `instamart.check_availability(ingredients[])` | Pantry mode — see if items are in stock nearby |

**How it fits in the daily flow:**

```
6:30 PM cron
  └─► Azure Function calls swiggy.get_order_history(delta=24h)
        → appends to user_profile.json on Azure Blob Storage

  └─► Function builds LLM prompt (profile + nudge + tools available)
        → Claude reasons over history, may call:
             swiggy.search_restaurants(...)   ← verify suggestion
             swiggy.get_eta(...)              ← attach real ETA
        → returns structured suggestion JSON

User taps "Okay, Mom"
  └─► Lambda calls swiggy.place_order(cart)
        → order placed, tracking ID returned
        → shown on "Done, beta." screen
```

**Why MCP over a direct API wrapper:**
Claude can decide *when* to call each tool mid-reasoning — e.g. it might search restaurants only if the top suggestion is delivery, or skip the menu check if the dish is generic enough. This keeps the backend code thin: one prompt, Claude orchestrates the tool calls, one JSON output comes back.

---

## What Makes This Work

- **One suggestion, not a list.** Decision fatigue comes from choice. Remove the choice.
- **The voice matters.** "Okay, Mom" vs "Place Order" is the whole product. The language makes it feel like trust, not a transaction.
- **The nudge is a steer, not a filter.** Hard dietary filters break recommendations. A soft nudge bends them.
- **Learning from rejection is as important as learning from acceptance.** Every "something else" is data.
- **The LLM reads history like a human.** No embeddings needed — the recent order log fits in a prompt window and the model reasons over it naturally.

---

## What's Next

- Morning suggestion option (breakfast / lunch)
- "Mom's note" — a one-line explanation of why she picked it, always shown
- Group mode — two flatmates, one compromise suggestion
- Pantry-first mode — check Instamart for ingredients before defaulting to delivery
- Weekly kitchen report card with a Mom-style note

---

*Built with love, mild guilt, and a lot of dal.*
