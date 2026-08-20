"use client";

import { useState } from "react";

export default function LandingPage() {
  const [loading, setLoading] = useState(false);
  const [sessionData, setSessionData] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const startVerification = async () => {
    setLoading(true);
    setError(null);
    try {
      const apiBase = process.env.NEXT_PUBLIC_API_BASE_URL || "http://localhost:8000/api/v1";
      const res = await fetch(`${apiBase}/sessions`, {
        method: "POST",
      });
      if (!res.ok) {
        throw new Error(`Failed to create session: ${res.statusText}`);
      }
      const data = await res.json();
      setSessionData(data);
    } catch (err: any) {
      setError(err.message || "Failed to reach backend API");
    } finally {
      setLoading(false);
    }
  };

  return (
    <main className="container" style={{ display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", minHeight: "85vh" }}>
      <div className="card" style={{ maxWidth: "600px", width: "100%", textAlign: "center" }}>
        <div style={{ marginBottom: "1.5rem" }}>
          <span className="badge badge-verified" style={{ marginBottom: "0.75rem" }}>
            Unleash Platform
          </span>
          <h1 style={{ fontSize: "2rem", fontWeight: "700", marginBottom: "0.5rem", letterSpacing: "-0.02em" }}>
            Active Human Verification
          </h1>
          <p style={{ color: "var(--text-secondary)", fontSize: "1rem", lineHeight: "1.5" }}>
            Multimodal proof-of-presence defending against real-time deepfakes, replay injections, and spoof attacks.
          </p>
        </div>

        {error && (
          <div style={{ padding: "0.75rem", background: "rgba(244, 63, 94, 0.1)", border: "1px solid var(--accent-rose)", borderRadius: "8px", color: "var(--accent-rose)", marginBottom: "1.5rem", fontSize: "0.9rem" }}>
            ⚠️ {error}
          </div>
        )}

        {sessionData ? (
          <div style={{ padding: "1.25rem", background: "var(--bg-card)", borderRadius: "8px", textAlign: "left", marginBottom: "1.5rem", border: "1px solid var(--border-color)" }}>
            <h3 style={{ fontSize: "1rem", color: "var(--accent-cyan)", marginBottom: "0.5rem" }}>Session Initialized (Stub Ready)</h3>
            <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>
              <strong>Session ID:</strong> {sessionData.session_id}
            </p>
            <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>
              <strong>Visual Challenge:</strong> {sessionData.challenge.visual}
            </p>
            <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)", marginBottom: "0.25rem" }}>
              <strong>Verbal Challenge:</strong> {sessionData.challenge.verbal}
            </p>
            <p style={{ fontSize: "0.85rem", color: "var(--text-secondary)" }}>
              <strong>Expires In:</strong> 120s
            </p>
          </div>
        ) : null}

        <button
          className="btn-primary"
          onClick={startVerification}
          disabled={loading}
          style={{ width: "100%", fontSize: "1rem", opacity: loading ? 0.7 : 1 }}
        >
          {loading ? "Generating Challenge..." : sessionData ? "Regenerate Challenge" : "Start Verification"}
        </button>

        <p style={{ marginTop: "1.5rem", fontSize: "0.8rem", color: "var(--text-muted)" }}>
          Phase 0 Alignment · Fast, local, tamper-resistant HMAC session generation.
        </p>
      </div>
    </main>
  );
}
