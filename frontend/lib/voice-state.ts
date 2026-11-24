// Voice session UI state, derived only from real events:
//   connection    - what VoicePanel knows about the LiveKit room (token request, connect,
//                   microphone permission, disconnects)
//   agentState    - the agent's `lk.agent.state` participant attribute, published by the
//                   LiveKit worker: initializing | idle | listening | thinking | speaking
//   sessionEnded  - the assessment API says the session is completed or incomplete
// Nothing here is simulated or timed; the component re-renders when these change.

export type VoiceConnection = "off" | "connecting" | "live" | "ended" | "failed";

export type VoiceUiState =
  | "idle" // voice not started (or stopped); the learner can start it
  | "connecting" // getting a token, joining the room, or waiting for the agent to join
  | "listening" // the agent is waiting for the learner to speak
  | "processing" // the agent is waiting on the assessment API (evaluating the answer)
  | "speaking" // the agent is talking (question, follow-up or closing line)
  | "completed" // the check-in is over
  | "error"; // voice failed; text still works and voice can be retried

export interface VoiceSignals {
  connection: VoiceConnection;
  agentState: string | null;
  sessionEnded: boolean;
}

export function voiceUiState({ connection, agentState, sessionEnded }: VoiceSignals): VoiceUiState {
  if (connection === "failed") return "error";
  if (connection === "connecting") return "connecting";
  if (connection === "live") {
    // While the closing line plays the agent is still "speaking"; after that, completed.
    if (agentState === "speaking") return "speaking";
    if (sessionEnded) return "completed";
    if (agentState === "thinking") return "processing";
    if (agentState === "listening" || agentState === "idle") return "listening";
    return "connecting"; // joined the room, agent not ready yet ("initializing" or unknown)
  }
  return sessionEnded ? "completed" : "idle";
}

export const VOICE_STATE_COPY: Record<VoiceUiState, { label: string; hint: string }> = {
  idle: { label: "Ready when you are", hint: "Press the microphone to answer by voice, or type below." },
  connecting: { label: "Connecting", hint: "Joining the voice room. This takes a few seconds." },
  listening: { label: "Listening", hint: "Speak your answer. Pause when you're done." },
  processing: { label: "Thinking", hint: "Checking your answer." },
  speaking: { label: "Kira Verbal is speaking", hint: "You can interrupt at any time." },
  completed: { label: "Check-in finished", hint: "Your teacher will review your answers." },
  error: { label: "Voice isn't working", hint: "You can keep answering by typing, or try voice again." },
};

// Whether the microphone/end controls apply in this state.
export function isLive(state: VoiceUiState) {
  return state === "listening" || state === "processing" || state === "speaking" || state === "connecting";
}
