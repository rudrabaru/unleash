from fastapi import APIRouter

from app.api.v1.endpoints import eval, sessions

api_router = APIRouter()
api_router.include_router(sessions.router, prefix="/sessions", tags=["Sessions"])
api_router.include_router(eval.router, prefix="/eval", tags=["Evaluation Dashboard"])
