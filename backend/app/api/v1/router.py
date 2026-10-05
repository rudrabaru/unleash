from fastapi import APIRouter

from app.api.v1.endpoints import sessions, verify

api_router = APIRouter()
api_router.include_router(sessions.router, prefix="/sessions", tags=["Sessions"])
api_router.include_router(verify.router, prefix="/verify", tags=["Module demo (development only)"])
