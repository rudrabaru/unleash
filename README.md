# Unleash — Multimodal Human Verification System

> **A real-time, multimodal challenge-response verification system defending against synthetic identity fraud, AI deepfakes, and replay attacks.**

---

## 👥 Team & Vertical Allocation

| Developer | Responsibility Domain | Core Modules |
|---|---|---|
| **Dev 1 (Audio Lead)** | Audio Pipeline & AV Temporal Alignment | `backend/app/modules/audio/` (VAD, Whisper STT, Spectral, AV Sync) |
| **Dev 2 (Visual Lead)** | Visual Liveness & Challenge Verification | `backend/app/modules/visual/` (MediaPipe Face Mesh, EAR, Head Pose) |
| **Dev 3 (Anti-Spoof & Infra Lead)**| Anti-Spoofing & Backend Orchestration | `backend/app/modules/antispoof/` (Deepfake, Replay FFT, Fusion Engine, DB) |

---

## 🚀 Quick Start (Local Setup for All 3 Developers)

### 1. Backend Setup (FastAPI)

```bash
# Navigate to backend
cd backend

# Create and activate Python virtual environment
python -m venv .venv
# On Windows (PowerShell):
.venv\Scripts\Activate.ps1
# On macOS/Linux:
source .venv/bin/activate

# Install dependencies
pip install -r requirements.txt
pip install -r requirements-visual.txt
pip install -r requirements-antispoof.txt --extra-index-url https://download.pytorch.org/whl/cpu

# Optional: Deepfake Model Checkpoint (Dev 3)
# Default path: backend/checkpoints/xception_deepfake_best.pth (independent of where you start the server)
# Or specify an alternate path using environment variable UNLEASH_XCEPTION_CHECKPOINT.
# If absent, the deepfake detector gracefully handles missing weights and returns score=None.
# NOT YET PUBLISHED: ask Dev 3 for the file (it is ~250 MB and not in git). Download URL: TBD (Dev 3, B7).
# SHA-256 of the copy on Dev 1's machine (2026-10-04); Dev 3 must confirm it matches the published file:
#   cb731a0a53dbdcaddb09ab6855039b24d6e633d723d951d08f566d79a9d1eb0b
# Verify (PowerShell): Get-FileHash checkpoints\xception_deepfake_best.pth -Algorithm SHA256
# Verify (Linux/bash): sha256sum checkpoints/xception_deepfake_best.pth

# Copy environment variables
cp .env.example .env

# Run FastAPI development server
uvicorn app.main:app --reload --port 8000
```
**v1.0 module demo (D-27):** the browser flow is not part of v1.0. To demo the three modules (visual, audio, anti-spoofing) plus fusion on a recorded clip, run from the **repository root** (not `backend/`):

```bash
python app.py                      # serves on http://localhost:8000, then open /docs and use POST /verify
# or: uvicorn app:app --port 8000
```

Upload a `.webm`/`.mp4`, choose the visual challenge, and optionally edit the 5 verbal words. The response lists each module's score, pass/fail and reason. No end-to-end human verdict is claimed for v1.0 (see `.claude/context/decisions.md`, D-27).

- **API Health Check:** [http://localhost:8000/health](http://localhost:8000/health)
- **Interactive OpenAPI Docs:** [http://localhost:8000/docs](http://localhost:8000/docs)

---

### 2. Frontend Setup (Next.js)

```bash
# Navigate to frontend
cd frontend

# Install Node dependencies
npm install

# Copy environment variables
cp .env.example .env.local

# Run Next.js development server
npm run dev
```
- **App URL:** [http://localhost:3000](http://localhost:3000)

---

## 📐 Inviolable Shared Contract: The 4-Key Schema

Every detector module across all verticals MUST return this exact schema (defined in `backend/app/schemas/detector.py`):

```json
{
  "score": 0.92,
  "passed": true,
  "reason": "Human-readable explanation of the verdict.",
  "error": null,
  "details": {
    "telemetry_key": "value"
  }
}
```

- **`score`**: Float between `0.0` (definitely fake/spoof) and `1.0` (definitely genuine). `null` if computation errored.
- **`passed`**: Boolean flag indicating whether the module passed its internal evaluation/hard gate.
- **`reason`**: Short explanation of why the score/verdict was assigned.
- **`error`**: Error message string if computation crashed, else `null`.
- **`details`**: Optional diagnostic sub-metrics stored in the evaluation database.

---

## 📁 Repository Structure

```text
Unleash/
├── backend/
│   ├── app/
│   │   ├── api/v1/endpoints/   # REST API endpoints (sessions, eval)
│   │   ├── core/               # Security, HMAC signing, app config
│   │   ├── modules/            # Domain-specific ML & heuristic modules
│   │   │   ├── audio/          # Dev 1 vertical
│   │   │   ├── visual/         # Dev 2 vertical
│   │   │   └── antispoof/      # Dev 3 vertical
│   │   ├── schemas/            # Inviolable Pydantic data contracts
│   │   └── main.py             # FastAPI entry point
│   ├── requirements.txt
│   └── .env.example
├── frontend/
│   ├── src/app/                # Next.js 14 App Router UI
│   ├── package.json
│   └── .env.example
├── docs/                       # Project specifications, visual workflows, and companion guides
├── .gitignore
└── README.md
```
