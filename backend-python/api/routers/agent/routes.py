# backend-python/api/routers/agent/routes.py
"""HTTP routes for agent endpoints."""

from __future__ import annotations

from fastapi import APIRouter

from .reply_routes import router as reply_router
from .session_routes import router as session_router

router = APIRouter(tags=["agent"])
router.include_router(session_router)
router.include_router(reply_router)
