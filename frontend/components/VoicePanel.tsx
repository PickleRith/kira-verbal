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

type Status = "off" | "connecting" | "live" | "ended";

const AGENT_STATE_LABEL: Record<string, string> = {
  initializing: "Starting…",
  idle: "Ready",
  listening: "Listening",
  thinking: "Thinking…",
  speaking: "Speaking",
};
const POLL_MS = 2000; // refresh the on-screen transcript while voice is active

export function VoicePanel({
  sessionId,
  token,
  onActivity,
}: {
  sessionId: string;
  token: string;
  onActivity: () => void;
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

  return (
    <section className="mt-6 rounded-md border border-gray-200 p-4" aria-label="Voice answers">
      <div className="flex flex-wrap items-center gap-2">
        {status === "live" ? (
          <>
            <span className="text-sm font-medium" role="status">
              Voice on · {AGENT_STATE_LABEL[agentState ?? "initializing"] ?? agentState}
            </span>
            <button
              type="button"
              onClick={() => void toggleMic()}
              aria-pressed={!micOn}
              className="ml-auto rounded-md border border-gray-300 px-3 py-1.5 text-sm"
            >
              {micOn ? "Mute mic" : "Unmute mic"}
            </button>
            <button
              type="button"
              onClick={stop}
              className="rounded-md border border-gray-300 px-3 py-1.5 text-sm"
            >
              Stop voice
            </button>
          </>
        ) : (
          <>
            <button
              type="button"
              onClick={() => void start()}
              disabled={status === "connecting"}
              className="rounded-md bg-gray-900 px-4 py-2 text-sm font-medium text-white disabled:opacity-50"
            >
              {status === "connecting" ? "Connecting…" : status === "ended" ? "Resume voice" : "Answer by voice"}
            </button>
            <span className="text-sm text-gray-600">or type below.</span>
          </>
        )}
      </div>
      <p className="mt-2 text-xs text-gray-500">
        Your speech is transcribed and sent as your answer. This app does not save audio.
        You can interrupt the questions at any time.
      </p>
      {message ? (
        <p role="status" className="mt-2 text-sm text-amber-900">
          {message}
        </p>
      ) : null}
      <div ref={audioRef} hidden />
    </section>
  );
}
