from fastapi import APIRouter

from app.api.endpoints import agents, imports, remote, search, sessions

api_router = APIRouter(prefix="/api/v1")
api_router.include_router(agents.router)
api_router.include_router(sessions.router)
api_router.include_router(imports.router)
api_router.include_router(search.router)
api_router.include_router(remote.router)
