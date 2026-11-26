from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import housekeeping, orchestrator
from app.analysis_queue import analysis_queue
from app.api.v1.router import api_router
from app.core.body_limit import BodyLimitMiddleware
from app.core.config import settings


@asynccontextmanager
async def lifespan(_app: FastAPI):
    # Blocking, but it runs once before the server accepts requests. Nothing here runs at import, so
    # importing the app (a test, a tool) never touches the database or the upload folder.
    housekeeping.startup()
    orchestrator.warm_up()
    analysis_queue.start(settings.MAX_QUEUED_ANALYSES)
    yield
    analysis_queue.stop()


API_VERSION = "1.0.0"

app = FastAPI(
    lifespan=lifespan,
    title="Unleash Multimodal Human Verification API",
    version=API_VERSION,
    # Claims policy (D-08): "targets", never "defends against", until an attack is measured.
    description="Active challenge-response check that a live person is present. Targets replay, face-swap, "
    "photo and synthetic-voice attacks; none of these is a measured defence yet.",
)

# CORS, for a browser that calls the API directly instead of through the Next.js proxy. The API uses no
# cookies or other credentials, and the browser only sends GETs and POSTs (form uploads, no custom headers).
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS if isinstance(settings.CORS_ORIGINS, list) else [settings.CORS_ORIGINS],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type"],
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
        "version": API_VERSION,
        "environment": settings.ENVIRONMENT
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("app.main:app", host=settings.HOST, port=settings.PORT, reload=settings.DEBUG)
