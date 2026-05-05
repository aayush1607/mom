"use client";

import Link from "next/link";
import { useState } from "react";

import { Phone } from "@/components/Phone";
import { Button } from "@/components/ui/Button";
import {
  saveSlots,
  useSlots,
  type NudgeSlot,
} from "@/lib/slots";

export default function SettingsPage() {
  const persisted = useSlots();
  // Edit-buffer seeded once from persisted state. Multi-tab sync is out of
  // scope for v1 — settings are single-user, single-device.
  const [slots, setSlots] = useState<NudgeSlot[]>(persisted);
  const [savedAt, setSavedAt] = useState<number | null>(null);

  function update(id: string, patch: Partial<NudgeSlot>) {
    setSlots((prev) =>
      prev.map((s) => (s.id === id ? { ...s, ...patch } : s)),
    );
  }

  function persist() {
    saveSlots(slots);
    setSavedAt(Date.now());
  }

  return (
    <Phone label="settings">
      <header className="px-6 pt-12 pb-2 flex items-center justify-between">
        <Link
          href="/"
          className="text-[12px] uppercase tracking-[0.18em] text-ink-3 hover:text-ink"
        >
          ← back
        </Link>
        <span className="brand-mark text-[18px]">
          mom<span className="dot">.</span>
        </span>
      </header>

      <section className="px-6 pt-4">
        <h1 className="h-display text-[28px] mb-1">Tell mom when.</h1>
        <p className="text-ink-3 text-[13px]">
          Saved on this device. No account yet.
        </p>
      </section>

      <section className="px-6 pt-6 flex-1 space-y-4 pb-4">
        {slots.map((slot) => (
          <div
            key={slot.id}
            className="rounded-3xl border border-line bg-bg/30 p-5 space-y-3"
          >
            <div className="flex items-center justify-between">
              <div className="text-[15px] font-medium">{slot.label}</div>
              <button
                type="button"
                onClick={() => update(slot.id, { enabled: !slot.enabled })}
                className={`px-3 py-1.5 rounded-full text-[12px] uppercase tracking-[0.18em] ${
                  slot.enabled
                    ? "bg-brand text-white"
                    : "border border-line text-ink-3"
                }`}
              >
                {slot.enabled ? "on" : "off"}
              </button>
            </div>

            <Field label="Time">
              <input
                type="time"
                value={slot.time}
                onChange={(e) => update(slot.id, { time: e.target.value })}
                className="bg-card border border-line rounded-xl px-3 py-2 text-[14px]"
                disabled={!slot.enabled}
              />
            </Field>

            <Field label="What should mom keep in mind?">
              <input
                type="text"
                value={slot.nudge}
                onChange={(e) => update(slot.id, { nudge: e.target.value })}
                placeholder="protein-heavy, not oily"
                className="w-full bg-card border border-line rounded-xl px-3 py-2 text-[14px]"
                disabled={!slot.enabled}
              />
            </Field>

            <Field label="Budget cap (₹, 0 = no cap)">
              <input
                type="number"
                min={0}
                step={50}
                value={slot.budgetInr}
                onChange={(e) =>
                  update(slot.id, { budgetInr: Number(e.target.value) || 0 })
                }
                className="w-32 bg-card border border-line rounded-xl px-3 py-2 text-[14px]"
                disabled={!slot.enabled}
              />
            </Field>

            <label className="flex items-center gap-2 text-[13px] text-ink-2">
              <input
                type="checkbox"
                checked={slot.vegetarian}
                onChange={(e) =>
                  update(slot.id, { vegetarian: e.target.checked })
                }
                disabled={!slot.enabled}
              />
              Vegetarian only
            </label>
          </div>
        ))}
      </section>

      <footer className="px-6 pb-8 pt-2 flex flex-col gap-2">
        <Button fullWidth onClick={persist}>
          Save
        </Button>
        {savedAt ? (
          <p className="text-center text-[12px] text-sage">Saved.</p>
        ) : null}
      </footer>
    </Phone>
  );
}

function Field({
  label,
  children,
}: {
  label: string;
  children: React.ReactNode;
}) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[11px] uppercase tracking-[0.18em] text-ink-3">
        {label}
      </span>
      {children}
    </label>
  );
}
