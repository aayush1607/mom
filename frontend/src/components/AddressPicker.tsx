"use client";

import { useEffect, useState } from "react";

import { useAddresses } from "@/lib/useAddresses";

/**
 * Address picker — small pill on /today (and /settings) that shows the
 * currently selected delivery address. Click → bottom sheet (mobile) /
 * centered modal (desktop) listing all the user's saved Swiggy addresses.
 *
 * State is owned by `useAddresses` (localStorage-backed); this component
 * is a thin presentation layer.
 */
export function AddressPicker({ className = "" }: { className?: string }) {
  const { addresses, selected, selectedId, setSelectedId, isLoading, error } =
    useAddresses();
  const [open, setOpen] = useState(false);

  // Lock body scroll while sheet is open so the page behind doesn't drift.
  useEffect(() => {
    if (!open) return;
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.body.style.overflow = prev;
    };
  }, [open]);

  // Close on Escape for keyboard accessibility on desktop.
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);

  const label = selected?.label ?? (isLoading ? "Loading…" : "Pick address");
  const disabled = !!error && addresses.length === 0;

  return (
    <>
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen(true)}
        title={selected?.address_line ?? undefined}
        className={[
          "inline-flex items-center gap-1.5 max-w-[60vw] sm:max-w-[280px]",
          "rounded-full border border-line bg-card",
          "px-3 py-1.5 text-[12px] sm:text-[13px] text-ink",
          "hover:border-brand/50 hover:text-brand transition-colors",
          "disabled:opacity-50 disabled:cursor-not-allowed",
          className,
        ].join(" ")}
      >
        <PinIcon />
        <span className="font-medium truncate">{label}</span>
        <ChevronIcon />
      </button>

      {open ? (
        <Sheet
          addresses={addresses}
          selectedId={selectedId}
          onPick={(id) => {
            setSelectedId(id);
            setOpen(false);
          }}
          onClose={() => setOpen(false)}
        />
      ) : null}
    </>
  );
}

// ── sheet / modal ───────────────────────────────────────────────────────────

interface SheetProps {
  addresses: ReturnType<typeof useAddresses>["addresses"];
  selectedId: string | null;
  onPick: (id: string) => void;
  onClose: () => void;
}

function Sheet({ addresses, selectedId, onPick, onClose }: SheetProps) {
  return (
    <div className="fixed inset-0 z-50 flex items-end sm:items-center justify-center">
      <button
        type="button"
        aria-label="Close address picker"
        onClick={onClose}
        className="absolute inset-0 bg-ink/40 sheet-fade"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label="Choose delivery address"
        className={[
          "relative w-full sm:max-w-[440px] max-h-[85vh] overflow-hidden",
          "bg-card sm:rounded-3xl rounded-t-3xl border border-line shadow-mom",
          "flex flex-col sheet-rise",
        ].join(" ")}
      >
        <div className="px-5 pt-4 pb-3 flex items-center justify-between border-b border-line">
          <div>
            <div className="text-[11px] uppercase tracking-[0.18em] text-ink-3">
              Delivering to
            </div>
            <div className="text-[18px] font-semibold mt-0.5">
              Where should mom send it?
            </div>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Close"
            className="rounded-full p-2 -mr-2 text-ink-3 hover:text-ink hover:bg-bg/60"
          >
            <CloseIcon />
          </button>
        </div>

        <ul className="flex-1 overflow-y-auto px-2 py-2">
          {addresses.length === 0 ? (
            <li className="px-3 py-6 text-center text-[13px] text-ink-3">
              No saved addresses on Swiggy. Add one in the Swiggy app first.
            </li>
          ) : (
            addresses.map((a) => {
              const isSel = a.id === selectedId;
              return (
                <li key={a.id}>
                  <button
                    type="button"
                    onClick={() => onPick(a.id)}
                    className={[
                      "w-full text-left px-3 py-3 rounded-2xl flex items-start gap-3",
                      "transition-colors",
                      isSel
                        ? "bg-brand/10 hover:bg-brand/15"
                        : "hover:bg-bg/60",
                    ].join(" ")}
                  >
                    <div className="pt-0.5 shrink-0">
                      <Tag category={a.category ?? null} />
                    </div>
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span
                          className={[
                            "text-[14px] font-semibold truncate",
                            isSel ? "text-brand" : "text-ink",
                          ].join(" ")}
                        >
                          {a.label}
                        </span>
                        {a.category && a.category !== a.label ? (
                          <span className="text-[10px] uppercase tracking-[0.15em] text-ink-3 shrink-0">
                            {a.category}
                          </span>
                        ) : null}
                      </div>
                      <div className="text-[12px] text-ink-2 mt-0.5 line-clamp-2">
                        {a.address_line}
                      </div>
                      {a.phone_masked ? (
                        <div className="text-[11px] text-ink-3 mt-1">
                          {a.phone_masked}
                        </div>
                      ) : null}
                    </div>
                    {isSel ? (
                      <span className="text-brand pt-0.5 shrink-0">
                        <CheckIcon />
                      </span>
                    ) : null}
                  </button>
                </li>
              );
            })
          )}
        </ul>

        <div className="px-5 py-3 border-t border-line text-[11px] text-ink-3 text-center">
          Saved on Swiggy. Add or edit in the Swiggy app.
        </div>
      </div>
    </div>
  );
}

// ── tiny icons ──────────────────────────────────────────────────────────────

function PinIcon() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 16 16"
      className="h-3.5 w-3.5 text-brand shrink-0"
      fill="none"
    >
      <path
        d="M8 14s5-4.5 5-8.5a5 5 0 10-10 0C3 9.5 8 14 8 14z"
        stroke="currentColor"
        strokeWidth="1.5"
        strokeLinejoin="round"
      />
      <circle cx="8" cy="5.5" r="1.5" fill="currentColor" />
    </svg>
  );
}

function ChevronIcon() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 16 16"
      className="h-3 w-3 text-ink-3 shrink-0"
      fill="none"
    >
      <path
        d="M4 6l4 4 4-4"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 16 16"
      className="h-4 w-4"
      fill="none"
    >
      <path
        d="M4 4l8 8M12 4l-8 8"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg
      aria-hidden
      viewBox="0 0 16 16"
      className="h-4 w-4"
      fill="none"
    >
      <path
        d="M3 8.5l3.5 3.5L13 5"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function Tag({ category }: { category: string | null }) {
  // Friendly emoji per Swiggy category bucket.
  const emoji =
    category === "Home"
      ? "🏠"
      : category === "Work"
        ? "💼"
        : category === "Friends & Family"
          ? "👥"
          : "📍";
  return (
    <span
      aria-hidden
      className="inline-flex h-9 w-9 items-center justify-center rounded-2xl bg-bg text-[16px]"
    >
      {emoji}
    </span>
  );
}
