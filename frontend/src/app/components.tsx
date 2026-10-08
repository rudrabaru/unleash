"use client";

import { useEffect, useRef, type ReactNode } from "react";

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
