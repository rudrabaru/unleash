# Facial Liveness & Interactive Challenge Verification Engine

A Python application and FastAPI service that evaluates video recordings to verify **physical liveness** (passive micro-movement, blink presence, tracking consistency) and **interactive challenge compliance** (head turns, looking up/down, eye blinks, mouth opening).

Powered by **Google MediaPipe FaceLandmarker Tasks API** (3D facial mesh, facial transformation matrices, and blendshapes) and **OpenCV**.

---

## Features

- **Interactive Challenge Detection**:
  - **Head Turn Left / Right**: Tracks yaw rotation relative to an initial baseline with direction validation and consecutive hold frame checks.
  - **Look Up / Down**: Tracks pitch displacement with direction validation.
  - **Blink**: Detects eye closure using MediaPipe `eyeBlinkLeft` / `eyeBlinkRight` blendshapes with minimum hold frames.
  - **Open Mouth**: Computes Mouth Aspect Ratio (MAR) across inner lip landmarks with median signal smoothing.
- **Passive Visual Liveness Scoring**:
  - **Micro-Movements**: Measures inter-frame Euclidean displacement across normalized 3D facial landmarks to differentiate living subjects from static printed photos or motionless screens.
  - **Tracking Quality Gate**: Evaluates continuous face landmark presence and penalizes tracking dropouts.
  - **Natural Blink Evidence**: Contributes supporting liveness evidence.
- **Production-Ready FastAPI REST Service**:
  - Pure REST API with `POST /analyze` accepting video file uploads and challenge parameters.
  - Standardized JSON schema: `score`, `pass/fail`, `reason`, `errors`, `details`.
  - Auto-generated interactive Swagger UI documentation at `/docs`.
- **Standalone CLI**:
  - Direct execution via `python main.py` with diagnostic printouts and optional Matplotlib signal visualization.

---

## Project Structure

```
Liveliness + challenge/
├── face_landmarker.task    # MediaPipe Face Landmarker model asset
├── config.py               # Configurable thresholds and model paths
├── requirements.txt        # Python package dependencies
├── video_process.py        # Video frame extraction, landmark detection, MAR calculation
├── calculation.py          # Micro-movement, face consistency, and baseline angle calculations
├── challenge_detector.py   # Detection logic for head turns, pitch, blinks, and mouth opening
├── scoring.py              # Visual liveness aggregation and micro-movement scoring
├── main.py                 # CLI interface with terminal outputs and plotting
└── app.py                  # Single-file FastAPI REST application
```

---

## Supported Challenges

| Challenge Key | User Aliases | Description | Default Threshold | Hold Duration |
| :--- | :--- | :--- | :--- | :--- |
| `TURN_LEFT` | `LEFT`, `TURN LEFT` | Physical head turn to the left | `20.0°` yaw | 2 frames |
| `TURN_RIGHT` | `RIGHT`, `TURN RIGHT` | Physical head turn to the right | `20.0°` yaw | 2 frames |
| `TURN_UP` | `LOOK_UP`, `UP`, `LOOK UP` | Head tilt upwards | `20.0°` pitch | 2 frames |
| `TURN_DOWN` | `LOOK_DOWN`, `DOWN`, `LOOK DOWN`| Head tilt downwards | `20.0°` pitch | 2 frames |
| `BLINK` | `BLINK` | Both eyes closed | `0.50` blendshape score | 2 frames |
| `OPEN_MOUTH` | `MOUTH`, `LIPS`, `MOUTH_OPEN` | Mouth / lips opened | `0.35` MAR | 2 frames |

---

## Installation & Setup

### 1. Prerequisites
- Python 3.10 or 3.11
- Virtual environment (recommended)

### 2. Install Dependencies
```bash
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

---

## Usage

### 1. Run the FastAPI Server

Start the API service with Uvicorn:

```bash
uvicorn app:app --host 0.0.0.0 --port 8000 --reload
```

- **Interactive Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc Documentation**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)

#### Example API Request (cURL)

```bash
curl -X POST "http://127.0.0.1:8000/analyze" \
  -F "file=@blink.mp4" \
  -F "challenge=BLINK"
```

#### Example API Request (Python `requests`)

```python
import requests

url = "http://127.0.0.1:8000/analyze"
files = {"file": open("blink.mp4", "rb")}
data = {"challenge": "BLINK"}

response = requests.post(url, files=files, data=data)
print(response.json())
```

#### API Response Schema

```json
{
  "score": 1.0,
  "pass/fail": "PASS",
  "reason": "Challenge Blink passed: eye closure reached 0.81 held for 5 consecutive frames (threshold: 0.5, required hold: 2 frames).",
  "errors": null,
  "details": {
    "liveness_score": 0.3747,
    "liveness_level": "LOW",
    "micro_movement_score": 0.1066,
    "blink_evidence_score": 1.0,
    "face_consistency_score": 1.0,
    "challenge_key": "BLINK",
    "challenge_name": "Blink Eyes",
    "challenge_detected": true,
    "longest_consecutive_run": 5,
    "max_displacement": 0.8102,
    "valid_frames": 108,
    "total_frames": 108,
    "video_metadata": {
      "fps": 29.92,
      "frame_count": 108,
      "duration_seconds": 3.61
    }
  }
}
```

---

### 2. Run via CLI

Execute the terminal script:

```bash
python main.py
```

You will be prompted to enter:
1. **Video file path** (e.g. `blink.mp4`, `mouth.mp4`, or full file path)
2. **Challenge name** (e.g. `BLINK`, `OPEN_MOUTH`, `TURN_LEFT`)

Sample CLI output:
```text
==================================================
CHALLENGE RESULT
==================================================
Challenge : Blink
Result    : PASSED
Confidence: 100.0%
Blink strength: 0.81
Duration      : 5 consecutive frames
==================================================

==================================================
VISUAL LIVENESS (EXPERIMENTAL)
==================================================
Liveness : 37.5%
Level    : LOW
Micro-movement : 10.7%
Blink evidence : 100.0%
Face tracking  : 100.0%
==================================================
```

---

## Configuration & Tuning

Key parameters can be customized in `config.py`:

```python
# Head / Vertical turn settings
HEAD_TURN_THRESHOLD = 20.0       # Angle in degrees required to pass
HEAD_HOLD_FRAMES = 2             # Consecutive frames required above threshold
BASELINE_SECONDS = 0.5           # Time window to establish neutral face angle

# Blink settings
BLINK_THRESHOLD = 0.5            # MediaPipe eyeBlink blendshape score threshold
BLINK_HOLD_FRAMES = 2            # Consecutive frames eyes must remain closed

# Mouth open settings
MOUTH_THRESHOLD = 0.35           # Mouth Aspect Ratio (MAR) threshold
MOUTH_HOLD_FRAMES = 2            # Consecutive frames mouth must remain open

# Micro-movement thresholds (normalized coordinate scale)
MICRO_MOVE_LOW_THRESHOLD = 0.0003
MICRO_MOVE_HIGH_THRESHOLD = 0.0030
```

---

## How It Works

1. **Feature Extraction (`video_process.py`)**:
   - Decodes video frames using OpenCV.
   - Feeds frames with strictly monotonically increasing timestamps to MediaPipe `FaceLandmarker` in `VIDEO` running mode.
   - Extracts 468+ normalized 3D landmarks, `facial_transformation_matrixes` (converted to Euler yaw, pitch, and roll via `atan2`), and 52 blendshape coefficients.
   - Calculates Mouth Aspect Ratio (MAR): $\frac{d_1 + d_2 + d_3}{3 \times \text{width}}$ and applies median smoothing.
2. **Interactive Challenge Verification (`challenge_detector.py`)**:
   - Calculates a neutral baseline pose using the median of initial frames (with fallback if tracking started late).
   - Computes displacement along the commanded direction only.
   - Evaluates consecutive qualifying frames against `hold_frames`.
3. **Passive Liveness Assessment (`scoring.py`, `calculation.py`)**:
   - Measures frame-to-frame mean Euclidean shift across landmarks.
   - Evaluates tracking continuity (`face_coverage` & `longest_missing_run`).
   - Calculates a weighted composite visual liveness score gated by tracking quality.
