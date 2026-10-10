import type { PhaseName, PhaseWindow, Protocol, VisualChallenge } from "./types";

// The server owns the phase windows (backend/app/protocol.py) and sends them with every new session.
// This file only reads them, so what the person is shown and what the backend judges cannot drift apart.

export const PHASE_LABELS: Record<PhaseName, string> = { read: "Read", speak: "Speak", act: "Act" };

// Seconds of "get ready" before the recording (and the Read phase) starts. Not part of the recording.
export const PRE_ROLL_SECONDS = 3;

export function phaseAt(protocol: Protocol, elapsedSeconds: number): PhaseName {
  const found = protocol.phases.find((phase) => elapsedSeconds < phase.end);
  return (found ?? protocol.phases[protocol.phases.length - 1]).name;
}

export function windowOf(protocol: Protocol, name: PhaseName): PhaseWindow {
  return protocol.phases.find((phase) => phase.name === name) ?? protocol.phases[0];
}

export function secondsLeftInRecording(protocol: Protocol, elapsedSeconds: number): number {
  return Math.max(0, Math.ceil(protocol.total_seconds - elapsedSeconds));
}

export function secondsLeftInPhase(protocol: Protocol, elapsedSeconds: number): number {
  const current = windowOf(protocol, phaseAt(protocol, elapsedSeconds));
  return Math.max(0, Math.ceil(current.end - elapsedSeconds));
}

// What to do in the Act phase. Left and right are the person's own left and right. The preview is
// mirrored for the user only; the recording is not, and the backend reads it unmirrored
// (see backend/app/modules/visual/_pose.py).
export const VISUAL_CUES: Record<VisualChallenge, { title: string; arrow: string }> = {
  TURN_HEAD_LEFT: { title: "Turn your head to your left", arrow: "←" },
  TURN_HEAD_RIGHT: { title: "Turn your head to your right", arrow: "→" },
  LOOK_UP: { title: "Look up", arrow: "↑" },
  LOOK_DOWN: { title: "Look down", arrow: "↓" },
  BLINK_TWICE: { title: "Blink twice", arrow: "●" },
};

// The movement is only complete when it is held and undone: the backend checks both.
export const VISUAL_CUE_DETAIL = "Hold it for a moment, then come back to the centre.";

// What each phase asks, in the words the person reads and a screen reader announces.
export const PHASE_GUIDANCE: Record<PhaseName, { heading: string; announce: string }> = {
  read: { heading: "Read these five words", announce: "Read the five words. Face the camera and keep still." },
  speak: { heading: "Say them now, in order, one at a time", announce: "Say the five words now, in order, one at a time with a short pause between them." },
  act: { heading: "Now the movement", announce: "The words are gone. Do the movement shown, hold it, then return to the centre." },
};

// The browser records straight from the camera, so these are the only labels the user sees.
export const SIGNAL_LABELS: Record<string, string> = {
  recording: "Recording",
  audio_pipeline: "Speech and phrase",
  visual_liveness: "Liveness",
  visual_challenge: "Challenge compliance",
  deepfake: "Deepfake detection",
  replay: "Replay detection",
};

// Signals whose thresholds have not been calibrated on recordings yet (see V1_RELEASE_PLAN.md).
export const UNCALIBRATED_SIGNALS = new Set(["deepfake", "replay"]);
