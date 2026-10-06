// Mirrors backend/app/schemas/session.py and detector.py (the API contract the recorder page reads).

export type VisualChallenge = "TURN_HEAD_LEFT" | "TURN_HEAD_RIGHT" | "LOOK_UP" | "LOOK_DOWN" | "BLINK_TWICE";

export type VerificationStatus = "CREATED" | "PROCESSING" | "VERIFIED" | "SUSPICIOUS" | "FAILED";

export interface DetectorResult {
  score: number | null;
  passed: boolean;
  reason: string;
  error: string | null;
  details: Record<string, unknown>;
}

export interface SessionChallenge {
  session_id: string;
  challenge: { visual: VisualChallenge; verbal: string };
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
