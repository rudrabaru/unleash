"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { Cancelled, submitRecording, waitForResult } from "./api";
import { Challenge } from "./screens/Challenge";
import { PreScan } from "./screens/PreScan";
import { Processing } from "./screens/Processing";
import { Result } from "./screens/Result";
import { Welcome } from "./screens/Welcome";
import type { SessionChallenge, SessionResult } from "./types";
import { useRecorder } from "./useRecorder";

type Screen = "welcome" | "prescan" | "challenge" | "uploading" | "analysing" | "result";

export default function Home() {
  const recorder = useRecorder();
  const { close } = recorder;
  const [screen, setScreen] = useState<Screen>("welcome");
  const [result, setResult] = useState<SessionResult | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [blob, setBlob] = useState<Blob | null>(null);
  const [session, setSession] = useState<SessionChallenge | null>(null);

  // The wait for a result can be cancelled: leaving the page or starting over stops polling at once.
  const waiting = useRef<AbortController | null>(null);
  useEffect(() => () => waiting.current?.abort(), []);

  const analyse = useCallback(
    async (recording: Blob, challenge: SessionChallenge) => {
      close(); // the camera is not needed any more
      setBlob(recording);
      setSession(challenge);
      setResult(null);
      setProblem(null);
      setScreen("uploading");
      waiting.current?.abort();
      const controller = new AbortController();
      waiting.current = controller;
      try {
        await submitRecording(challenge, recording);
        setScreen("analysing");
        setResult(await waitForResult(challenge.session_id, controller.signal));
      } catch (err: any) {
        if (err instanceof Cancelled) return;
        setProblem(err.message);
      }
      setScreen("result");
    },
    [close],
  );

  const startOver = () => {
    waiting.current?.abort();
    setResult(null);
    setProblem(null);
    setBlob(null);
    setSession(null);
    setScreen("prescan");
  };

  return (
    <div className="app">
      <div className="dot-grid" />
      <div className="glow glow-a" />
      <div className="glow glow-b" />

      <header className="header">
        <div className="brand-mark">
          <svg width="12" height="14" viewBox="0 0 12 14" fill="none" aria-hidden="true">
            <path d="M6 0L0 2.5v4c0 3.5 2.3 6.8 6 8 3.7-1.2 6-4.5 6-8v-4L6 0z" fill="white" />
          </svg>
        </div>
        <span className="brand-name">Unleash</span>
        <span className="brand-tag">Prototype</span>
      </header>

      <main className="stage">
        {screen === "welcome" && <Welcome onNext={() => setScreen("prescan")} />}
        {screen === "prescan" && <PreScan recorder={recorder} onNext={() => setScreen("challenge")} />}
        {screen === "challenge" && <Challenge recorder={recorder} onFinished={analyse} onCancel={() => setScreen("prescan")} />}
        {screen === "uploading" && <Processing stage="uploading" />}
        {screen === "analysing" && <Processing stage="analysing" />}
        {screen === "result" && <Result result={result} problem={problem} blob={blob} session={session} onRetry={startOver} />}
      </main>
    </div>
  );
}
