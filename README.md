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

# Copy environment variables
cp .env.example .env

# Run FastAPI development server
uvicorn app.main:app --reload --port 8000
```
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
