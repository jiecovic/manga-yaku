# backend-python/api/routers/images.py
from pathlib import Path

from config import VOLUMES_ROOT, safe_join
from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse

router = APIRouter(tags=["images"])


@router.get("/images/{volume_id}/{filename}")
async def get_image(volume_id: str, filename: str):
    try:
        img_path: Path = safe_join(VOLUMES_ROOT, volume_id, filename)
    except ValueError as e:
        raise HTTPException(status_code=400, detail="Invalid path") from e

    if not img_path.exists() or not img_path.is_file():
        raise HTTPException(status_code=404, detail="Not found")

    # Optional: disable caching in dev
    return FileResponse(
        img_path,
        headers={
            "Cache-Control": "no-cache, no-store, must-revalidate",
            "Pragma": "no-cache",
            "Expires": "0",
        },
    )
