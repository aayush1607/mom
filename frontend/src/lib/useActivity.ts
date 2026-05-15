"use client";

import useSWR from "swr";

import { api } from "@/lib/api";
import type { RunActivity } from "@/types/agent";

const POLL_MS = 800;

interface UseActivity {
  activity: RunActivity | undefined;
  error: Error | undefined;
  isLoading: boolean;
}

/**
 * Polls `GET /agent/runs/:id/activity` every 800 ms.
 *
 * Caller must pass `enabled=false` once the run reaches a non-running
 * status so we stop hitting the backend (the loader screen unmounts then
 * anyway, but better safe).
 */
export function useActivity(
  runId: string | null | undefined,
  enabled = true,
): UseActivity {
  const { data, error, isLoading } = useSWR<RunActivity>(
    runId && enabled ? `/agent/runs/${runId}/activity` : null,
    () => api.getRunActivity(runId as string),
    {
      refreshInterval: enabled ? POLL_MS : 0,
      revalidateOnFocus: false,
      shouldRetryOnError: true,
      errorRetryInterval: 1500,
      errorRetryCount: 6,
      keepPreviousData: true,
    },
  );

  return {
    activity: data,
    error: error as Error | undefined,
    isLoading,
  };
}
