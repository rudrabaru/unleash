"""
SQLite persistence for verification sessions and their per-signal results.

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


def claim_for_processing(session_id: str, updated_at: datetime) -> bool:
    """Move a CREATED session to PROCESSING in one statement. False if another request got there first."""
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE sessions SET status = ?, updated_at = ? WHERE session_id = ? AND status = ?",
            ("PROCESSING", updated_at.isoformat(), session_id, "CREATED"),
        )
        return cursor.rowcount == 1


def close_session(session_id: str, status: str, reason: str, updated_at: datetime) -> None:
    """End a session with a status and a reason, for a session that never reached a verdict."""
    with _connect() as conn:
        conn.execute(
            "UPDATE sessions SET status = ?, decision_reason = ?, updated_at = ? WHERE session_id = ?",
            (status, reason, updated_at.isoformat(), session_id),
        )


def fail_orphaned_sessions(updated_at: datetime) -> int:
    """
    Close every session still PROCESSING as RETRY. Analyses run inside the server process, so at
    startup any PROCESSING session belongs to a process that has died (crash, restart, reload); the
    person did nothing wrong and may try again. Returns how many were closed.
    """
    with _connect() as conn:
        cursor = conn.execute(
            "UPDATE sessions SET status = ?, decision_reason = ?, updated_at = ? WHERE status = ?",
            (
                "RETRY",
                "The analysis was interrupted before it finished. Please try again.",
                updated_at.isoformat(),
                "PROCESSING",
            ),
        )
        return cursor.rowcount


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
