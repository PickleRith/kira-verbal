// Mirrors backend/app/schemas/*.py. Keep in sync by hand until types are generated
// from the OpenAPI schema (http://127.0.0.1:8000/openapi.json).

export type SessionStatus =
  | "created"
  | "awaiting_answer"
  | "evaluating"
  | "completed"
  | "incomplete";

// "respond": the same question again after a turn that was not an answer
// (a question about the topic, "say that again", off topic).
export type Purpose = "open" | "diagnostic" | "clarify" | "hint" | "respond";

export type FinishReason =
  | "learner_request"
  | "budget"
  | "objectives_exhausted"
  | "timeout"
  | "learner_exit";

export interface LessonSummary {
  id: string;
  version: number;
  title: string;
  objective_count: number;
}

export interface Prompt {
  question_id: string;
  text: string;
  purpose: Purpose;
  lead_in: string | null;
  hint: string | null;
}

export interface TranscriptEntry {
  sequence: number;
  question_id: string;
  question_text: string;
  answer: string;
  modality: "text" | "voice";
  assisted: boolean;
  reply: string | null; // what the agent said after this turn
}

export interface SessionView {
  id: string;
  lesson: { id: string; version: number; title: string };
  status: SessionStatus;
  state_version: number;
  prompt: Prompt | null;
  finish_reason: FinishReason | null;
  transcript: TranscriptEntry[];
  deadline_at: string;
}

export interface CreateSessionResponse extends SessionView {
  session_token: string;
}

export interface TurnInput {
  client_turn_id: string;
  expected_state_version: number;
  transcript: string;
  modality: "text" | "voice";
  question_id: string;
}

export interface TurnResponse {
  state_version: number;
  status: SessionStatus;
  prompt: Prompt | null;
  finish_reason: FinishReason | null;
}

export interface VoiceToken {
  server_url: string;
  participant_token: string;
  room_name: string;
  expires_at: string;
}

export type ErrorCode =
  | "voice_unavailable"
  | "missing_token"
  | "session_not_found"
  | "lesson_not_found"
  | "stale_state_version"
  | "idempotency_mismatch"
  | "turn_in_progress"
  | "claim_lost"
  | "question_mismatch"
  | "session_closed"
  | "session_expired"
  | "evaluation_unavailable"
  | "invalid_input"
  | "network_error"
  | "unknown_error";
