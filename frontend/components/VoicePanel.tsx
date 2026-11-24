"use client";

// Optional voice mode, built around one central microphone.
//
// The text form on the page always stays usable: if voice isn't configured, the microphone
// is blocked, or the connection drops, the learner keeps typing. The browser never decides
// anything about the assessment; it streams audio to a LiveKit room where the worker
// forwards finalized answers to the same API the text form uses.
//
// UI state comes from real events only (lib/voice-state.ts): the voice-token request, the
// room connection, microphone permission, the agent's `lk.agent.state` attribute, and the
// assessment API saying the session ended.
//
// livekit-client usage follows the LiveKit docs (Room.connect, setMicrophoneEnabled,
// RoomEvent.TrackSubscribed + track.attach(), agent state in the `lk.agent.state` attribute).
// The waveform reads the raw tracks: localParticipant.getTrackPublication(Track.Source.Microphone)
// and RemoteTrack.mediaStreamTrack (both in the livekit-client 2.25 type definitions).

import { Room, RoomEvent, Track, type RemoteTrack } from "livekit-client";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, api } from "@/lib/api";
import { VOICE_STATE_COPY, isLive, voiceUiState, type VoiceConnection, type VoiceUiState } from "@/lib/voice-state";

import { Button, Card, Icon, Spinner, cx } from "./ui";
import { Waveform } from "./Waveform";

const POLL_MS = 2000; // refresh the on-screen transcript while voice is active
// After the session ends the worker speaks the closing line and then leaves the room.
// If that never happens (network, worker crash), hang up ourselves after this long.
const CLOSING_GRACE_MS = 30_000;

const BADGE: Record<VoiceUiState, string> = {
  idle: "bg-sunken text-muted",
  connecting: "bg-lavender-soft text-purple-ink",
  listening: "bg-lavender-soft text-purple-ink",
  processing: "bg-lavender-soft text-purple-ink",
  speaking: "bg-lavender-soft text-purple-ink",
  completed: "bg-ok-soft text-ok",
  error: "bg-bad-soft text-bad",
};

export function VoicePanel({
  sessionId,
  token,
  onActivity,
  finished = false,
}: {
  sessionId: string;
  token: string;
  onActivity: () => void;
  finished?: boolean; // the assessment is over: no new voice, but let the closing line play
}) {
  const [connection, setConnection] = useState<VoiceConnection>("off");
  const [agentState, setAgentState] = useState<string | null>(null);
  const [micOn, setMicOn] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [micTrack, setMicTrack] = useState<MediaStreamTrack | null>(null);
  const [agentTrack, setAgentTrack] = useState<MediaStreamTrack | null>(null);
  const roomRef = useRef<Room | null>(null);
  const audioRef = useRef<HTMLDivElement>(null);

  const teardown = useCallback(() => {
    const room = roomRef.current;
    roomRef.current = null;
    if (room) void room.disconnect();
    if (audioRef.current) audioRef.current.innerHTML = "";
    setAgentState(null);
    setMicTrack(null);
    setAgentTrack(null);
  }, []);

  useEffect(() => teardown, [teardown]); // disconnect when leaving the page

  useEffect(() => {
    if (!finished || connection !== "live") return;
    const id = window.setTimeout(() => {
      teardown();
      setConnection("ended");
    }, CLOSING_GRACE_MS);
    return () => window.clearTimeout(id);
  }, [finished, connection, teardown]);

  useEffect(() => {
    if (connection !== "live") return;
    const id = window.setInterval(onActivity, POLL_MS);
    return () => window.clearInterval(id);
  }, [connection, onActivity]);

  const readMicTrack = useCallback((room: Room) => {
    const track = room.localParticipant.getTrackPublication(Track.Source.Microphone)?.track;
    setMicTrack(track?.mediaStreamTrack ?? null);
  }, []);

  function fail(message: string) {
    teardown();
    setConnection("failed");
    setError(message);
  }

  async function start() {
    setError(null);
    setConnection("connecting");
    let details;
    try {
      details = await api.createVoiceToken(sessionId, token);
    } catch (e) {
      fail(
        e instanceof ApiError && e.code === "voice_unavailable"
          ? "Voice isn't available on this server. You can keep answering by typing."
          : e instanceof ApiError && e.code === "network_error"
            ? "Couldn't reach the server to start voice. Check your connection, or keep typing."
            : "Couldn't start voice. You can keep answering by typing.",
      );
      return;
    }

    const room = new Room();
    roomRef.current = room;
    room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
      if (track.kind === Track.Kind.Audio && audioRef.current) {
        audioRef.current.appendChild(track.attach());
        setAgentTrack(track.mediaStreamTrack);
      }
    });
    room.on(RoomEvent.LocalTrackPublished, () => readMicTrack(room));
    room.on(RoomEvent.ParticipantAttributesChanged, (_changed, participant) => {
      const state = participant.attributes["lk.agent.state"];
      if (state) setAgentState(state);
    });
    // The agent leaves after speaking the closing line (or if the worker stops). With no
    // one left to talk to, end voice here instead of leaving the learner in an empty room.
    room.on(RoomEvent.ParticipantDisconnected, () => {
      if (roomRef.current === room && room.remoteParticipants.size === 0) {
        teardown();
        setConnection("ended");
        onActivity();
      }
    });
    room.on(RoomEvent.Disconnected, () => {
      if (roomRef.current === room) {
        teardown();
        setConnection("ended");
        onActivity();
      }
    });

    try {
      await room.connect(details.server_url, details.participant_token);
    } catch {
      fail("Couldn't connect to voice. You can keep answering by typing, or try again.");
      return;
    }
    try {
      await room.localParticipant.setMicrophoneEnabled(true);
      setMicOn(true);
      readMicTrack(room);
    } catch {
      fail("Microphone access was blocked. Allow it in your browser to use voice, or keep typing.");
      return;
    }
    setConnection("live");
  }

  async function toggleMic() {
    const room = roomRef.current;
    if (!room) return;
    const next = !micOn;
    await room.localParticipant.setMicrophoneEnabled(next);
    setMicOn(next);
    readMicTrack(room); // unmuting can replace the underlying track
  }

  function end() {
    teardown();
    setConnection("ended");
    onActivity();
  }

  const state = voiceUiState({ connection, agentState, sessionEnded: finished });
  if (finished && connection !== "live") return null; // over, and nothing left to hear
  const copy = VOICE_STATE_COPY[state];
  const live = isLive(state) && connection === "live";
  const muted = live && !micOn;

  // The central microphone: starts voice when idle or after an error, mutes while live.
  const micAction =
    state === "idle" || state === "error" ? () => void start() : live ? () => void toggleMic() : undefined;
  const micLabel =
    state === "error"
      ? "Try voice again"
      : state === "idle"
        ? "Start answering by voice"
        : muted
          ? "Unmute microphone"
          : live
            ? "Mute microphone"
            : copy.label;

  return (
    <Card className="mt-4 p-5 md:p-6" aria-label="Voice answers">
      <div className="flex items-center justify-between gap-3">
        <p className="flex items-center gap-2 text-sm font-medium text-ink">
          <Icon.Waveform className="h-4 w-4 text-purple" /> Voice
        </p>
        <span
          role="status"
          aria-live="polite"
          data-testid="voice-state"
          data-state={state}
          className={cx("inline-flex items-center gap-1.5 rounded-md px-2 py-0.5 text-xs font-medium", BADGE[state])}
        >
          <span className={cx("h-1.5 w-1.5 rounded-full", state === "error" ? "bg-bad" : state === "completed" ? "bg-ok" : state === "idle" ? "bg-faint" : "bg-purple")} />
          {muted ? "Muted" : copy.label}
        </span>
      </div>

      <div className="mt-5 flex flex-col items-center text-center">
        <span className="relative flex h-20 w-20 items-center justify-center">
          {state === "listening" && !muted ? <span className="kv-pulse absolute inset-0 rounded-full bg-lavender" /> : null}
          <button
            type="button"
            onClick={micAction}
            disabled={!micAction}
            aria-label={micLabel}
            aria-pressed={live ? muted : undefined}
            className={cx(
              "kv-ease relative flex h-20 w-20 items-center justify-center rounded-full border transition-colors disabled:cursor-default",
              state === "error"
                ? "border-bad/40 bg-bad-soft text-bad hover:bg-[#fbdcd8]"
                : state === "completed"
                  ? "border-ok/30 bg-ok-soft text-ok"
                  : muted
                    ? "border-line-strong bg-surface text-muted hover:bg-raised"
                    : state === "idle"
                      ? "border-purple-ink bg-purple-ink text-white hover:bg-[#4a22c2]"
                      : "border-purple bg-purple text-white",
            )}
          >
            {state === "connecting" ? (
              <Spinner className="h-7 w-7" />
            ) : state === "error" ? (
              <Icon.Retry className="h-7 w-7" />
            ) : state === "completed" ? (
              <Icon.Check className="h-7 w-7" />
            ) : state === "speaking" ? (
              <Icon.Speaker className="h-7 w-7" />
            ) : muted ? (
              <Icon.MicOff className="h-7 w-7" />
            ) : (
              <Icon.Mic className="h-7 w-7" />
            )}
          </button>
        </span>
        <p className="mt-4 font-serif text-[22px] text-ink">{muted ? "Microphone muted" : copy.label}</p>
        <p className="mt-1 max-w-sm text-sm text-muted">
          {error ?? (finished && live ? "The check-in is finished. Voice ends after this message." : copy.hint)}
        </p>
        {state === "processing" ? (
          <span className="mt-2 flex gap-1" aria-hidden="true">
            <span className="kv-dot" />
            <span className="kv-dot" style={{ animationDelay: "150ms" }} />
            <span className="kv-dot" style={{ animationDelay: "300ms" }} />
          </span>
        ) : null}
      </div>

      {connection === "live" ? <Waveform className="mt-5" micTrack={micTrack} agentTrack={agentTrack} muted={!micOn} /> : null}

      {live || state === "error" ? (
        <div className="mt-4 flex flex-wrap justify-center gap-2">
          {live ? (
            <>
              <Button variant="secondary" onClick={() => void toggleMic()} aria-pressed={muted} className="py-2">
                {muted ? <Icon.Mic className="h-4 w-4" /> : <Icon.MicOff className="h-4 w-4" />}
                {muted ? "Unmute" : "Mute"}
              </Button>
              <Button variant="danger" onClick={end} className="py-2">
                <Icon.EndCall className="h-4 w-4" /> End voice
              </Button>
            </>
          ) : (
            <Button variant="ai" onClick={() => void start()} className="py-2">
              <Icon.Retry className="h-4 w-4" /> Retry voice
            </Button>
          )}
        </div>
      ) : null}
      <div ref={audioRef} hidden />
    </Card>
  );
}
