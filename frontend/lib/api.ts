// Typed HTTP client for the Kira Verbal API. Every failure becomes an ApiError with a
// machine-readable `code`, so pages can decide how to recover without parsing strings.

import type {
  AuthResponse,
  CreateSessionResponse,
  Me,
  RegisterRequest,
  StudentSessionItem,
  ErrorCode,
  ExportResponse,
  LessonSummary,
  ReportView,
  ReviewRequest,
  TeacherSessionCreated,
  TeacherSessionItem,
  WorkspaceCreated,
  SessionView,
  TurnInput,
  TurnResponse,
  VoiceToken,
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
  empty?: boolean; // 204 No Content
  body?: unknown;
  token?: string;
}

async function request<T>(path: string, { method = "GET", body, token, empty }: RequestOptions = {}) {
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
  if (empty) return undefined as T;
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

  createVoiceToken: (sessionId: string, token: string) =>
    request<VoiceToken>(`/v1/sessions/${sessionId}/voice-token`, { method: "POST", token }),

  finish: (sessionId: string, token: string, expectedStateVersion: number) =>
    request<SessionView>(`/v1/sessions/${sessionId}/finish`, {
      method: "POST",
      body: { expected_state_version: expectedStateVersion },
      token,
    }),

  // --- accounts (token = the sign-in token) -------------------------------------------
  register: (body: RegisterRequest) =>
    request<AuthResponse>("/v1/auth/register", { method: "POST", body }),

  login: (email: string, password: string) =>
    request<AuthResponse>("/v1/auth/login", { method: "POST", body: { email, password } }),

  logout: (token: string) => request<void>("/v1/auth/logout", { method: "POST", token, empty: true }),

  me: (token: string) => request<Me>("/v1/me", { token }),

  joinClass: (token: string, joinCode: string) =>
    request<Me>("/v1/me/class", { method: "POST", body: { join_code: joinCode }, token }),

  mySessions: (token: string) => request<StudentSessionItem[]>("/v1/me/sessions", { token }),

  startLesson: (token: string, lessonId: string) =>
    request<CreateSessionResponse>("/v1/me/sessions", { method: "POST", body: { lesson_id: lessonId }, token }),

  resumeSession: (token: string, sessionId: string) =>
    request<{ session_id: string; session_token: string }>(`/v1/me/sessions/${sessionId}/resume`, {
      method: "POST",
      token,
    }),

  // --- teacher (token = a signed-in teacher's token, or a demo classroom token) -------
  createWorkspace: () =>
    request<WorkspaceCreated>("/v1/teacher/workspaces", { method: "POST" }),

  checkWorkspace: (teacherToken: string) =>
    request<{ workspace_id: string }>("/v1/teacher/workspace", { token: teacherToken }),

  teacherCreateSession: (teacherToken: string, lessonId: string, learnerId: string) =>
    request<TeacherSessionCreated>("/v1/teacher/sessions", {
      method: "POST",
      body: { lesson_id: lessonId, synthetic_learner_id: learnerId },
      token: teacherToken,
    }),

  teacherSessions: (teacherToken: string) =>
    request<TeacherSessionItem[]>("/v1/teacher/sessions", { token: teacherToken }),

  getReport: (teacherToken: string, sessionId: string) =>
    request<ReportView>(`/v1/sessions/${sessionId}/report`, { token: teacherToken }),

  reviewReport: (teacherToken: string, reportId: string, body: ReviewRequest) =>
    request<ReportView>(`/v1/reports/${reportId}/review`, { method: "POST", body, token: teacherToken }),

  exportReport: (teacherToken: string, reportId: string) =>
    request<ExportResponse>(`/v1/reports/${reportId}/export`, { method: "POST", token: teacherToken }),
};
