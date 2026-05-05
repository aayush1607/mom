"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import type { Proposal } from "@/types/agent";

interface SuggestionProps {
  runId: string;
  proposal: Proposal;
  onAfterAction: () => void;
}

export function Suggestion({ runId, proposal, onAfterAction }: SuggestionProps) {
  const [busy, setBusy] = useState<"accept" | "swap" | null>(null);
  const [err, setErr] = useState<string | null>(null);

  async function decide(decision: "accept" | "swap") {
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

  const dish = proposal.dish;

  return (
    <div className="flex flex-col h-full">
      <header className="px-6 pt-12 pb-2 flex items-center justify-between">
        <span className="brand-mark text-[18px]">
          mom<span className="dot">.</span>
        </span>
        <span className="text-[12px] text-brand">📞 mom&apos;s calling</span>
      </header>

      <section className="px-6 pt-2">
        <h1 className="h-display text-[34px] mb-1">{proposal.voice_heading}</h1>
        <p className="text-ink-3 text-[14px]">{proposal.voice_reason}</p>
      </section>

      <section className="px-6 pt-8 flex-1">
        <div className="rounded-3xl border border-line bg-bg/50 p-5">
          <div className="text-[11px] uppercase tracking-[0.18em] text-ink-3 mb-2">
            mom&apos;s pick
          </div>
          <h2 className="h-display text-[24px] mb-1">{dish.name}</h2>
          <div className="text-[13px] text-ink-2 mb-3">
            {dish.restaurant_name}
          </div>
          {dish.description ? (
            <p className="text-[13px] text-ink-3 leading-snug mb-4">
              {dish.description}
            </p>
          ) : null}
          <div className="flex items-center justify-between text-[13px] text-ink-2">
            <span>₹{dish.price_inr}</span>
            {dish.veg === true ? (
              <span className="text-sage">veg</span>
            ) : dish.veg === false ? (
              <span className="text-rose">non-veg</span>
            ) : null}
          </div>
        </div>
      </section>

      {err ? (
        <p className="px-6 text-[13px] text-rose">Couldn&apos;t reach mom: {err}</p>
      ) : null}

      <footer className="px-6 pb-8 pt-4 flex flex-col gap-3">
        <Button
          fullWidth
          onClick={() => decide("accept")}
          disabled={busy !== null}
        >
          {busy === "accept" ? "Calling Swiggy…" : proposal.voice_cta_yes}
        </Button>
        <Button
          variant="outline"
          fullWidth
          onClick={() => decide("swap")}
          disabled={busy !== null}
        >
          {busy === "swap" ? "Picking again…" : proposal.voice_cta_swap}
        </Button>
      </footer>
    </div>
  );
}
