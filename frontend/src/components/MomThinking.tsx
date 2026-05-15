"use client";

import { useEffect, useState } from "react";

import { useActivity } from "@/lib/useActivity";
import type { ActivityStep } from "@/types/agent";

interface MomThinkingProps {
  runId: string;
}

/**
 * Live agent activity loader. Replaces the generic spinner during
 * `status === "running"` with a real-time trace of mom's internal nodes.
 *
 * Each step shows:
 *   - sage check ✓ when the node is done
 *   - pulsing terracotta dot when the node is mid-flight
 *   - rose × when the node hit an error (run-level failure shown elsewhere)
 *
 * Polls the backend at 800ms; new steps slide in as the agent advances.
 */
export function MomThinking({ runId }: MomThinkingProps) {
  const { activity } = useActivity(runId, true);
  const steps = activity?.steps ?? [];
  const ellipsis = useEllipsis();

  // Until any node has emitted, show a friendly warm-up so the UI is never
  // empty — the first event usually lands within ~200ms but the LLM call
  // for interpret_prompt can be the long pole, so this is honest.
  const isWarming = steps.length === 0;

  return (
    <div className="flex flex-col h-full">
      <header className="px-6 sm:px-8 pt-12 sm:pt-14 pb-2 flex items-center justify-between">
        <span className="brand-mark text-[18px]">
          mom<span className="dot">.</span>
        </span>
        <span className="text-[12px] text-brand inline-flex items-center gap-1.5">
          <span className="relative inline-flex h-2 w-2">
            <span className="absolute inset-0 rounded-full bg-brand animate-ping opacity-60" />
            <span className="relative inline-flex h-2 w-2 rounded-full bg-brand" />
          </span>
          thinking{ellipsis}
        </span>
      </header>

      <div className="px-6 sm:px-8 pt-6 pb-2">
        <h2 className="text-[26px] sm:text-[30px] leading-tight font-semibold text-ink">
          Hold on, beta —
          <br />
          <span className="text-brand">mom&apos;s on it.</span>
        </h2>
      </div>

      <div className="flex-1 px-6 sm:px-8 pb-10 pt-4 overflow-hidden">
        {isWarming ? (
          <WarmupRow />
        ) : (
          <ol className="flex flex-col gap-3">
            {steps.map((step, idx) => (
              <Row key={step.node} step={step} index={idx} />
            ))}
          </ol>
        )}
      </div>
    </div>
  );
}

// ── individual row ──────────────────────────────────────────────────────────

function Row({ step, index }: { step: ActivityStep; index: number }) {
  const isActive = step.status === "active";
  const isDone = step.status === "done";
  const isError = step.status === "error";

  // Stagger the entrance so new steps glide in instead of pop.
  // Cap the delay so we don't have a 2s wait on the 8th step.
  const delayMs = Math.min(index * 60, 240);

  return (
    <li
      className="flex items-start gap-3 mom-row"
      style={{ animationDelay: `${delayMs}ms` }}
    >
      <div className="pt-[3px] shrink-0">
        <Marker status={step.status} />
      </div>
      <div className="flex-1 min-w-0">
        <div
          className={[
            "text-[15px] leading-snug transition-colors",
            isActive ? "text-ink font-semibold" : "",
            isDone ? "text-ink-2" : "",
            isError ? "text-rose font-semibold" : "",
          ].join(" ")}
        >
          {step.label}
          {isActive ? <span className="text-brand">…</span> : null}
        </div>
        {step.detail ? (
          <div
            className={[
              "text-[12.5px] leading-snug mt-0.5 truncate",
              isActive ? "text-brand" : "text-ink-3",
            ].join(" ")}
          >
            {step.detail}
          </div>
        ) : null}
      </div>
      {isDone ? (
        <span className="text-[11px] text-ink-3 pt-[5px] shrink-0 tabular-nums">
          {durationLabel(step)}
        </span>
      ) : null}
    </li>
  );
}

function Marker({ status }: { status: ActivityStep["status"] }) {
  if (status === "done") {
    return (
      <span
        aria-hidden
        className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-sage/15 text-sage"
      >
        <svg viewBox="0 0 16 16" className="h-3 w-3" fill="none">
          <path
            d="M3 8.5l3 3 7-7"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
            strokeLinejoin="round"
          />
        </svg>
      </span>
    );
  }
  if (status === "error") {
    return (
      <span
        aria-hidden
        className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-rose/15 text-rose"
      >
        <svg viewBox="0 0 16 16" className="h-3 w-3" fill="none">
          <path
            d="M4 4l8 8M12 4l-8 8"
            stroke="currentColor"
            strokeWidth="2.2"
            strokeLinecap="round"
          />
        </svg>
      </span>
    );
  }
  // active
  return (
    <span aria-hidden className="relative inline-flex h-5 w-5 items-center justify-center">
      <span className="absolute inset-0 rounded-full bg-brand/20 animate-ping" />
      <span className="relative inline-flex h-2.5 w-2.5 rounded-full bg-brand" />
    </span>
  );
}

function WarmupRow() {
  return (
    <div className="flex items-start gap-3">
      <div className="pt-[3px]">
        <Marker status="active" />
      </div>
      <div className="text-[15px] text-ink font-semibold">
        Pulling up your kitchen<span className="text-brand">…</span>
      </div>
    </div>
  );
}

// ── helpers ─────────────────────────────────────────────────────────────────

function durationLabel(step: ActivityStep): string {
  if (!step.finished_at) return "";
  const start = Date.parse(step.started_at);
  const end = Date.parse(step.finished_at);
  if (!Number.isFinite(start) || !Number.isFinite(end)) return "";
  const ms = Math.max(0, end - start);
  if (ms < 950) return `${Math.round(ms / 100) / 10}s`;
  return `${Math.round(ms / 100) / 10}s`;
}

/** Cycles through "", ".", "..", "..." every 350ms so the header
 * "thinking…" bounces gently. Cheap dependency-free animation. */
function useEllipsis(): string {
  const [n, setN] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setN((x) => (x + 1) % 4), 350);
    return () => clearInterval(id);
  }, []);
  return ".".repeat(n);
}
