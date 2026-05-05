"use client";

import Link from "next/link";

import { Button } from "@/components/ui/Button";
import type { AgentError, FailureReason } from "@/types/agent";

interface GiveUpProps {
  error: AgentError | null | undefined;
  status: "failed" | "cancelled_by_user";
}

const FALLBACK_VOICE: Record<FailureReason, string> = {
  swap_exhausted:
    "Okay, no order this time. I'll try again at the next nudge.",
  no_candidates:
    "Nothing good open right now near you. Try the Swiggy app directly?",
  nothing_orderable:
    "What I picked just went out of stock. Try again in a few minutes.",
  mcp_error: "Couldn't reach Swiggy. Try again in a few minutes.",
  address_not_serviceable: "This address isn't deliverable right now.",
  interrupt_timeout: "Took too long to hear back. Skipped this nudge.",
  payment_not_supported:
    "No supported payment method on this cart. Open Swiggy to set one up.",
};

export function GiveUp({ error, status }: GiveUpProps) {
  const cancelled = status === "cancelled_by_user";

  const heading = cancelled ? "Cancelled." : "Bas itna hi.";
  const subline = cancelled
    ? "No order this time."
    : error?.voice_message ??
      (error?.reason ? FALLBACK_VOICE[error.reason] : "mom couldn't decide this round.");

  return (
    <div className="flex flex-col h-full">
      <header className="px-6 pt-12 pb-2 flex items-center justify-between">
        <span className="brand-mark text-[18px]">
          mom<span className="dot">.</span>
        </span>
        <span className="text-[11px] uppercase tracking-[0.18em] text-ink-3">
          {cancelled ? "cancelled" : "no order"}
        </span>
      </header>

      <section className="px-6 pt-12 flex-1">
        <h1 className="h-display text-[34px] mb-3">{heading}</h1>
        <p className="text-ink-2 text-[15px] leading-snug max-w-[28ch]">
          {subline}
        </p>

        {error?.detail && !cancelled ? (
          <details className="mt-6 text-[12px] text-ink-3">
            <summary className="cursor-pointer">Technical details</summary>
            <pre className="whitespace-pre-wrap break-words mt-2">
              {error.detail}
            </pre>
          </details>
        ) : null}
      </section>

      <footer className="px-6 pb-8 pt-4 flex flex-col gap-3">
        <Link href="/" className="block">
          <Button fullWidth>Back home</Button>
        </Link>
      </footer>
    </div>
  );
}
