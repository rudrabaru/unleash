// Mirrors backend/app/schemas/session.py and detector.py (the API contract the recorder page reads).

export type VisualChallenge = "TURN_HEAD_LEFT" | "TURN_HEAD_RIGHT" | "LOOK_UP" | "LOOK_DOWN" | "BLINK_TWICE";

export type VerificationStatus = "CREATED" | "PROCESSING" | "VERIFIED" | "SUSPICIOUS" | "FAILED" | "RETRY";

export interface DetectorResult {
  score: number | null;
  passed: boolean;
  reason: string;
  error: string | null;
  details: Record<string, unknown>;
}

export type PhaseName = "read" | "speak" | "act";

// Seconds from the start of the recording. The server owns these numbers (backend/app/protocol.py).
export interface PhaseWindow {
  name: PhaseName;
  start: number;
  end: number;
}

export interface Protocol {
  version: number;
  total_seconds: number;
  min_recording_seconds: number;
  max_recording_seconds: number;
  phases: PhaseWindow[];
}

export interface SessionChallenge {
  session_id: string;
  challenge: { visual: VisualChallenge; verbal: string };
  protocol: Protocol;
  token: string;
  expires_at: number; // epoch seconds
  created_at: string;
}

export interface SessionResult {
  session_id: string;
  status: VerificationStatus;
  confidence: number | null;
  decision_reason: string;
  created_at: string;
  updated_at: string;
  signals: Record<string, DetectorResult> | null;
}
