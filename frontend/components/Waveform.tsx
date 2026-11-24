"use client";

// Live waveform of the learner's microphone (purple line over lavender bars) and, while it
// talks, the agent (grey line). Audio is analysed in the browser with the Web Audio API and
// drawn to a canvas. Nothing is recorded or sent anywhere by this component; the analyser
// is never connected to the speakers, so it can't cause echo.
//
// The session state label lives in VoicePanel (derived from real LiveKit events); this
// component only shows the signal and an input meter.

import { useEffect, useRef, useState } from "react";

import { cx } from "./ui";

const PURPLE = "129, 86, 255"; // --color-purple
const LAVENDER = "177, 150, 255"; // --color-lavender
const INK = "26, 26, 26";
const BARS = 56;
const POINTS = 160;

type Probe = { analyser: AnalyserNode; time: Float32Array<ArrayBuffer>; freq: Uint8Array<ArrayBuffer> };

function probe(ctx: AudioContext, track: MediaStreamTrack): Probe {
  const source = ctx.createMediaStreamSource(new MediaStream([track]));
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 2048;
  analyser.smoothingTimeConstant = 0.82;
  source.connect(analyser);
  return {
    analyser,
    time: new Float32Array(analyser.fftSize),
    freq: new Uint8Array(analyser.frequencyBinCount),
  };
}

function rms(samples: Float32Array) {
  let sum = 0;
  for (let i = 0; i < samples.length; i++) sum += samples[i] * samples[i];
  return Math.sqrt(sum / samples.length);
}

export function Waveform({
  micTrack,
  agentTrack,
  muted,
  className,
}: {
  micTrack: MediaStreamTrack | null;
  agentTrack: MediaStreamTrack | null;
  muted: boolean;
  className?: string;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [level, setLevel] = useState(0);
  const mutedRef = useRef(muted);
  useEffect(() => {
    mutedRef.current = muted;
  }, [muted]);

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || (!micTrack && !agentTrack)) return;
    const AudioCtor =
      window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
    if (!AudioCtor) return;
    const audio = new AudioCtor();
    void audio.resume().catch(() => undefined);
    let mic: Probe | null = null;
    let agent: Probe | null = null;
    try {
      if (micTrack) mic = probe(audio, micTrack);
      if (agentTrack) agent = probe(audio, agentTrack);
    } catch {
      // Some browsers refuse to analyse remote WebRTC audio; the mic still works.
    }

    const g = canvas.getContext("2d");
    if (!g) return;
    const fit = () => {
      const ratio = window.devicePixelRatio || 1;
      canvas.width = Math.max(1, Math.round(canvas.clientWidth * ratio));
      canvas.height = Math.max(1, Math.round(canvas.clientHeight * ratio));
    };
    fit();
    const observer = new ResizeObserver(fit);
    observer.observe(canvas);

    let frame = 0;
    let lastLevelUpdate = 0;
    let smoothLevel = 0;
    let lineGain = 3; // automatic gain: quiet voices still draw a visible wave

    const drawLine = (samples: Float32Array | null, color: string, width: number, gain: number, t: number) => {
      const { width: w, height: h } = canvas;
      g.beginPath();
      for (let i = 0; i <= POINTS; i++) {
        const x = (i / POINTS) * w;
        const taper = Math.sin((Math.PI * i) / POINTS); // meet the centre line at both ends
        const sample = samples ? samples[Math.floor((i / POINTS) * (samples.length - 1))] : 0;
        const idle = Math.sin(i * 0.12 + t * 0.002) * 0.01; // a slow breath when silent
        const y = h / 2 + (sample * gain + idle) * h * 0.42 * taper;
        if (i === 0) g.moveTo(x, y);
        else g.lineTo(x, y);
      }
      g.strokeStyle = color;
      g.lineWidth = width * (window.devicePixelRatio || 1);
      g.lineJoin = "round";
      g.stroke();
    };

    const render = (now: number) => {
      const { width: w, height: h } = canvas;
      const ratio = window.devicePixelRatio || 1;
      g.clearRect(0, 0, w, h);
      const isMuted = mutedRef.current;

      let micLevel = 0;
      if (mic && !isMuted) {
        mic.analyser.getFloatTimeDomainData(mic.time);
        mic.analyser.getByteFrequencyData(mic.freq);
        micLevel = rms(mic.time);
        let peak = 0;
        for (let i = 0; i < mic.time.length; i++) peak = Math.max(peak, Math.abs(mic.time[i]));
        const target = peak > 0.004 ? Math.min(16, 0.9 / peak) : 3;
        lineGain += (target - lineGain) * 0.08;
      }
      if (agent) agent.analyser.getFloatTimeDomainData(agent.time);

      // Spectrum bars behind the line, mirrored around the centre.
      const gap = 3 * ratio;
      const barW = (w - gap * (BARS - 1)) / BARS;
      for (let i = 0; i < BARS; i++) {
        let v = 0;
        if (mic && !isMuted) {
          const mirrored = i < BARS / 2 ? BARS / 2 - 1 - i : i - BARS / 2;
          const bin = Math.floor(Math.pow(mirrored / (BARS / 2), 1.6) * mic.freq.length * 0.45) + 2;
          v = mic.freq[bin] / 255;
        }
        const barH = Math.max(2 * ratio, Math.pow(v, 1.5) * h * 0.78);
        g.fillStyle = `rgba(${LAVENDER}, ${0.25 + v * 0.6})`;
        g.beginPath();
        g.roundRect(i * (barW + gap), (h - barH) / 2, barW, barH, Math.min(barW / 2, 2 * ratio));
        g.fill();
      }

      if (agent) drawLine(agent.time, `rgba(${INK}, 0.35)`, 1.25, 2.2, now);
      drawLine(mic && !isMuted ? mic.time : null, `rgba(${PURPLE}, ${isMuted ? 0.35 : 1})`, 2, lineGain, now);

      smoothLevel = smoothLevel * 0.85 + Math.min(1, micLevel * 9) * 0.15;
      if (now - lastLevelUpdate > 120) {
        lastLevelUpdate = now;
        setLevel(smoothLevel);
      }
      frame = requestAnimationFrame(render);
    };
    frame = requestAnimationFrame(render);

    return () => {
      cancelAnimationFrame(frame);
      observer.disconnect();
      void audio.close().catch(() => undefined);
    };
  }, [micTrack, agentTrack]);

  return (
    <div className={cx("overflow-hidden rounded-lg border border-line bg-raised", className)}>
      <canvas ref={canvasRef} className="block h-28 w-full md:h-32" aria-label="Live waveform of your microphone" role="img" />
      <div className="flex items-center gap-3 border-t border-line bg-surface px-3 py-2">
        <span className="text-xs text-muted">Mic input</span>
        <span className="h-1 flex-1 overflow-hidden rounded-sm bg-sunken">
          <span
            className="block h-full bg-purple transition-[width] duration-150"
            style={{ width: `${Math.round((muted ? 0 : level) * 100)}%` }}
          />
        </span>
        <span className="text-xs text-muted">{muted ? "Muted" : "Not recorded"}</span>
      </div>
    </div>
  );
}
