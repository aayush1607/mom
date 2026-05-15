"use client";

import { useCallback, useEffect, useState } from "react";

/**
 * Status of the PWA install affordance for the current browser/device.
 *
 * - `loading`     — first paint, before we've checked the environment
 * - `installed`   — already running standalone (or iOS-standalone)
 * - `ready`       — Chrome/Edge/Brave fired `beforeinstallprompt`; one tap installs
 * - `ios`         — iOS Safari (no programmatic prompt; needs the Share-sheet hint)
 * - `unsupported` — desktop Firefox, in-app browsers, etc. — no install path
 */
export type InstallStatus =
  | "loading"
  | "installed"
  | "ready"
  | "ios"
  | "unsupported";

interface BeforeInstallPromptEvent extends Event {
  prompt: () => Promise<void>;
  userChoice: Promise<{ outcome: "accepted" | "dismissed" }>;
}

function detectIOS(): boolean {
  if (typeof navigator === "undefined") return false;
  const ua = navigator.userAgent;
  if (/iPad|iPhone|iPod/.test(ua)) return true;
  // iPadOS 13+ reports as MacIntel; touch points reveal it.
  return (
    navigator.platform === "MacIntel" &&
    typeof navigator.maxTouchPoints === "number" &&
    navigator.maxTouchPoints > 1
  );
}

function detectStandalone(): boolean {
  if (typeof window === "undefined") return false;
  if (window.matchMedia?.("(display-mode: standalone)").matches) return true;
  // iOS exposes a non-standard boolean.
  const navWithStandalone = window.navigator as Navigator & {
    standalone?: boolean;
  };
  return navWithStandalone.standalone === true;
}

export function useInstallPrompt() {
  const [status, setStatus] = useState<InstallStatus>("loading");
  const [deferred, setDeferred] = useState<BeforeInstallPromptEvent | null>(
    null,
  );

  useEffect(() => {
    if (typeof window === "undefined") return;

    const isIOS = detectIOS();

    const onBefore = (e: Event) => {
      e.preventDefault();
      setDeferred(e as BeforeInstallPromptEvent);
      setStatus("ready");
    };
    const onInstalled = () => {
      setStatus("installed");
      setDeferred(null);
    };

    window.addEventListener("beforeinstallprompt", onBefore);
    window.addEventListener("appinstalled", onInstalled);

    // Fire on next tick so React doesn't see a synchronous setState during the
    // effect body (avoids the "set-state-in-effect" lint and matches the rest
    // of our async detection flow).
    const initial = window.setTimeout(() => {
      if (detectStandalone()) setStatus("installed");
    }, 0);

    // If we don't hear from beforeinstallprompt within 1.2s, decide a fallback.
    // iOS will never fire it; other unsupported browsers won't either.
    const fallback = window.setTimeout(() => {
      setStatus((current) => {
        if (current !== "loading") return current;
        return isIOS ? "ios" : "unsupported";
      });
    }, 1200);

    return () => {
      window.removeEventListener("beforeinstallprompt", onBefore);
      window.removeEventListener("appinstalled", onInstalled);
      window.clearTimeout(initial);
      window.clearTimeout(fallback);
    };
  }, []);

  /**
   * Trigger the native install prompt (Chromium only). Resolves to the user's
   * choice. Callers should fall back to the iOS sheet when status === "ios".
   */
  const install = useCallback(async (): Promise<
    "accepted" | "dismissed" | "unavailable"
  > => {
    if (!deferred) return "unavailable";
    try {
      await deferred.prompt();
      const choice = await deferred.userChoice;
      setDeferred(null);
      if (choice.outcome === "accepted") {
        setStatus("installed");
      }
      return choice.outcome;
    } catch {
      return "unavailable";
    }
  }, [deferred]);

  return { status, install };
}
