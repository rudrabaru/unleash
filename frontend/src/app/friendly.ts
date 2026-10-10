import type { DetectorResult, SessionResult } from "./types";

// Turns what the backend reports into plain words for the person who did the check. The backend sends
// machine-readable codes (`details.failure_code` and the counts in the audio details) next to its own
// technical `reason`; the technical text is never shown to the person unless debugging is on.

export interface Check {
  label: string;
  ok: boolean | null; // null = not checked (an earlier step already stopped the check)
  note?: string;
}

export interface Explanation {
  message: string; // one sentence under the verdict title
  checks: Check[]; // the three things every session is judged on
  advice: string[]; // what to do differently next time (empty on success)
}

const codeOf = (signal?: DetectorResult): string | null => {
  const code = signal?.details?.failure_code;
  return typeof code === "string" ? code : null;
};
const detail = (signal: DetectorResult | undefined, key: string): unknown => signal?.details?.[key];

// ── Why a recording could not be judged (status RETRY) ─────────────────────────────────────────────
const RETRY_MESSAGES: Record<string, { message: string; advice: string }> = {
  too_short: { message: "The recording was too short to check.", advice: "Stay on the page until the timer ends." },
  too_long: { message: "The recording was longer than expected.", advice: "Start again and let the timer finish on its own." },
  too_large: { message: "The picture of the recording was too large to check.", advice: "Use the camera's normal resolution (up to 1080p)." },
  av_skew: { message: "The picture and the sound of the recording did not line up.", advice: "Close other programs that use the camera or microphone, then try again." },
  bad_baseline: { message: "We could not see your face clearly at the start.", advice: "Look straight at the camera for the first seconds, with light on your face." },
  no_face: { message: "We lost sight of your face during the movement.", advice: "Keep your face in the picture while you move your head." },
  mic_silent: { message: "We could not hear anything from your microphone.", advice: "Check that your microphone is on and not muted, then try again." },
};
const OUR_SIDE = "Something went wrong on our side, not yours.";

// A recording that could not be judged shows no pass/fail marks: nothing was concluded about it.
function retryExplanation(result: SessionResult): Explanation {
  const signals = result.signals ?? {};
  // Several signals can carry a code at once (a missed movement next to a dead microphone): use the first
  // one that explains why the recording could not be judged.
  const code = [signals.recording, signals.visual_challenge, signals.audio_pipeline]
    .map(codeOf)
    .find((candidate): candidate is string => candidate !== null && candidate in RETRY_MESSAGES);
  const known = code ? RETRY_MESSAGES[code] : undefined;
  if (known) return { message: known.message, checks: [], advice: [known.advice] };
  return { message: OUR_SIDE, checks: [], advice: ["Please try again in a moment."] };
}

// ── The movement ───────────────────────────────────────────────────────────────────────────────────
const MOVEMENT_FAILURES: Record<string, { note: string; advice: string }> = {
  no_motion: { note: "We did not see a clear movement.", advice: "Make the movement bigger and slower, so it is easy to see." },
  wrong_direction: { note: "You moved the other way.", advice: "Move the way the arrow points." },
  no_hold: { note: "The movement was not held long enough.", advice: "Hold the position for about a second." },
  no_return: { note: "You did not come back to the centre.", advice: "After holding it, return to face the camera." },
};

function movementCheck(visual?: DetectorResult): { check: Check; advice?: string } {
  if (!visual) return { check: { label: "Head movement", ok: null } };
  if (visual.passed) return { check: { label: "Head movement", ok: true, note: "Turned, held and returned to the centre." } };
  const known = MOVEMENT_FAILURES[codeOf(visual) ?? ""];
  return {
    check: { label: "Head movement", ok: false, note: known?.note ?? "We did not see the movement." },
    advice: known?.advice ?? "Do the movement shown, hold it, then return to the centre.",
  };
}

// ── The words ──────────────────────────────────────────────────────────────────────────────────────
function speechChecks(audio?: DetectorResult): { checks: Check[]; advice: string[] } {
  const speech: Check = { label: "Speech", ok: null };
  const words: Check = { label: "The five words, in order", ok: null };
  if (!audio) return { checks: [speech, words], advice: [] };
  if (audio.passed) {
    speech.ok = true;
    words.ok = true;
    return { checks: [speech, words], advice: [] };
  }
  const phraseRan = typeof detail(audio, "phrase_matched") === "boolean";
  if (!phraseRan) {
    speech.ok = false;
    speech.note = audio.error ? "We could not process the sound." : "We did not hear enough speech.";
    return { checks: [speech, words], advice: ["Speak clearly and a little louder, close to the microphone, while the words are shown."] };
  }
  speech.ok = true;
  words.ok = false;
  const matched = Number(detail(audio, "match_count") ?? 0);
  const extra = Number(detail(audio, "insertions") ?? 0);
  const limit = Number(detail(audio, "max_insertions") ?? 3);
  if (matched >= 4 && extra > limit) {
    words.note = "Other words were said as well.";
    return { checks: [speech, words], advice: ["Say only the five words, nothing before or after."] };
  }
  words.note = `We heard ${matched} of the 5 words in the right order.`;
  return { checks: [speech, words], advice: ["Say the five words exactly as shown, in order, at a steady pace."] };
}

// ── Put together ───────────────────────────────────────────────────────────────────────────────────
export function explain(result: SessionResult): Explanation {
  const signals = result.signals ?? {};
  const movement = movementCheck(signals.visual_challenge);
  const spoken = speechChecks(signals.audio_pipeline);
  const checks = [movement.check, ...spoken.checks];

  if (result.status === "RETRY") return retryExplanation(result);

  if (result.status === "VERIFIED") {
    return { message: "The movement and the words were both seen in this recording.", checks, advice: [] };
  }
  if (result.status === "SUSPICIOUS") {
    return {
      message: "The movement and the words were seen, but the recording was not clear enough to be sure.",
      checks,
      advice: ["Try again with good light on your face and no one else in the picture."],
    };
  }
  const advice = [movement.advice, ...spoken.advice].filter((a): a is string => Boolean(a));
  const missed = checks.some((c) => c.ok === false);
  return {
    message: missed ? "Something the check needs was missing from this recording." : "The checks together did not pass.",
    checks,
    advice: advice.length ? advice : ["Try again with good light on your face and no one else in the picture."],
  };
}
