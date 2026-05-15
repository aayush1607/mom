"use client";

import { useEffect } from "react";

interface IosInstallSheetProps {
  open: boolean;
  onClose: () => void;
}

/**
 * Bottom sheet that explains the iOS Add-to-Home-Screen flow. Shown when the
 * user taps the Install button on iOS Safari, since Apple still doesn't
 * expose a programmatic prompt API.
 */
export function IosInstallSheet({ open, onClose }: IosInstallSheetProps) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-end sm:items-center justify-center bg-ink/40 backdrop-blur-sm"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
      aria-label="Install mom on iPhone"
    >
      <div
        className="
          w-full max-w-[440px] bg-card rounded-t-[28px] sm:rounded-[28px]
          border border-line p-7 pb-9 shadow-mom
        "
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center justify-between mb-5">
          <span className="brand-mark text-[22px]">
            mom<span className="dot">.</span>
          </span>
          <button
            onClick={onClose}
            className="text-[12px] uppercase tracking-[0.18em] text-ink-3 hover:text-ink"
            aria-label="Close"
          >
            close
          </button>
        </div>

        <h2 className="h-display text-[22px] mb-2">
          Add mom. to your home screen
        </h2>
        <p className="text-[13px] text-ink-2 mb-6">
          Two taps and she lives on your home screen — no app store, no signup.
        </p>

        <ol className="space-y-4">
          <Step n={1} label="Tap the Share button">
            <ShareGlyph />
            <span className="text-[12px] text-ink-3">at the bottom of Safari</span>
          </Step>
          <Step n={2} label="Scroll down → Add to Home Screen">
            <PlusGlyph />
          </Step>
          <Step n={3} label="Tap Add">
            <span className="text-[12px] text-ink-3">top-right of the sheet</span>
          </Step>
        </ol>

        <p className="text-[11px] text-ink-3 mt-7 leading-relaxed">
          Don&apos;t see Share? You&apos;re probably in Chrome or another
          browser. iOS only allows install from <strong>Safari</strong> — open
          this page there.
        </p>
      </div>
    </div>
  );
}

function Step({
  n,
  label,
  children,
}: {
  n: number;
  label: string;
  children?: React.ReactNode;
}) {
  return (
    <li className="flex items-start gap-4">
      <span
        className="
          shrink-0 inline-flex items-center justify-center
          w-8 h-8 rounded-full bg-brand text-white text-[13px] font-medium
        "
      >
        {n}
      </span>
      <div className="flex-1">
        <div className="text-[14px] text-ink font-medium leading-snug">
          {label}
        </div>
        <div className="mt-1 flex items-center gap-2">{children}</div>
      </div>
    </li>
  );
}

function ShareGlyph() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-ink-2"
      aria-hidden
    >
      <path d="M12 3v13" />
      <path d="m7 8 5-5 5 5" />
      <path d="M5 13v6a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6" />
    </svg>
  );
}

function PlusGlyph() {
  return (
    <svg
      width="22"
      height="22"
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="1.8"
      strokeLinecap="round"
      strokeLinejoin="round"
      className="text-ink-2"
      aria-hidden
    >
      <rect x="4" y="4" width="16" height="16" rx="3" />
      <path d="M12 8v8" />
      <path d="M8 12h8" />
    </svg>
  );
}
