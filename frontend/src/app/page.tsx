"use client";

import { useState, useRef, useEffect, useCallback } from "react";
import type { SessionChallenge, SessionResult, VisualChallenge } from "./types";
import {
  ShieldCheck,
  ShieldAlert,
  ShieldX,
  Lock,
  Unlock,
  CheckCircle2,
  XCircle,
  AlertTriangle,
  AlertCircle,
  RefreshCw,
  Video,
  Mic,
  ArrowLeft,
  ArrowRight,
  ArrowUp,
  ArrowDown,
  Eye,
  Sparkles,
  ExternalLink,
  ChevronRight,
  Layers,
  Activity,
  UserCheck,
  HelpCircle,
} from "lucide-react";

// Config: Relative /api/v1 uses Next.js rewrites to proxy to backend, avoiding Mixed Content on mobile HTTPS
const API_BASE = process.env.NEXT_PUBLIC_API_BASE_URL || "/api/v1";

// STRICT Timing Sequence (Seconds)
const SCAN_SECONDS = 3.0; // 0s - 3s: Passive face scan (nothing displayed)
const SPEAK_SECONDS = 5.0; // 3s - 8s: Say the 5 words (5s duration)
const ACT_SECONDS = 5.0; // 8s - 13s: Perform visual gesture (5s duration)
const TOTAL_SECONDS = SCAN_SECONDS + SPEAK_SECONDS + ACT_SECONDS; // 13.0s total

const VISUAL_ACTIONS: Record<VisualChallenge, { text: string; icon: any }> = {
  TURN_HEAD_LEFT: { text: "Turn your head to your LEFT", icon: ArrowLeft },
  TURN_HEAD_RIGHT: { text: "Turn your head to your RIGHT", icon: ArrowRight },
  LOOK_UP: { text: "Look UP towards the top", icon: ArrowUp },
  LOOK_DOWN: { text: "Look DOWN towards the bottom", icon: ArrowDown },
  BLINK_TWICE: { text: "Blink your eyes TWICE naturally", icon: Eye },
};

const ANALYSIS_CHECKLIST = [
  { label: "Encrypted Recording Upload", sub: "WebM payload validated" },
  { label: "Speech & Audio Authenticity", sub: "Silero-VAD & Whisper transcription" },
  { label: "Head Pose & Gesture Check", sub: "MediaPipe 3D landmark tracking" },
  { label: "Replay & Anti-Spoof Detection", sub: "Moiré 2D FFT & sensor noise variance" },
  { label: "Neural Classification & Fusion", sub: "Joint weighted decision engine" },
];

type ModalPhase = "INTRO" | "RECORDING" | "ANALYZING" | "RESULT";

export default function UnleashApp() {
  // Verification Modal Visibility
  const [isModalOpen, setIsModalOpen] = useState<boolean>(true);
  const [modalPhase, setModalPhase] = useState<ModalPhase>("INTRO");
  const [isSiteUnlocked, setIsSiteUnlocked] = useState<boolean>(false);

  // Backend Challenge Session
  const [session, setSession] = useState<SessionChallenge | null>(null);
  const [loadingSession, setLoadingSession] = useState<boolean>(false);
  const [sessionError, setSessionError] = useState<string | null>(null);
  const sessionRef = useRef<SessionChallenge | null>(null);

  // Hardware & Media State
  const [permission, setPermission] = useState<"idle" | "requesting" | "granted" | "denied">("idle");
  const [permissionError, setPermissionError] = useState<string | null>(null);
  const [volumeLevel, setVolumeLevel] = useState<number>(0);
  const mediaStreamRef = useRef<MediaStream | null>(null);
  const videoPreviewRef = useRef<HTMLVideoElement | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animFrameIdRef = useRef<number | null>(null);

  // Recording & Timing
  const [isRecording, setIsRecording] = useState<boolean>(false);
  const [elapsedSeconds, setElapsedSeconds] = useState<number>(0);
  const mediaRecorderRef = useRef<MediaRecorder | null>(null);
  const recordedChunksRef = useRef<Blob[]>([]);
  const recordStartTimeRef = useRef<number>(0);
  const timerIntervalRef = useRef<NodeJS.Timeout | null>(null);

  // Dynamic Analysis Progress & Step Ticks
  const [analysisProgress, setAnalysisProgress] = useState<number>(0);
  const [completedAnalysisSteps, setCompletedAnalysisSteps] = useState<number[]>([0]);

  // Final Result State
  const [sessionResult, setSessionResult] = useState<SessionResult | null>(null);
  const [analysisError, setAnalysisError] = useState<string | null>(null);

  // Fetch or Refresh Challenge from Backend
  const fetchNewSession = async (): Promise<SessionChallenge | null> => {
    setLoadingSession(true);
    setSessionError(null);
    try {
      const res = await fetch(`${API_BASE}/sessions`, { method: "POST" });
      if (!res.ok) throw new Error(`HTTP ${res.status}: ${res.statusText}`);
      const data: SessionChallenge = await res.json();
      setSession(data);
      sessionRef.current = data;
      return data;
    } catch (err: any) {
      setSession(null);
      sessionRef.current = null;
      let msg = "Could not connect to the verification service.";
      if (typeof navigator !== "undefined" && !navigator.onLine) {
        msg = "No internet connection detected. Please check your network.";
      } else if (err.message && (err.message.includes("Failed to fetch") || err.message.includes("NetworkError"))) {
        msg = "Bad connection: Unable to reach verification server. Ensure backend is running.";
      } else if (err.message) {
        msg = err.message;
      }
      setSessionError(msg);
      return null;
    } finally {
      setLoadingSession(false);
    }
  };

  useEffect(() => {
    fetchNewSession();
  }, []);

  // Request Hardware Media Access (Camera + Mic) with Precise Hardware Diagnostics
  const initMedia = async (): Promise<MediaStream | null> => {
    // If stream is already active, reuse it (one-time permission, retained across retries)
    if (mediaStreamRef.current && mediaStreamRef.current.active) {
      setPermission("granted");
      return mediaStreamRef.current;
    }

    setPermission("requesting");
    setPermissionError(null);

    // Browser support guard
    if (typeof navigator === "undefined" || !navigator.mediaDevices || !navigator.mediaDevices.getUserMedia) {
      setPermission("denied");
      setPermissionError("Camera & microphone access is not supported on this browser or connection. Verification requires a secure HTTPS connection.");
      return null;
    }

    let stream: MediaStream | null = null;
    try {
      // Primary attempt: high-quality ideal settings with front-facing camera
      stream = await navigator.mediaDevices.getUserMedia({
        video: {
          width: { ideal: 1280 },
          height: { ideal: 720 },
          facingMode: { ideal: "user" },
          frameRate: { ideal: 30 },
        },
        audio: {
          echoCancellation: true,
          noiseSuppression: true,
          sampleRate: 16000,
        },
      });
    } catch (firstErr: any) {
      // Fallback for older webcams that reject resolution/facingMode constraints
      if (firstErr.name === "OverconstrainedError") {
        try {
          stream = await navigator.mediaDevices.getUserMedia({ video: true, audio: true });
        } catch {
          // Handled below
        }
      }

      if (!stream) {
        setPermission("denied");
        let friendlyMsg = "Camera or microphone access failed.";

        // Diagnostic probe: inspect connected hardware via enumerateDevices
        try {
          if (navigator.mediaDevices.enumerateDevices) {
            const devices = await navigator.mediaDevices.enumerateDevices();
            const hasCamera = devices.some((d) => d.kind === "videoinput");
            const hasMic = devices.some((d) => d.kind === "audioinput");

            if (!hasCamera && !hasMic) {
              friendlyMsg = "No camera and microphone found. Please connect a webcam and microphone to proceed.";
            } else if (!hasCamera) {
              friendlyMsg = "Camera / webcam not found. Please connect a camera to proceed with identity verification.";
            } else if (!hasMic) {
              friendlyMsg = "Microphone not found. Please connect a microphone to proceed with the speech challenge.";
            }
          }
        } catch {
          // Fall back to error name inspection
        }

        // If specific device absence was not confirmed, parse WebRTC error codes
        if (friendlyMsg === "Camera or microphone access failed.") {
          if (firstErr.name === "NotFoundError" || firstErr.name === "DevicesNotFoundError") {
            friendlyMsg = "Camera or microphone not found. Please check that your camera and microphone are plugged in and enabled.";
          } else if (firstErr.name === "NotAllowedError" || firstErr.name === "PermissionDeniedError") {
            friendlyMsg = "Camera or microphone permission was blocked. Please allow camera and microphone access in your browser or device settings.";
          } else if (firstErr.name === "NotReadableError" || firstErr.name === "TrackStartError") {
            friendlyMsg = "Camera or microphone is currently in use by another application (e.g. Zoom, Teams, or another browser tab). Please close other apps and try again.";
          } else if (firstErr.name === "OverconstrainedError") {
            friendlyMsg = "Your camera does not support the required video resolution.";
          } else if (firstErr.name === "SecurityError") {
            friendlyMsg = "Media access is restricted. Verification requires a secure HTTPS connection.";
          } else if (firstErr.message && firstErr.message !== "Requested device not found") {
            friendlyMsg = firstErr.message;
          }
        }

        setPermissionError(friendlyMsg);
        return null;
      }
    }

    mediaStreamRef.current = stream;
    setPermission("granted");
    setPermissionError(null);

    // Audio volume monitoring for visual feedback
    try {
      const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
      const audioCtx = new AudioCtx();
      audioContextRef.current = audioCtx;
      const analyser = audioCtx.createAnalyser();
      analyser.fftSize = 64;
      analyserRef.current = analyser;
      const source = audioCtx.createMediaStreamSource(stream);
      source.connect(analyser);

      const dataArray = new Uint8Array(analyser.frequencyBinCount);
      const updateMeter = () => {
        if (!analyserRef.current) return;
        analyserRef.current.getByteFrequencyData(dataArray);
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) sum += dataArray[i] * dataArray[i];
        const rms = Math.sqrt(sum / dataArray.length);
        setVolumeLevel(Math.min(100, Math.round((rms / 128) * 100)));
        animFrameIdRef.current = requestAnimationFrame(updateMeter);
      };
      updateMeter();
    } catch {
      // Audio level meter is decorative; ignore failure if AudioContext is unsupported
    }
    return stream;
  };

  const stopMedia = useCallback(() => {
    if (animFrameIdRef.current) cancelAnimationFrame(animFrameIdRef.current);
    if (audioContextRef.current) audioContextRef.current.close().catch(() => {});
    if (mediaStreamRef.current) {
      mediaStreamRef.current.getTracks().forEach((t) => t.stop());
      mediaStreamRef.current = null;
    }
    setPermission("idle");
    setVolumeLevel(0);
  }, []);

  // Attach live video preview
  useEffect(() => {
    if (videoPreviewRef.current && mediaStreamRef.current) {
      videoPreviewRef.current.srcObject = mediaStreamRef.current;
    }
  }, [permission, modalPhase]);

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      stopMedia();
      if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
    };
  }, [stopMedia]);

  // Execute Recording
  const startVerificationProcess = async () => {
    let stream = mediaStreamRef.current;
    if (!stream || !stream.active || permission !== "granted") {
      stream = await initMedia();
    }
    if (!stream) return;

    const currentSession = sessionRef.current || (await fetchNewSession());
    if (!currentSession) return;

    recordedChunksRef.current = [];
    setElapsedSeconds(0);
    setModalPhase("RECORDING");
    setIsRecording(true);

    try {
      const mimeType = "video/webm;codecs=vp8,opus";
      const recorder = new MediaRecorder(stream, {
        mimeType: MediaRecorder.isTypeSupported(mimeType) ? mimeType : "video/webm",
        videoBitsPerSecond: 2_500_000,
      });

      recorder.ondataavailable = (e) => {
        if (e.data && e.data.size > 0) recordedChunksRef.current.push(e.data);
      };

      recorder.onstop = () => {
        const blob = new Blob(recordedChunksRef.current, { type: "video/webm" });
        submitToBackend(blob, currentSession);
      };

      recordStartTimeRef.current = Date.now();
      recorder.start(100);
      mediaRecorderRef.current = recorder;

      // Master 100ms clock
      timerIntervalRef.current = setInterval(() => {
        const elapsed = (Date.now() - recordStartTimeRef.current) / 1000;
        setElapsedSeconds(Number(elapsed.toFixed(1)));

        if (elapsed >= TOTAL_SECONDS) {
          if (timerIntervalRef.current) clearInterval(timerIntervalRef.current);
          recorder.stop();
          setIsRecording(false);
        }
      }, 100);
    } catch (err: any) {
      setModalPhase("INTRO");
      setSessionError(`Recorder initialization failed: ${err.message}`);
    }
  };

  // Submit Video & Poll Backend Verification
  const submitToBackend = async (blob: Blob, currentSession: SessionChallenge) => {
    setModalPhase("ANALYZING");
    setAnalysisError(null);
    setAnalysisProgress(15);
    setCompletedAnalysisSteps([0]); // Step 0: Upload complete

    // Progressive step animation timer
    const progressTimer = setInterval(() => {
      setAnalysisProgress((prev) => {
        const next = Math.min(prev + (prev < 50 ? 2.8 : prev < 80 ? 1.6 : 0.5), 94);
        if (next >= 35) setCompletedAnalysisSteps((s) => (s.includes(1) ? s : [...s, 1]));
        if (next >= 60) setCompletedAnalysisSteps((s) => (s.includes(2) ? s : [...s, 2]));
        if (next >= 82) setCompletedAnalysisSteps((s) => (s.includes(3) ? s : [...s, 3]));
        return next;
      });
    }, 180);

    try {
      const form = new FormData();
      form.append("token", currentSession.token);
      form.append("media", blob, "recording.webm");

      const submitRes = await fetch(`${API_BASE}/sessions/${currentSession.session_id}/submit`, {
        method: "POST",
        body: form,
      });

      if (!submitRes.ok) {
        const errJson = await submitRes.json().catch(() => null);
        throw new Error(errJson?.detail || `Upload rejected (${submitRes.status})`);
      }

      // Poll results every 1.2s (max 60 attempts = 72s)
      for (let i = 0; i < 60; i++) {
        await new Promise((r) => setTimeout(r, 1200));
        const res = await fetch(`${API_BASE}/sessions/${currentSession.session_id}`);
        if (!res.ok) continue;

        const data: SessionResult = await res.json();
        if (data.status !== "PROCESSING") {
          clearInterval(progressTimer);
          setAnalysisProgress(100);
          setCompletedAnalysisSteps([0, 1, 2, 3, 4]);

          // Smooth brief pause at 100% so the user sees completion before results reveal
          await new Promise((r) => setTimeout(r, 450));

          setSessionResult(data);
          setModalPhase("RESULT");
          if (data.status === "VERIFIED") {
            setIsSiteUnlocked(true);
            stopMedia();
          }
          return;
        }
      }
      throw new Error("Verification timed out waiting for backend models.");
    } catch (err: any) {
      clearInterval(progressTimer);
      let friendly = err.message || "Failed to complete verification.";
      if (typeof navigator !== "undefined" && !navigator.onLine) {
        friendly = "Network connection lost. Please check your internet connection.";
      } else if (err.message && (err.message.includes("Failed to fetch") || err.message.includes("NetworkError"))) {
        friendly = "Bad connection: Failed to reach the verification server during upload.";
      }
      setAnalysisError(friendly);
      setModalPhase("RESULT");
    }
  };

  // Computed Step State during 13s Recording
  const currentStep =
    elapsedSeconds < SCAN_SECONDS ? "SCAN" : elapsedSeconds < SCAN_SECONDS + SPEAK_SECONDS ? "SPEAK" : "ACT";

  const challengeWords = session?.challenge.verbal ? session.challenge.verbal.split(/\s+/).filter(Boolean) : [];
  const actionInfo = session?.challenge.visual ? VISUAL_ACTIONS[session.challenge.visual] : null;
  const ActionIcon = actionInfo?.icon || Sparkles;

  return (
    <div style={{ minHeight: "100vh", position: "relative" }}>
      {/* =========================================================================
          BACKGROUND MOCK HOMEPAGE (Protected Portal Showcase)
      ========================================================================= */}
      <div
        style={{
          filter: !isSiteUnlocked && isModalOpen ? "blur(8px) brightness(0.6)" : "none",
          transition: "filter 0.5s ease",
          pointerEvents: !isSiteUnlocked && isModalOpen ? "none" : "auto",
        }}
      >
        {/* Navigation Bar */}
        <nav
          style={{
            borderBottom: "1px solid var(--border-color)",
            padding: "1.2rem 2.5rem",
            display: "flex",
            alignItems: "center",
            justifyContent: "space-between",
            background: "rgba(10, 14, 23, 0.9)",
            backdropFilter: "blur(12px)",
          }}
        >
          <div style={{ display: "flex", alignItems: "center", gap: "0.85rem" }}>
            <div
              style={{
                width: "36px",
                height: "36px",
                borderRadius: "8px",
                background: "linear-gradient(135deg, #06b6d4, #6366f1)",
                display: "flex",
                alignItems: "center",
                justifyContent: "center",
              }}
            >
              <ShieldCheck color="#fff" size={20} />
            </div>
            <div>
              <span style={{ fontWeight: 800, fontSize: "1.2rem", letterSpacing: "-0.02em" }}>APEX VAULT</span>
              <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", display: "block" }}>Enterprise Portal</span>
            </div>
          </div>

          <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
            {isSiteUnlocked ? (
              <span className="badge badge-verified">
                <CheckCircle2 size={14} /> Biometrics Verified
              </span>
            ) : (
              <span className="badge badge-failed">
                <Lock size={14} /> Access Locked
              </span>
            )}
            <button
              className="btn-secondary"
              onClick={() => {
                fetchNewSession();
                setModalPhase("INTRO");
                setIsModalOpen(true);
              }}
              style={{ fontSize: "0.85rem", padding: "0.5rem 1rem" }}
            >
              {isSiteUnlocked ? "Test Re-Verify" : "Open Verification"}
            </button>
          </div>
        </nav>

        {/* Dashboard Content */}
        <main style={{ maxWidth: "1200px", margin: "2.5rem auto", padding: "0 2rem" }}>
          {isSiteUnlocked ? (
            <div
              className="card card-glass"
              style={{
                marginBottom: "2rem",
                borderColor: "rgba(16, 185, 129, 0.4)",
                background: "linear-gradient(135deg, rgba(16, 185, 129, 0.08), rgba(6, 182, 212, 0.05))",
                padding: "1.75rem 2rem",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                <div
                  style={{
                    background: "rgba(16, 185, 129, 0.2)",
                    borderRadius: "50%",
                    padding: "0.75rem",
                    display: "flex",
                  }}
                >
                  <Unlock color="var(--accent-emerald)" size={28} />
                </div>
                <div>
                  <h2 style={{ fontSize: "1.4rem", fontWeight: 700, color: "var(--accent-emerald)" }}>
                    Identity Authenticated — Access Granted
                  </h2>
                  <p style={{ color: "var(--text-secondary)", marginTop: "0.2rem" }}>
                    Multimodal liveness, speech fidelity, and anti-spoof checks passed successfully. Welcome to your
                    secure dashboard.
                  </p>
                </div>
              </div>
            </div>
          ) : (
            <div
              className="card"
              style={{
                marginBottom: "2rem",
                borderColor: "rgba(244, 63, 94, 0.3)",
                background: "linear-gradient(135deg, rgba(244, 63, 94, 0.06), rgba(245, 158, 11, 0.04))",
                padding: "1.75rem 2rem",
              }}
            >
              <div style={{ display: "flex", alignItems: "center", gap: "1rem" }}>
                <Lock color="var(--accent-rose)" size={26} />
                <div>
                  <h3 style={{ fontSize: "1.1rem", fontWeight: 600 }}>Zero-Trust Biometric Gate Active</h3>
                  <p style={{ color: "var(--text-muted)", fontSize: "0.9rem" }}>
                    This portal requires proof-of-presence verification against live deepfakes and media replay before
                    unlocking.
                  </p>
                </div>
              </div>
            </div>
          )}

          {/* Metrics Grid */}
          <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "1.5rem" }}>
            <div className="card">
              <span style={{ fontSize: "0.85rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Security Level</span>
              <p style={{ fontSize: "1.8rem", fontWeight: 800, marginTop: "0.5rem" }}>Tier 4 Multimodal</p>
              <span style={{ color: "var(--accent-cyan)", fontSize: "0.85rem", marginTop: "0.5rem", display: "block" }}>
                VAD + Whisper + MediaPipe + OpenCV FFT
              </span>
            </div>
            <div className="card">
              <span style={{ fontSize: "0.85rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Identity Token</span>
              <p style={{ fontSize: "1.2rem", fontFamily: "JetBrains Mono", fontWeight: 600, marginTop: "0.5rem" }}>
                {session ? `${session.session_id.slice(0, 16)}...` : "Awaiting Gate..."}
              </p>
              <span style={{ color: "var(--accent-emerald)", fontSize: "0.85rem", marginTop: "0.5rem", display: "block" }}>
                HMAC-SHA256 Signed
              </span>
            </div>
            <div className="card">
              <span style={{ fontSize: "0.85rem", color: "var(--text-muted)", textTransform: "uppercase" }}>Local Inference</span>
              <p style={{ fontSize: "1.8rem", fontWeight: 800, marginTop: "0.5rem" }}>100% CPU Only</p>
              <span style={{ color: "var(--text-secondary)", fontSize: "0.85rem", marginTop: "0.5rem", display: "block" }}>
                Zero Cloud Biometrics Storage
              </span>
            </div>
          </div>
        </main>
      </div>

      {/* =========================================================================
          VERIFICATION MODAL POP-UP (The Verification Window)
      ========================================================================= */}
      {isModalOpen && (
        <div className="modal-overlay">
          <div className="modal-content" style={{ padding: "2rem" }}>
            {/* Modal Header */}
            <div
              style={{
                display: "flex",
                justifyContent: "space-between",
                alignItems: "flex-start",
                marginBottom: "1.5rem",
              }}
            >
              <div>
                <div style={{ display: "flex", alignItems: "center", gap: "0.5rem" }}>
                  <span className="badge badge-info">Unleash Verification</span>
                  <span style={{ fontSize: "0.75rem", color: "var(--text-muted)", fontFamily: "JetBrains Mono" }}>
                    v1.0 Demo
                  </span>
                </div>
                <h2 style={{ fontSize: "1.5rem", fontWeight: 700, marginTop: "0.4rem" }}>
                  Human Identity Verification
                </h2>
              </div>
              {isSiteUnlocked && (
                <button
                  onClick={() => setIsModalOpen(false)}
                  style={{
                    background: "none",
                    border: "none",
                    color: "var(--text-muted)",
                    cursor: "pointer",
                    fontSize: "1.2rem",
                  }}
                >
                  ✕
                </button>
              )}
            </div>

            {/* Error Banner */}
            {sessionError && (
              <div
                style={{
                  background: "rgba(244, 63, 94, 0.12)",
                  border: "1px solid rgba(244, 63, 94, 0.3)",
                  borderRadius: "10px",
                  padding: "0.85rem 1rem",
                  color: "#fca5a5",
                  marginBottom: "1.25rem",
                  fontSize: "0.85rem",
                }}
              >
                {sessionError}
              </div>
            )}

            {/* ---------------------------------------------------------------------
                PHASE 1: INTRO / BRIEFING SCREEN
            --------------------------------------------------------------------- */}
            {modalPhase === "INTRO" && (
              <div>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.95rem", lineHeight: "1.5" }}>
                  To ensure you are a live human in front of the camera, you will complete a <strong>13-second</strong> active
                  challenge. Please follow the instructions as they appear on screen:
                </p>

                {/* Bullet Points */}
                <div style={{ margin: "1.5rem 0", display: "flex", flexDirection: "column", gap: "0.85rem" }}>
                  <div
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: "0.85rem",
                      background: "rgba(255, 255, 255, 0.03)",
                      padding: "0.85rem 1rem",
                      borderRadius: "10px",
                    }}
                  >
                    <span style={{ fontWeight: 700, color: "var(--accent-cyan)", minWidth: "24px" }}>1.</span>
                    <div>
                      <strong style={{ display: "block", fontSize: "0.92rem" }}>First 3 Seconds — Passive Face Scan</strong>
                      <span style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
                        Face the camera naturally without moving. The system captures your baseline biometric geometry.
                      </span>
                    </div>
                  </div>

                  <div
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: "0.85rem",
                      background: "rgba(255, 255, 255, 0.03)",
                      padding: "0.85rem 1rem",
                      borderRadius: "10px",
                    }}
                  >
                    <span style={{ fontWeight: 700, color: "var(--accent-cyan)", minWidth: "24px" }}>2.</span>
                    <div>
                      <strong style={{ display: "block", fontSize: "0.92rem" }}>Next 5 Seconds — Verbal Challenge</strong>
                      <span style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
                        5 random challenge words will appear. Read them aloud facing the camera.
                      </span>
                    </div>
                  </div>

                  <div
                    style={{
                      display: "flex",
                      alignItems: "flex-start",
                      gap: "0.85rem",
                      background: "rgba(255, 255, 255, 0.03)",
                      padding: "0.85rem 1rem",
                      borderRadius: "10px",
                    }}
                  >
                    <span style={{ fontWeight: 700, color: "var(--accent-cyan)", minWidth: "24px" }}>3.</span>
                    <div>
                      <strong style={{ display: "block", fontSize: "0.92rem" }}>Final 5 Seconds — Active Gesture</strong>
                      <span style={{ color: "var(--text-muted)", fontSize: "0.85rem" }}>
                        The words will disappear and an action instruction will appear (head turn, look up/down, or blink).
                      </span>
                    </div>
                  </div>
                </div>

                {/* Permission Denied Warning (if any) */}
                {permissionError && (
                  <div
                    style={{
                      display: "flex",
                      alignItems: "center",
                      gap: "0.6rem",
                      padding: "0.75rem 1rem",
                      background: "rgba(244, 63, 94, 0.12)",
                      border: "1px solid rgba(244, 63, 94, 0.35)",
                      borderRadius: "10px",
                      marginBottom: "1.2rem",
                      color: "#fda4af",
                      fontSize: "0.85rem",
                    }}
                  >
                    <AlertCircle size={16} color="var(--accent-rose)" />
                    <span>{permissionError}</span>
                  </div>
                )}

                {/* Start Button */}
                <button
                  className="btn-primary"
                  onClick={startVerificationProcess}
                  disabled={loadingSession || !session || permission === "requesting"}
                  style={{ width: "100%", justifyContent: "center", padding: "1rem" }}
                >
                  {loadingSession || permission === "requesting" ? (
                    <RefreshCw className="spin" size={18} />
                  ) : (
                    <ShieldCheck size={18} />
                  )}
                  {permission === "requesting"
                    ? "Requesting Camera & Mic..."
                    : "Start 13-Second Verification"}
                </button>
              </div>
            )}

            {/* ---------------------------------------------------------------------
                PHASE 2: LIVE RECORDING (STRICT TIMING ENFORCEMENT)
            --------------------------------------------------------------------- */}
            {modalPhase === "RECORDING" && (
              <div>
                {/* Stage Indicators */}
                <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: "0.75rem" }}>
                  <div style={{ display: "flex", gap: "0.5rem" }}>
                    <span
                      style={{
                        padding: "0.25rem 0.6rem",
                        borderRadius: "6px",
                        fontSize: "0.75rem",
                        fontWeight: 600,
                        background: currentStep === "SCAN" ? "var(--accent-cyan)" : "var(--bg-card)",
                        color: currentStep === "SCAN" ? "#000" : "var(--text-muted)",
                      }}
                    >
                      1. Scan (3s)
                    </span>
                    <span
                      style={{
                        padding: "0.25rem 0.6rem",
                        borderRadius: "6px",
                        fontSize: "0.75rem",
                        fontWeight: 600,
                        background: currentStep === "SPEAK" ? "var(--accent-cyan)" : "var(--bg-card)",
                        color: currentStep === "SPEAK" ? "#000" : "var(--text-muted)",
                      }}
                    >
                      2. Speak (5s)
                    </span>
                    <span
                      style={{
                        padding: "0.25rem 0.6rem",
                        borderRadius: "6px",
                        fontSize: "0.75rem",
                        fontWeight: 600,
                        background: currentStep === "ACT" ? "var(--accent-cyan)" : "var(--bg-card)",
                        color: currentStep === "ACT" ? "#000" : "var(--text-muted)",
                      }}
                    >
                      3. Action (5s)
                    </span>
                  </div>

                  <span
                    style={{
                      fontFamily: "JetBrains Mono",
                      fontWeight: 700,
                      color: "var(--accent-cyan)",
                      fontSize: "0.95rem",
                    }}
                  >
                    ⏱️ {elapsedSeconds.toFixed(1)}s / {TOTAL_SECONDS}s
                  </span>
                </div>

                {/* Camera Viewport with Futuristic Corner Reticle */}
                <div className="camera-frame">
                  <video
                    ref={videoPreviewRef}
                    autoPlay
                    playsInline
                    muted
                    style={{
                      width: "100%",
                      height: "100%",
                      objectFit: "cover",
                      transform: "scaleX(-1)",
                    }}
                  />
                  <div className="camera-reticle" />

                  {/* Audio Volume Bar Overlay */}
                  <div
                    style={{
                      position: "absolute",
                      bottom: "12px",
                      left: "16px",
                      right: "16px",
                      display: "flex",
                      alignItems: "center",
                      gap: "0.5rem",
                      background: "rgba(0, 0, 0, 0.6)",
                      padding: "0.35rem 0.75rem",
                      borderRadius: "9999px",
                      zIndex: 20,
                    }}
                  >
                    <Mic size={14} color="var(--accent-cyan)" />
                    <div style={{ flex: 1, height: "6px", background: "rgba(255, 255, 255, 0.2)", borderRadius: "3px", overflow: "hidden" }}>
                      <div
                        style={{
                          height: "100%",
                          width: `${volumeLevel}%`,
                          background: volumeLevel > 15 ? "var(--accent-emerald)" : "var(--accent-cyan)",
                          transition: "width 0.05s ease-out",
                        }}
                      />
                    </div>
                  </div>
                </div>

                {/* Progress Bar Across 13 Seconds */}
                <div className="step-bar-container">
                  <div
                    className="step-bar-segment"
                    style={{
                      width: `${Math.min(100, (elapsedSeconds / TOTAL_SECONDS) * 100)}%`,
                      background:
                        currentStep === "SCAN"
                          ? "var(--accent-cyan)"
                          : currentStep === "SPEAK"
                          ? "var(--accent-blue)"
                          : "var(--accent-indigo)",
                    }}
                  />
                </div>

                {/* DYNAMIC PROMPT BOX STRICTLY FOLLOWING THE 3 STEPS */}
                <div style={{ marginTop: "1.25rem", minHeight: "110px", display: "flex", flexDirection: "column", justifyContent: "center" }}>
                  {/* STEP 1: 0s - 3s (Neutral Face Scan) */}
                  {currentStep === "SCAN" && (
                    <div style={{ textAlign: "center", animation: "fadeIn 0.25s ease" }}>
                      <span className="badge badge-info" style={{ marginBottom: "0.5rem" }}>
                        Step 1 · Neutral Face Scan
                      </span>
                      <h3 style={{ fontSize: "1.25rem", fontWeight: 700 }}>Face the camera naturally</h3>
                      <p style={{ color: "var(--text-muted)", fontSize: "0.85rem", marginTop: "0.25rem" }}>
                        Looking straight ahead. Calibrating facial landmarks & ambient lighting...
                      </p>
                    </div>
                  )}

                  {/* STEP 2: 3s - 8s (Verbal Challenge) */}
                  {currentStep === "SPEAK" && (
                    <div style={{ textAlign: "center", animation: "fadeIn 0.25s ease" }}>
                      <span className="badge badge-info" style={{ marginBottom: "0.5rem", background: "rgba(245, 158, 11, 0.15)", color: "var(--accent-amber)", borderColor: "rgba(245, 158, 11, 0.3)" }}>
                        Step 2 · Say the 5 Words Aloud
                      </span>
                      <div style={{ display: "flex", justifyContent: "center", gap: "0.5rem", flexWrap: "wrap", marginTop: "0.5rem" }}>
                        {challengeWords.map((word, i) => (
                          <span key={i} className="word-pill">
                            {word}
                          </span>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* STEP 3: 8s - 13s (Active Gesture) */}
                  {currentStep === "ACT" && (
                    <div style={{ textAlign: "center", animation: "fadeIn 0.25s ease" }}>
                      <span className="badge badge-info" style={{ marginBottom: "0.5rem", background: "rgba(99, 102, 241, 0.15)", color: "var(--accent-indigo)", borderColor: "rgba(99, 102, 241, 0.3)" }}>
                        Step 3 · Perform Visual Gesture
                      </span>
                      <div className="action-box" style={{ display: "inline-flex", alignItems: "center", gap: "0.75rem", margin: "0 auto" }}>
                        <ActionIcon size={28} color="var(--accent-cyan)" />
                        <span style={{ fontSize: "1.25rem", fontWeight: 800 }}>{actionInfo?.text}</span>
                      </div>
                    </div>
                  )}
                </div>
              </div>
            )}

            {/* ---------------------------------------------------------------------
                PHASE 3: ANALYZING & POLLING
            --------------------------------------------------------------------- */}
            {modalPhase === "ANALYZING" && (
              <div style={{ textAlign: "center", padding: "2.5rem 1rem" }}>
                {/* Radial Spinner with Percentage */}
                <div style={{ position: "relative", width: "88px", height: "88px", margin: "0 auto 1.5rem" }}>
                  <div
                    style={{
                      width: "100%",
                      height: "100%",
                      borderRadius: "50%",
                      border: "3px solid rgba(255, 255, 255, 0.08)",
                      borderTopColor: "var(--accent-cyan)",
                      borderRightColor: "var(--accent-emerald)",
                      animation: "spin 1.2s linear infinite",
                    }}
                  />
                  <div
                    style={{
                      position: "absolute",
                      inset: 0,
                      display: "flex",
                      alignItems: "center",
                      justifyContent: "center",
                      fontFamily: "JetBrains Mono, monospace",
                      fontSize: "1.05rem",
                      fontWeight: 700,
                      color: "var(--accent-cyan)",
                    }}
                  >
                    {Math.round(analysisProgress)}%
                  </div>
                </div>

                <h3 style={{ fontSize: "1.35rem", fontWeight: 700 }}>Processing Multimodal Biometrics</h3>
                <p style={{ color: "var(--text-secondary)", fontSize: "0.9rem", marginTop: "0.35rem" }}>
                  Running local AI models across audio, pose, replay, and deepfake signals...
                </p>

                {/* Progress Bar */}
                <div style={{ maxWidth: "380px", margin: "1.5rem auto 1.2rem" }}>
                  <div style={{ display: "flex", justifyContent: "space-between", marginBottom: "0.45rem", fontSize: "0.78rem", color: "var(--text-muted)" }}>
                    <span>Pipeline Progress</span>
                    <span style={{ color: "var(--accent-cyan)", fontWeight: 700, fontFamily: "JetBrains Mono, monospace" }}>
                      {Math.round(analysisProgress)}%
                    </span>
                  </div>
                  <div style={{ height: "6px", background: "rgba(255, 255, 255, 0.08)", borderRadius: "999px", overflow: "hidden" }}>
                    <div
                      style={{
                        height: "100%",
                        width: `${analysisProgress}%`,
                        background: "linear-gradient(90deg, #06b6d4, #10b981)",
                        borderRadius: "999px",
                        transition: "width 0.25s ease",
                        boxShadow: "0 0 12px rgba(6, 182, 212, 0.4)",
                      }}
                    />
                  </div>
                </div>

                {/* Dynamic Checklist */}
                <div style={{ maxWidth: "380px", margin: "1.2rem auto 0", textAlign: "left", display: "flex", flexDirection: "column", gap: "0.5rem" }}>
                  {ANALYSIS_CHECKLIST.map((step, idx) => {
                    const isDone = completedAnalysisSteps.includes(idx);
                    const isCurrent = !isDone && completedAnalysisSteps.length === idx;
                    return (
                      <div
                        key={idx}
                        style={{
                          display: "flex",
                          alignItems: "center",
                          justifyContent: "space-between",
                          padding: "0.55rem 0.85rem",
                          borderRadius: "10px",
                          background: isCurrent ? "rgba(6, 182, 212, 0.08)" : isDone ? "rgba(16, 185, 129, 0.04)" : "rgba(255, 255, 255, 0.02)",
                          border: isCurrent ? "1px solid rgba(6, 182, 212, 0.25)" : "1px solid transparent",
                          transition: "all 0.3s ease",
                        }}
                      >
                        <div style={{ display: "flex", alignItems: "center", gap: "0.65rem" }}>
                          {isDone ? (
                            <CheckCircle2 size={16} color="var(--accent-emerald)" />
                          ) : isCurrent ? (
                            <RefreshCw size={14} className="spin" color="var(--accent-cyan)" />
                          ) : (
                            <div style={{ width: "14px", height: "14px", borderRadius: "50%", border: "2px solid rgba(255,255,255,0.2)" }} />
                          )}
                          <div>
                            <span
                              style={{
                                display: "block",
                                fontSize: "0.85rem",
                                color: isDone ? "#fff" : isCurrent ? "var(--accent-cyan)" : "var(--text-muted)",
                                fontWeight: isCurrent ? 600 : 400,
                              }}
                            >
                              {step.label}
                            </span>
                            <span style={{ display: "block", fontSize: "0.72rem", color: "var(--text-muted)" }}>
                              {step.sub}
                            </span>
                          </div>
                        </div>
                        <span
                          style={{
                            fontSize: "0.72rem",
                            fontWeight: 600,
                            color: isDone ? "var(--accent-emerald)" : isCurrent ? "var(--accent-cyan)" : "rgba(255, 255, 255, 0.25)",
                          }}
                        >
                          {isDone ? "✓ Done" : isCurrent ? "Running..." : "Queued"}
                        </span>
                      </div>
                    );
                  })}
                </div>
              </div>
            )}

            {/* ---------------------------------------------------------------------
                PHASE 4: RESULTS & SCORES BREAKDOWN
            --------------------------------------------------------------------- */}
            {modalPhase === "RESULT" && sessionResult && (
              <div>
                {/* Verdict Card */}
                <div
                  className="card"
                  style={{
                    textAlign: "center",
                    padding: "1.5rem",
                    marginBottom: "1.5rem",
                    borderColor:
                      sessionResult.status === "VERIFIED"
                        ? "rgba(16, 185, 129, 0.4)"
                        : sessionResult.status === "SUSPICIOUS"
                        ? "rgba(245, 158, 11, 0.4)"
                        : "rgba(244, 63, 94, 0.4)",
                    background:
                      sessionResult.status === "VERIFIED"
                        ? "linear-gradient(135deg, rgba(16, 185, 129, 0.12), rgba(6, 182, 212, 0.05))"
                        : sessionResult.status === "SUSPICIOUS"
                        ? "linear-gradient(135deg, rgba(245, 158, 11, 0.12), rgba(244, 63, 94, 0.05))"
                        : "linear-gradient(135deg, rgba(244, 63, 94, 0.12), rgba(244, 63, 94, 0.05))",
                  }}
                >
                  <div style={{ marginBottom: "0.5rem" }}>
                    {sessionResult.status === "VERIFIED" && <ShieldCheck size={44} color="var(--accent-emerald)" />}
                    {sessionResult.status === "SUSPICIOUS" && <AlertTriangle size={44} color="var(--accent-amber)" />}
                    {sessionResult.status === "FAILED" && <ShieldAlert size={44} color="var(--accent-rose)" />}
                  </div>

                  <span
                    className={
                      sessionResult.status === "VERIFIED"
                        ? "badge badge-verified"
                        : sessionResult.status === "SUSPICIOUS"
                        ? "badge badge-suspicious"
                        : "badge badge-failed"
                    }
                    style={{ fontSize: "0.95rem", padding: "0.4rem 1rem" }}
                  >
                    VERDICT: {sessionResult.status}
                  </span>

                  <p style={{ marginTop: "0.75rem", fontSize: "0.95rem", color: "var(--text-primary)" }}>
                    {sessionResult.decision_reason || "Verification analysis complete."}
                  </p>
                  {sessionResult.confidence !== null && (
                    <span style={{ fontSize: "0.85rem", color: "var(--text-muted)", display: "block", marginTop: "0.25rem" }}>
                      Overall Confidence: {(sessionResult.confidence * 100).toFixed(0)}%
                    </span>
                  )}
                </div>

                {/* Per-Module Scores Breakdown */}
                <h4 style={{ fontSize: "0.9rem", color: "var(--text-muted)", textTransform: "uppercase", letterSpacing: "0.06em", marginBottom: "0.75rem" }}>
                  Detector Module Telemetry
                </h4>

                <div className="scores-grid" style={{ marginBottom: "1.5rem" }}>
                  {/* 1. Speech Gate & Phrase Check */}
                  <div className="score-card">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontWeight: 600, fontSize: "0.88rem" }}>Audio Pipeline</span>
                      {sessionResult.signals?.audio_pipeline?.passed ? (
                        <span className="badge badge-verified" style={{ fontSize: "0.7rem", padding: "0.2rem 0.5rem" }}>PASS</span>
                      ) : (
                        <span className="badge badge-failed" style={{ fontSize: "0.7rem", padding: "0.2rem 0.5rem" }}>FAIL</span>
                      )}
                    </div>
                    <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                      {sessionResult.signals?.audio_pipeline?.reason || "Speech & 5-word challenge"}
                    </span>
                  </div>

                  {/* 2. Visual Challenge */}
                  <div className="score-card">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontWeight: 600, fontSize: "0.88rem" }}>Visual Challenge</span>
                      {sessionResult.signals?.visual_challenge?.passed ? (
                        <span className="badge badge-verified" style={{ fontSize: "0.7rem", padding: "0.2rem 0.5rem" }}>PASS</span>
                      ) : (
                        <span className="badge badge-failed" style={{ fontSize: "0.7rem", padding: "0.2rem 0.5rem" }}>FAIL</span>
                      )}
                    </div>
                    <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                      {sessionResult.signals?.visual_challenge?.reason || "Head angle / blink compliance"}
                    </span>
                  </div>

                  {/* 3. Visual Liveness */}
                  <div className="score-card">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontWeight: 600, fontSize: "0.88rem" }}>Passive Liveness</span>
                      <span style={{ fontFamily: "JetBrains Mono", fontSize: "0.85rem", color: "var(--accent-cyan)" }}>
                        {sessionResult.signals?.visual_liveness?.score !== null
                          ? `${(sessionResult.signals!.visual_liveness.score! * 100).toFixed(0)}%`
                          : "—"}
                      </span>
                    </div>
                    <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                      {sessionResult.signals?.visual_liveness?.reason || "EAR variance & micro-movements"}
                    </span>
                  </div>

                  {/* 4. Replay Detection */}
                  <div className="score-card">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontWeight: 600, fontSize: "0.88rem" }}>Replay Defense</span>
                      <span style={{ fontFamily: "JetBrains Mono", fontSize: "0.85rem", color: "var(--accent-cyan)" }}>
                        {sessionResult.signals?.replay?.score !== null
                          ? `${(sessionResult.signals!.replay.score! * 100).toFixed(0)}%`
                          : "—"}
                      </span>
                    </div>
                    <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                      {sessionResult.signals?.replay?.reason || "FFT moiré & temporal noise"}
                    </span>
                  </div>

                  {/* 5. Deepfake Classifier */}
                  <div className="score-card">
                    <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
                      <span style={{ fontWeight: 600, fontSize: "0.88rem" }}>Deepfake Model</span>
                      <span style={{ fontFamily: "JetBrains Mono", fontSize: "0.85rem", color: "var(--text-secondary)" }}>
                        {sessionResult.signals?.deepfake?.score !== null
                          ? `${(sessionResult.signals!.deepfake.score! * 100).toFixed(0)}%`
                          : "Advisory"}
                      </span>
                    </div>
                    <span style={{ fontSize: "0.78rem", color: "var(--text-muted)" }}>
                      {sessionResult.signals?.deepfake?.reason || "Xception neural classifier"}
                    </span>
                  </div>
                </div>

                {/* Footer Action Buttons */}
                <div style={{ display: "flex", gap: "1rem" }}>
                  {sessionResult.status === "VERIFIED" ? (
                    <button
                      className="btn-primary"
                      onClick={() => {
                        stopMedia();
                        setIsModalOpen(false);
                      }}
                      style={{ flex: 1, justifyContent: "center" }}
                    >
                      <Unlock size={18} /> Enter Protected Website
                    </button>
                  ) : (
                    <button
                      className="btn-primary"
                      onClick={() => {
                        fetchNewSession();
                        setModalPhase("INTRO");
                      }}
                      style={{ flex: 1, justifyContent: "center" }}
                    >
                      <RefreshCw size={18} /> Try Verification Again
                    </button>
                  )}
                  <button
                    className="btn-secondary"
                    onClick={() => {
                      fetchNewSession();
                      setModalPhase("INTRO");
                    }}
                    style={{ padding: "0.75rem 1rem" }}
                  >
                    Reset
                  </button>
                </div>
              </div>
            )}

            {/* Error in Phase 4 (if any) */}
            {modalPhase === "RESULT" && !sessionResult && analysisError && (
              <div style={{ textAlign: "center", padding: "1.5rem" }}>
                <ShieldX size={44} color="var(--accent-rose)" style={{ margin: "0 auto 1rem" }} />
                <h3 style={{ fontSize: "1.2rem", fontWeight: 700 }}>Analysis Request Error</h3>
                <p style={{ color: "var(--text-muted)", margin: "0.5rem 0 1.5rem", fontSize: "0.9rem" }}>
                  {analysisError}
                </p>
                <button
                  className="btn-primary"
                  onClick={() => {
                    fetchNewSession();
                    setModalPhase("INTRO");
                  }}
                  style={{ width: "100%", justifyContent: "center" }}
                >
                  <RefreshCw size={18} /> Retry Challenge
                </button>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
