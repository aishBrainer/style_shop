"""v1 router assembly (§56)."""

from fastapi import APIRouter

from app.api.v1 import admin, assets, auth, catalog, jobs, studio

api_router = APIRouter()
api_router.include_router(auth.router)
api_router.include_router(assets.router)
api_router.include_router(catalog.router)
api_router.include_router(jobs.router)
api_router.include_router(studio.router)
api_router.include_router(admin.router)
