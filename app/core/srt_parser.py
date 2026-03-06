"""
SRT Parser module - Parse DJI telemetry from SRT files and store to PostgreSQL.

Supports two DJI SRT altitude formats:
  [altitude: 41.20]                    — newer DJI firmware
  [rel_alt: 5.000 abs_alt: 687.112]   — DJI Mini / older firmware
"""

import re
import requests
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import func as sqlfunc

from app.core.models import DroneFrame


# =============================================================================
# SRT PARSING FUNCTIONS
# =============================================================================

def calculate_fps_from_srt(srt_content: str) -> float:
    """
    Calculate FPS from SRT DiffTime values.

    Handles both formats:
      FrameCnt: 1, DiffTime: 16ms    (drone.SRT)
      SrtCnt : 1, DiffTime : 16ms   (video.SRT)

    Averages the first 100 DiffTime values for accuracy.
    Falls back to 59.94 if not found.
    """
    diff_times = re.findall(r"DiffTime\s*:\s*(\d+)ms", srt_content)
    if not diff_times:
        return 59.94
    sample = [int(d) for d in diff_times[:100]]
    avg_ms = sum(sample) / len(sample)
    return round(1000.0 / avg_ms, 6)


def get_video_fps_from_db(db: Session, video_id: str) -> float:
    """
    Compute FPS from the drone_frames table for a given video.

    Uses: (max_frame_number - min_frame_number) / (max_timestamp - min_timestamp)
    This is the most accurate runtime method — derived from the ingested data.
    Falls back to 59.94 if data is insufficient.
    """
    from sqlalchemy import func as _f
    row = (
        db.query(
            (_f.max(DroneFrame.frame_number) - _f.min(DroneFrame.frame_number)).label("frames"),
            (_f.max(DroneFrame.timestamp)    - _f.min(DroneFrame.timestamp)).label("duration"),
        )
        .filter(DroneFrame.video_id == video_id)
        .first()
    )
    if row and row.duration and row.duration > 0:
        return round(row.frames / row.duration, 6)
    return 59.94


def fetch_srt_from_url(url: str) -> str:
    """Fetch raw SRT file content from a URL."""
    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def parse_timestamp_to_seconds(ts: str) -> float:
    """Convert SRT timestamp '00:00:12,533' → 12.533 seconds."""
    ts = ts.replace(",", ".")
    parts = ts.split(":")
    h, m, s = int(parts[0]), int(parts[1]), float(parts[2])
    return h * 3600 + m * 60 + s


def extract_float(pattern: str, text: str, default: float = 0.0) -> float:
    """Extract a float value using a regex pattern."""
    match = re.search(pattern, text)
    return float(match.group(1)) if match else default


def extract_altitude(text: str) -> float:
    """
    Extract altitude in metres from either:
      [altitude: 41.20]                  — newer DJI / files/ format
      [rel_alt: 5.000 abs_alt: 687.112]  — DJI Mini / older firmware
    """
    m = re.search(r"\[altitude:\s*([-\d.]+)\]", text)
    if m:
        return float(m.group(1))
    m = re.search(r"\[rel_alt:\s*([-\d.]+)", text)
    if m:
        return float(m.group(1))
    return 0.0


def parse_srt_block(block_text: str, frame_number: int) -> Optional[Dict[str, Any]]:
    """Parse a single SRT subtitle block into a telemetry dict."""
    lines = block_text.strip().splitlines()
    if len(lines) < 3:
        return None

    # Timestamp: "00:00:00,033 --> 00:00:00,066"
    time_match = re.match(r"(\d+:\d+:\d+[,\.]\d+)", lines[1])
    if not time_match:
        return None
    timestamp = parse_timestamp_to_seconds(time_match.group(1))

    full_text = " ".join(lines[2:])

    return {
        "frame_number": frame_number,
        "timestamp": timestamp,
        "latitude": extract_float(r"\[latitude:\s*([-\d.]+)\]", full_text),
        "longitude": extract_float(r"\[longitude:\s*([-\d.]+)\]", full_text),
        "altitude": extract_altitude(full_text),
    }


def parse_srt_content(srt_content: str) -> List[Dict[str, Any]]:
    """
    Parse full SRT file content into a list of telemetry records.
    Each SRT block = one record; frame_number is 1-based sequential index.
    """
    blocks = re.split(r"\n\s*\n", srt_content.strip())
    records = []
    for i, block in enumerate(blocks):
        parsed = parse_srt_block(block, frame_number=i + 1)
        if parsed:
            records.append(parsed)
    return records


# =============================================================================
# DATABASE STORAGE FUNCTIONS
# =============================================================================

def store_srt_to_db(
    db: Session,
    srt_url: str,
    video_id: str,
    overwrite: bool = False,
) -> Dict[str, Any]:
    """
    Full pipeline: fetch SRT from URL → parse → bulk insert into drone_frames.

    Returns a summary dict.
    """
    print(f"📡 Fetching SRT from: {srt_url}")
    srt_content = fetch_srt_from_url(srt_url)

    fps = calculate_fps_from_srt(srt_content)
    print(f"🎞️  Detected FPS: {fps}")

    print("🔍 Parsing SRT content…")
    records = parse_srt_content(srt_content)

    if not records:
        return {"status": "error", "message": "No valid SRT blocks parsed"}

    existing = db.query(DroneFrame).filter(DroneFrame.video_id == video_id).count()
    if existing > 0 and not overwrite:
        print(f"⏭️  Skipping ingest — {existing} frames already exist for video_id={video_id}")
        return {
            "status": "already_exists",
            "video_id": video_id,
            "total_frames": existing,
            "message": f"SRT already ingested ({existing} frames). Use overwrite=true to re-ingest.",
        }

    if overwrite:
        deleted = db.query(DroneFrame).filter(DroneFrame.video_id == video_id).delete()
        print(f"🗑️  Deleted {deleted} existing records for video_id={video_id}")
        db.commit()

    frames = [
        DroneFrame(
            video_id=video_id,
            frame_number=r["frame_number"],
            timestamp=r["timestamp"],
            latitude=r["latitude"],
            longitude=r["longitude"],
            altitude=r["altitude"],
        )
        for r in records
    ]

    db.bulk_save_objects(frames)
    db.commit()

    print(f"✅ Stored {len(frames)} frames for video_id={video_id} @ {fps} fps")
    return {
        "status": "success",
        "video_id": video_id,
        "total_frames": len(frames),
        "fps": fps,
        "first_frame": records[0],
        "last_frame": records[-1],
    }


# =============================================================================
# TELEMETRY FETCH FUNCTIONS
# =============================================================================

def get_telemetry_for_frame(db: Session, video_id: str, frame_number: int) -> Optional[DroneFrame]:
    """Exact lookup by video_id + frame_number (sequential SRT index)."""
    return (
        db.query(DroneFrame)
        .filter(
            DroneFrame.video_id == video_id,
            DroneFrame.frame_number == frame_number,
        )
        .first()
    )


def get_closest_frame_by_timestamp(db: Session, video_id: str, timestamp: float) -> Optional[DroneFrame]:
    """
    Find the SRT frame whose timestamp is closest to the given value.
    Use this when converting video time → telemetry (most reliable approach).
    """
    return (
        db.query(DroneFrame)
        .filter(DroneFrame.video_id == video_id)
        .order_by(sqlfunc.abs(DroneFrame.timestamp - timestamp))
        .first()
    )