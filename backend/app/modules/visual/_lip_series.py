"""
Per-frame lip openness series export for Stage 4 AV alignment (Phase 5).
Normalized by face height (top-of-forehead to chin), not raw x/y width, to
avoid the aspect-distortion bug found in the standalone app's MAR ratio.
Per av-alignment-interface.md Section 4 (B4 fix): outputs real presentation
timestamp `time_seconds` on each lip sample.
"""
from typing import Any, Dict


def build_lip_series(features: Dict[str, Any], fps: float) -> Dict[str, Any]:
    frames = features.get("frames", [])
    series = []
    for i, f in enumerate(frames):
        if f.get("mouth_open") is not None:
            time_sec = f.get("time_seconds")
            orig_idx = f.get("original_index", i)
            if time_sec is None and fps > 0:
                time_sec = round(float(orig_idx / fps), 4)

            entry = {
                "frame_index": orig_idx,
                "lip_openness_ratio": round(float(f["mouth_open"]), 4),
            }
            if time_sec is not None:
                entry["time_seconds"] = round(float(time_sec), 4)

            series.append(entry)

    return {"fps": fps, "series": series}
