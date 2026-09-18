"""
Replay Screen Attack Detector (Phase 4). New module — nothing existed before this.

Per docs/unleash_project_plan.md Section "Tech Stack" (OpenCV + NumPy, FFT + brightness
analysis) and implement-all-three-pillars.md Phase 4: three real, independently-computed
sub-signals, weighted and combined into one 0.0-1.0 score:

  - FFT moire detection      (55%) - screens/monitors photographed by a camera produce a
                                      periodic pixel-grid pattern that shows up as sharp,
                                      unnatural peaks in the spatial-frequency spectrum.
  - Temporal noise std       (30%) - a live camera sensor has a natural, moderate amount of
                                      frame-to-frame pixel noise even when the subject is
                                      still; a screen replay tends to be either too clean
                                      (pure digital-to-digital re-encode) or too noisy
                                      (moire flicker / refresh-rate beating).
  - Brightness histogram     (15%) - screen/backlight capture tends to compress the dynamic
                                      range and clip at the extremes compared to natural,
                                      ambient-lit footage.

Threshold: pass if combined score >= REPLAY_PASS_THRESHOLD (0.60).

**Calibration status: [UNCALIBRATED].** These are real computations over real frames -
nothing here is a fabricated number (J5) - but every threshold and weight below (the ring
radii, MOIRE_PEAKINESS_FLOOR/CEIL, the natural noise-std band, CLIP_FRACTION_CEIL, the
0.55/0.30/0.15 weights, the 0.60 pass line) is an initial, reasoned guess never fitted to a
labelled replay-vs-genuine recording set, per the same honesty standard as Stage 3 voice
authenticity (see .claude/context/audio-pipeline/stage-specifications.md). Do not cite a
score from this module as a tuned/validated number until scenario recordings exist to
calibrate against.
"""
from typing import Any, Dict, List

import numpy as np

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:  # pragma: no cover
    CV2_AVAILABLE = False

# --- weights -----------------------------------------------------------------
MOIRE_WEIGHT = 0.55
NOISE_WEIGHT = 0.30
BRIGHTNESS_WEIGHT = 0.15

REPLAY_PASS_THRESHOLD = 0.60

# --- moire (FFT) ---------------------------------------------------------------
# Ring around the spectrum center, excluding the low-frequency content that carries the
# actual image and the extreme corners that are mostly sensor/compression noise.
MOIRE_RING_INNER_FRACTION = 0.15
MOIRE_RING_OUTER_FRACTION = 0.85
# A natural photo's high-frequency ring decays smoothly (low peak-to-mean ratio); a
# periodic pixel-grid/moire pattern concentrates energy into a few sharp bins.
MOIRE_PEAKINESS_FLOOR = 6.0
MOIRE_PEAKINESS_CEIL = 20.0
MOIRE_MAX_FRAMES_SAMPLED = 10

# --- temporal noise --------------------------------------------------------------
# Mean frame-to-frame grayscale absolute-difference std, on a 0-255 scale, expected for a
# live webcam sensor on a mostly-still subject.
NATURAL_NOISE_STD_LOW = 1.5
NATURAL_NOISE_STD_HIGH = 14.0

# --- brightness histogram --------------------------------------------------------
CLIP_FRACTION_CEIL = 0.35
HISTOGRAM_BINS = 256
MAX_ENTROPY_BITS = 8.0  # log2(256)


def _to_gray_frames(frames: List[np.ndarray]) -> List[np.ndarray]:
    return [cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY) for frame in frames]


def _sample_for_fft(frames: List[np.ndarray], max_frames: int) -> List[np.ndarray]:
    if len(frames) <= max_frames:
        return frames
    step = len(frames) / max_frames
    return [frames[int(i * step)] for i in range(max_frames)]


def _moire_score_for_frame(gray: np.ndarray) -> float:
    spectrum = np.fft.fftshift(np.fft.fft2(gray.astype(np.float32)))
    magnitude = np.abs(spectrum)

    height, width = magnitude.shape
    center_y, center_x = height // 2, width // 2
    max_radius = float(min(center_y, center_x))
    if max_radius <= 0:
        return 1.0

    y_indices, x_indices = np.ogrid[:height, :width]
    radius = np.sqrt((y_indices - center_y) ** 2 + (x_indices - center_x) ** 2)
    ring_mask = (radius >= MOIRE_RING_INNER_FRACTION * max_radius) & (
        radius <= MOIRE_RING_OUTER_FRACTION * max_radius
    )

    ring_values = magnitude[ring_mask]
    ring_mean = float(ring_values.mean()) if ring_values.size else 0.0
    if ring_mean < 1e-6:
        return 1.0

    peakiness = float(ring_values.max()) / ring_mean
    normalized = (peakiness - MOIRE_PEAKINESS_FLOOR) / (MOIRE_PEAKINESS_CEIL - MOIRE_PEAKINESS_FLOOR)
    return float(1.0 - min(1.0, max(0.0, normalized)))


def _moire_score(gray_frames: List[np.ndarray]) -> Dict[str, Any]:
    sampled = _sample_for_fft(gray_frames, MOIRE_MAX_FRAMES_SAMPLED)
    per_frame_scores = [_moire_score_for_frame(frame) for frame in sampled]
    score = float(np.mean(per_frame_scores)) if per_frame_scores else 0.5
    return {"score": score, "frames_sampled": len(sampled)}


def _temporal_noise_score(gray_frames: List[np.ndarray]) -> Dict[str, Any]:
    if len(gray_frames) < 2:
        # Not enough frames to measure frame-to-frame noise: neither confirm nor deny.
        return {"score": 0.5, "mean_diff_std": None, "degraded_reason": "fewer than 2 frames"}

    diff_stds = [
        float(cv2.absdiff(gray_frames[i], gray_frames[i - 1]).std())
        for i in range(1, len(gray_frames))
    ]
    mean_diff_std = float(np.mean(diff_stds))

    if NATURAL_NOISE_STD_LOW <= mean_diff_std <= NATURAL_NOISE_STD_HIGH:
        score = 1.0
    elif mean_diff_std < NATURAL_NOISE_STD_LOW:
        score = max(0.0, mean_diff_std / NATURAL_NOISE_STD_LOW)
    else:
        excess = mean_diff_std - NATURAL_NOISE_STD_HIGH
        score = max(0.0, 1.0 - excess / NATURAL_NOISE_STD_HIGH)

    return {"score": float(score), "mean_diff_std": round(mean_diff_std, 4)}


def _brightness_histogram_score(gray_frames: List[np.ndarray]) -> Dict[str, Any]:
    histogram = np.zeros(HISTOGRAM_BINS, dtype=np.float64)
    for gray in gray_frames:
        frame_hist, _ = np.histogram(gray, bins=HISTOGRAM_BINS, range=(0, 256))
        histogram += frame_hist

    total = histogram.sum()
    if total <= 0:
        return {"score": 0.5, "entropy_bits": None, "clip_fraction": None}

    probabilities = histogram / total
    nonzero = probabilities[probabilities > 0]
    entropy_bits = float(-np.sum(nonzero * np.log2(nonzero)))
    entropy_ratio = entropy_bits / MAX_ENTROPY_BITS

    clip_fraction = float((histogram[0] + histogram[-1]) / total)
    clip_penalty = min(1.0, clip_fraction / CLIP_FRACTION_CEIL)

    score = max(0.0, min(1.0, entropy_ratio - clip_penalty))
    return {
        "score": float(score),
        "entropy_bits": round(entropy_bits, 4),
        "clip_fraction": round(clip_fraction, 4),
    }


def score_replay(frames: List[np.ndarray]) -> Dict[str, Any]:
    """
    Compute the combined replay-detection score for a list of RGB frames.

    Never raises: callers (the antispoof `__init__.py` wrapper) still catch exceptions per
    the detector contract, but every sub-signal here already degrades to a neutral 0.5
    rather than crashing on edge-case input (single frame, blank frame, etc).
    """
    # Guard against missing cv2 dependency (DIP violation fix)
    if not CV2_AVAILABLE:
        return {
            "score": 0.5,
            "passed": False,
            "moire": {"score": 0.5, "frames_sampled": 0},
            "temporal_noise": {"score": 0.5, "mean_diff_std": None},
            "brightness_histogram": {"score": 0.5, "entropy_bits": None, "clip_fraction": None},
            "frames_analyzed": len(frames),
            "degraded_reason": "cv2 (OpenCV) not installed",
        }

    gray_frames = _to_gray_frames(frames)

    moire = _moire_score(gray_frames)
    noise = _temporal_noise_score(gray_frames)
    brightness = _brightness_histogram_score(gray_frames)

    combined = (
        moire["score"] * MOIRE_WEIGHT
        + noise["score"] * NOISE_WEIGHT
        + brightness["score"] * BRIGHTNESS_WEIGHT
    )

    return {
        "score": round(float(combined), 4),
        "passed": combined >= REPLAY_PASS_THRESHOLD,
        "moire": moire,
        "temporal_noise": noise,
        "brightness_histogram": brightness,
        "frames_analyzed": len(frames),
    }
