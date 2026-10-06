"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import { Mic, MicOff, Volume2, Play, Square, RefreshCw, CheckCircle2, AlertTriangle, ShieldCheck } from "lucide-react";

type PermissionStatus = "idle" | "requesting" | "granted" | "denied" | "error";

interface SessionChallenge {
  session_id: string;
  challenge: {
    visual: string;
    verbal: string;
  };
  token: string;
  expires_at: number;
}

// Left and right are the person's own left and right (the backend reads an unmirrored recording).
const VISUAL_INSTRUCTIONS: Record<string, string> = {
  TURN_HEAD_LEFT: "Turn your head to your left",
  TURN_HEAD_RIGHT: "Turn your head to your right",
  LOOK_UP: "Look up",
  LOOK_DOWN: "Look down",
  BLINK_TWICE: "Blink twice",
};

export default function AudioCapturePrototype() {
  // Session State
  const [session, setSession] = useState<SessionChallenge | null>(null);
  const [loadingSession, setLoadingSession] = useState(false);
  const [sessionError, setSessionError] = useState<string | null>(null);

  // Audio & Hardware State
  const [permission, setPermission] = useState<PermissionStatus>("idle");
  const [permissionError, setPermissionError] = useState<string | null>(null);
  const [volumeLevel, setVolumeLevel] = useState<number>(0);
  const [frequencyData, setFrequencyData] = useState<number[]>([0, 0, 0, 0, 0, 0, 0, 0]);
  const [isVoiceActive, setIsVoiceActive] = useState<boolean>(false);

  // Recording State
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [recordedBlobUrl, setRecordedBlobUrl] = useState<string | null>(null);
  const [recordingBlobInfo, setRecordingBlobInfo] = useState<{ size: number; type: string; duration: number } | null>(null);
  const [recordingDuration, setRecordingDuration] = useState<number>(0);

  // Web Audio Refs
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const animFrameIdRef = useRef<number | null>(null);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordedChunksRef = useRef<Blob[]>([]);
  const recordingTimerRef = useRef<NodeJS.Timeout | null>(null);
  const recordStartTimeRef = useRef<number>(0);
  const videoPreviewRef = useRef<HTMLVideoElement | null>(null);

  // Initialize or fetch challenge session
  const fetchSession = async () => {
    setLoadingSession(true);
    setSessionError(null);
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";
      const res = await fetch(`${apiBase}/sessions`, { method: "POST" });
      if (!res.ok) {
        throw new Error(`Failed to create session (${res.status}: ${res.statusText})`);
      }
      const data: SessionChallenge = await res.json();
      setSession(data);
    } catch (err: any) {
      setSession(null);
      setSessionError(`Backend unreachable: ${err.message}. Start the API on port 8000 and click New Challenge.`);
    } finally {
      setLoadingSession(false);
    }
  };

  useEffect(() => {
    fetchSession();
  }, []);

  // Request Microphone with Required Constraints (Project Plan Section 5.7)
  const startAudioMonitoring = async () => {
    setPermission("requesting");
    setPermissionError(null);

    const audioConstraints: MediaTrackConstraints = {
      echoCancellation: true,
      noiseSuppression: true,
      sampleRate: 16000, // Browser hint (backend forces 16kHz server-side regardless)
    };

    try {
      const stream = await navigator.mediaDevices.getUserMedia({
        audio: audioConstraints,
        video: { width: { ideal: 1280 }, height: { ideal: 720 }, frameRate: { ideal: 30 }, facingMode: "user" },
      });

      mediaStreamRef.current = stream;
      setPermission("granted");

      // Initialize Web Audio API for Live Volume Metering
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      const audioCtx = new AudioCtx();
      audioContextRef.current = audioCtx;

      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 64;
      analyser.smoothingTimeConstant = 0.4;
      analyserRef.current = analyser;

      const source = audioCtx.createMediaStreamSource(stream);
      source.connect(analyser);

      // Volume metering loop
      const bufferLength = analyser.frequencyBinCount;
      const dataArray = new Uint8Array(bufferLength);

      const updateVolume = () => {
        if (!analyserRef.current) return;
        analyserRef.current.getByteFrequencyData(dataArray);

        // Compute RMS volume
        let sum = 0;
        for (let i = 0; i < bufferLength; i++) {
          sum += dataArray[i] * dataArray[i];
        }
        const rms = Math.sqrt(sum / bufferLength);
        const normalized = Math.min(100, Math.round((rms / 128) * 100));

        setVolumeLevel(normalized);
        setIsVoiceActive(normalized > 12);

        // Sample 8 frequency bands for the visualizer
        const bands = [];
        const step = Math.floor(bufferLength / 8);
        for (let b = 0; b < 8; b++) {
          const val = dataArray[b * step] || 0;
          bands.push(Math.round((val / 255) * 100));
        }
        setFrequencyData(bands);

        animFrameIdRef.current = requestAnimationFrame(updateVolume);
      };

      updateVolume();
    } catch (err: any) {
      console.error("Microphone capture failed:", err);
      setPermission("denied");
      if (err.name === "NotAllowedError" || err.name === "PermissionDeniedError") {
        setPermissionError("Camera or microphone access was denied. Allow both in your browser address bar.");
      } else if (err.name === "NotFoundError" || err.name === "DevicesNotFoundError") {
        setPermissionError("No camera or microphone was detected on your computer.");
      } else {
        setPermissionError(`Camera or microphone error: ${err.message || err.name}`);
      }
    }
  };

  // Stop Audio Monitoring
  const stopAudioMonitoring = useCallback(() => {
    if (animFrameIdRef.current) {
      cancelAnimationFrame(animFrameIdRef.current);
      animFrameIdRef.current = null;
    }
    if (audioContextRef.current) {
      audioContextRef.current.close().catch(() => {});
      audioContextRef.current = null;
    }
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((track) => track.stop());
      mediaStreamRef.current = null;
    }
    setVolumeLevel(0);
    setFrequencyData([0, 0, 0, 0, 0, 0, 0, 0]);
    setIsVoiceActive(false);
    setPermission("idle");
  }, []);

  // Show the live camera feed while the stream is connected
  useEffect(() => {
    if (videoPreviewRef.current) {
      videoPreviewRef.current.srcObject = permission === "granted" ? mediaStreamRef.current : null;
    }
  }, [permission]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopAudioMonitoring();
      if (recordingTimerRef.current) clearInterval(recordingTimerRef.current);
    };
  }, [stopAudioMonitoring]);

  // Start MediaRecorder Capture
  const startRecording = () => {
    if (!mediaStreamRef.current) return;
    recordedChunksRef.current = [];
    setRecordedBlobUrl(null);
    setRecordingBlobInfo(null);
    setRecordingDuration(0);

    try {
      // One VP8 + Opus WebM file: the backend splits audio and video itself.
      const mimeType = "video/webm;codecs=vp8,opus";
      if (!MediaRecorder.isTypeSupported(mimeType)) {
        setPermissionError("This browser cannot record VP8 + Opus WebM. Use Chrome, Edge or Firefox.");
        return;
      }

      const recorder = new MediaRecorder(mediaStreamRef.current, { mimeType, videoBitsPerSecond: 2_500_000 });

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) {
          recordedChunksRef.current.push(e.data);
        }
      };

      recorder.onstop = () => {
        const blob = new Blob(recordedChunksRef.current, { type: mimeType });
        const url = URL.createObjectURL(blob);
        const elapsed = (Date.now() - recordStartTimeRef.current) / 1000;
        setRecordedBlobUrl(url);
        setRecordingBlobInfo({
          size: blob.size,
          type: blob.type,
          duration: Number(elapsed.toFixed(2)),
        });
      };

      recordStartTimeRef.current = Date.now();
      recorder.start(100); // 100ms chunk timeslice
      mediaRecorderRef.current = recorder;
      setIsRecording(true);

      recordingTimerRef.current = setInterval(() => {
        setRecordingDuration((prev) => Number((prev + 0.1).toFixed(1)));
      }, 100);
    } catch (err: any) {
      console.error("Failed to start MediaRecorder:", err);
    }
  };

  // Stop MediaRecorder Capture
  const stopRecording = () => {
    if (mediaRecorderRef.current && isRecording) {
      mediaRecorderRef.current.stop();
      setIsRecording(false);
      if (recordingTimerRef.current) {
        clearInterval(recordingTimerRef.current);
        recordingTimerRef.current = null;
      }
    }
  };

  // Split the verbal challenge into its words
  const verbalWords: string[] = session?.challenge.verbal ? session.challenge.verbal.split(/\s+/).filter(Boolean) : [];

  return (
    <main className="container" style={{ maxWidth: "800px", minHeight: "90vh", display: "flex", flexDirection: "column", gap: "1.5rem" }}>
      {/* Header */}
      <header className="card" style={{ padding: "1.5rem 2rem", display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div>
          <div style={{ display: "flex", alignItems: "center", gap: "0.5rem", marginBottom: "0.25rem" }}>
            <span className="badge badge-verified">Recorder prototype</span>
            <span style={{ fontSize: "0.85rem", color: "var(--text-muted)" }}>Calibration clips</span>
          </div>
          <h1 style={{ fontSize: "1.5rem", fontWeight: "700" }}>Camera and Microphone Recorder</h1>
        </div>
        <button className="btn-secondary" onClick={fetchSession} disabled={loadingSession} style={{ display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.85rem" }}>
          <RefreshCw size={14} className={loadingSession ? "spin" : ""} />
          {loadingSession ? "Generating..." : "New Challenge"}
        </button>
      </header>

      {sessionError && (
        <section className="card" role="alert" style={{ color: "#fca5a5", borderColor: "#7f1d1d" }}>
          {sessionError}
        </section>
      )}

      {/* Verbal Challenge Display Section */}
      <section className="card" style={{ textAlign: "center", display: "flex", flexDirection: "column", alignItems: "center", gap: "1.25rem" }}>
        <div>
          <span style={{ fontSize: "0.85rem", textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--accent-cyan)", fontWeight: 600 }}>
            Verbal Challenge Phrase
          </span>
          <p style={{ color: "var(--text-secondary)", fontSize: "0.95rem", marginTop: "0.25rem" }}>
            Say these 5 words clearly, in order, during the recording window
          </p>
        </div>

        <div
          className="challenge-word-box"
          style={{ letterSpacing: "normal", fontSize: "1.9rem", flexWrap: "wrap", gap: "0.5rem 1.25rem", textTransform: "lowercase" }}
        >
          {verbalWords.length > 0
            ? verbalWords.map((word, i) => <span key={`${word}-${i}`}>{word}</span>)
            : "• • • • •"}
        </div>

        <div style={{ display: "flex", gap: "0.5rem", flexWrap: "wrap", justifyContent: "center" }}>
          <span className="badge" style={{ background: "rgba(255,255,255,0.05)", border: "1px solid var(--border-color)", color: "var(--text-secondary)", fontSize: "0.75rem" }}>
            Speak naturally: say the words, do not spell them
          </span>
          <span className="badge" style={{ background: "rgba(255,255,255,0.05)", border: "1px solid var(--border-color)", color: "var(--text-secondary)", fontSize: "0.75rem" }}>
            Must-pass: at least 4 of 5 words match
          </span>
        </div>
      </section>

      {/* Visual Challenge */}
      <section className="card" style={{ textAlign: "center" }}>
        <span style={{ fontSize: "0.85rem", textTransform: "uppercase", letterSpacing: "0.08em", color: "var(--accent-cyan)", fontWeight: 600 }}>
          Visual Challenge
        </span>
        <p style={{ fontSize: "1.4rem", fontWeight: 600, marginTop: "0.4rem" }}>
          {session?.challenge.visual ? (VISUAL_INSTRUCTIONS[session.challenge.visual] ?? session.challenge.visual) : "•"}
        </p>
        <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginTop: "0.25rem" }}>
          Do this while saying the words.
        </p>
      </section>

      {/* Camera, Microphone & Feedback Section */}
      <section className="card" style={{ display: "flex", flexDirection: "column", gap: "1.25rem" }}>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", flexWrap: "wrap", gap: "0.5rem" }}>
          <div>
            <h2 style={{ fontSize: "1.15rem", fontWeight: "600", display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <Mic size={18} color="var(--accent-cyan)" />
              Camera, Microphone and Level Meter
            </h2>
            <p style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginTop: "0.2rem" }}>
              About 720p at 30 fps; echoCancellation, noiseSuppression
            </p>
          </div>

          <div>
            {permission === "granted" ? (
              <span className="badge badge-verified" style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem" }}>
                <CheckCircle2 size={13} /> Camera and Mic Connected
              </span>
            ) : permission === "denied" ? (
              <span className="badge badge-failed" style={{ display: "inline-flex", alignItems: "center", gap: "0.3rem" }}>
                <MicOff size={13} /> Blocked
              </span>
            ) : (
              <span className="badge" style={{ background: "rgba(100,116,139,0.15)", color: "var(--text-muted)", border: "1px solid var(--border-color)" }}>
                Inactive
              </span>
            )}
          </div>
        </div>

        {/* Permission Error Banner */}
        {permissionError && (
          <div style={{ padding: "0.85rem 1rem", background: "rgba(244, 63, 94, 0.12)", border: "1px solid var(--accent-rose)", borderRadius: "8px", color: "#fca5a5", fontSize: "0.9rem", display: "flex", alignItems: "center", gap: "0.5rem" }}>
            <AlertTriangle size={18} color="var(--accent-rose)" />
            <span>{permissionError}</span>
          </div>
        )}

        <video
          ref={videoPreviewRef}
          autoPlay
          muted
          playsInline
          style={{ width: "100%", maxHeight: "360px", background: "#000", borderRadius: "10px", display: permission === "granted" ? "block" : "none", transform: "scaleX(-1)" }}
        />

        {/* Live Volume Meter & Equalizer Visualizer */}
        <div style={{ background: "var(--bg-card)", padding: "1.25rem", borderRadius: "10px", border: "1px solid var(--border-color)", display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
            <span style={{ fontSize: "0.85rem", color: "var(--text-secondary)", display: "flex", alignItems: "center", gap: "0.4rem" }}>
              <Volume2 size={16} color={isVoiceActive ? "var(--accent-emerald)" : "var(--text-muted)"} />
              Audio Input Level: <strong style={{ color: "var(--text-primary)" }}>{volumeLevel}%</strong>
            </span>
            <span className={`badge ${isVoiceActive ? "badge-verified" : ""}`} style={{ fontSize: "0.75rem", opacity: isVoiceActive ? 1 : 0.4 }}>
              {isVoiceActive ? "● Voice Activity Detected" : "○ Ambient Level"}
            </span>
          </div>

          {/* Continuous Level Bar */}
          <div className="meter-track">
            <div
              className="meter-fill"
              style={{
                width: `${volumeLevel}%`,
                background: volumeLevel > 60
                  ? "linear-gradient(90deg, #10b981 0%, #f59e0b 70%, #f43f5e 100%)"
                  : volumeLevel > 15
                  ? "linear-gradient(90deg, #06b6d4 0%, #10b981 100%)"
                  : "var(--text-muted)",
              }}
            />
          </div>

          {/* 8-Band Equalizer Frequency Visualizer */}
          <div style={{ display: "flex", alignItems: "flex-end", justifyContent: "center", gap: "8px", height: "40px", padding: "4px 0" }}>
            {frequencyData.map((val, idx) => (
              <div
                key={idx}
                className="equalizer-bar"
                style={{
                  height: `${Math.max(4, (val / 100) * 36)}px`,
                  background: isVoiceActive ? "var(--accent-cyan)" : "var(--border-color)",
                }}
              />
            ))}
          </div>
        </div>

        {/* Action Controls */}
        <div style={{ display: "flex", gap: "0.75rem", flexWrap: "wrap", alignItems: "center" }}>
          {permission !== "granted" ? (
            <button className="btn-primary" onClick={startAudioMonitoring} disabled={permission === "requesting"} style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
              <Mic size={16} />
              {permission === "requesting" ? "Requesting access..." : "Enable Camera and Microphone"}
            </button>
          ) : (
            <>
              {!isRecording ? (
                <button className="btn-record" onClick={startRecording}>
                  <Play size={16} fill="white" />
                  Start Test Recording
                </button>
              ) : (
                <button className="btn-stop" onClick={stopRecording}>
                  <Square size={16} fill="var(--accent-rose)" />
                  Stop Recording ({recordingDuration}s)
                </button>
              )}
              <button className="btn-secondary" onClick={stopAudioMonitoring}>
                Disconnect
              </button>
            </>
          )}
        </div>
      </section>

      {/* Recorded Audio Playback & Verification Check */}
      {recordedBlobUrl && (
        <section className="card" style={{ background: "rgba(16, 185, 129, 0.05)", border: "1px solid rgba(16, 185, 129, 0.3)", display: "flex", flexDirection: "column", gap: "1rem" }}>
          <div style={{ display: "flex", alignItems: "center", justifyContent: "space-between" }}>
            <h3 style={{ fontSize: "1rem", fontWeight: "600", color: "var(--accent-emerald)", display: "flex", alignItems: "center", gap: "0.4rem" }}>
              <ShieldCheck size={18} />
              Captured Clip
            </h3>
            <span style={{ fontSize: "0.8rem", color: "var(--text-secondary)" }}>
              {recordingBlobInfo?.duration}s • {(Number(recordingBlobInfo?.size || 0) / 1024).toFixed(1)} KB
            </span>
          </div>

          <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
            Play it back to confirm your face is in frame and the voice is audible, then save the clip:
          </p>

          <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
            <video src={recordedBlobUrl} controls playsInline style={{ width: "100%", borderRadius: "8px" }} />
            <button
              className="btn-primary"
              onClick={() => {
                if (recordedBlobUrl) {
                  const link = document.createElement("a");
                  link.href = recordedBlobUrl;
                  link.download = `clip-${session?.challenge.visual ?? "NONE"}-${Date.now()}.webm`;
                  document.body.appendChild(link);
                  link.click();
                  document.body.removeChild(link);
                }
              }}
              style={{ alignSelf: "flex-start" }}
            >
              ⬇ Save Clip
            </button>
          </div>

          <div style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "flex", gap: "1rem" }}>
            <span>MIME: {recordingBlobInfo?.type}</span>
            <span>Video VP8 + audio Opus (browser)</span>
            <span>Server splits audio to 16kHz WAV</span>
          </div>
        </section>
      )}
    </main>
  );
}
