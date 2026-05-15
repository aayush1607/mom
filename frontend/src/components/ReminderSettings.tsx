"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import {
  getPermission,
  requestPermission,
  type ReminderPermission,
} from "@/lib/reminders";

/**
 * Settings card: turn on / show status of meal-time reminders.
 *
 * The permission state is browser-native and not directly subscribable —
 * we read it once on mount and refresh after the user clicks Enable.
 * If they later flip it in browser settings we won't notice until the
 * next mount; that's an acceptable v1 trade-off.
 */
export function ReminderSettings() {
  const [perm, setPerm] = useState<ReminderPermission>("unsupported");
  const [busy, setBusy] = useState(false);
  const [testedAt, setTestedAt] = useState<number | null>(null);

  useEffect(() => {
    // Defer setState a tick to satisfy React 19's set-state-in-effect rule.
    const t = window.setTimeout(() => setPerm(getPermission()), 0);
    return () => window.clearTimeout(t);
  }, []);

  async function enable() {
    setBusy(true);
    try {
      const next = await requestPermission();
      setPerm(next);
    } finally {
      setBusy(false);
    }
  }

  async function sendTest() {
    if (perm !== "granted") return;
    setBusy(true);
    try {
      const opts: NotificationOptions = {
        body: "Reminders are on. mom will nudge you at your meal times.",
        icon: "/icons/icon-192.png",
        badge: "/icons/icon-192.png",
        tag: "mom-reminder-test",
        data: { url: "/today" },
      };
      if ("serviceWorker" in navigator) {
        const reg = await navigator.serviceWorker.getRegistration();
        if (reg) {
          await reg.showNotification("Test ping from mom.", opts);
          setTestedAt(Date.now());
          return;
        }
      }
      const n = new window.Notification("Test ping from mom.", opts);
      n.onclick = () => {
        window.focus();
        window.location.href = "/today";
        n.close();
      };
      setTestedAt(Date.now());
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="rounded-3xl border border-line bg-bg/30 p-5 sm:p-6 space-y-3">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-[15px] sm:text-[16px] font-medium">
            Meal-time reminders
          </div>
          <p className="text-[12px] sm:text-[13px] text-ink-3 mt-0.5">
            mom nudges you at the times you set above. One tap to call mom
            from the notification.
          </p>
        </div>
        <StatusPill perm={perm} />
      </div>

      <Caveat perm={perm} />

      <div className="flex flex-wrap gap-2 pt-1">
        {perm === "default" || perm === "unsupported" ? (
          <Button
            variant="brand"
            disabled={perm === "unsupported" || busy}
            onClick={enable}
          >
            {busy ? "Asking…" : "Enable reminders"}
          </Button>
        ) : null}
        {perm === "granted" ? (
          <Button variant="outline" disabled={busy} onClick={sendTest}>
            {busy ? "Sending…" : "Send a test ping"}
          </Button>
        ) : null}
      </div>

      {testedAt ? (
        <p className="text-[12px] text-sage">
          Sent. Check your notifications shade.
        </p>
      ) : null}
    </div>
  );
}

function StatusPill({ perm }: { perm: ReminderPermission }) {
  const { label, klass } = pillFor(perm);
  return (
    <span
      className={`shrink-0 text-[10.5px] uppercase tracking-[0.16em] rounded-full px-2.5 py-1 ${klass}`}
    >
      {label}
    </span>
  );
}

function pillFor(perm: ReminderPermission): { label: string; klass: string } {
  switch (perm) {
    case "granted":
      return { label: "On", klass: "bg-sage/15 text-sage" };
    case "denied":
      return { label: "Blocked", klass: "bg-rose/15 text-rose" };
    case "unsupported":
      return { label: "Not available", klass: "bg-ink-3/15 text-ink-3" };
    default:
      return { label: "Off", klass: "bg-ink-3/15 text-ink-3" };
  }
}

function Caveat({ perm }: { perm: ReminderPermission }) {
  if (perm === "denied") {
    return (
      <p className="text-[12px] text-ink-2">
        Reminders are blocked for this site. Enable notifications for{" "}
        <span className="font-medium">mom.</span> in your browser settings,
        then refresh.
      </p>
    );
  }
  if (perm === "unsupported") {
    return (
      <p className="text-[12px] text-ink-2">
        This browser doesn&apos;t support web notifications. Install mom. as
        a PWA on a recent Chrome / Safari for reminders.
      </p>
    );
  }
  if (perm === "granted") {
    return (
      <p className="text-[12px] text-ink-3">
        Heads up: reminders fire while the app or its installed PWA is
        running in the background. For a full lock-screen ping we&apos;d
        need push (coming later).
      </p>
    );
  }
  return null;
}
