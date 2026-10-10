import type { SessionChallenge, SessionResult } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "/api/v1";

const POLL_INTERVAL_MS = 1500;
const POLL_ATTEMPTS = 80;

async function request(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch {
    throw new Error("Could not reach the server. Start the API on port 8000 and try again.");
  }
}

export async function createSession(): Promise<SessionChallenge> {
  const res = await request(`${API_BASE}/sessions`, { method: "POST" });
  if (!res.ok) throw new Error(`Could not start a session (${res.status}).`);
  return res.json();
}

export async function submitRecording(session: SessionChallenge, blob: Blob): Promise<void> {
  const form = new FormData();
  form.append("token", session.token);
  form.append("media", blob, "recording.webm");
  const res = await request(`${API_BASE}/sessions/${session.session_id}/submit`, { method: "POST", body: form });
  if (!res.ok) {
    const body = await res.json().catch(() => null);
    throw new Error(typeof body?.detail === "string" ? body.detail : `Upload failed (${res.status}).`);
  }
}

export async function waitForResult(sessionId: string): Promise<SessionResult> {
  for (let attempt = 0; attempt < POLL_ATTEMPTS; attempt++) {
    await new Promise((resolve) => setTimeout(resolve, POLL_INTERVAL_MS));
    const res = await request(`${API_BASE}/sessions/${sessionId}`);
    if (!res.ok) throw new Error(`Could not read the result (${res.status}).`);
    const result: SessionResult = await res.json();
    if (result.status !== "PROCESSING") return result;
  }
  throw new Error("The analysis did not finish in time.");
}
