"""
Per-frame lip openness series export for Stage 4 AV alignment (Phase 5).
Normalized by face height (top-of-forehead to chin), not raw x/y width, to
avoid the aspect-distortion bug found in the standalone app's MAR ratio.
"""
from typing import Any, Dict


def build_lip_series(features: Dict[str, Any], fps: float) -> Dict[str, Any]:
    frames = features.get("frames", [])
    series = [
        {"frame_index": i, "lip_openness_ratio": f["mouth_open"]}
        for i, f in enumerate(frames)
        if f.get("mouth_open") is not None
    ]
    return {"fps": fps, "series": series}
