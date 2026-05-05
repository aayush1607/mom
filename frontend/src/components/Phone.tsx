"use client";

import type { ReactNode } from "react";

interface PhoneFrameProps {
  children: ReactNode;
  /**
   * Optional label shown above the frame on desktop only — a small breadcrumb
   * for debugging multiple states side by side.
   */
  label?: string;
}

/**
 * Phone — desktop chrome that frames the app like a phone, mirroring
 * `frames/screens.html`. On mobile (< 480 px) the chrome dissolves and the
 * content fills the viewport.
 */
export function Phone({ children, label }: PhoneFrameProps) {
  return (
    <div className="min-h-screen w-full flex flex-col items-center justify-start sm:justify-center sm:py-10">
      {label ? (
        <div className="hidden sm:block text-[12px] text-ink-3 uppercase tracking-[0.18em] mb-3">
          {label}
        </div>
      ) : null}
      <div
        className="
          relative w-full max-w-[414px] min-h-screen sm:min-h-[820px]
          bg-card sm:rounded-[44px] sm:border sm:border-line
          sm:shadow-mom overflow-hidden flex flex-col
        "
      >
        {children}
      </div>
    </div>
  );
}
