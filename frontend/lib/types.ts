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
  | "teacher_not_found"
  | "report_not_found"
  | "stale_revision"
  | "report_not_ready"
  | "report_not_approved"
  | "invalid_review"
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

// --- teacher (mirrors backend/app/schemas/reports.py) -----------------------------------

export type ReportStatus = "pending" | "ready_for_review" | "approved" | "rejected";

export interface LessonRef {
  id: string;
  version: number;
  title: string;
}

export interface WorkspaceCreated {
  workspace_id: string;
  teacher_token: string;
}

export interface TeacherSessionCreated {
  session_id: string;
  session_token: string;
  lesson: LessonRef;
  synthetic_learner_id: string;
}

export interface TeacherSessionItem {
  session_id: string;
  lesson: LessonRef;
  synthetic_learner_id: string;
  session_status: SessionStatus;
  finish_reason: FinishReason | null;
  created_at: string;
  report_status: ReportStatus;
  report_revision: number | null;
  answer_turns: number;
  wellbeing_flags: number;
}

export interface EvidenceItem {
  id: string;
  turn_sequence: number;
  criterion_id: string;
  quote: string;
  proposed_level: number | null;
  status: "accepted" | "abstained" | "rejected";
  assisted: boolean;
  misconception_tag: string | null;
  reason: string;
  rejection_reason: string | null;
  evaluator_version: string;
}

export interface CriterionReport {
  criterion_id: string;
  objective: string;
  objective_description: string;
  level_descriptors: Record<string, string>;
  suggested_level: number | null;
  level: number | null;
  independent_levels: number[];
  assisted_levels: number[];
  misconceptions: { tag: string; description: string }[];
  conflicting: boolean;
  abstentions: number;
  rejected: number;
  evidence: EvidenceItem[];
}

export interface TeacherTranscriptTurn {
  sequence: number;
  question_id: string;
  question_text: string;
  answer: string;
  modality: "text" | "voice";
  assisted: boolean;
  intent: string | null;
  signal: string | null;
  reply: string | null;
}

export interface ReviewEntry {
  id: string;
  from_revision: number;
  to_revision: number;
  reviewer_id: string;
  decision: "approve" | "reject";
  approved_levels: Record<string, number | null> | null;
  reason: string;
  created_at: string;
}

export interface ExportEntry {
  id: string;
  report_id: string;
  report_revision: number;
  schema_version: string;
  idempotency_key: string;
  payload: Record<string, unknown>;
  created_at: string;
}

export interface ReportView {
  session_id: string;
  report_id: string | null;
  revision: number | null;
  status: ReportStatus;
  lesson: LessonRef;
  synthetic_learner_id: string;
  session_status: SessionStatus;
  finish_reason: FinishReason | null;
  session_created_at: string;
  coverage: { with_evidence: number; total: number };
  needs_review: boolean;
  wellbeing_turns: number[];
  hints_used: number;
  side_turns: number;
  criteria: CriterionReport[];
  transcript: TeacherTranscriptTurn[];
  revisions: { report_id: string; revision: number; status: ReportStatus; created_by: string; created_at: string }[];
  reviews: ReviewEntry[];
  exports: ExportEntry[];
}

export interface ReviewRequest {
  decision: "approve" | "reject";
  levels?: Record<string, number | null>;
  reason: string;
  reviewer_id?: string;
}

export interface ExportResponse extends ExportEntry {
  replayed: boolean;
}
