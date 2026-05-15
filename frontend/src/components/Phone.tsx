"use client";

import type { ReactNode } from "react";

interface PhoneFrameProps {
  children: ReactNode;
  /** Optional small breadcrumb shown above the card on desktop only. */
  label?: string;
  /**
   * Card width on desktop.
   * - `narrow` (default, 480px) for focused single-decision screens
   *   (Suggestion, CartConfirm, Pakka, GiveUp).
   * - `wide` (720px) for list/form screens (Today, Settings) where extra
   *   horizontal room makes the page feel comfortable on a laptop.
   * Mobile (< 640px) is always full-bleed regardless of this prop.
   */
  width?: "narrow" | "wide";
}

/**
 * Phone — app-shell container that's mobile-first and adapts on desktop:
 *  • mobile: full-bleed, fills viewport, no chrome
 *  • desktop: centered card with rounded corners, soft border, mom shadow
 *    Sizing comes from content (no fixed min-height), so short screens like
 *    Pakka don't stretch into empty space.
 */
export function Phone({ children, label, width = "narrow" }: PhoneFrameProps) {
  const maxClass =
    width === "wide" ? "sm:max-w-[720px]" : "sm:max-w-[480px]";

  return (
    <div className="min-h-screen w-full flex flex-col items-stretch sm:items-center sm:justify-start sm:py-12">
      {label ? (
        <div className="hidden sm:block text-[11px] text-ink-3 uppercase tracking-[0.2em] mb-4">
          {label}
        </div>
      ) : null}
      <div
        className={`
          relative w-full ${maxClass} flex-1 sm:flex-none
          bg-card sm:rounded-[32px] sm:border sm:border-line sm:shadow-mom
          flex flex-col overflow-hidden
        `}
      >
        {children}
      </div>
    </div>
  );
}

