"use client";

// Optional voice mode. The text form on the page always stays usable: if voice isn't
// configured, the microphone is blocked, or the connection drops, the learner keeps typing.
// The browser never decides anything about the assessment; it streams audio to a LiveKit
// room where the worker forwards finalized answers to the same API the text form uses.
//
// livekit-client usage follows the LiveKit docs (Room.connect, setMicrophoneEnabled,
// RoomEvent.TrackSubscribed + track.attach(), agent state in the `lk.agent.state` attribute).

import { Room, RoomEvent, Track, type RemoteTrack } from "livekit-client";
import { useCallback, useEffect, useRef, useState } from "react";

import { ApiError, api } from "@/lib/api";

import { Button, Callout, Card, Icon, Spinner, cx } from "./ui";

type Status = "off" | "connecting" | "live" | "ended";

const AGENT_STATE_LABEL: Record<string, string> = {
  initializing: "Starting…",
  idle: "Ready",
  listening: "Listening",
  thinking: "Thinking…",
  speaking: "Speaking",
};
const POLL_MS = 2000; // refresh the on-screen transcript while voice is active
// After the session ends the worker speaks the closing line and then leaves the room.
// If that never happens (network, worker crash), hang up ourselves after this long.
const CLOSING_GRACE_MS = 30_000;

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
  const [status, setStatus] = useState<Status>("off");
  const [agentState, setAgentState] = useState<string | null>(null);
  const [micOn, setMicOn] = useState(true);
  const [message, setMessage] = useState<string | null>(null);
  const roomRef = useRef<Room | null>(null);
  const audioRef = useRef<HTMLDivElement>(null);

  const teardown = useCallback(() => {
    const room = roomRef.current;
    roomRef.current = null;
    if (room) void room.disconnect();
    if (audioRef.current) audioRef.current.innerHTML = "";
    setAgentState(null);
  }, []);

  useEffect(() => teardown, [teardown]); // disconnect when leaving the page

  useEffect(() => {
    if (!finished || status !== "live") return;
    const id = window.setTimeout(() => {
      teardown();
      setStatus("ended");
    }, CLOSING_GRACE_MS);
    return () => window.clearTimeout(id);
  }, [finished, status, teardown]);

  useEffect(() => {
    if (status !== "live") return;
    const id = window.setInterval(onActivity, POLL_MS);
    return () => window.clearInterval(id);
  }, [status, onActivity]);

  async function start() {
    setMessage(null);
    setStatus("connecting");
    let details;
    try {
      details = await api.createVoiceToken(sessionId, token);
    } catch (e) {
      setStatus("off");
      setMessage(
        e instanceof ApiError && e.code === "voice_unavailable"
          ? "Voice isn't available on this server. You can keep answering by typing."
          : "Couldn't start voice. You can keep answering by typing.",
      );
      return;
    }

    const room = new Room();
    roomRef.current = room;
    room.on(RoomEvent.TrackSubscribed, (track: RemoteTrack) => {
      if (track.kind === Track.Kind.Audio && audioRef.current) {
        audioRef.current.appendChild(track.attach());
      }
    });
    room.on(RoomEvent.ParticipantAttributesChanged, (_changed, participant) => {
      const state = participant.attributes["lk.agent.state"];
      if (state) setAgentState(state);
    });
    // The agent leaves after speaking the closing line (or if the worker stops). With no
    // one left to talk to, end voice here instead of leaving the learner in an empty room.
    room.on(RoomEvent.ParticipantDisconnected, () => {
      if (roomRef.current === room && room.remoteParticipants.size === 0) {
        teardown();
        setStatus("ended");
        onActivity();
      }
    });
    room.on(RoomEvent.Disconnected, () => {
      if (roomRef.current === room) {
        teardown();
        setStatus("ended");
        onActivity();
      }
    });

    try {
      await room.connect(details.server_url, details.participant_token);
    } catch {
      teardown();
      setStatus("off");
      setMessage("Couldn't connect to voice. You can keep answering by typing.");
      return;
    }
    try {
      await room.localParticipant.setMicrophoneEnabled(true);
      setMicOn(true);
    } catch {
      teardown();
      setStatus("off");
      setMessage("Microphone access was blocked. You can keep answering by typing.");
      return;
    }
    setStatus("live");
  }

  async function toggleMic() {
    const room = roomRef.current;
    if (!room) return;
    const next = !micOn;
    await room.localParticipant.setMicrophoneEnabled(next);
    setMicOn(next);
  }

  function stop() {
    teardown();
    setStatus("ended");
    onActivity();
  }

  const live = status === "live";
  if (finished && !live) return null; // over, and nothing left to hear
  const speaking = agentState === "speaking";
  const listening = agentState === "listening";

  return (
    <Card className="mt-3 p-4" aria-label="Voice answers">
      <div className="flex flex-wrap items-center gap-3">
        {live ? (
          <>
            <span className="relative flex h-12 w-12 items-center justify-center">
              {listening && micOn ? (
                <span className="kv-pulse absolute inset-0 rounded-full bg-brand-400" />
              ) : null}
              <span
                className={cx(
                  "relative flex h-12 w-12 items-center justify-center rounded-full text-white",
                  micOn ? "bg-gradient-to-br from-brand-500 to-brand-700" : "bg-faint",
                )}
              >
                {micOn ? <Icon.Mic /> : <Icon.MicOff />}
              </span>
            </span>
            <div className="min-w-0" role="status">
              <p className="text-sm font-semibold text-ink">
                {micOn ? AGENT_STATE_LABEL[agentState ?? "initializing"] ?? agentState : "Microphone muted"}
              </p>
              <p className="text-xs text-muted">
                {finished
                  ? "The assessment is finished. Voice will end after this message."
                  : speaking
                    ? "You can interrupt at any time."
                    : "Voice is on. Speak your answer."}
              </p>
            </div>
            {speaking ? (
              <span className="flex h-6 items-end gap-0.5" aria-hidden="true">
                {[8, 16, 11, 20, 13, 9].map((h, i) => (
                  <span
                    key={i}
                    className="w-1 animate-pulse rounded-full bg-brand-500"
                    style={{ height: h, animationDelay: `${i * 120}ms` }}
                  />
                ))}
              </span>
            ) : null}
            <div className="ml-auto flex gap-2">
              <Button variant="secondary" onClick={() => void toggleMic()} aria-pressed={!micOn} className="px-3 py-2">
                {micOn ? <Icon.MicOff className="h-4 w-4" /> : <Icon.Mic className="h-4 w-4" />}
                {micOn ? "Mute" : "Unmute"}
              </Button>
              <Button variant="secondary" onClick={stop} className="px-3 py-2">
                <Icon.X className="h-4 w-4" /> Stop voice
              </Button>
            </div>
          </>
        ) : (
          <>
            <button
              type="button"
              onClick={() => void start()}
              disabled={status === "connecting"}
              aria-label={status === "ended" ? "Resume voice" : "Answer by voice"}
              className="flex h-12 w-12 items-center justify-center rounded-full bg-gradient-to-br from-brand-500 to-brand-700 text-white shadow-lift transition hover:scale-105 disabled:opacity-60"
            >
              {status === "connecting" ? <Spinner className="h-5 w-5" /> : <Icon.Mic />}
            </button>
            <div className="min-w-0">
              <p className="text-sm font-semibold text-ink">
                {status === "connecting" ? "Connecting…" : status === "ended" ? "Resume voice" : "Answer by voice"}
              </p>
              <p className="text-xs text-muted">Or type below. Audio is never saved.</p>
            </div>
          </>
        )}
      </div>
      {message ? (
        <div className="mt-3">
          <Callout tone="amber" role="status" icon={<Icon.Alert className="h-4 w-4" />}>
            {message}
          </Callout>
        </div>
      ) : null}
      <div ref={audioRef} hidden />
    </Card>
  );
}
