"use client";

import { useEffect, useState } from "react";

interface DetectorResult {
  score: number | null;
  passed: boolean;
  reason: string;
  error: string | null;
  details?: Record<string, any>;
}

interface SessionRecord {
  session_id: string;
  status: string;
  confidence: number | null;
  decision_reason: string;
  created_at: string;
  updated_at: string;
  signals?: Record<string, DetectorResult>;
}

export default function EvaluationDashboard() {
  const [sessions, setSessions] = useState<SessionRecord[]>([]);
  const [loading, setLoading] = useState<boolean>(true);
  const [error, setError] = useState<string | null>(null);

  const fetchSessions = async () => {
    setLoading(true);
    setError(null);
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";
      const res = await fetch(`${apiBase}/eval/sessions`);
      if (!res.ok) {
        throw new Error(`Failed to load sessions (${res.status}: ${res.statusText})`);
      }
      const data: SessionRecord[] = await res.json();
      setSessions(data);
    } catch (err: any) {
      setError(err.message || "Failed to connect to backend evaluation API");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchSessions();
  }, []);

  const formatScore = (score: number | null | undefined): string => {
    if (score === null || score === undefined) {
      return "not measured";
    }
    return score.toFixed(4);
  };

  const getStatusBadge = (status: string) => {
    switch (status.toUpperCase()) {
      case "VERIFIED":
        return <span className="px-2.5 py-1 rounded text-xs font-semibold bg-emerald-950 text-emerald-300 border border-emerald-700">VERIFIED</span>;
      case "SUSPICIOUS":
        return <span className="px-2.5 py-1 rounded text-xs font-semibold bg-amber-950 text-amber-300 border border-amber-700">SUSPICIOUS</span>;
      case "FAILED":
        return <span className="px-2.5 py-1 rounded text-xs font-semibold bg-rose-950 text-rose-300 border border-rose-700">FAILED</span>;
      default:
        return <span className="px-2.5 py-1 rounded text-xs font-semibold bg-zinc-800 text-zinc-300 border border-zinc-700">{status}</span>;
    }
  };

  const totalCount = sessions.length;
  const verifiedCount = sessions.filter((s) => s.status === "VERIFIED").length;
  const suspiciousCount = sessions.filter((s) => s.status === "SUSPICIOUS").length;
  const failedCount = sessions.filter((s) => s.status === "FAILED").length;

  return (
    <div className="min-h-screen bg-zinc-950 text-zinc-100 p-6 md:p-10 font-sans">
      <div className="max-w-7xl mx-auto space-y-8">
        {/* Header */}
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 border-b border-zinc-800 pb-6">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-zinc-50">Evaluation Dashboard</h1>
            <p className="text-sm text-zinc-400 mt-1">
              Per-session multimodal verification telemetry, signal breakdowns, and TAR/FAR analysis metrics.
            </p>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={fetchSessions}
              disabled={loading}
              className="px-4 py-2 bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 text-sm font-medium rounded-lg border border-zinc-700 transition-colors"
            >
              {loading ? "Refreshing..." : "Refresh Sessions"}
            </button>
          </div>
        </div>

        {/* Aggregate Stats */}
        <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
            <p className="text-xs uppercase tracking-wider text-zinc-400">Total Sessions</p>
            <p className="text-2xl font-bold text-zinc-100 mt-1">{totalCount}</p>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
            <p className="text-xs uppercase tracking-wider text-emerald-400">Verified</p>
            <p className="text-2xl font-bold text-emerald-400 mt-1">{verifiedCount}</p>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
            <p className="text-xs uppercase tracking-wider text-amber-400">Suspicious</p>
            <p className="text-2xl font-bold text-amber-400 mt-1">{suspiciousCount}</p>
          </div>
          <div className="bg-zinc-900 border border-zinc-800 rounded-xl p-4">
            <p className="text-xs uppercase tracking-wider text-rose-400">Failed</p>
            <p className="text-2xl font-bold text-rose-400 mt-1">{failedCount}</p>
          </div>
        </div>

        {/* Error notification */}
        {error && (
          <div className="bg-rose-950/40 border border-rose-800 text-rose-300 p-4 rounded-xl text-sm">
            <strong>Error connecting to evaluation API:</strong> {error}
          </div>
        )}

        {/* Sessions List */}
        <div className="bg-zinc-900 border border-zinc-800 rounded-xl overflow-hidden">
          <div className="px-6 py-4 border-b border-zinc-800 flex items-center justify-between">
            <h2 className="text-base font-semibold text-zinc-200">Historical Sessions ({sessions.length})</h2>
            <span className="text-xs text-zinc-400">Note: Stage 3 & Replay signals are explicitly UNCALIBRATED in v1</span>
          </div>

          {loading && sessions.length === 0 ? (
            <div className="p-12 text-center text-zinc-400 text-sm">Loading session telemetry...</div>
          ) : sessions.length === 0 ? (
            <div className="p-12 text-center text-zinc-400 text-sm">No verification sessions found in the database.</div>
          ) : (
            <div className="divide-y divide-zinc-800">
              {sessions.map((sess) => {
                const sigs = sess.signals || {};
                const audio = sigs.audio_pipeline;
                const visualLive = sigs.visual_liveness;
                const visualChal = sigs.visual_challenge;
                const deepfake = sigs.deepfake;
                const replay = sigs.replay;

                // Stage 3 voice authenticity score
                const stage3Score = audio?.details?.voice_authenticity_score;

                // AV alignment: top-level signal takes precedence, fallback to details
                const avScore = sigs.av_alignment?.score ?? audio?.details?.av_alignment_score;

                return (
                  <div key={sess.session_id} className="p-6 space-y-4 hover:bg-zinc-900/50 transition-colors">
                    {/* Session Summary Row */}
                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                      <div className="space-y-1">
                        <div className="flex items-center gap-3">
                          <span className="font-mono text-xs text-zinc-400 bg-zinc-800 px-2 py-0.5 rounded">
                            {sess.session_id}
                          </span>
                          {getStatusBadge(sess.status)}
                          <span className="text-xs text-zinc-400">
                            Confidence: <strong className="text-zinc-200 font-mono">{formatScore(sess.confidence)}</strong>
                          </span>
                        </div>
                        {sess.decision_reason && (
                          <p className="text-xs text-zinc-400 italic">{sess.decision_reason}</p>
                        )}
                      </div>
                      <div className="text-right text-xs text-zinc-400">
                        {new Date(sess.created_at).toLocaleString()}
                      </div>
                    </div>

                    {/* Per-Signal Breakdown Grid */}
                    <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3 pt-2">
                      {/* Visual Liveness */}
                      <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800 text-xs">
                        <p className="text-zinc-400 font-medium">Visual Liveness</p>
                        <p className="font-mono text-zinc-200 mt-1 font-semibold">{formatScore(visualLive?.score)}</p>
                        <p className="text-[11px] text-zinc-400 mt-0.5">
                          Gate: {visualLive?.passed ? "Passed" : "Failed"}
                        </p>
                      </div>

                      {/* Visual Challenge */}
                      <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800 text-xs">
                        <p className="text-zinc-400 font-medium">Visual Challenge</p>
                        <p className="font-mono text-zinc-200 mt-1 font-semibold">{formatScore(visualChal?.score)}</p>
                        <p className="text-[11px] text-zinc-400 mt-0.5">
                          Hard Gate: {visualChal?.passed ? "Passed" : "Failed"}
                        </p>
                      </div>

                      {/* Audio Pipeline */}
                      <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800 text-xs">
                        <p className="text-zinc-400 font-medium">Audio Pipeline</p>
                        <p className="font-mono text-zinc-200 mt-1 font-semibold">{formatScore(audio?.score)}</p>
                        <p className="text-[11px] text-zinc-400 mt-0.5">
                          Hard Gate: {audio?.passed ? "Passed" : "Failed"}
                        </p>
                      </div>

                      {/* Stage 3 Voice Authenticity */}
                      <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800 text-xs">
                        <div className="flex items-center justify-between">
                          <p className="text-zinc-400 font-medium">Voice Auth</p>
                          <span className="text-[9px] bg-zinc-800 text-amber-400 px-1 py-0.2 rounded font-mono">UNCALIBRATED</span>
                        </div>
                        <p className="font-mono text-zinc-200 mt-1 font-semibold">{formatScore(stage3Score)}</p>
                        <p className="text-[11px] text-zinc-400 mt-0.5">Stage 3 Heuristics</p>
                      </div>

                      {/* Deepfake Detector */}
                      <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800 text-xs">
                        <p className="text-zinc-400 font-medium">Deepfake</p>
                        <p className="font-mono text-zinc-200 mt-1 font-semibold">{formatScore(deepfake?.score)}</p>
                        <p className="text-[11px] text-zinc-400 mt-0.5">
                          Class: {deepfake?.details?.prediction ?? "not measured"}
                        </p>
                      </div>

                      {/* Replay Detector */}
                      <div className="bg-zinc-950 p-3 rounded-lg border border-zinc-800 text-xs">
                        <div className="flex items-center justify-between">
                          <p className="text-zinc-400 font-medium">Replay</p>
                          <span className="text-[9px] bg-zinc-800 text-amber-400 px-1 py-0.2 rounded font-mono">UNCALIBRATED</span>
                        </div>
                        <p className="font-mono text-zinc-200 mt-1 font-semibold">{formatScore(replay?.score)}</p>
                        <p className="text-[11px] text-zinc-400 mt-0.5">
                          Gate: {replay?.passed ? "Passed" : "Failed"}
                        </p>
                      </div>
                    </div>
                  </div>
                );
              })}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
