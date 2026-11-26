"""
Start-up and routine clean-up.

`startup` runs once when the server starts (from the app's lifespan, never at import, so importing
the app in a test or a tool touches nothing): it creates the upload folder, removes leftovers a
previous run may have left there, creates the database tables, closes sessions a dead process left
PROCESSING and deletes sessions past their retention. `prune_old_sessions` repeats the last step
while the server runs, at most every few minutes.

Uploads and extracted audio are removed after every analysis, so anything still in the upload folder
at start-up belongs to a process that died in the middle of one, and it is a person's face or voice.
"""
import logging
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from app import db
from app.core.config import settings

logger = logging.getLogger("unleash.housekeeping")

# What the upload and analysis steps create in the upload directory.
_LEFTOVER_PATTERNS = ("upload_*", "verify_*", "audio_*", "*.webm")

# Retention is checked at most this often while the server runs.
PRUNE_INTERVAL_SECONDS = 600.0

_last_prune: Optional[float] = None
_prune_lock = threading.Lock()


def sweep_leftover_media(upload_dir: Path) -> int:
    """Delete leftover upload files and temporary audio folders in `upload_dir`. Returns how many were removed."""
    if not upload_dir.is_dir():
        return 0
    removed = 0
    for pattern in _LEFTOVER_PATTERNS:
        for entry in upload_dir.glob(pattern):
            try:
                shutil.rmtree(entry) if entry.is_dir() else entry.unlink()
                removed += 1
            except OSError:
                logger.warning("Could not remove leftover %s", entry)
    return removed


def prune_old_sessions(now: datetime, force: bool = False) -> int:
    """Delete sessions past SESSION_RETENTION_HOURS (0 keeps all). Throttled unless `force`. Returns how many."""
    global _last_prune
    hours = settings.SESSION_RETENTION_HOURS
    if hours <= 0:
        return 0
    with _prune_lock:
        clock = time.monotonic()
        if not force and _last_prune is not None and clock - _last_prune < PRUNE_INTERVAL_SECONDS:
            return 0
        _last_prune = clock
    deleted = db.delete_sessions_created_before(now - timedelta(hours=hours))
    if deleted:
        logger.info("Deleted %d session(s) older than %g h", deleted, hours)
    return deleted


def startup() -> None:
    """Everything the server does on disk before it accepts requests."""
    upload_dir = Path(settings.UPLOAD_TEMP_DIR)
    upload_dir.mkdir(parents=True, exist_ok=True)
    swept = sweep_leftover_media(upload_dir)
    if swept:
        logger.warning("Removed %d leftover upload(s) from a previous run", swept)
    db.init_db()
    now = datetime.now(timezone.utc)
    orphaned = db.fail_orphaned_sessions(now)
    if orphaned:
        logger.warning("Closed %d session(s) left in PROCESSING by a previous run", orphaned)
    prune_old_sessions(now, force=True)
