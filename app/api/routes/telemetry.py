"""
Telemetry API Routes - Frame telemetry lookup endpoints.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.models import DroneFrame
from app.services.telemetry_service import TelemetryService
from app.config import DEFAULT_VIDEO_ID

router = APIRouter(prefix="/telemetry", tags=["Telemetry"])


@router.get("/{frame_num}")
def get_telemetry(frame_num: int, video_id: str = DEFAULT_VIDEO_ID, db: Session = Depends(get_db)):
    """Get telemetry for a specific frame number."""
    telem = TelemetryService.get_telemetry(db, video_id, frame_num)
    if not telem:
        raise HTTPException(503, "Telemetry unavailable — call POST /ingest-srt first")
    return {**telem, "requested_frame": frame_num}


@router.get("/video/{video_id}/frames")
def list_video_frames(video_id: str, db: Session = Depends(get_db)):
    """List all stored SRT frames for a video."""
    frames = (
        db.query(DroneFrame)
        .filter(DroneFrame.video_id == video_id)
        .order_by(DroneFrame.frame_number)
        .all()
    )
    if not frames:
        raise HTTPException(404, f"No frames found for video_id={video_id}")
    return {
        "video_id": video_id,
        "total_frames": len(frames),
        "frames": [
            {
                "id": f.id,
                "frame_number": f.frame_number,
                "timestamp": f.timestamp,
                "latitude": f.latitude,
                "longitude": f.longitude,
                "altitude": f.altitude,
            }
            for f in frames
        ],
    }


@router.delete("/video/{video_id}/frames")
def delete_video_frames(video_id: str, db: Session = Depends(get_db)):
    """Delete all stored SRT frames for a video_id."""
    deleted = db.query(DroneFrame).filter(DroneFrame.video_id == video_id).delete()
    db.commit()
    return {"video_id": video_id, "deleted": deleted}