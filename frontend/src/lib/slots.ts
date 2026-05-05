/**
 * localStorage-backed nudge config. v1 only: the FE shapes the prompt
 * for `POST /agent/runs` from these slots; nothing is sent to the backend
 * outside the run input itself.
 */

import { useSyncExternalStore } from "react";

import type { Constraints, UserContext } from "@/types/agent";

export type SlotId = "breakfast" | "lunch" | "snack" | "dinner";

export interface NudgeSlot {
  id: SlotId;
  label: string;
  enabled: boolean;
  time: string; // "HH:mm" 24-hour
  nudge: string; // free-text — what should mom keep in mind?
  budgetInr: number; // 0 → no cap
  vegetarian: boolean;
}

export const DEFAULT_SLOTS: NudgeSlot[] = [
  {
    id: "breakfast",
    label: "Breakfast",
    enabled: false,
    time: "09:00",
    nudge: "light, not too heavy",
    budgetInr: 0,
    vegetarian: false,
  },
  {
    id: "lunch",
    label: "Lunch",
    enabled: true,
    time: "13:30",
    nudge: "balanced — protein + sabzi",
    budgetInr: 350,
    vegetarian: false,
  },
  {
    id: "snack",
    label: "Snack",
    enabled: false,
    time: "17:30",
    nudge: "chhota, halka",
    budgetInr: 0,
    vegetarian: false,
  },
  {
    id: "dinner",
    label: "Dinner",
    enabled: true,
    time: "20:00",
    nudge: "protein-heavy, not oily",
    budgetInr: 500,
    vegetarian: false,
  },
];

const STORAGE_KEY = "mom.slots.v1";

export function loadSlots(): NudgeSlot[] {
  if (typeof window === "undefined") return DEFAULT_SLOTS;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return DEFAULT_SLOTS;
    const parsed = JSON.parse(raw) as NudgeSlot[];
    if (!Array.isArray(parsed) || parsed.length === 0) return DEFAULT_SLOTS;
    // Merge with defaults so newly added slot ids show up on next load.
    return DEFAULT_SLOTS.map(
      (def) => parsed.find((s) => s.id === def.id) ?? def,
    );
  } catch {
    return DEFAULT_SLOTS;
  }
}

export function saveSlots(slots: NudgeSlot[]): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(slots));
  window.dispatchEvent(new Event("mom:slots"));
}

/**
 * SSR-safe hook returning the current slots. Returns `DEFAULT_SLOTS` on the
 * server and during the first client render, then swaps to the persisted
 * value once hydration completes — using `useSyncExternalStore` so we don't
 * trigger React 19's "setState in effect" rule.
 */
export function useSlots(): NudgeSlot[] {
  return useSyncExternalStore(
    subscribeSlots,
    getSlotsSnapshot,
    getDefaultSnapshot,
  );
}

function subscribeSlots(callback: () => void): () => void {
  if (typeof window === "undefined") return () => {};
  const handler = () => callback();
  window.addEventListener("storage", handler);
  window.addEventListener("mom:slots", handler);
  return () => {
    window.removeEventListener("storage", handler);
    window.removeEventListener("mom:slots", handler);
  };
}

let cachedSnapshot: NudgeSlot[] | null = null;
let cachedRaw: string | null = null;

function getSlotsSnapshot(): NudgeSlot[] {
  if (typeof window === "undefined") return DEFAULT_SLOTS;
  const raw = window.localStorage.getItem(STORAGE_KEY);
  if (raw === cachedRaw && cachedSnapshot) return cachedSnapshot;
  cachedRaw = raw;
  cachedSnapshot = loadSlots();
  return cachedSnapshot;
}

function getDefaultSnapshot(): NudgeSlot[] {
  return DEFAULT_SLOTS;
}

export function nextSlot(slots: NudgeSlot[], now = new Date()): NudgeSlot | null {
  const enabled = slots.filter((s) => s.enabled);
  if (enabled.length === 0) return null;
  const minutesNow = now.getHours() * 60 + now.getMinutes();
  const upcoming = enabled
    .map((s) => {
      const [h, m] = s.time.split(":").map(Number);
      const mins = h * 60 + m;
      const delta = mins - minutesNow;
      return { slot: s, delta: delta < 0 ? delta + 24 * 60 : delta };
    })
    .sort((a, b) => a.delta - b.delta);
  return upcoming[0]?.slot ?? null;
}

export function slotToContext(slot: NudgeSlot, now = new Date()): UserContext {
  return {
    active_nudge: slot.nudge.trim() || null,
    meal_slot: slot.id,
    day_of_week: now.toLocaleDateString("en-IN", { weekday: "long" }),
    local_time: now.toISOString(),
  };
}

export function slotToConstraints(slot: NudgeSlot): Constraints {
  return {
    max_price_inr: slot.budgetInr > 0 ? slot.budgetInr : 1000,
    max_eta_min: 60,
    vegetarian: slot.vegetarian,
    jain: false,
    egg_ok: true,
  };
}

export function slotToPrompt(slot: NudgeSlot): string {
  const bits: string[] = [`Pick something for ${slot.label.toLowerCase()}.`];
  if (slot.nudge.trim()) bits.push(`Keep in mind: ${slot.nudge.trim()}.`);
  if (slot.budgetInr > 0) bits.push(`Stay under ₹${slot.budgetInr}.`);
  if (slot.vegetarian) bits.push("Vegetarian only.");
  return bits.join(" ");
}
