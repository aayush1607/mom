"""Node 7: `review_cart` — read-back the cart, build CartSnapshot.

This produces the `cart_hash` that `place_order` uses for idempotency.
The hash is over a canonical (sorted, normalized) representation of items +
total + address. Two runs with semantically identical carts get the same
hash; any change (item, quantity, address, total) yields a fresh hash.

Hard-stop guards:
  * total > constraints.max_price_inr   → FailureReason.NOTHING_ORDERABLE
  * "ADDRESS_NOT_SERVICEABLE" in error  → FailureReason.ADDRESS_NOT_SERVICEABLE
  * 0 line items                        → FailureReason.NOTHING_ORDERABLE
"""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime
from typing import Any

from meal_agent.agent.nodes import Deps
from meal_agent.agent.state import (
    AgentError,
    AgentState,
    AgentStatus,
    CartLine,
    CartSnapshot,
    FailureReason,
)
from meal_agent.settings import get_settings
from meal_agent.tools.mcp_envelope import unwrap

NODE_NAME = "review_cart"


async def run(state: AgentState, deps: Deps) -> dict[str, Any]:
    address_id = state.input.address_id
    args = {"addressId": address_id}
    await deps.audit.write_event(
        run_id=deps.run_id, node=NODE_NAME, event="enter", payload=args
    )

    try:
        raw = await deps.swiggy.food_tool("get_food_cart").ainvoke(args)
    except Exception as e:
        return _fail(FailureReason.MCP_ERROR, f"get_food_cart raised: {e}")

    data, err = unwrap(raw)
    if err:
        reason = (
            FailureReason.ADDRESS_NOT_SERVICEABLE
            if "ADDRESS_NOT_SERVICEABLE" in err.upper()
            else FailureReason.MCP_ERROR
        )
        return _fail(reason, err)

    # Real Swiggy `get_food_cart` nests its payload under a `data` key:
    #   { statusCode, statusMessage, data: { items, pricing, ... }, availablePaymentMethods }
    # Test fixtures pass items at top-level, so we accept either shape.
    inner = data.get("data") if isinstance(data.get("data"), dict) else data

    lines = list(_iter_lines(inner))
    if not lines:
        return _fail(FailureReason.NOTHING_ORDERABLE, "cart has 0 items")

    # `pricing` is the real key; older tests use `bill`/`billDetails`.
    bill = inner.get("pricing") or inner.get("bill") or inner.get("billDetails") or {}
    subtotal = _i(
        bill.get("item_total")
        or bill.get("subTotal")
        or bill.get("itemTotal")
        or sum(line.qty * line.price_inr for line in lines)
    )
    delivery = _i(
        bill.get("delivery_charge")
        or bill.get("deliveryFee")
        or bill.get("deliveryCharges")
        or 0
    )
    discount = _i(
        bill.get("coupon_discount")
        or bill.get("discount")
        or bill.get("totalDiscount")
        or 0
    )
    total = _i(
        bill.get("to_pay")
        or bill.get("totalAmount")
        or bill.get("toPay")
        or subtotal + delivery - discount
    )

    payment_methods_raw = list(
        data.get("availablePaymentMethods")
        or inner.get("availablePaymentMethods")
        or inner.get("payment_methods")
        or []
    )

    # Bawarchi UX: never let users place a Cash-on-Delivery order through the
    # agent — they must pre-pay in-app so we never owe a delivery person.
    settings = get_settings()
    cod_aliases = {"cash", "cod", "cash on delivery", "cashondelivery"}
    payment_methods: list[str] = []
    cod_seen = False
    for p in payment_methods_raw:
        if str(p).strip().lower() in cod_aliases:
            cod_seen = True
            if not settings.agent.block_cod:
                payment_methods.append(str(p))
            continue
        payment_methods.append(str(p))

    if settings.agent.block_cod and cod_seen and not payment_methods:
        # COD was offered and was the ONLY method → refuse (user can't prepay).
        return _fail(
            FailureReason.PAYMENT_NOT_SUPPORTED,
            (
                "this restaurant only offers Cash on Delivery; Bawarchi "
                "requires a prepaid payment method"
            ),
        )

    address_label = (
        (inner.get("address") or {}).get("displayText")
        or inner.get("address_label")
        or state.input.address_label
        or "Selected address"
    )

    cap = state.input.constraints.max_price_inr
    if total > cap:
        return _fail(
            FailureReason.NOTHING_ORDERABLE,
            f"cart total ₹{total} > constraint ₹{cap}",
        )

    cart_hash = _hash_cart(lines=lines, total=total, address_id=address_id)

    cart = CartSnapshot(
        lines=lines,
        subtotal_inr=subtotal,
        delivery_fee_inr=delivery,
        discount_inr=discount,
        total_inr=total,
        payment_methods=[str(p) for p in payment_methods],
        address_label=address_label,
        cart_hash=cart_hash,
    )

    await deps.audit.write_event(
        run_id=deps.run_id,
        node=NODE_NAME,
        event="exit",
        payload={"total": total, "cart_hash": cart_hash, "lines": len(lines)},
    )

    return {"cart": cart, "status": AgentStatus.AWAITING_CONFIRM}


# ── helpers ──────────────────────────────────────────────────────────────────


def _iter_lines(data: dict):
    items = data.get("items") or data.get("cart_items") or data.get("lineItems") or []
    for it in items:
        name = it.get("name") or it.get("itemName") or "Item"
        qty = _i(it.get("quantity") or it.get("qty") or 1)
        # Real Swiggy keys: final_price (post-addon), subtotal, total. Tests use price.
        price = _i(
            it.get("final_price")
            or it.get("subtotal")
            or it.get("total")
            or it.get("price")
            or it.get("finalPrice")
            or it.get("totalPrice")
            or it.get("price_inr")
            or 0
        )
        if price > 50_000:
            price = price // 100  # paise → rupees defensive normalisation
        yield CartLine(name=str(name), qty=qty, price_inr=price)


def _i(v: Any) -> int:
    try:
        return int(float(v))
    except (TypeError, ValueError):
        return 0


def _hash_cart(*, lines: list[CartLine], total: int, address_id: str) -> str:
    """SHA-256 over a canonical JSON representation."""
    canonical = {
        "address_id": address_id,
        "total": total,
        "items": sorted(
            (
                {"name": line.name, "qty": line.qty, "price": line.price_inr}
                for line in lines
            ),
            key=lambda x: (x["name"], x["qty"], x["price"]),
        ),
    }
    blob = json.dumps(canonical, separators=(",", ":"), sort_keys=True).encode()
    return hashlib.sha256(blob).hexdigest()


def _fail(reason: FailureReason, detail: str) -> dict[str, Any]:
    return {
        "status": AgentStatus.FAILED,
        "error": AgentError(
            reason=reason,
            detail=detail,
            occurred_at=datetime.now(UTC),
            node=NODE_NAME,
        ),
    }


__all__ = ["NODE_NAME", "run"]
