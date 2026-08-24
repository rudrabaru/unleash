# Visual Liveness & Challenge Detection

A computer-vision based system for detecting user responses to visual
liveness challenges and generating an experimental visual-liveness signal.

The system uses MediaPipe Face Landmarker to extract facial landmarks,
head pose, and eye-related features from video.

---

## Overview

The system processes a video and can evaluate challenges such as:

- Turn Left
- Turn Right
- Look Up
- Look Down
- Blink

Alongside challenge detection, the project contains an experimental
Visual Liveness component based on facial movement, blink evidence, and
face-tracking consistency.

The challenge detection and liveness analysis are treated as separate
signals.

---

## Workflow

```text
                    Input Video
                         |
                         v
              MediaPipe Face Landmarker
                         |
                         v
                Feature Extraction
                         |
              +----------+----------+
              |                     |
              v                     v
       Challenge Detection    Visual Liveness
              |                     |
              v                     v
       Pass / Fail Result      Liveness Score
```
## Features

### Head Movement Detection

Head pose is extracted from the MediaPipe transformation matrix.

* **Left / Right** movement is detected using yaw.
* **Up / Down** movement is detected using pitch.
* A baseline pose is calculated at the beginning of the video.
* Movement is measured relative to that baseline.
* A temporal run requirement helps avoid triggering from a single noisy frame.

### Blink Detection

Blink detection uses eye-related facial features extracted by MediaPipe.

The system evaluates whether the eye signal crosses the configured blink threshold for the required number of frames.

### Visual Liveness

The project currently contains an experimental liveness signal using:

* Facial micro-movement
* Blink evidence
* Face/landmark tracking consistency

> **Note:** The Visual Liveness component is still being calibrated and should not yet be treated as the final production liveness model.

---

## Project Structure

```text
.
├── main.py
├── feature_extractor.py
├── challenge_detector.py
├── calculation.py
├── scoring.py
├── config.py
└── README.md
```

### `main.py`

Entry point for testing the system.

It:

1. Loads the input video.
2. Extracts facial features.
3. Runs the selected challenge detector.
4. Displays a human-readable result.
5. Optionally runs the experimental liveness analysis.

### `feature_extractor.py`

Handles MediaPipe processing and extracts the facial information required by the rest of the system.

### `challenge_detector.py`

Contains challenge-specific detection logic:

* Head turns
* Vertical head movements
* Blink detection

### `calculation.py`

Contains numerical feature calculations such as:

* Facial micro-movement
* Face consistency
* Liveness calculation

### `scoring.py`

Contains scoring utilities used by the current experimental liveness pipeline.

### `config.py`

Stores configurable thresholds and detection parameters.

---

## Running the Project

Set the video path and challenge in `main.py`:

```python
VIDEO_PATH = "up.mp4"
CHALLENGE = "TURN_UP"
```

### Supported Challenges

```text
TURN_LEFT
TURN_RIGHT
TURN_UP
TURN_DOWN
BLINK
```

Then run:

```bash
python main.py
```

---

## Example Output

```text
==================================================
CHALLENGE RESULT
==================================================
Challenge : Turn Left
Result    : PASSED
Confidence: 100.0%
Movement  : 48.6° detected
Duration  : 40 consecutive frames
Tracking  : 110/110 frames
==================================================
```

The output is intentionally kept human-readable for testing and demonstrations.

---

## Current Status

### Challenge Detection

* [x] Turn Left
* [x] Turn Right
* [x] Look Up
* [x] Look Down
* [x] Blink

### Visual Liveness

* [x] Facial micro-movement extraction
* [x] Face tracking consistency
* [x] Blink evidence
* [x] Initial liveness scoring
* [ ] Final liveness-score calibration
* [ ] Production-ready liveness model

---

## Scope

The current focus is **visual liveness and challenge-response detection**.

Replay-attack detection and other advanced anti-spoofing techniques are outside the current scope.
