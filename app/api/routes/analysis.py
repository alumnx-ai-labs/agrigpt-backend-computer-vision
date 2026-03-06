"""
Analysis API Routes - Area calculation and agricultural analysis endpoints.
"""

import math
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.srt_parser import get_closest_frame_by_timestamp, get_video_fps_from_db
from app.services.telemetry_service import TelemetryService
from app.agents.calc_tools import calculate_gsd
from app.config import VIDEO_WIDTH_PX, VIDEO_HEIGHT_PX, DEFAULT_VIDEO_ID
from app.utils.geo_utils import pixel_to_gps, geodesic_area, shoelace_area

router = APIRouter(prefix="/calculate", tags=["Analysis"])


class CalculateRequest(BaseModel):
    frame: int
    points: list[list[float]]
    video_id: str = None


@router.post("")
def calculate_area(body: CalculateRequest, db: Session = Depends(get_db)):
    """Calculate area for a polygon of 3 or more points."""
    if len(body.points) < 3:
        raise HTTPException(400, "At least 3 points required")

    video_id = body.video_id or DEFAULT_VIDEO_ID
    fps = get_video_fps_from_db(db, video_id)
    frame_time = body.frame / fps

    row = get_closest_frame_by_timestamp(db, video_id, frame_time)
    if not row:
        raise HTTPException(503, "Telemetry unavailable — ingest the SRT first")

    telem = {
        "rel_alt_m": row.altitude,
        "lat": row.latitude,
        "lon": row.longitude,
        "frame_num": row.frame_number,
    }

    gsd = calculate_gsd(telem["rel_alt_m"])
    clat = telem.get("lat")
    clon = telem.get("lon")
    has_gps = bool(clat and clon and not (clat == 0.0 and clon == 0.0))

    pts = [(p[0], p[1]) for p in body.points]

    if has_gps:
        # GPS → Geodesic area on WGS-84 ellipsoid (most accurate)
        gps_pts = [pixel_to_gps(x, y, VIDEO_WIDTH_PX, VIDEO_HEIGHT_PX, gsd, clat, clon) for x, y in pts]
        area_m2 = geodesic_area(gps_pts)
        method = "GPS_Geodesic_WGS84"
    else:
        # Fallback: pixel → metre via GSD → Shoelace
        pts_m = [(x * gsd, y * gsd) for x, y in pts]
        area_m2 = shoelace_area(pts_m)
        gps_pts = None
        method = "GSD_Shoelace"

    return {
        "frame": body.frame,
        "method": method,
        "alt_m": telem["rel_alt_m"],
        "gsd_cm_px": round(gsd * 100, 6),
        "area_m2": round(area_m2, 4),
        "area_sqft": round(area_m2 * 10.7639, 2),
        "area_sq_yards": round(area_m2 * 1.19599, 2),
        "area_cents": round(area_m2 / 40.4686, 6),
        "area_acres": round(area_m2 / 4046.86, 8),
        "gps_centre": [clat, clon] if has_gps else None,
        "gps_markers": [[lat, lon] for lat, lon in gps_pts] if has_gps else None,
    }