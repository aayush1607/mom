"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { InstallButton } from "@/components/InstallButton";
import { useInstallPrompt } from "@/lib/useInstallPrompt";

export default function LandingPage() {
  const router = useRouter();
  const { status } = useInstallPrompt();

  // If a user lands on `/` from an already-installed shortcut (rare — most
  // users will land directly on start_url), shortcut them straight to /today.
  useEffect(() => {
    if (status === "installed") {
      const t = window.setTimeout(() => router.replace("/today"), 200);
      return () => window.clearTimeout(t);
    }
  }, [status, router]);

  return (
    <main className="min-h-screen flex flex-col">
      <Header />
      <Hero />
      <Why />
      <CtaStrip />
      <Footer />
    </main>
  );
}

function Header() {
  return (
    <header className="px-6 sm:px-10 pt-8 flex items-center justify-between max-w-[960px] w-full mx-auto">
      <span className="brand-mark text-[26px] sm:text-[28px]">
        mom<span className="dot">.</span>
      </span>
      <Link
        href="/today"
        className="text-[12px] uppercase tracking-[0.18em] text-ink-3 hover:text-ink"
      >
        peek inside →
      </Link>
    </header>
  );
}

function Hero() {
  return (
    <section className="px-6 sm:px-10 pt-14 sm:pt-24 pb-16 max-w-[680px] w-full mx-auto">
      <p className="text-[12px] uppercase tracking-[0.22em] text-brand mb-5">
        for people who are tired at 9pm
      </p>

      <h1 className="h-display text-[44px] sm:text-[64px] leading-[0.98] mb-6">
        Stop deciding
        <br />
        what to eat.
      </h1>

      <p className="text-[17px] sm:text-[19px] text-ink-2 leading-snug mb-10 max-w-[520px]">
        mom. picks dinner in seconds. one tap to confirm. no more scrolling
        Swiggy at midnight wondering why nothing looks good.
      </p>

      <InstallButton className="max-w-[360px]" />

      <ul className="mt-12 grid grid-cols-3 gap-4 text-center text-[11px] uppercase tracking-[0.16em] text-ink-3 max-w-[420px]">
        <li>
          <span className="block text-[22px] text-ink mb-1 normal-case tracking-normal h-display">
            seconds
          </span>
          to a pick
        </li>
        <li>
          <span className="block text-[22px] text-ink mb-1 normal-case tracking-normal h-display">
            1 tap
          </span>
          to order
        </li>
        <li>
          <span className="block text-[22px] text-ink mb-1 normal-case tracking-normal h-display">
            0
          </span>
          scrolling
        </li>
      </ul>
    </section>
  );
}

function Why() {
  const points = [
    {
      h: "She listens to one nudge.",
      p: "“protein-heavy, not oily.” That's it. mom. holds it for you and picks accordingly — every meal, every day.",
    },
    {
      h: "She won't push the same plate twice.",
      p: "Tap swap and mom thinks again — same nudge, fresh idea, never the dish she just suggested.",
    },
    {
      h: "Pakka? Order placed.",
      p: "Tap “Okay, mom” and you're done. No menu rabbit holes, no payment screens, no second-guessing.",
    },
  ];
  return (
    <section className="px-6 sm:px-10 py-16 bg-card border-y border-line">
      <div className="max-w-[720px] mx-auto">
        <p className="text-[12px] uppercase tracking-[0.22em] text-ink-3 mb-8">
          why mom?
        </p>
        <ul className="space-y-10">
          {points.map((pt, i) => (
            <li key={i} className="flex gap-5">
              <span className="shrink-0 text-brand text-[22px] h-display w-8">
                0{i + 1}
              </span>
              <div>
                <h3 className="h-display text-[22px] sm:text-[26px] mb-2">
                  {pt.h}
                </h3>
                <p className="text-[15px] text-ink-2 leading-relaxed">{pt.p}</p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

function CtaStrip() {
  return (
    <section className="px-6 sm:px-10 py-20 max-w-[680px] w-full mx-auto text-center">
      <h2 className="h-display text-[34px] sm:text-[44px] mb-4">
        Tonight, let mom. pick.
      </h2>
      <p className="text-[15px] text-ink-2 mb-8">
        Free. No signup. Lives on your home screen like any other app.
      </p>
      <InstallButton className="max-w-[360px] mx-auto" />
      <p className="mt-10 text-[12px] text-ink-3">
        or{" "}
        <Link
          href="/today"
          className="underline decoration-ink-3/50 underline-offset-4 hover:text-ink"
        >
          peek inside without installing →
        </Link>
      </p>
    </section>
  );
}

function Footer() {
  return (
    <footer className="px-6 sm:px-10 py-10 border-t border-line text-center text-[11px] text-ink-3">
      <p className="mb-1">
        mom. is in dry-run mode for now — no real orders are placed.
      </p>
      <p>
        a little side project ·{" "}
        <Link
          href="/settings"
          className="underline decoration-ink-3/40 underline-offset-2 hover:text-ink"
        >
          settings
        </Link>
      </p>
    </footer>
  );
}
