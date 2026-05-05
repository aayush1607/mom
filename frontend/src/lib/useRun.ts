"use client";

import useSWR from "swr";

import { api } from "@/lib/api";
import type { RunSnapshot } from "@/types/agent";
import { isTerminal } from "@/types/agent";

const POLL_MS = 1500;

interface UseRun {
  snapshot: RunSnapshot | undefined;
  error: Error | undefined;
  isLoading: boolean;
  mutate: () => void;
}

/**
 * Polls `GET /agent/runs/:id` every 1500 ms while the run is non-terminal.
 * Terminates polling as soon as status ∈ {placed, cancelled_by_user, failed}.
 */
export function useRun(runId: string | null | undefined): UseRun {
  const { data, error, isLoading, mutate } = useSWR<RunSnapshot>(
    runId ? `/agent/runs/${runId}` : null,
    () => api.getRun(runId as string),
    {
      refreshInterval: (latest) => {
        if (!latest) return POLL_MS;
        return isTerminal(latest.status) ? 0 : POLL_MS;
      },
      revalidateOnFocus: false,
      shouldRetryOnError: true,
      errorRetryInterval: 2000,
      errorRetryCount: 5,
    },
  );

  return {
    snapshot: data,
    error: error as Error | undefined,
    isLoading,
    mutate: () => void mutate(),
  };
}
