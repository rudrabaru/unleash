"use client";

import { useCallback, useEffect, useRef, type ReactNode } from "react";
import { PHASE_LABELS, phaseAt } from "./challenge";
import type { Protocol } from "./types";

export function StepIndicator({ current, total = 5 }: { current: number; total?: number }) {
  return (
    <div className="steps" aria-label={`Step ${current + 1} of ${total}`}>
      {Array.from({ length: total }).map((_, i) => (
        <div key={i} className={`step-dot ${i < current ? "done" : i === current ? "current" : ""}`} />
      ))}
    </div>
  );
}

export function LiveVideo({ stream }: { stream: MediaStream | null }) {
  const ref = useRef<HTMLVideoElement>(null);
  useEffect(() => {
    if (ref.current) ref.current.srcObject = stream;
  }, [stream]);
  return <video ref={ref} autoPlay muted playsInline />;
}

export function CircularTimer({ secondsLeft, total }: { secondsLeft: number; total: number }) {
  const radius = 24;
  const circumference = 2 * Math.PI * radius;
  const progress = ((total - secondsLeft) / total) * circumference;
  const low = secondsLeft <= 3;
  return (
    <div className="timer" role="timer" aria-label={`${secondsLeft} seconds left`}>
      <svg width="56" height="56" viewBox="0 0 56 56">
        <circle cx="28" cy="28" r={radius} fill="none" stroke="rgba(30,58,138,0.12)" strokeWidth="4" />
        <circle
          cx="28"
          cy="28"
          r={radius}
          fill="none"
          stroke={low ? "#f59e0b" : "#2563eb"}
          strokeWidth="4"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference - progress}
          style={{ transition: "stroke-dashoffset 0.2s linear, stroke 0.3s" }}
        />
      </svg>
      <span style={{ color: low ? "#d97706" : "#1e3a8a" }}>{String(Math.max(0, secondsLeft)).padStart(2, "0")}s</span>
    </div>
  );
}

export function Check({ state, children, detail }: { state: "done" | "working" | "pending" | "warn"; children: ReactNode; detail?: string }) {
  return (
    <div className={`check ${state === "pending" ? "pending" : ""}`}>
      {state === "done" ? <div className="tick" /> : state === "warn" ? <div className="cross" /> : state === "working" ? <div className="spin-ring" /> : <div className="wait" />}
      <span>{children}</span>
      {detail && <span className="detail">{detail}</span>}
    </div>
  );
}

// The steps of the recording (Read, Speak, Act), drawn from the server's windows.
export function PhaseBar({ protocol, elapsed }: { protocol: Protocol; elapsed: number }) {
  const current = phaseAt(protocol, elapsed);
  const index = protocol.phases.findIndex((phase) => phase.name === current);
  return (
    <ol className="phases" aria-label="Steps of the recording">
      {protocol.phases.map((phase, i) => {
        const fill = i < index ? 100 : i === index ? Math.min(100, ((elapsed - phase.start) / (phase.end - phase.start)) * 100) : 0;
        return (
          <li key={phase.name} className={`phase ${i < index ? "done" : i === index ? "current" : ""}`} aria-current={i === index ? "step" : undefined}>
            <span className="phase-name">{PHASE_LABELS[phase.name]}</span>
            <span className="phase-track" aria-hidden="true">
              <i style={{ width: `${fill}%` }} />
            </span>
          </li>
        );
      })}
    </ol>
  );
}

// Text for screen readers that is announced when it changes and is not shown on screen.
export function Announcer({ message }: { message: string }) {
  return (
    <div className="sr-only" role="status" aria-live="polite" aria-atomic="true">
      {message}
    </div>
  );
}

// A very short, quiet tone: the audible half of a phase change for people who are not looking at the
// screen. Played at low volume (the browser's echo cancellation removes most of it from the recording).
export function useBeeper() {
  const contextRef = useRef<AudioContext | null>(null);
  useEffect(() => () => void contextRef.current?.close().catch(() => {}), []);
  return useCallback((frequency = 880, milliseconds = 90) => {
    try {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      contextRef.current ??= new AudioCtx();
      const context = contextRef.current;
      const oscillator = context.createOscillator();
      const gain = context.createGain();
      gain.gain.value = 0.04;
      oscillator.frequency.value = frequency;
      oscillator.connect(gain).connect(context.destination);
      oscillator.start();
      oscillator.stop(context.currentTime + milliseconds / 1000);
    } catch {
      // no sound is not a reason to stop the check
    }
  }, []);
}
