"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createSession } from "../api";
import {
  PHASE_GUIDANCE,
  PHASE_LABELS,
  PRE_ROLL_SECONDS,
  VISUAL_CUES,
  VISUAL_CUE_DETAIL,
  phaseAt,
  secondsLeftInPhase,
  secondsLeftInRecording,
} from "../challenge";
import { Announcer, CircularTimer, LiveVideo, PhaseBar, StepIndicator, useBeeper } from "../components";
import type { PhaseName, SessionChallenge } from "../types";
import type { Recorder } from "../useRecorder";

export function Challenge({
  recorder,
  onFinished,
  onCancel,
}: {
  recorder: Recorder;
  onFinished: (blob: Blob, session: SessionChallenge) => void;
  onCancel: () => void;
}) {
  const { stream, recording, faulted, error, elapsed, level, start, stop } = recorder;
  const [session, setSession] = useState<SessionChallenge | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [countdown, setCountdown] = useState<number | null>(null);
  const [announcement, setAnnouncement] = useState("");
  const sessionRef = useRef<SessionChallenge | null>(null);
  const begun = useRef(false);
  const finished = useRef(false);
  const lastPhase = useRef<PhaseName | null>(null);
  const beep = useBeeper();

  // A fresh challenge is fetched when the check begins, so the words are new and the token is valid
  // for the whole recording. A short "get ready" follows; it is not part of the recording.
  const begin = useCallback(async () => {
    setProblem(null);
    setSession(null);
    setCountdown(null);
    finished.current = false;
    lastPhase.current = null;
    try {
      const created = await createSession();
      sessionRef.current = created;
      setSession(created);
      setCountdown(PRE_ROLL_SECONDS);
      setAnnouncement(`Get ready. The check starts in ${PRE_ROLL_SECONDS} seconds.`);
    } catch (err: any) {
      setProblem(err.message);
    }
  }, []);

  useEffect(() => {
    if (begun.current) return;
    begun.current = true;
    begin();
  }, [begin]);

  // 3-2-1, then the recording (and the Read phase) starts
  useEffect(() => {
    if (countdown === null) return;
    if (countdown === 0) {
      setCountdown(null);
      if (!start()) setProblem("Could not start the recording. Please use a recent Chrome, Edge or Firefox.");
      return;
    }
    const timer = setTimeout(() => setCountdown(countdown - 1), 1000);
    return () => clearTimeout(timer);
  }, [countdown, start]);

  // A recording that breaks off (camera unplugged, recorder error) ends the check with a clear message
  useEffect(() => {
    if (!faulted || finished.current) return;
    finished.current = true;
    setProblem(error ?? "The recording stopped unexpectedly. Please try again.");
  }, [faulted, error]);

  // Stop by itself at the end of the last phase
  const total = session?.protocol.total_seconds ?? Infinity;
  useEffect(() => {
    if (!recording || elapsed < total || finished.current) return;
    finished.current = true;
    stop().then((blob) => {
      if (blob && blob.size > 0 && sessionRef.current) onFinished(blob, sessionRef.current);
      else setProblem("The recording was empty. Please try again.");
    });
  }, [recording, elapsed, total, stop, onFinished]);

  // A phase change is announced to screen readers and marked with a short quiet tone
  const phase = session ? phaseAt(session.protocol, elapsed) : null;
  useEffect(() => {
    if (!recording || !phase || phase === lastPhase.current) return;
    lastPhase.current = phase;
    setAnnouncement(PHASE_GUIDANCE[phase].announce);
    beep(phase === "act" ? 988 : 784);
  }, [recording, phase, beep]);

  const cancel = async () => {
    finished.current = true;
    setCountdown(null);
    await stop();
    onCancel();
  };

  if (problem) {
    return (
      <div className="glass-card">
        <StepIndicator current={2} />
        <h2>The check was interrupted</h2>
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

  if (!recording) {
    return (
      <div className="glass-card center">
        <Announcer message={announcement} />
        <StepIndicator current={2} />
        <h2>Get ready</h2>
        <p className="sub">Face the camera and keep still. The words appear when the countdown ends.</p>
        <div className="preroll" aria-hidden="true">{countdown ?? ""}</div>
        <div className="btn-row">
          <button className="btn-secondary" onClick={cancel}>Cancel</button>
        </div>
      </div>
    );
  }

  const { protocol, challenge } = session;
  const current = phase ?? "read";
  const cue = VISUAL_CUES[challenge.visual];
  const words = challenge.verbal.split(/\s+/).filter(Boolean);

  return (
    <div className="glass-card wide">
      <Announcer message={announcement} />
      <div className="challenge-top">
        <div>
          <StepIndicator current={2} />
          <h2>
            {PHASE_LABELS[current]} <span className="phase-seconds">{secondsLeftInPhase(protocol, elapsed)} s</span>
          </h2>
        </div>
        <div className="top-right">
          <div className="pip">
            <LiveVideo stream={stream} />
            <div className="live"><i />LIVE</div>
          </div>
          <CircularTimer secondsLeft={secondsLeftInRecording(protocol, elapsed)} total={protocol.total_seconds} />
        </div>
      </div>

      <PhaseBar protocol={protocol} elapsed={elapsed} />

      {current === "act" ? (
        <div className="instruction visual act">
          <div className="label">Movement</div>
          <div className="cue">
            <span className="cue-arrow" aria-hidden="true">{cue.arrow}</span>
            <div>
              <p className="big">{cue.title}</p>
              <p className="sub">{VISUAL_CUE_DETAIL}</p>
            </div>
          </div>
        </div>
      ) : (
        <div className="instruction audio">
          <div className="label">Words</div>
          <p className="hint">{PHASE_GUIDANCE[current].heading}</p>
          <div className="words">
            {words.map((word, i) => (
              <div key={`${word}-${i}`} className="word">{word}</div>
            ))}
          </div>
          <div className="meter" aria-label="Microphone level"><div style={{ width: `${level}%` }} /></div>
          <p className="sub upcoming">After you have said the words, a short head movement is shown here.</p>
        </div>
      )}

      <div className="status-row">
        <div className="status-pill"><i />Recording…</div>
        <button className="btn-secondary" onClick={cancel}>Cancel</button>
      </div>
    </div>
  );
}
