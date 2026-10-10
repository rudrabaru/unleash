import type { VisualChallenge } from "./types";

// One recording is three steps: read the words, say them facing the camera, then do the action.
export const READ_SECONDS = 3;
export const SPEAK_SECONDS = 5;
export const ACT_SECONDS = 5;
export const TOTAL_SECONDS = READ_SECONDS + SPEAK_SECONDS + ACT_SECONDS;

export type ChallengeStep = "read" | "speak" | "act";

export function stepAt(elapsedSeconds: number): ChallengeStep {
  if (elapsedSeconds < READ_SECONDS) return "read";
  if (elapsedSeconds < READ_SECONDS + SPEAK_SECONDS) return "speak";
  return "act";
}

// Left and right are the person's own left and right. The preview is mirrored for the user only;
// the recording is not, and the backend reads it unmirrored (see backend/app/modules/visual/_pose.py).
export const VISUAL_INSTRUCTIONS: Record<VisualChallenge, string> = {
  TURN_HEAD_LEFT: "Turn your head to your left",
  TURN_HEAD_RIGHT: "Turn your head to your right",
  LOOK_UP: "Look up",
  LOOK_DOWN: "Look down",
  BLINK_TWICE: "Blink twice",
};

// The browser records straight from the camera, so these are the only labels the user sees.
export const SIGNAL_LABELS: Record<string, string> = {
  audio_pipeline: "Speech and phrase",
  visual_liveness: "Liveness",
  visual_challenge: "Challenge compliance",
  deepfake: "Deepfake detection",
  replay: "Replay detection",
};

// Signals whose thresholds have not been calibrated on recordings yet (see V1_RELEASE_PLAN.md).
export const UNCALIBRATED_SIGNALS = new Set(["deepfake", "replay"]);
