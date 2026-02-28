# backend-python/app.py
import sys
from contextlib import asynccontextmanager

from api.errors import register_exception_handlers
from api.routers import (
    agent,
    box_detection,
    boxes,
    images,
    jobs,
    logs,
    ocr,
    training,
    translation,
    volumes,
    volumes_memory,
    volumes_sync,
)
from api.routers import (
    settings as settings_router,
)
from core.usecases.ocr import initialize_ocr_runtime
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from infra.db.db import init_db
from infra.domain_bindings import bind_domain_ports
from infra.jobs.runtime import start_jobs_runtime, stop_jobs_runtime
from infra.logging import setup_logging
from settings import settings

setup_logging(settings.log_level)
bind_domain_ports()

sys.stdout.reconfigure(encoding="utf-8")
sys.stderr.reconfigure(encoding="utf-8")


@asynccontextmanager
async def lifespan(_: FastAPI):
    if settings.db_init:
        init_db()

    initialize_ocr_runtime()
    await start_jobs_runtime()
    try:
        yield
    finally:
        await stop_jobs_runtime()


app = FastAPI(title="MangaYaku Python Backend", lifespan=lifespan)
register_exception_handlers(app)

cors_origins = settings.cors_origins
allow_credentials = settings.cors_allow_credentials
if "*" in cors_origins:
    allow_credentials = False

# CORS for dev (relax later if you want)
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins or ["http://localhost:5173"],
    allow_credentials=allow_credentials,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Everything gets prefix /api
app.include_router(volumes.router, prefix="/api")
app.include_router(volumes_sync.router, prefix="/api")
app.include_router(volumes_memory.router, prefix="/api")
app.include_router(images.router, prefix="/api")
app.include_router(boxes.router, prefix="/api")
app.include_router(ocr.router, prefix="/api")
app.include_router(agent.router, prefix="/api")
app.include_router(jobs.router, prefix="/api")
app.include_router(translation.router, prefix="/api")
app.include_router(box_detection.router, prefix="/api")
app.include_router(training.router, prefix="/api")
app.include_router(settings_router.router, prefix="/api")
app.include_router(logs.router, prefix="/api")
