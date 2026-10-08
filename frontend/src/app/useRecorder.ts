"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type Access = "idle" | "requesting" | "ready" | "error";

// One VP8 + Opus WebM file: the backend splits audio and video itself.
const MIME_TYPE = "video/webm;codecs=vp8,opus";
const VIDEO_BITS_PER_SECOND = 2_500_000;

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
    return `${busy} is in use by another program or browser tab. Close it (or stop and restart DroidCam) and try again.`;
  }
  if (err?.name === "NotAllowedError" || err?.name === "PermissionDeniedError") {
    return "Camera or microphone access was denied. Allow both in your browser address bar and try again.";
  }
  if (err?.name === "NotFoundError" || err?.name === "DevicesNotFoundError") {
    return "No camera or microphone was detected on this computer.";
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
  const [elapsed, setElapsed] = useState(0);

  const streamRef = useRef<MediaStream | null>(null);
  const audioContextRef = useRef<AudioContext | null>(null);
  const meterTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunksRef = useRef<Blob[]>([]);
  const clockRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const startedAtRef = useRef(0);

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

  const close = useCallback(() => {
    if (clockRef.current) clearInterval(clockRef.current);
    clockRef.current = null;
    if (recorderRef.current && recorderRef.current.state !== "inactive") recorderRef.current.stop();
    recorderRef.current = null;
    stopMeters();
    streamRef.current?.getTracks().forEach((track) => track.stop());
    streamRef.current = null;
    setStream(null);
    setRecording(false);
    setAccess("idle");
  }, [stopMeters]);

  const open = useCallback(
    async (deviceId?: string) => {
      close();
      setAccess("requesting");
      setError(null);
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
        streamRef.current = media;
        setStream(media);
        setAccess("ready");
        // Camera names are only available after access is granted
        const devices = await navigator.mediaDevices.enumerateDevices();
        setCameras(devices.filter((d) => d.kind === "videoinput"));
        setCameraId(media.getVideoTracks()[0]?.getSettings().deviceId ?? "");
        startMeters(media);
      } catch (err: any) {
        console.error("Camera or microphone capture failed:", err);
        setAccess("error");
        setError(await describeAccessError(err));
      }
    },
    [close, startMeters],
  );

  const start = useCallback((): boolean => {
    const media = streamRef.current;
    if (!media) return false;
    if (!MediaRecorder.isTypeSupported(MIME_TYPE)) {
      setError("This browser cannot record VP8 + Opus WebM. Use Chrome, Edge or Firefox.");
      return false;
    }
    chunksRef.current = [];
    const recorder = new MediaRecorder(media, { mimeType: MIME_TYPE, videoBitsPerSecond: VIDEO_BITS_PER_SECOND });
    recorder.ondataavailable = (event) => {
      if (event.data && event.data.size > 0) chunksRef.current.push(event.data);
    };
    startedAtRef.current = Date.now();
    recorder.start(100);
    recorderRef.current = recorder;
    setElapsed(0);
    setRecording(true);
    clockRef.current = setInterval(() => setElapsed((Date.now() - startedAtRef.current) / 1000), 100);
    return true;
  }, []);

  const stop = useCallback((): Promise<Blob | null> => {
    const recorder = recorderRef.current;
    if (clockRef.current) clearInterval(clockRef.current);
    clockRef.current = null;
    setRecording(false);
    if (!recorder || recorder.state === "inactive") return Promise.resolve(null);
    return new Promise((resolve) => {
      recorder.onstop = () => resolve(new Blob(chunksRef.current, { type: MIME_TYPE }));
      recorder.stop();
      recorderRef.current = null;
    });
  }, []);

  useEffect(() => close, [close]);

  return { access, error, stream, cameras, cameraId, level, brightness, recording, elapsed, open, close, start, stop };
}

export type Recorder = ReturnType<typeof useRecorder>;
