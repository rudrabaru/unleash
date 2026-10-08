"use client";

import { useState } from "react";
import { SIGNAL_LABELS, UNCALIBRATED_SIGNALS } from "../challenge";
import { StepIndicator } from "../components";
import type { SessionChallenge, SessionResult } from "../types";

interface Row {
  key: string;
  label: string;
  score: number | null;
  passed: boolean | null;
  note: string;
  uncalibrated: boolean;
  failed: boolean; // the detector could not measure
}

const VERDICT = {
  VERIFIED: { tone: "good", icon: "✓", title: "Verification passed", sub: "The checks passed on this recording." },
  SUSPICIOUS: { tone: "mid", icon: "!", title: "Inconclusive", sub: "Some checks were not convincing. Try again in good light." },
  FAILED: { tone: "bad", icon: "✕", title: "Verification failed", sub: "" },
} as const;

function buildRows(result: SessionResult): Row[] {
  const signals = result.signals ?? {};
  const rows: Row[] = Object.entries(signals).map(([key, signal]) => ({
    key,
    label: SIGNAL_LABELS[key] ?? key,
    score: signal.score,
    passed: signal.error ? null : signal.passed,
    note: signal.error ?? signal.reason,
    uncalibrated: UNCALIBRATED_SIGNALS.has(key),
    failed: signal.error !== null,
  }));
  // The two advisory audio checks are reported inside the audio result
  const details = signals.audio_pipeline?.details ?? {};
  for (const [key, label] of [
    ["voice_authenticity_score", "Voice authenticity"],
    ["av_alignment_score", "Lip sync"],
  ] as const) {
    const value = details[key];
    if (typeof value === "number") {
      rows.push({ key, label, score: value, passed: null, note: "Advisory check, uncalibrated.", uncalibrated: true, failed: false });
    }
  }
  return rows;
}

function colour(row: Row): string {
  if (row.failed || row.score === null) return "#94a3b8";
  return row.passed === false ? "#d97706" : "#16a34a";
}

export function Result({
  result,
  problem,
  blob,
  session,
  onRetry,
}: {
  result: SessionResult | null;
  problem: string | null;
  blob: Blob | null;
  session: SessionChallenge | null;
  onRetry: () => void;
}) {
  const [open, setOpen] = useState<string | null>(null);

  const saveRecording = () => {
    if (!blob) return;
    const words = (session?.challenge.verbal ?? "").split(/\s+/).filter(Boolean).join("_");
    const link = document.createElement("a");
    link.href = URL.createObjectURL(blob);
    link.download = `clip-${session?.challenge.visual ?? "NONE"}-${words}-${Date.now()}.webm`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    URL.revokeObjectURL(link.href);
  };

  if (!result) {
    return (
      <div className="glass-card">
        <StepIndicator current={4} />
        <h2>We could not finish the check</h2>
        <div className="notice" role="alert">{problem ?? "Something went wrong."}</div>
        <div className="btn-row">
          <button className="btn-primary" onClick={onRetry}>Try again</button>
          {blob && <button className="btn-secondary" onClick={saveRecording}>Save recording</button>}
        </div>
      </div>
    );
  }

  const verdict = VERDICT[result.status as keyof typeof VERDICT] ?? VERDICT.FAILED;
  const rows = buildRows(result);
  const circumference = 2 * Math.PI * 44;
  const confidence = result.confidence;
  const tone = verdict.tone;
  const ringColour = tone === "good" ? "#16a34a" : tone === "mid" ? "#d97706" : "#dc2626";

  return (
    <div className="glass-card">
      <StepIndicator current={4} />

      <div className="center mb-15">
        <div className="verdict-icon"><div className={tone}>{verdict.icon}</div></div>
        <h2>{verdict.title}</h2>
        <p className="sub">{verdict.sub || result.decision_reason}</p>
      </div>

      <div className={`confidence ${tone}`}>
        <div className="donut">
          <svg width="96" height="96" viewBox="0 0 96 96" aria-hidden="true">
            <circle cx="48" cy="48" r="44" fill="none" stroke="rgba(15,23,42,0.08)" strokeWidth="7" />
            <circle
              cx="48"
              cy="48"
              r="44"
              fill="none"
              stroke={ringColour}
              strokeWidth="7"
              strokeLinecap="round"
              strokeDasharray={circumference}
              strokeDashoffset={circumference * (1 - (confidence ?? 0))}
            />
          </svg>
          <span style={{ color: ringColour }}>{confidence === null ? "–" : Math.round(confidence * 100)}</span>
        </div>
        <div>
          <div className="section-label" style={{ marginBottom: 4 }}>Combined score</div>
          <p className="sub" style={{ color: "#334155" }}>
            {confidence === null
              ? "No score: a required check did not pass, so the other signals are not combined."
              : result.decision_reason}
          </p>
        </div>
      </div>

      <div className="section-label">Signal breakdown</div>
      {rows.map((row) => (
        <div className="signal" key={row.key}>
          <button className="signal-head" onClick={() => setOpen(open === row.key ? null : row.key)} aria-expanded={open === row.key}>
            <span className="name">
              {row.label} {row.uncalibrated && <span className="tag">not calibrated</span>}
            </span>
            <span className="value" style={{ color: colour(row) }}>
              {row.failed ? "error" : row.score === null ? (row.passed ? "passed" : "failed") : `${Math.round(row.score * 100)}%`}
              {row.passed === true ? " ✓" : row.passed === false ? " ✗" : ""}
            </span>
          </button>
          {open === row.key && (
            <div className="signal-body">
              {row.score !== null && (
                <div className="bar"><div style={{ width: `${row.score * 100}%`, background: colour(row) }} /></div>
              )}
              {row.note}
            </div>
          )}
        </div>
      ))}

      <div className="meta">
        <div><div className="k">Session</div><div className="v">{result.session_id.slice(0, 8)}</div></div>
        <div><div className="k">Verdict</div><div className="v">{result.status}</div></div>
        <div><div className="k">Signals scored</div><div className="v">{rows.filter((r) => r.score !== null).length}</div></div>
      </div>

      <div className="btn-row">
        <button className="btn-primary" onClick={onRetry}>Run another check</button>
        {blob && <button className="btn-secondary" onClick={saveRecording}>Save recording (for evaluation)</button>}
      </div>
      <p className="fine">
        Prototype: the deepfake and replay checks are not calibrated and often disagree with a genuine recording. This result is a measurement, not a decision about you.
      </p>
    </div>
  );
}
