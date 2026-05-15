"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { IosInstallSheet } from "@/components/IosInstallSheet";
import { Button } from "@/components/ui/Button";
import { useInstallPrompt } from "@/lib/useInstallPrompt";

interface InstallButtonProps {
  /**
   * Where to send the user when they're already installed (or just accepted
   * the prompt). Defaults to `/today`.
   */
  installedHref?: string;
  /** Override the primary label shown when ready/iOS/unsupported. */
  label?: string;
  className?: string;
}

/**
 * Smart install CTA:
 * - Chromium + prompt available → fires the native install dialog.
 * - iOS Safari → opens the Add-to-Home-Screen instructions sheet.
 * - Already installed → label flips to "Open mom." and routes into the app.
 * - Unsupported (Firefox desktop, in-app browsers) → routes into the app
 *   directly so we never dead-end the user.
 */
export function InstallButton({
  installedHref = "/today",
  label,
  className,
}: InstallButtonProps) {
  const router = useRouter();
  const { status, install } = useInstallPrompt();
  const [iosOpen, setIosOpen] = useState(false);

  async function onClick() {
    if (status === "installed") {
      router.push(installedHref);
      return;
    }
    if (status === "ready") {
      const outcome = await install();
      if (outcome === "accepted") {
        router.push(installedHref);
      }
      return;
    }
    if (status === "ios") {
      setIosOpen(true);
      return;
    }
    // unsupported / loading — let the user in anyway
    router.push(installedHref);
  }

  const text =
    status === "installed"
      ? "Open mom."
      : status === "loading"
        ? "Install mom."
        : (label ?? "Install mom. — free");

  const sub =
    status === "ready"
      ? "one tap, lives on your home screen"
      : status === "ios"
        ? "iPhone? we'll show you how"
        : status === "installed"
          ? "you've got her — let's eat"
          : status === "unsupported"
            ? "open in Chrome or Safari to install"
            : "";

  return (
    <>
      <div className={className}>
        <Button
          variant="brand"
          fullWidth
          onClick={onClick}
          className="!py-4 !text-[16px] shadow-mom"
        >
          {text}
        </Button>
        {sub ? (
          <p className="mt-2 text-center text-[12px] text-ink-3">{sub}</p>
        ) : null}
      </div>
      <IosInstallSheet open={iosOpen} onClose={() => setIosOpen(false)} />
    </>
  );
}
