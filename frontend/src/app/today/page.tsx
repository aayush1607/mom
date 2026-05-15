"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { AddressPicker } from "@/components/AddressPicker";
import { Phone } from "@/components/Phone";
import { Button } from "@/components/ui/Button";
import { api } from "@/lib/api";
import { MOM_PERSONA } from "@/lib/persona";
import {
  nextSlot,
  slotToConstraints,
  slotToContext,
  slotToPrompt,
  useSlots,
  type NudgeSlot,
} from "@/lib/slots";
import { useAddresses } from "@/lib/useAddresses";

const USER_ID = process.env.NEXT_PUBLIC_USER_ID ?? "u_dev";
const ADDRESS_ID_FALLBACK =
  process.env.NEXT_PUBLIC_TEST_ADDRESS_ID ?? "d2t62h7va4r6aip36a50";

export default function TodayPage() {
  const router = useRouter();
  const slots = useSlots();
  const { selected: selectedAddress } = useAddresses();
  const [busy, setBusy] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);

  const upcoming = nextSlot(slots);

  async function wakeMom(slot: NudgeSlot) {
    setBusy(slot.id);
    setErr(null);
    try {
      const res = await api.createRun({
        input: {
          user_id: USER_ID,
          address_id: selectedAddress?.id ?? ADDRESS_ID_FALLBACK,
          address_label: selectedAddress?.label ?? "Home",
          prompt: slotToPrompt(slot),
          context: slotToContext(slot),
          constraints: slotToConstraints(slot),
          persona: MOM_PERSONA,
        },
      });
      router.push(`/run/${res.run_id}`);
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
      setBusy(null);
    }
  }

  return (
    <Phone label="today" width="wide">
      <header className="px-6 sm:px-10 pt-12 sm:pt-14 pb-2 flex items-center justify-between gap-3">
        <Link href="/" className="brand-mark text-[28px]">
          mom<span className="dot">.</span>
        </Link>
        <div className="flex items-center gap-2 sm:gap-3 min-w-0">
          <AddressPicker />
          <Link
            href="/settings"
            className="text-[12px] uppercase tracking-[0.18em] text-ink-3 hover:text-ink shrink-0"
          >
            settings
          </Link>
        </div>
      </header>

      <section className="px-6 sm:px-10 pt-4">
        <h1 className="h-display text-[28px] sm:text-[36px] mb-1">
          {upcoming ? `Next: ${upcoming.label}` : "No nudges set"}
        </h1>
        <p className="text-ink-3 text-[13px] sm:text-[14px]">
          {upcoming
            ? `at ${upcoming.time} — “${upcoming.nudge}”`
            : "Open settings to enable a meal slot."}
        </p>
      </section>

      <section className="px-6 sm:px-10 pt-8 pb-2 flex-1 grid grid-cols-1 sm:grid-cols-2 gap-3 sm:gap-4">
        {slots.map((slot) => (
          <div
            key={slot.id}
            className={`rounded-3xl border border-line p-5 sm:p-6 flex flex-col ${
              slot.enabled ? "bg-bg/40" : "bg-card opacity-60"
            }`}
          >
            <div className="flex items-center justify-between mb-2">
              <div>
                <div className="text-[15px] sm:text-[16px] font-medium">
                  {slot.label}
                </div>
                <div className="text-[12px] text-ink-3">
                  {slot.enabled ? `${slot.time} · daily` : "off"}
                </div>
              </div>
              <Button
                variant={slot.enabled ? "brand" : "outline"}
                disabled={!slot.enabled || busy !== null}
                onClick={() => wakeMom(slot)}
              >
                {busy === slot.id ? "Order kar rahi…" : "Khila do"}
              </Button>
            </div>
            {slot.enabled && slot.nudge ? (
              <p className="text-[12px] sm:text-[13px] text-ink-2 mt-1">
                “{slot.nudge}”
              </p>
            ) : null}
          </div>
        ))}
      </section>

      {err ? (
        <p className="px-6 sm:px-10 pb-2 text-[12px] text-rose">
          Couldn&apos;t start: {err}
        </p>
      ) : null}
    </Phone>
  );
}
