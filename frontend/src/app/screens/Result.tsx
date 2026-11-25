"use client";

import { useState } from "react";
import { SIGNAL_LABELS, UNCALIBRATED_SIGNALS } from "../challenge";
import { StepIndicator } from "../components";
import { DEBUG } from "../debug";
import { explain } from "../friendly";
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
  VERIFIED: { tone: "good", icon: "✓", title: "Verification passed" },
  SUSPICIOUS: { tone: "mid", icon: "!", title: "Inconclusive" },
  FAILED: { tone: "bad", icon: "✕", title: "Verification failed" },
  RETRY: { tone: "mid", icon: "↻", title: "We could not check this recording" },
} as const;

const MARK = { true: { cls: "ok", symbol: "✓", word: "Passed" }, false: { cls: "no", symbol: "✕", word: "Not passed" }, null: { cls: "skip", symbol: "–", word: "Not checked" } };

// Debug view only: every signal the backend reported, with its own technical text.
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
  if (row.failed || row.score === null) return "#64748b";
  return row.passed === false ? "#b45309" : "#15803d";
}

function DebugDetails({ result }: { result: SessionResult }) {
  const [open, setOpen] = useState<string | null>(null);
  const rows = buildRows(result);
  const circumference = 2 * Math.PI * 44;
  const confidence = result.confidence;
  const tone = VERDICT[result.status as keyof typeof VERDICT]?.tone ?? "bad";
  const ringColour = tone === "good" ? "#16a34a" : tone === "mid" ? "#d97706" : "#dc2626";
  return (
    <div>
      <div className={`confidence ${tone}`}>
        <div className="donut">
          <svg width="96" height="96" viewBox="0 0 96 96" aria-hidden="true">
            <circle cx="48" cy="48" r="44" fill="none" stroke="rgba(15,23,42,0.08)" strokeWidth="7" />
            <circle cx="48" cy="48" r="44" fill="none" stroke={ringColour} strokeWidth="7" strokeLinecap="round" strokeDasharray={circumference} strokeDashoffset={circumference * (1 - (confidence ?? 0))} />
          </svg>
          <span style={{ color: ringColour }}>{confidence === null ? "–" : Math.round(confidence * 100)}</span>
        </div>
        <div>
          <div className="section-label" style={{ marginBottom: 4 }}>Combined score</div>
          <p className="sub" style={{ color: "#334155" }}>{result.decision_reason}</p>
        </div>
      </div>
      <div className="section-label">Signal breakdown (debug)</div>
      {rows.map((row) => (
        <div className="signal" key={row.key}>
          <button className="signal-head" onClick={() => setOpen(open === row.key ? null : row.key)} aria-expanded={open === row.key}>
            <span className="name">{row.label} {row.uncalibrated && <span className="tag">not calibrated</span>}</span>
            <span className="value" style={{ color: colour(row) }}>
              {row.failed ? "error" : row.score === null ? (row.passed ? "passed" : "failed") : `${Math.round(row.score * 100)}%`}
              {row.passed === true ? " ✓" : row.passed === false ? " ✗" : ""}
            </span>
          </button>
          {open === row.key && (
            <div className="signal-body">
              {row.score !== null && <div className="bar"><div style={{ width: `${row.score * 100}%`, background: colour(row) }} /></div>}
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
    </div>
  );
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
  const saveRecording = () => {
    if (!blob) return;
    const words = (session?.challenge.verbal ?? "").split(/\s+/).filter(Boolean).join("_");
    const link = document.createElement("a");
    const url = URL.createObjectURL(blob);
    link.href = url;
    link.download = `clip-${session?.challenge.visual ?? "NONE"}-${words}-${Date.now()}.webm`;
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
    setTimeout(() => URL.revokeObjectURL(url), 10_000); // a revoked address can cancel a download that has not started
  };

  if (!result) {
    return (
      <div className="glass-card">
        <StepIndicator current={4} />
        <h2>We could not finish the check</h2>
        <div className="notice" role="alert">{problem ?? "Something went wrong."}</div>
        <div className="btn-row">
          <button className="btn-primary" onClick={onRetry}>Try again</button>
          {DEBUG && blob && <button className="btn-secondary" onClick={saveRecording}>Save recording</button>}
        </div>
      </div>
    );
  }

  const verdict = VERDICT[result.status as keyof typeof VERDICT] ?? VERDICT.FAILED;
  const explanation = explain(result);

  return (
    <div className="glass-card">
      <StepIndicator current={4} />

      <div className="center mb-15" role="status">
        <div className="verdict-icon"><div className={verdict.tone} aria-hidden="true">{verdict.icon}</div></div>
        <h2>{verdict.title}</h2>
        <p className="sub">{explanation.message}</p>
      </div>

      {explanation.checks.length > 0 && (
        <div className="what-happened">
          <h3>What we saw</h3>
          <ul className="checks">
            {explanation.checks.map((check) => {
              const mark = MARK[String(check.ok) as keyof typeof MARK];
              return (
                <li key={check.label}>
                  <span className={`mark ${mark.cls}`} role="img" aria-label={mark.word}>{mark.symbol}</span>
                  <span>
                    {check.label}
                    {check.note && <span className="note">{check.note}</span>}
                  </span>
                </li>
              );
            })}
          </ul>
        </div>
      )}

      {explanation.advice.length > 0 && (
        <div className="what-happened">
          <h3>Next time</h3>
          <ul className="advice">
            {explanation.advice.map((line) => <li key={line}>{line}</li>)}
          </ul>
        </div>
      )}

      {DEBUG && <DebugDetails result={result} />}

      <div className="btn-row">
        <button className="btn-primary" onClick={onRetry}>
          {result.status === "VERIFIED" ? "Run another check" : "Try again"}
        </button>
        {DEBUG && blob && <button className="btn-secondary" onClick={saveRecording}>Save recording (for evaluation)</button>}
      </div>
      <p className="fine">
        Prototype: the deepfake and replay checks are not calibrated and can disagree with a genuine recording. This result is a measurement, not a decision about you.
      </p>
    </div>
  );
}
