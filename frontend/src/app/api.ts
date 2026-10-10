import type { SessionChallenge, SessionResult } from "./types";

export const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "/api/v1";

const POLL_INTERVAL_MS = 1500;
const POLL_TIMEOUT_MS = 150_000;
const MAX_CONSECUTIVE_ERRORS = 4; // a blip or a restarting server is not a failure; a steady outage is
const MAX_BACKOFF_MS = 6000;

// Thrown when the person (or the page) cancels the wait; callers treat it as "stop quietly".
export class Cancelled extends Error {
  constructor() {
    super("Cancelled");
    this.name = "Cancelled";
  }
}

async function request(url: string, init?: RequestInit): Promise<Response> {
  try {
    return await fetch(url, init);
  } catch (err: any) {
    if (err?.name === "AbortError") throw new Cancelled();
    throw new Error("Could not reach the server. Check your connection and try again.");
  }
}

export async function createSession(): Promise<SessionChallenge> {
  const res = await request(`${API_BASE}/sessions`, { method: "POST" });
  if (!res.ok) throw new Error(`Could not start a session (${res.status}). Please try again.`);
  return res.json();
}

// The server explains a refusal in plain words (too large, too soon, unreadable); show that, not a code.
async function refusalMessage(res: Response): Promise<string> {
  const body = await res.json().catch(() => null);
  return typeof body?.detail === "string" ? body.detail : `The recording could not be sent (${res.status}). Please try again.`;
}

export async function submitRecording(session: SessionChallenge, blob: Blob): Promise<void> {
  const form = new FormData();
  form.append("token", session.token);
  form.append("media", blob, "recording.webm");
  const res = await request(`${API_BASE}/sessions/${session.session_id}/submit`, { method: "POST", body: form });
  if (!res.ok) throw new Error(await refusalMessage(res));
}

function pause(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    if (signal?.aborted) return reject(new Cancelled());
    const timer = setTimeout(() => {
      signal?.removeEventListener("abort", onAbort);
      resolve();
    }, ms);
    const onAbort = () => {
      clearTimeout(timer);
      reject(new Cancelled());
    };
    signal?.addEventListener("abort", onAbort, { once: true });
  });
}

// Waits for the analysis to finish. A network error or a 5xx answer is retried with a growing pause;
// anything else that is not "still processing" ends the wait. `signal` cancels it at any moment.
export async function waitForResult(sessionId: string, signal?: AbortSignal): Promise<SessionResult> {
  const deadline = Date.now() + POLL_TIMEOUT_MS;
  let errors = 0;
  while (Date.now() < deadline) {
    await pause(Math.min(MAX_BACKOFF_MS, POLL_INTERVAL_MS * 1.5 ** errors), signal);
    try {
      const res = await request(`${API_BASE}/sessions/${sessionId}`, { signal });
      if (res.status >= 500) throw new Error(`The server had a problem (${res.status}).`);
      if (!res.ok) throw Object.assign(new Error("The result could not be found."), { fatal: true });
      const result: SessionResult = await res.json();
      if (result.status !== "PROCESSING") return result;
      errors = 0;
    } catch (err: any) {
      if (err instanceof Cancelled || err?.fatal || ++errors > MAX_CONSECUTIVE_ERRORS) throw err;
    }
  }
  throw new Error("The analysis is taking longer than expected. Please try again.");
}
