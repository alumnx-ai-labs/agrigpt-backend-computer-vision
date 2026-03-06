"""
Frames API Routes - Frame capture and query endpoints.
"""

import base64
import uuid
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy.orm import Session
import cv2
import numpy as np

from app.core.database import get_db
from app.core.srt_parser import get_closest_frame_by_timestamp, get_video_fps_from_db
from app.services.storage_service import StorageService
from app.services.video_service import VideoService
from app.agents.calc_tools import calculate_gsd
from app.agents.drone_agent import run_drone_agent
from app.config import DEFAULT_VIDEO_ID

router = APIRouter(prefix="/image-query", tags=["Frames"])

storage_service = StorageService()
video_service = VideoService()


class CaptureRequest(BaseModel):
    time_sec: float
    video_id: str = DEFAULT_VIDEO_ID


class QueryRequest(BaseModel):
    frame_id: str
    points: list[list[float]]
    question: str
    use_llm: bool = False


@router.post("/capture")
def capture_frame(body: CaptureRequest, db: Session = Depends(get_db)):
    """Capture a frame from the video at the given time, sync with telemetry, and store."""
    try:
        fps = get_video_fps_from_db(db, body.video_id)
        frame_num = max(1, round(body.time_sec * fps))

        # Extract frame
        ok, jpeg_bytes, frame_num = video_service.extract_frame_bytes_at_time(
            body.time_sec, body.video_id
        )

        if not ok or jpeg_bytes is None:
            raise HTTPException(500, f"Failed to capture frame at {body.time_sec}s")

        frame_id = str(uuid.uuid4())

        # Telemetry lookup
        row = get_closest_frame_by_timestamp(db, body.video_id, body.time_sec)
        if not row:
            raise HTTPException(503, "Telemetry unavailable — ensure SRT is ingested into DB")

        telem = {
            "rel_alt_m": row.altitude,
            "lat": row.latitude,
            "lon": row.longitude,
            "frame_num": row.frame_number,
        }

        gsd_cm_px = round(calculate_gsd(telem["rel_alt_m"]) * 100, 4)

        # Store frame (metadata → Postgres, bytes → S3/local)
        entry = storage_service.store_frame(
            jpeg_bytes=jpeg_bytes,
            frame_id=frame_id,
            video_id=body.video_id,
            frame_num=frame_num,
            time_sec=body.time_sec,
            telemetry=telem,
            gsd_cm_px=gsd_cm_px,
            db=db,
        )

        return entry

    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(500, f"Capture failed: {str(e)}")


@router.get("/frames")
def list_frames(video_id: str = DEFAULT_VIDEO_ID, db: Session = Depends(get_db)):
    """Return captured frame metadata for a specific video."""
    frames = storage_service.get_frames_by_video(video_id, db)
    return {"frames": frames, "video_id": video_id}


@router.get("/frame/{frame_id}")
def get_frame(frame_id: str, db: Session = Depends(get_db)):
    """Proxy frame bytes from S3 or local storage."""
    data = storage_service.get_frame_bytes(frame_id, db)

    if data is None:
        raise HTTPException(404, "Frame not found")

    return Response(
        content=data,
        media_type="image/jpeg",
        headers={"Cache-Control": "max-age=3600"},
    )


@router.post("/query")
def query_frame(body: QueryRequest, db: Session = Depends(get_db)):
    """
    Annotate a frame with user points and return agricultural analysis.

    Uses PURE CV/MATH by default (no LLM needed, FREE & FAST).
    """
    entry = storage_service.get_frame_entry(body.frame_id, db)
    if not entry:
        raise HTTPException(404, "Frame not found")

    # Fetch frame bytes
    data = storage_service.get_frame_bytes(body.frame_id, db)
    if data is None:
        raise HTTPException(404, "Frame data not found in storage")

    # Decode + annotate
    arr = np.frombuffer(data, dtype=np.uint8)
    frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)

    for i, pt in enumerate(body.points, start=1):
        cx, cy = int(pt[0]), int(pt[1])
        cv2.circle(frame, (cx, cy), 14, (255, 255, 255), 3)
        cv2.circle(frame, (cx, cy), 10, (0, 0, 220), -1)
        cv2.putText(
            frame, str(i), (cx - 5, cy + 5),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2, cv2.LINE_AA,
        )

    _, enc = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 85])
    b64 = base64.b64encode(enc.tobytes()).decode()

    telem = entry.get("telemetry") or {}

    try:
        answer = run_drone_agent(
            question=body.question,
            image_b64=b64,
            points=body.points,
            telemetry=telem,
            use_llm=body.use_llm
        )
    except Exception as exc:
        print(f"[drone_agent] Error: {exc}")
        raise HTTPException(502, f"Drone Agent error: {exc}") from exc

    return {
        "frame_id": body.frame_id,
        "question": body.question,
        "points": body.points,
        "answer": answer,
        "annotated_b64": b64,
        "telemetry": telem,
        "llm_used": body.use_llm,
    }
