"use client";

import Link from "next/link";

import { Button } from "@/components/ui/Button";
import type { OrderResult } from "@/types/agent";

interface PakkaProps {
  order: OrderResult;
}

export function Pakka({ order }: PakkaProps) {
  const isDryRun = order.order_id.startsWith("DRYRUN_");
  const placedAt = new Date(order.placed_at);

  return (
    <div className="flex flex-col h-full">
      <header className="px-6 pt-12 pb-2 flex items-center justify-between">
        <span className="brand-mark text-[18px]">
          mom<span className="dot">.</span>
        </span>
        {isDryRun ? (
          <span className="text-[11px] uppercase tracking-[0.18em] text-warm">
            dry run
          </span>
        ) : (
          <span className="text-[12px] text-sage">✓ placed</span>
        )}
      </header>

      <section className="px-6 pt-6">
        <h1 className="h-display text-[44px] mb-2">Pakka.</h1>
        <p className="text-ink-2 text-[15px]">
          {order.eta_min
            ? `On the way · ${order.eta_min} min`
            : "On the way."}
        </p>
      </section>

      <section className="px-6 pt-8 flex-1">
        <div className="rounded-3xl border border-line bg-bg/40 p-5 space-y-3">
          <Row
            label="Order id"
            value={order.order_id}
            mono
          />
          <Row
            label="Placed"
            value={placedAt.toLocaleTimeString("en-IN", {
              hour: "numeric",
              minute: "2-digit",
            })}
          />
          {order.eta_min ? (
            <Row label="ETA" value={`${order.eta_min} min`} />
          ) : null}
        </div>

        {isDryRun ? (
          <p className="mt-4 text-[12px] text-ink-3 leading-snug">
            This was a dry-run. mom never called Swiggy — toggle{" "}
            <code className="text-ink-2">AGENT_LIVE_ORDERS_ENABLED=true</code>{" "}
            in <code className="text-ink-2">backend/.env</code> to place a real
            order.
          </p>
        ) : null}
      </section>

      <footer className="px-6 pb-8 pt-4 flex flex-col gap-3">
        <a
          href="https://www.swiggy.com/my-account/orders"
          target="_blank"
          rel="noreferrer"
          className="inline-flex items-center justify-center px-5 py-3 rounded-2xl text-[15px] font-medium bg-card text-ink border border-line hover:bg-bg/60"
        >
          Track in Swiggy →
        </a>
        <Link href="/" className="block">
          <Button variant="ghost" fullWidth>
            Done
          </Button>
        </Link>
      </footer>
    </div>
  );
}

function Row({
  label,
  value,
  mono = false,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between text-[13px]">
      <span className="text-ink-3">{label}</span>
      <span className={`text-ink-2 ${mono ? "font-mono text-[12px]" : ""}`}>
        {value}
      </span>
    </div>
  );
}
