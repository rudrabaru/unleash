"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createSession } from "../api";
import { TOTAL_SECONDS, VISUAL_INSTRUCTIONS, stepAt } from "../challenge";
import { CircularTimer, LiveVideo, StepIndicator } from "../components";
import type { SessionChallenge } from "../types";
import type { Recorder } from "../useRecorder";

const STEP_NUMBER = { read: 1, speak: 2, act: 3 } as const;

export function Challenge({
  recorder,
  onFinished,
  onCancel,
}: {
  recorder: Recorder;
  onFinished: (blob: Blob, session: SessionChallenge) => void;
  onCancel: () => void;
}) {
  const { stream, recording, elapsed, level, start, stop } = recorder;
  const [session, setSession] = useState<SessionChallenge | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const sessionRef = useRef<SessionChallenge | null>(null);
  const begun = useRef(false);
  const finished = useRef(false);

  // A fresh challenge is fetched when the recording starts, so the words are new and the token is valid
  const begin = useCallback(async () => {
    setProblem(null);
    finished.current = false;
    try {
      const created = await createSession();
      sessionRef.current = created;
      setSession(created);
      if (!start()) setProblem("Could not start the recording. Use Chrome, Edge or Firefox.");
    } catch (err: any) {
      setProblem(err.message);
    }
  }, [start]);

  useEffect(() => {
    if (begun.current) return;
    begun.current = true;
    begin();
  }, [begin]);

  // Stop by itself at the end of the last step
  useEffect(() => {
    if (!recording || elapsed < TOTAL_SECONDS || finished.current) return;
    finished.current = true;
    stop().then((blob) => {
      if (blob && blob.size > 0 && sessionRef.current) onFinished(blob, sessionRef.current);
      else setProblem("The recording was empty. Please try again.");
    });
  }, [recording, elapsed, stop, onFinished]);

  const cancel = async () => {
    finished.current = true;
    await stop();
    onCancel();
  };

  if (problem) {
    return (
      <div className="glass-card">
        <StepIndicator current={2} />
        <h2>Could not run the challenge</h2>
        <div className="notice" role="alert">{problem}</div>
        <div className="btn-row">
          <button className="btn-primary" onClick={begin}>Try again</button>
          <button className="btn-secondary" onClick={onCancel}>Back</button>
        </div>
      </div>
    );
  }

  if (!session) {
    return (
      <div className="glass-card center">
        <StepIndicator current={2} />
        <h2>Preparing your challenge…</h2>
        <p className="sub">Getting five random words from the server.</p>
      </div>
    );
  }

  const step = stepAt(elapsed);
  const words = session.challenge.verbal.split(/\s+/).filter(Boolean);
  const secondsLeft = Math.max(0, Math.ceil(TOTAL_SECONDS - elapsed));

  return (
    <div className="glass-card wide">
      <div className="challenge-top">
        <div>
          <StepIndicator current={2} />
          <h2>Step {STEP_NUMBER[step]} of 3</h2>
        </div>
        <div className="top-right">
          <div className="pip">
            <LiveVideo stream={stream} />
            <div className="live"><i />LIVE</div>
          </div>
          <CircularTimer secondsLeft={secondsLeft} total={TOTAL_SECONDS} />
        </div>
      </div>

      <div className={`instruction visual ${step === "act" ? "act" : ""}`}>
        <div className="label">Head movement</div>
        <p className="big">
          {step === "act" ? VISUAL_INSTRUCTIONS[session.challenge.visual] : "Face the camera and keep still"}
        </p>
        {step !== "act" && <p className="sub">The movement appears here after you have said the words.</p>}
      </div>

      <div className="instruction audio">
        <div className="label">Words</div>
        <p className="hint">
          {step === "read" ? "Read these five words" : step === "speak" ? "Say them now, in order" : "Done. Now the movement above"}
        </p>
        <div className="words">
          {words.map((word, i) => (
            <div key={`${word}-${i}`} className={`word ${step === "act" ? "hidden" : ""}`}>
              {word}
            </div>
          ))}
        </div>
        <div className="meter" aria-label="Microphone level"><div style={{ width: `${level}%` }} /></div>
      </div>

      <div className="status-row">
        <div className="status-pill"><i />Recording…</div>
        <button className="btn-secondary" onClick={cancel}>Cancel</button>
      </div>
    </div>
  );
}
