/**
 * Thin typed wrapper over the four meal-agent endpoints.
 *
 * The backend lives at `NEXT_PUBLIC_API_BASE` (default localhost:8765).
 * `user_token` is passed in the request body for now — it's a stub during
 * v1 because the FE skips Swiggy OAuth and the backend reads its own token
 * from `.env`. We send an empty string and rely on the backend's MCP layer.
 */

import type {
  CreateRunRequest,
  CreateRunResponse,
  ResumeRequest,
  RunSnapshot,
  UserDecisionKind,
} from "@/types/agent";

const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE ?? "http://localhost:8765";

const USER_TOKEN_PLACEHOLDER =
  process.env.NEXT_PUBLIC_USER_TOKEN ?? ""; // backend resolves from .env in v1

export class ApiError extends Error {
  constructor(
    public status: number,
    public detail: string,
  ) {
    super(`${status}: ${detail}`);
    this.name = "ApiError";
  }
}

async function request<T>(
  path: string,
  init?: RequestInit,
): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      ...(init?.headers ?? {}),
    },
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      // ignore
    }
    throw new ApiError(res.status, detail);
  }
  return (await res.json()) as T;
}

export const api = {
  baseUrl: API_BASE,

  createRun(body: Omit<CreateRunRequest, "user_token">): Promise<CreateRunResponse> {
    return request<CreateRunResponse>("/agent/runs", {
      method: "POST",
      body: JSON.stringify({
        ...body,
        user_token: USER_TOKEN_PLACEHOLDER,
      }),
    });
  },

  getRun(runId: string): Promise<RunSnapshot> {
    return request<RunSnapshot>(`/agent/runs/${runId}`);
  },

  resumeRun(
    runId: string,
    decision: UserDecisionKind,
    note?: string,
  ): Promise<CreateRunResponse> {
    const body: ResumeRequest = {
      decision,
      note,
      user_token: USER_TOKEN_PLACEHOLDER,
    };
    return request<CreateRunResponse>(`/agent/runs/${runId}/resume`, {
      method: "POST",
      body: JSON.stringify(body),
    });
  },

  cancelRun(runId: string): Promise<{ run_id: string; status: string }> {
    return request<{ run_id: string; status: string }>(
      `/agent/runs/${runId}/cancel`,
      { method: "POST" },
    );
  },
};
