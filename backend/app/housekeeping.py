"""
Clean-up of leftovers a previous run may have left on disk. Called once at startup, when nothing can
be using them: uploads and extracted audio are removed after every analysis, so anything still there
belongs to a process that died in the middle of one, and it is a person's face or voice.
"""
import logging
import shutil
from pathlib import Path

logger = logging.getLogger("unleash.housekeeping")

# What the upload and analysis steps create in the upload directory.
_LEFTOVER_PATTERNS = ("upload_*", "verify_*", "audio_*", "*.webm")


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
