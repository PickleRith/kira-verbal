// Typed HTTP client for the Kira Verbal API. Every failure becomes an ApiError with a
// machine-readable `code`, so pages can decide how to recover without parsing strings.

import type {
  CreateSessionResponse,
  ErrorCode,
  LessonSummary,
  SessionView,
  TurnInput,
  TurnResponse,
} from "./types";

const BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly code: ErrorCode,
    message: string,
    public readonly stateVersion: number | null = null,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

interface RequestOptions {
  method?: "GET" | "POST";
  body?: unknown;
  token?: string;
}

async function request<T>(path: string, { method = "GET", body, token }: RequestOptions = {}) {
  const headers: Record<string, string> = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (token) headers["Authorization"] = `Bearer ${token}`;

  let response: Response;
  try {
    response = await fetch(`${BASE_URL}${path}`, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
      cache: "no-store",
    });
  } catch {
    throw new ApiError(0, "network_error", "Can't reach the server. Check your connection and try again.");
  }

  if (!response.ok) {
    let data: { error?: string; message?: string; state_version?: number | null } = {};
    try {
      data = await response.json();
    } catch {
      // non-JSON error body; fall through to generic message
    }
    const code = (data.error ?? (response.status === 422 ? "invalid_input" : "unknown_error")) as ErrorCode;
    throw new ApiError(
      response.status,
      code,
      data.message ?? `Request failed (${response.status})`,
      data.state_version ?? null,
    );
  }
  return (await response.json()) as T;
}

export const api = {
  listLessons: () => request<LessonSummary[]>("/v1/lessons"),

  createSession: (lessonId: string) =>
    request<CreateSessionResponse>("/v1/sessions", {
      method: "POST",
      body: { lesson_id: lessonId },
    }),

  getSession: (sessionId: string, token: string) =>
    request<SessionView>(`/v1/sessions/${sessionId}`, { token }),

  submitTurn: (sessionId: string, token: string, turn: TurnInput) =>
    request<TurnResponse>(`/v1/sessions/${sessionId}/turns`, { method: "POST", body: turn, token }),

  finish: (sessionId: string, token: string, expectedStateVersion: number) =>
    request<SessionView>(`/v1/sessions/${sessionId}/finish`, {
      method: "POST",
      body: { expected_state_version: expectedStateVersion },
      token,
    }),
};
