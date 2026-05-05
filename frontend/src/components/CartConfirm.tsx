"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import type { CartSnapshot } from "@/types/agent";

interface CartConfirmProps {
  runId: string;
  cart: CartSnapshot;
  onAfterAction: () => void;
}

export function CartConfirm({ runId, cart, onAfterAction }: CartConfirmProps) {
  const [busy, setBusy] = useState<"confirm" | "cancel" | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function decide(decision: "confirm" | "cancel") {
    setBusy(decision);
    setErr(null);
    try {
      await api.resumeRun(runId, decision);
      onAfterAction();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(null);
    }
  }

  return (
    <div className="flex flex-col h-full">
      <header className="px-6 pt-12 pb-2 flex items-center justify-between">
        <span className="brand-mark text-[18px]">
          mom<span className="dot">.</span>
        </span>
        <span className="text-[12px] text-ink-3 uppercase tracking-[0.18em]">
          confirm
        </span>
      </header>

      <section className="px-6 pt-2">
        <h1 className="h-display text-[28px] mb-1">
          Confirm before I place it.
        </h1>
        <p className="text-ink-3 text-[13px]">
          mom will use Swiggy to order. No surprises.
        </p>
      </section>

      <section className="px-6 pt-6 flex-1">
        <div className="rounded-3xl border border-line bg-bg/40 p-5">
          {cart.lines.map((line, idx) => (
            <div
              key={`${line.name}-${idx}`}
              className="flex items-center justify-between py-2 text-[14px]"
            >
              <span className="text-ink">
                {line.qty} × {line.name}
              </span>
              <span className="text-ink-2">₹{line.price_inr}</span>
            </div>
          ))}
          <div className="border-t border-line my-3" />
          <Row label="Subtotal" value={`₹${cart.subtotal_inr}`} />
          <Row label="Delivery" value={`₹${cart.delivery_fee_inr}`} />
          {cart.discount_inr > 0 ? (
            <Row
              label="mom's coupon"
              value={`−₹${cart.discount_inr}`}
              accent="text-sage"
            />
          ) : null}
          <div className="border-t border-line my-3" />
          <div className="flex items-center justify-between text-[16px] font-semibold">
            <span>Total</span>
            <span>₹{cart.total_inr}</span>
          </div>
        </div>

        <div className="mt-4 rounded-2xl border border-line p-4 text-[13px] text-ink-2">
          <div className="text-ink-3 text-[11px] uppercase tracking-[0.18em] mb-1">
            Delivering to
          </div>
          <div>{cart.address_label}</div>
        </div>

        <div className="mt-3 rounded-2xl border border-line p-4 text-[13px] text-ink-2">
          <div className="text-ink-3 text-[11px] uppercase tracking-[0.18em] mb-1">
            Payment
          </div>
          <div>
            {cart.payment_methods.length > 0
              ? cart.payment_methods.join(" · ")
              : "Pay on Swiggy"}
          </div>
        </div>
      </section>

      {err ? (
        <p className="px-6 text-[13px] text-rose">Couldn&apos;t place: {err}</p>
      ) : null}

      <footer className="px-6 pb-8 pt-4 flex flex-col gap-3">
        <Button
          fullWidth
          onClick={() => decide("confirm")}
          disabled={busy !== null}
        >
          {busy === "confirm" ? "Placing…" : "Confirm — place order"}
        </Button>
        <Button
          variant="ghost"
          fullWidth
          onClick={() => decide("cancel")}
          disabled={busy !== null}
        >
          {busy === "cancel" ? "Cancelling…" : "Not now"}
        </Button>
      </footer>
    </div>
  );
}

function Row({
  label,
  value,
  accent = "text-ink-2",
}: {
  label: string;
  value: string;
  accent?: string;
}) {
  return (
    <div className="flex items-center justify-between py-1 text-[13px]">
      <span className="text-ink-3">{label}</span>
      <span className={accent}>{value}</span>
    </div>
  );
}
