"use client";

import { useEffect, useState } from "react";
import { Check, StepIndicator } from "../components";

export function Processing({ stage, onCancel }: { stage: "uploading" | "analysing"; onCancel: () => void }) {
  // Seconds since this screen appeared: the analysis has no progress figure, but a running clock shows it has not stalled
  const [seconds, setSeconds] = useState(0);
  useEffect(() => {
    const started = Date.now();
    const timer = setInterval(() => setSeconds(Math.floor((Date.now() - started) / 1000)), 1000);
    return () => clearInterval(timer);
  }, []);

  return (
    <div className="glass-card center">
      <StepIndicator current={3} />
      <h2>Analysing your recording</h2>
      <p className="sub mb-15">
        This usually takes 10 to 20 seconds. <span className="elapsed" aria-live="off">{seconds} s so far.</span>
      </p>

      <div className="orbit" aria-hidden="true">
        <svg width="160" height="160" viewBox="0 0 160 160">
          <circle cx="80" cy="80" r="66" fill="none" stroke="rgba(30,58,138,0.06)" />
          <circle className="spinner" cx="80" cy="80" r="66" fill="none" stroke="rgba(29,78,216,0.5)" strokeWidth="2" strokeDasharray="60 360" strokeLinecap="round" />
        </svg>
        <div className="core"><div /></div>
      </div>

      <div className="analysis-list" role="status">
        <Check state={stage === "uploading" ? "working" : "done"}>Uploading the recording</Check>
        <Check state={stage === "uploading" ? "pending" : "working"}>Checking speech, face, movement and video</Check>
      </div>
      <div className="btn-row">
        <button className="btn-secondary" onClick={onCancel}>Cancel</button>
      </div>
    </div>
  );
}
