import { describe, expect, it } from "vitest";

import { VOICE_STATE_COPY, isLive, voiceUiState, type VoiceSignals } from "./voice-state";

const live = (agentState: string | null, sessionEnded = false): VoiceSignals => ({
  connection: "live",
  agentState,
  sessionEnded,
});

describe("voiceUiState", () => {
  it("is idle before voice starts and after the learner stops it", () => {
    expect(voiceUiState({ connection: "off", agentState: null, sessionEnded: false })).toBe("idle");
    expect(voiceUiState({ connection: "ended", agentState: null, sessionEnded: false })).toBe("idle");
  });

  it("is connecting while the token/room is being set up and until the agent is ready", () => {
    expect(voiceUiState({ connection: "connecting", agentState: null, sessionEnded: false })).toBe("connecting");
    expect(voiceUiState(live(null))).toBe("connecting");
    expect(voiceUiState(live("initializing"))).toBe("connecting");
  });

  it("follows the agent's published state while live", () => {
    expect(voiceUiState(live("listening"))).toBe("listening");
    expect(voiceUiState(live("idle"))).toBe("listening");
    expect(voiceUiState(live("thinking"))).toBe("processing");
    expect(voiceUiState(live("speaking"))).toBe("speaking");
  });

  it("lets the closing line play, then shows completed", () => {
    expect(voiceUiState(live("speaking", true))).toBe("speaking");
    expect(voiceUiState(live("listening", true))).toBe("completed");
    expect(voiceUiState({ connection: "ended", agentState: null, sessionEnded: true })).toBe("completed");
  });

  it("shows an error for any failure, even if the session also ended", () => {
    expect(voiceUiState({ connection: "failed", agentState: null, sessionEnded: false })).toBe("error");
    expect(voiceUiState({ connection: "failed", agentState: "speaking", sessionEnded: true })).toBe("error");
  });

  it("has copy for every state, and live controls only while connected", () => {
    for (const state of ["idle", "connecting", "listening", "processing", "speaking", "completed", "error"] as const) {
      expect(VOICE_STATE_COPY[state].label).toBeTruthy();
    }
    expect(isLive("listening")).toBe(true);
    expect(isLive("idle")).toBe(false);
    expect(isLive("error")).toBe(false);
    expect(isLive("completed")).toBe(false);
  });
});
