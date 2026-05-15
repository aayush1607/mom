"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import useSWR from "swr";

import { api } from "@/lib/api";
import type { Address, ListAddressesResponse } from "@/types/agent";

const STORAGE_KEY = "mom.address.id";

interface UseAddresses {
  addresses: Address[];
  isLoading: boolean;
  error: Error | undefined;
  selected: Address | null;
  selectedId: string | null;
  /** Persist a new selection. Use null to clear. */
  setSelectedId: (id: string | null) => void;
}

/**
 * Lists the user's saved Swiggy addresses and tracks which one is selected.
 *
 * Selection is persisted in localStorage (`mom.address.id`) so the choice
 * survives reloads. If the persisted id isn't in the fetched list (e.g.
 * the user removed it on Swiggy), we silently fall back to the first
 * address in the list — never leave the user with an invalid selection.
 *
 * Default seed: `NEXT_PUBLIC_TEST_ADDRESS_ID` env var, then first address.
 */
export function useAddresses(): UseAddresses {
  const { data, error, isLoading } = useSWR<ListAddressesResponse>(
    "/agent/addresses",
    () => api.listAddresses(),
    {
      revalidateOnFocus: false,
      dedupingInterval: 60_000,
      shouldRetryOnError: true,
      errorRetryCount: 2,
    },
  );

  const addresses = useMemo(() => data?.addresses ?? [], [data]);

  const [selectedId, setSelectedIdState] = useState<string | null>(null);

  // Hydrate selection from localStorage exactly once on mount.
  useEffect(() => {
    if (typeof window === "undefined") return;
    const fromStorage = window.localStorage.getItem(STORAGE_KEY);
    if (!fromStorage) return;
    // Defer setState a tick to satisfy React 19's set-state-in-effect rule.
    const t = window.setTimeout(() => setSelectedIdState(fromStorage), 0);
    return () => window.clearTimeout(t);
  }, []);

  // When the address list arrives, validate / seed the selection.
  useEffect(() => {
    if (addresses.length === 0) return;
    const t = window.setTimeout(() => {
      setSelectedIdState((current) => {
        if (current && addresses.some((a) => a.id === current)) {
          return current; // already valid
        }
        const envSeed = process.env.NEXT_PUBLIC_TEST_ADDRESS_ID ?? null;
        const seedHit =
          envSeed && addresses.find((a) => a.id === envSeed)?.id;
        const next = seedHit ?? addresses[0]?.id ?? null;
        if (next && typeof window !== "undefined") {
          window.localStorage.setItem(STORAGE_KEY, next);
        }
        return next ?? null;
      });
    }, 0);
    return () => window.clearTimeout(t);
  }, [addresses]);

  const setSelectedId = useCallback((id: string | null) => {
    setSelectedIdState(id);
    if (typeof window === "undefined") return;
    if (id) window.localStorage.setItem(STORAGE_KEY, id);
    else window.localStorage.removeItem(STORAGE_KEY);
  }, []);

  const selected = useMemo(
    () => addresses.find((a) => a.id === selectedId) ?? null,
    [addresses, selectedId],
  );

  return {
    addresses,
    isLoading,
    error: error as Error | undefined,
    selected,
    selectedId,
    setSelectedId,
  };
}
