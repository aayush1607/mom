"use client";

import { useEffect } from "react";

import { loadSlots, type NudgeSlot } from "@/lib/slots";

/**
 * Local meal-time reminders.
 *
 * **Honest scope** — this is *not* push: it fires only while the app's
 * tab/PWA is alive (or recently backgrounded so the OS keeps the tab).
 * For real "phone is locked" delivery we'd need Web Push (VAPID server
 * + a backend cron). This module is the v1 simple-reminder path: when
 * the app is open it nudges you at meal time so you can tap "Wake mom".
 *
 * Behaviour:
 *   * Polls every 30s while mounted.
 *   * For each enabled slot whose HH:mm equals "now" (with a 1-minute
 *     window of forgiveness for skew), fires one notification.
 *   * Tracks last-fired in localStorage with a per-day key so we never
 *     send the same slot twice in one day even if the tab reloads.
 *   * Tapping the notification opens (or focuses) /today via the
 *     service worker's `notificationclick` handler.
 */

const FIRED_PREFIX = "mom.reminder.fired"; // mom.reminder.fired.<slot>.<YYYY-MM-DD>
const POLL_MS = 30_000;

export type ReminderPermission = "default" | "granted" | "denied" | "unsupported";

export function getPermission(): ReminderPermission {
  if (typeof window === "undefined") return "unsupported";
  if (!("Notification" in window)) return "unsupported";
  return window.Notification.permission as ReminderPermission;
}

export async function requestPermission(): Promise<ReminderPermission> {
  if (typeof window === "undefined" || !("Notification" in window)) {
    return "unsupported";
  }
  if (window.Notification.permission !== "default") {
    return window.Notification.permission as ReminderPermission;
  }
  const result = await window.Notification.requestPermission();
  return result as ReminderPermission;
}

/** Mount once at the root layout. Idempotent across re-mounts. */
export function useReminderScheduler(): void {
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!("Notification" in window)) return;

    let cancelled = false;
    const tick = async () => {
      if (cancelled) return;
      if (window.Notification.permission !== "granted") return;
      const slots = loadSlots();
      const now = new Date();
      const due = pickDueSlots(slots, now);
      for (const slot of due) {
        if (alreadyFired(slot.id, now)) continue;
        markFired(slot.id, now);
        try {
          await fireNotification(slot);
        } catch {
          // Swallow — notifications are best-effort. If this throws, the
          // user has bigger problems than a missed reminder.
        }
      }
    };

    // Run once immediately so a slot whose time was hit while the tab
    // was loading still nudges the user.
    void tick();
    const id = window.setInterval(tick, POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, []);
}

// ── internals ───────────────────────────────────────────────────────────────

function pickDueSlots(slots: NudgeSlot[], now: Date): NudgeSlot[] {
  const minutesNow = now.getHours() * 60 + now.getMinutes();
  return slots.filter((s) => {
    if (!s.enabled) return false;
    const [h, m] = s.time.split(":").map(Number);
    if (Number.isNaN(h) || Number.isNaN(m)) return false;
    const slotMin = h * 60 + m;
    // Fire if "now" is within the slot's minute. Polling every 30s means
    // we may evaluate twice in the same minute — the dedupe below handles it.
    return slotMin === minutesNow;
  });
}

function dayKey(now: Date): string {
  // Local date, not UTC — slots are local-time semantics.
  const y = now.getFullYear();
  const m = String(now.getMonth() + 1).padStart(2, "0");
  const d = String(now.getDate()).padStart(2, "0");
  return `${y}-${m}-${d}`;
}

function firedKey(slotId: string, now: Date): string {
  return `${FIRED_PREFIX}.${slotId}.${dayKey(now)}`;
}

function alreadyFired(slotId: string, now: Date): boolean {
  try {
    return window.localStorage.getItem(firedKey(slotId, now)) === "1";
  } catch {
    return false;
  }
}

function markFired(slotId: string, now: Date): void {
  try {
    window.localStorage.setItem(firedKey(slotId, now), "1");
    // Best-effort cleanup of yesterday's keys so localStorage doesn't grow
    // forever. Cheap O(n) sweep limited to our prefix.
    const today = dayKey(now);
    for (let i = window.localStorage.length - 1; i >= 0; i--) {
      const k = window.localStorage.key(i);
      if (!k || !k.startsWith(`${FIRED_PREFIX}.`)) continue;
      const day = k.split(".").pop() ?? "";
      if (day !== today) window.localStorage.removeItem(k);
    }
  } catch {
    // localStorage might be full / disabled; reminder still fires today.
  }
}

async function fireNotification(slot: NudgeSlot): Promise<void> {
  const title = titleFor(slot);
  const body = bodyFor(slot);
  const opts: NotificationOptions = {
    body,
    icon: "/icons/icon-192.png",
    badge: "/icons/icon-192.png",
    tag: `mom-slot-${slot.id}`,
    // Replace any earlier same-tag notification rather than stacking.
    renotify: false,
    data: { url: "/today" },
  } as NotificationOptions;

  // Prefer SW-backed notifications — they survive past the tab and the
  // SW's notificationclick handler can focus/open the right route.
  if ("serviceWorker" in navigator) {
    const reg = await navigator.serviceWorker.getRegistration();
    if (reg) {
      await reg.showNotification(title, opts);
      return;
    }
  }
  // Fallback: in-tab notification. Click handling is best-effort and
  // browser-dependent.
  const n = new window.Notification(title, opts);
  n.onclick = () => {
    window.focus();
    window.location.href = "/today";
    n.close();
  };
}

function titleFor(slot: NudgeSlot): string {
  // Friendly, mom-voice. Keep it short — most platforms truncate aggressively.
  switch (slot.id) {
    case "breakfast":
      return "Breakfast time, beta.";
    case "lunch":
      return "Lunch o'clock.";
    case "snack":
      return "Snack break?";
    case "dinner":
      return "Dinner time.";
  }
}

function bodyFor(slot: NudgeSlot): string {
  const nudge = (slot.nudge || "").trim();
  if (nudge) return `${nudge} — tap to call mom.`;
  return "Tap to call mom.";
}
