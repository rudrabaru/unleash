"""
Per-frame lip openness series export for Stage 4 AV alignment (Phase 5).
Normalized by face height (top-of-forehead to chin), not raw x/y width, to
avoid the aspect-distortion bug found in the standalone app's MAR ratio.

Per av-alignment-interface.md §5 (B4 fix): each sample carries the frame's real
presentation timestamp `time_seconds`. A timestamp is NEVER derived here from
`frame_index / fps`: browser `.webm` reports a bogus 1000 fps and indices count sampled
frames, so that clock is wrong. When a frame has no real timestamp the field is omitted and
Stage 4 degrades to `score=None` instead of scoring against an invented clock (J5).
"""
from typing import Any, Dict


def build_lip_series(features: Dict[str, Any], fps: float) -> Dict[str, Any]:
    series = []
    for i, f in enumerate(features.get("frames", [])):
        if f.get("mouth_open") is None:
            continue
        entry = {
            "frame_index": f.get("original_index", i),
            "lip_openness_ratio": round(float(f["mouth_open"]), 4),
        }
        if f.get("time_seconds") is not None:
            entry["time_seconds"] = round(float(f["time_seconds"]), 4)
        series.append(entry)
    return {"fps": fps, "series": series}
