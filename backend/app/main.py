import logging
import os
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api.v1.router import api_router
from app.core.body_limit import BodyLimitMiddleware
from app.core.config import settings
from app import db, housekeeping, orchestrator

# Ensure temp uploads directory exists
os.makedirs(settings.UPLOAD_TEMP_DIR, exist_ok=True)
_swept = housekeeping.sweep_leftover_media(Path(settings.UPLOAD_TEMP_DIR))
if _swept:
    logging.getLogger("unleash").warning("Removed %d leftover upload(s) from a previous run", _swept)
db.init_db()
_orphaned = db.fail_orphaned_sessions(datetime.now(timezone.utc))
if _orphaned:
    logging.getLogger("unleash").warning("Closed %d session(s) left in PROCESSING by a previous run", _orphaned)

@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Blocking, but it runs once before the server accepts requests.
    orchestrator.warm_up()
    yield


app = FastAPI(
    lifespan=lifespan,
    title="Unleash Multimodal Human Verification API",
    version="1.0.0",
    description="Multimodal active challenge-response verification defending against deepfakes and replay attacks."
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else [settings.CORS_ORIGINS],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Outermost, so an oversized body is refused while it arrives, before anything else reads it
app.add_middleware(BodyLimitMiddleware, limit=lambda: settings.MAX_UPLOAD_BYTES)

# Mount API routes
app.include_router(api_router, prefix="/api/v1")


@app.get("/ready", tags=["System"])
def readiness_check():
    """
    Whether the models the analysis needs are loaded. 503 with the reason for each model that is not,
    so a deployment is only sent traffic once it can answer it. The deepfake classifier is optional.
    """
    models = orchestrator.model_status()
    ready = all(models[name] is None for name in orchestrator.REQUIRED_MODELS)
    return JSONResponse({"ready": ready, "models": models}, status_code=200 if ready else 503)


@app.get("/health", tags=["System"])
async def health_check():
    """Liveness: the process is up. Use /ready to know whether it can analyse a recording."""
    return {
        "status": "healthy",
        "service": "unleash-verification-api",
        "version": "1.0.0",
        "environment": settings.ENVIRONMENT
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
