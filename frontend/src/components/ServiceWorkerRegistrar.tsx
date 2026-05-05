"use client";

import { useEffect } from "react";

/** Registers /sw.js once on mount in the browser. No-op in dev/SSR. */
export function ServiceWorkerRegistrar() {
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (!("serviceWorker" in navigator)) return;
    if (process.env.NODE_ENV !== "production") return;
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // swallow — PWA shell is non-critical
    });
  }, []);
  return null;
}
