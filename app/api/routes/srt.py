"""
SRT API Routes - SRT file ingestion and management endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.srt_parser import store_srt_to_db
from app.config import SRT_PATH, DEFAULT_VIDEO_ID

router = APIRouter(prefix="/srt", tags=["SRT"])


class IngestSRTRequest(BaseModel):
    srt_url: str
    video_id: str = DEFAULT_VIDEO_ID
    overwrite: bool = False


@router.get("")
def serve_srt():
    """Serve the local drone.SRT so POST /ingest-srt can point to this server."""
    if not SRT_PATH.exists():
        raise HTTPException(404, "SRT file not found on this server")
    return PlainTextResponse(
        SRT_PATH.read_text(encoding="utf-8", errors="replace"),
        media_type="text/plain",
    )


@router.post("/ingest")
def ingest_srt(req: IngestSRTRequest, db: Session = Depends(get_db)):
    """
    Fetch SRT from a URL and bulk-insert all telemetry into PostgreSQL.
    
    Dev workflow:
      POST /srt/ingest {"srt_url": "http://localhost:8000/srt", "video_id": "drone", "overwrite": true}
    """
    try:
        result = store_srt_to_db(
            db=db,
            srt_url=req.srt_url,
            video_id=req.video_id,
            overwrite=req.overwrite,
        )
    except Exception as exc:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, str(exc))
    
    if result.get("status") == "error":
        raise HTTPException(422, result["message"])
    
    return result