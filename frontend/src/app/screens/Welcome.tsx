"use client";

import { StepIndicator } from "../components";

export function Welcome({ onNext }: { onNext: () => void }) {
  return (
    <div className="glass-card center">
      <StepIndicator current={0} />
      <div className="shield">
        <div className="shield-box">
          <svg width="40" height="44" viewBox="0 0 40 44" fill="none" aria-hidden="true">
            <path d="M20 2L4 9v12c0 10.5 6.8 20.3 16 23 9.2-2.7 16-12.5 16-23V9L20 2z" fill="#1d4ed8" stroke="rgba(29,78,216,0.3)" />
            <path d="M14 22l4 4 8-8" stroke="white" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </div>
      </div>

      <div className="mb-15">
        <div className="eyebrow">Liveness check</div>
        <h1>Show that a live person is here</h1>
        <p className="sub">
          You will read five words, say them, and then make one head movement. It takes a <strong>13-second recording</strong> from your camera and
          microphone.
        </p>
      </div>

      <div className="facts">
        <div className="fact">🎥<br />One short recording</div>
        <div className="fact">🗑️<br />Recording deleted after analysis</div>
        <div className="fact">🚫<br />Not an identity check</div>
      </div>

      <button className="btn-primary" onClick={onNext}>
        Start verification →
      </button>
      <p className="fine">
        This needs camera and microphone access. Only the scores are kept. Prototype: some checks are not calibrated yet, so results are for evaluation.
      </p>
    </div>
  );
}
