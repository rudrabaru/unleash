"use client";

import { useEffect } from "react";
import { Check, LiveVideo, StepIndicator } from "../components";
import type { Recorder } from "../useRecorder";

const TOO_DARK = 60;
const TOO_BRIGHT = 235;

export function PreScan({ recorder, onNext }: { recorder: Recorder; onNext: () => void }) {
  const { access, error, stream, cameras, cameraId, level, brightness, open } = recorder;

  useEffect(() => {
    if (access === "idle") open();
    // open once when the screen appears
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const ready = access === "ready";
  const lighting =
    brightness === null ? "working" : brightness < TOO_DARK || brightness > TOO_BRIGHT ? "warn" : "done";
  const lightingNote =
    brightness === null
      ? ""
      : brightness < TOO_DARK
      ? "Too dark: face a window or a lamp"
      : brightness > TOO_BRIGHT
      ? "Too bright: avoid a light behind you"
      : "";

  return (
    <div className="glass-card">
      <StepIndicator current={1} />
      <div className="center mb-1">
        <h2>Position your face</h2>
        <p className="sub">Centre your face in the oval, with light on it</p>
      </div>

      <div className="oval-wrap">
        <div className="oval">
          <LiveVideo stream={stream} />
          {ready && <div className="scan-line" />}
        </div>
      </div>

      {error && <div className="notice" role="alert">{error}</div>}

      {cameras.length > 1 && (
        <label className="field">
          Camera
          <select value={cameraId} onChange={(e) => open(e.target.value)}>
            {cameras.map((camera, i) => (
              <option key={camera.deviceId} value={camera.deviceId}>
                {camera.label || `Camera ${i + 1}`}
              </option>
            ))}
          </select>
        </label>
      )}

      <div className="check-list">
        <Check state={ready ? "done" : access === "requesting" ? "working" : access === "error" ? "warn" : "pending"}>
          {ready ? "Camera and microphone connected" : "Connecting camera and microphone"}
        </Check>
        <Check state={!ready ? "pending" : lighting} detail={lightingNote}>
          {lighting === "done" ? "Lighting looks good" : "Checking the lighting"}
        </Check>
        <Check state={!ready ? "pending" : level > 8 ? "done" : "working"} detail={ready ? `level ${level}%` : ""}>
          {level > 8 ? "Microphone hears you" : "Say a word to test the microphone (optional)"}
        </Check>
      </div>

      <div className="btn-row">
        {access === "error" ? (
          <button className="btn-primary" onClick={() => open()}>
            Try again
          </button>
        ) : (
          <button className="btn-primary" onClick={onNext} disabled={!ready}>
            Begin challenge →
          </button>
        )}
      </div>
    </div>
  );
}
