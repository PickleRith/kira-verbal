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
  | "not_signed_in"
  | "invalid_credentials"
  | "email_taken"
  | "wrong_role"
  | "class_not_found"
  | "no_class"
  | "rate_limited"
  | "payload_too_large"
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

export type GradeBand = "mastered" | "proficient" | "developing" | "beginning" | "incomplete";

// Rubric levels as a score. Unknown criteria are left out of the points (never zero) and
// make the band "incomplete". Rule: backend/app/domain/grading.py, mirrored in lib/grading.ts.
export interface ScoreView {
  points: number;
  max_points: number;
  percent: number | null;
  assessed: number;
  total: number;
  band: GradeBand;
}

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
  learner_name: string | null;
  session_status: SessionStatus;
  finish_reason: FinishReason | null;
  created_at: string;
  report_status: ReportStatus;
  report_revision: number | null;
  answer_turns: number;
  wellbeing_flags: number;
  score: ScoreView | null; // null while the student is answering
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
  learner_name: string | null;
  session_status: SessionStatus;
  finish_reason: FinishReason | null;
  session_created_at: string;
  coverage: { with_evidence: number; total: number };
  needs_review: boolean;
  wellbeing_turns: number[];
  hints_used: number;
  side_turns: number;
  criteria: CriterionReport[];
  score: ScoreView; // this revision's levels
  suggested_score: ScoreView; // the system's suggestion
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

// --- accounts (mirrors backend/app/schemas/accounts.py) ---------------------------------

export type Role = "student" | "teacher";

export interface ClassView {
  id: string;
  name: string;
  join_code: string | null; // teacher only
  teacher_name: string | null;
  student_count: number | null; // teacher only
}

export interface Me {
  id: string;
  email: string;
  display_name: string;
  role: Role;
  created_at: string;
  class: ClassView | null;
}

export interface AuthResponse {
  token: string;
  expires_at: string;
  user: Me;
}

export interface RegisterRequest {
  email: string;
  password: string;
  display_name: string;
  role: Role;
  join_code?: string;
  class_name?: string;
}

export type ReviewStatus = "in_progress" | "awaiting_review" | "reviewed";

export interface StudentCriterionResult {
  criterion_id: string;
  objective_description: string;
  level: number | null;
  max_level: number;
  descriptor: string | null;
}

// Only present once the teacher has approved the check-in.
export interface StudentResult {
  score: ScoreView;
  approved_at: string;
  criteria: StudentCriterionResult[];
}

export interface StudentSessionItem {
  session_id: string;
  lesson: LessonRef;
  session_status: SessionStatus;
  finish_reason: FinishReason | null;
  created_at: string;
  answers: number;
  review_status: ReviewStatus;
  result: StudentResult | null;
}
