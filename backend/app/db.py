"""
SQLite persistence for verification sessions, per plan's "SQLite Schema" section.

One connection per call (SQLite + FastAPI BackgroundTasks doesn't benefit from a
pool at this scale); WAL mode so a read during a background write doesn't block.
"""
import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from app.core.config import settings
from app.schemas.detector import DetectorResult

_DB_PATH = Path(settings.DATABASE_URL.replace("sqlite:///", "", 1)) if "sqlite" in settings.DATABASE_URL else Path("./unleash.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS sessions (
    session_id TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    visual_challenge TEXT,
    verbal_challenge TEXT,
    confidence REAL,
    decision_reason TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS signal_scores (
    session_id TEXT NOT NULL,
    signal_name TEXT NOT NULL,
    score REAL,
    passed INTEGER,
    reason TEXT,
    error TEXT,
    details TEXT,
    PRIMARY KEY (session_id, signal_name),
    FOREIGN KEY (session_id) REFERENCES sessions(session_id)
);

CREATE TABLE IF NOT EXISTS error_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    signal_name TEXT,
    error TEXT NOT NULL,
    logged_at TEXT NOT NULL
);
"""


@contextmanager
def _connect():
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(_DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    finally:
        conn.close()


def init_db() -> None:
    with _connect() as conn:
        conn.executescript(_SCHEMA)


def create_session(
    session_id: str,
    status: str,
    visual_challenge: str,
    verbal_challenge: str,
    created_at: datetime,
) -> None:
    with _connect() as conn:
        conn.execute(
            """INSERT INTO sessions
               (session_id, status, visual_challenge, verbal_challenge,
                confidence, decision_reason, created_at, updated_at)
               VALUES (?, ?, ?, ?, NULL, ?, ?, ?)""",
            (
                session_id, status, visual_challenge, verbal_challenge,
                "Session created. Awaiting media upload.",
                created_at.isoformat(), created_at.isoformat(),
            ),
        )


def set_challenge(session_id: str, visual_challenge: Optional[str] = None, verbal_challenge: Optional[str] = None) -> None:
    """Test/tooling helper to override a session's stored challenge before submit."""
    with _connect() as conn:
        if visual_challenge is not None:
            conn.execute("UPDATE sessions SET visual_challenge = ? WHERE session_id = ?", (visual_challenge, session_id))
        if verbal_challenge is not None:
            conn.execute("UPDATE sessions SET verbal_challenge = ? WHERE session_id = ?", (verbal_challenge, session_id))


def update_session_status(session_id: str, status: str, updated_at: datetime) -> None:
    with _connect() as conn:
        conn.execute(
            "UPDATE sessions SET status = ?, updated_at = ? WHERE session_id = ?",
            (status, updated_at.isoformat(), session_id),
        )


def write_decision(
    session_id: str,
    status: str,
    confidence: Optional[float],
    decision_reason: str,
    signals: Dict[str, DetectorResult],
    updated_at: datetime,
) -> None:
    with _connect() as conn:
        conn.execute(
            """UPDATE sessions
               SET status = ?, confidence = ?, decision_reason = ?, updated_at = ?
               WHERE session_id = ?""",
            (status, confidence, decision_reason, updated_at.isoformat(), session_id),
        )
        for name, result in signals.items():
            conn.execute(
                """INSERT INTO signal_scores
                   (session_id, signal_name, score, passed, reason, error, details)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(session_id, signal_name) DO UPDATE SET
                       score=excluded.score, passed=excluded.passed, reason=excluded.reason,
                       error=excluded.error, details=excluded.details""",
                (
                    session_id, name, result.score, int(result.passed), result.reason,
                    result.error, json.dumps(result.details) if result.details else None,
                ),
            )
            if result.error:
                conn.execute(
                    "INSERT INTO error_log (session_id, signal_name, error, logged_at) VALUES (?, ?, ?, ?)",
                    (session_id, name, result.error, updated_at.isoformat()),
                )


def get_session(session_id: str) -> Optional[Dict[str, Any]]:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM sessions WHERE session_id = ?", (session_id,)).fetchone()
        if row is None:
            return None
        session = dict(row)
        signal_rows = conn.execute(
            "SELECT * FROM signal_scores WHERE session_id = ?", (session_id,)
        ).fetchall()
        session["signals"] = {
            r["signal_name"]: DetectorResult(
                score=r["score"],
                passed=bool(r["passed"]),
                reason=r["reason"],
                error=r["error"],
                details=json.loads(r["details"]) if r["details"] else None,
            )
            for r in signal_rows
        }
        return session


def list_sessions() -> list[Dict[str, Any]]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM sessions ORDER BY created_at DESC").fetchall()
        session_ids = [r["session_id"] for r in rows]
    return [get_session(sid) for sid in session_ids]
