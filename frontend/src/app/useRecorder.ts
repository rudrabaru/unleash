"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type Access = "idle" | "requesting" | "ready" | "error";

// One WebM file with video and audio: the backend splits the tracks itself. VP8 + Opus first (what the
// analysis was built and measured on), then the other WebM variants Chromium and Firefox offer.
const MIME_CANDIDATES = ["video/webm;codecs=vp8,opus", "video/webm;codecs=vp9,opus", "video/webm"];
const VIDEO_BITS_PER_SECOND = 2_500_000;

const UNSUPPORTED_BROWSER =
  "This browser cannot record the video this check needs. Please use a recent Chrome, Edge or Firefox on a computer.";
const INSECURE_ORIGIN = "The camera needs a secure connection. Open this page over https (or from localhost).";

function pickMimeType(): string | null {
  if (typeof MediaRecorder === "undefined") return null;
  return MIME_CANDIDATES.find((type) => MediaRecorder.isTypeSupported(type)) ?? null;
}

// The browser only says "device in use"; try each device alone to say which one is busy.
async function findBusyDevices(): Promise<string> {
  const busy: string[] = [];
  for (const [label, constraints] of [
    ["The camera", { video: true }],
    ["The microphone", { audio: true }],
  ] as [string, MediaStreamConstraints][]) {
    try {
      const probe = await navigator.mediaDevices.getUserMedia(constraints);
      probe.getTracks().forEach((track) => track.stop());
    } catch {
      busy.push(label);
    }
  }
  return busy.length ? busy.join(" and ") : "The camera or microphone";
}

async function describeAccessError(err: any): Promise<string> {
  if (err?.name === "NotReadableError" || err?.name === "TrackStartError") {
    const busy = await findBusyDevices();
    return `${busy} is in use by another program or browser tab. Close it and try again.`;
  }
  if (err?.name === "NotAllowedError" || err?.name === "PermissionDeniedError") {
    return "Camera or microphone access was denied. Allow both in your browser address bar and try again.";
  }
  if (err?.name === "NotFoundError" || err?.name === "DevicesNotFoundError") {
    return "No camera or microphone was detected on this computer.";
  }
  if (err?.name === "OverconstrainedError") {
    return "The selected camera cannot provide the picture this check needs. Choose another camera.";
  }
  return `Camera or microphone error: ${err?.message || err?.name || "unknown"}`;
}

export function useRecorder() {
  const [access, setAccess] = useState<Access>("idle");
  const [error, setError] = useState<string | null>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [cameras, setCameras] = useState<MediaDeviceInfo[]>([]);
  const [cameraId, setCameraId] = useState("");
  const [level, setLevel] = useState(0); // microphone level, 0-100
  const [brightness, setBrightness] = useState<number | null>(null); // mean picture brightness, 0-255
  const [recording, setRecording] = useState(false);
  const [faulted, setFaulted] = useState(false); // the recording broke off (camera lost, recorder error)
  const [elapsed, setElapsed] = useState(0);

  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const meterTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const mimeRef = useRef<string>(MIME_CANDIDATES[0]);
  const chunksRef = useRef<Blob[]>([]);
  const clockRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startedAtRef = useRef(0);
  // Each open() takes a number; a slower, older request that finishes after a newer one is discarded.
  const openRequestRef = useRef(0);

  const stopMeters = useCallback(() => {
    if (meterTimerRef.current) clearInterval(meterTimerRef.current);
    meterTimerRef.current = null;
    audioContextRef.current?.close().catch(() => {});
    audioContextRef.current = null;
    setLevel(0);
    setBrightness(null);
  }, []);

  const startMeters = useCallback((media: MediaStream) => {
    const AudioCtx = window.AudioContext || (window as any).webkitAudioContext;
    const context = new AudioCtx();
    audioContextRef.current = context;
    const analyser = context.createAnalyser();
    analyser.fftSize = 1024;
    context.createMediaStreamSource(media).connect(analyser);
    const samples = new Uint8Array(analyser.fftSize);

    // A hidden video element and a tiny canvas give the picture brightness
    const probe = document.createElement("video");
    probe.muted = true;
    probe.playsInline = true;
    probe.srcObject = media;
    probe.play().catch(() => {});
    const canvas = document.createElement("canvas");
    canvas.width = 32;
    canvas.height = 18;
    const drawing = canvas.getContext("2d", { willReadFrequently: true });

    let tick = 0;
    meterTimerRef.current = setInterval(() => {
      analyser.getByteTimeDomainData(samples);
      let sum = 0;
      for (let i = 0; i < samples.length; i++) sum += ((samples[i] - 128) / 128) ** 2;
      setLevel(Math.min(100, Math.round(Math.sqrt(sum / samples.length) * 400)));

      if (drawing && probe.videoWidth > 0 && tick++ % 5 === 0) {
        drawing.drawImage(probe, 0, 0, canvas.width, canvas.height);
        const pixels = drawing.getImageData(0, 0, canvas.width, canvas.height).data;
        let total = 0;
        for (let i = 0; i < pixels.length; i += 4) total += 0.2126 * pixels[i] + 0.7152 * pixels[i + 1] + 0.0722 * pixels[i + 2];
        setBrightness(Math.round(total / (pixels.length / 4)));
      }
    }, 100);
  }, []);

  const stopClock = useCallback(() => {
    if (clockRef.current) clearInterval(clockRef.current);
    clockRef.current = null;
  }, []);

  const close = useCallback(() => {
    openRequestRef.current++; // an open() still waiting for the camera must not keep what it gets
    stopClock();
    const recorder = recorderRef.current;
    if (recorder && recorder.state !== "inactive") {
      recorder.onstop = null;
      recorder.stop();
    }
    recorderRef.current = null;
    stopMeters();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setStream(null);
    setRecording(false);
    setAccess("idle");
  }, [stopClock, stopMeters]);

  // A recording that breaks off (the camera is unplugged, the recorder errors) is thrown away, not uploaded half-made.
  const fault = useCallback(
    (message: string) => {
      stopClock();
      const recorder = recorderRef.current;
      if (recorder && recorder.state !== "inactive") {
        recorder.onstop = null;
        recorder.stop();
      }
      recorderRef.current = null;
      chunksRef.current = [];
      setRecording(false);
      setFaulted(true);
      setError(message);
    },
    [stopClock],
  );

  const open = useCallback(
    async (deviceId?: string) => {
      close();
      const attempt = openRequestRef.current;
      setAccess("requesting");
      setError(null);
      setFaulted(false);
      if (!pickMimeType()) {
        setAccess("error");
        setError(UNSUPPORTED_BROWSER);
        return;
      }
      if (!navigator.mediaDevices?.getUserMedia) {
        setAccess("error");
        setError(INSECURE_ORIGIN);
        return;
      }
      try {
        const media = await navigator.mediaDevices.getUserMedia({
          audio: { echoCancellation: true, noiseSuppression: true },
          video: {
            width: { ideal: 1280 },
            height: { ideal: 720 },
            frameRate: { ideal: 30 },
            ...(deviceId ? { deviceId: { exact: deviceId } } : { facingMode: "user" }),
          },
        });
        if (attempt !== openRequestRef.current) {
          media.getTracks().forEach((track) => track.stop()); // superseded while waiting: do not keep the camera on
          return;
        }
        streamRef.current = media;
        media.getTracks().forEach((track) =>
          track.addEventListener("ended", () => {
            if (streamRef.current !== media) return;
            if (recorderRef.current) fault("The camera or microphone was disconnected during the recording. Please try again.");
            else {
              setAccess("error");
              setError("The camera or microphone was disconnected.");
            }
          }),
        );
        setStream(media);
        setAccess("ready");
        // Camera names are only available after access is granted
        const devices = await navigator.mediaDevices.enumerateDevices();
        if (attempt !== openRequestRef.current) return;
        setCameras(devices.filter((d) => d.kind === "videoinput"));
        setCameraId(media.getVideoTracks()[0]?.getSettings().deviceId ?? "");
        startMeters(media);
      } catch (err: any) {
        if (attempt !== openRequestRef.current) return;
        console.error("Camera or microphone capture failed:", err);
        streamRef.current?.getTracks().forEach((track) => track.stop());
        streamRef.current = null;
        setStream(null);
        setAccess("error");
        setError(await describeAccessError(err));
      }
    },
    [close, fault, startMeters],
  );

  // The clock starts when the recorder really starts (its `start` event), not when start() is called,
  // so the on-screen phases follow the recording and not the few milliseconds before it.
  const start = useCallback((): boolean => {
    const media = streamRef.current;
    const mimeType = pickMimeType();
    if (!media || !mimeType) return false;
    mimeRef.current = mimeType;
    chunksRef.current = [];
    setFaulted(false);
    const recorder = new MediaRecorder(media, { mimeType, videoBitsPerSecond: VIDEO_BITS_PER_SECOND });
    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) chunksRef.current.push(event.data);
    };
    recorder.onstart = () => {
      startedAtRef.current = performance.now();
      setElapsed(0);
      setRecording(true);
      clockRef.current = setInterval(() => setElapsed((performance.now() - startedAtRef.current) / 1000), 100);
    };
    recorder.onerror = () => fault("The recording stopped unexpectedly. Please try again.");
    recorderRef.current = recorder;
    recorder.start(100);
    return true;
  }, [fault]);

  const stop = useCallback((): Promise<Blob | null> => {
    const recorder = recorderRef.current;
    stopClock();
    setRecording(false);
    if (!recorder || recorder.state === "inactive") return Promise.resolve(null);
    return new Promise((resolve) => {
      recorder.onstop = () => resolve(new Blob(chunksRef.current, { type: mimeRef.current }));
      recorder.stop();
      recorderRef.current = null;
    });
  }, [stopClock]);

  useEffect(() => close, [close]);

  return { access, error, faulted, stream, cameras, cameraId, level, brightness, recording, elapsed, open, close, start, stop };
}

export type Recorder = ReturnType<typeof useRecorder>;
