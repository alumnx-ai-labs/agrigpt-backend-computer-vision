#!/usr/bin/env python3
"""
ingest_srt.py — Parse SRT telemetry files and store to PostgreSQL.

Usage:
  1. Place .SRT file(s) in this folder  (tools/ingest/)
     Filename stem MUST match the video_id  (e.g. drone.SRT → video_id "drone")
  2. Run from image-query/:
       python tools/ingest/ingest_srt.py

The linking rule that makes everything work:
  ┌─────────────────────────────────────────────────────────┐
  │  drone.mp4  → S3: computer-vision/drone.mp4             │
  │  drone.SRT  → DB: drone_frames WHERE video_id='drone'   │
  │                                                         │
  │  video.mp4  → S3: computer-vision/video.mp4             │
  │  video.SRT  → DB: drone_frames WHERE video_id='video'   │
  └─────────────────────────────────────────────────────────┘

The filename stem IS the video_id. Keep them identical.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent.parent  # image-query/
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

from app.core.database import SessionLocal
from app.core.srt_parser import parse_srt_content, calculate_fps_from_srt
from app.core.models import DroneFrame

INGEST_DIR = Path(__file__).resolve().parent


def ingest_srt_file(srt_path: Path, overwrite: bool = True) -> None:
    video_id = srt_path.stem

    print(f"\n{'─'*55}")
    print(f"  File     : {srt_path.name}")
    print(f"  video_id : {video_id}")
    print(f"{'─'*55}")

    srt_content = srt_path.read_text(encoding="utf-8", errors="replace")
    fps = calculate_fps_from_srt(srt_content)
    records = parse_srt_content(srt_content)

    if not records:
        print(f"  ❌ No valid SRT blocks found in {srt_path.name}")
        return

    print(f"  Parsed {len(records)} telemetry blocks")

    db = SessionLocal()
    try:
        existing = db.query(DroneFrame).filter(DroneFrame.video_id == video_id).count()

        if existing > 0 and not overwrite:
            print(f"  ⏭  Already ingested ({existing} frames). Set overwrite=True to re-ingest.")
            return

        if existing > 0:
            deleted = db.query(DroneFrame).filter(DroneFrame.video_id == video_id).delete()
            db.commit()
            print(f"  🗑  Cleared {deleted} existing frames for '{video_id}'")

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

        first, last = records[0], records[-1]
        print(f"  ✅ Stored {len(frames)} frames for video_id='{video_id}' @ {fps} fps")
        print(f"     First → frame {first['frame_number']:>5} | t={first['timestamp']:>8.3f}s"
              f" | lat={first['latitude']} lon={first['longitude']} alt={first['altitude']}m")
        print(f"     Last  → frame {last['frame_number']:>5} | t={last['timestamp']:>8.3f}s"
              f" | lat={last['latitude']} lon={last['longitude']} alt={last['altitude']}m")

    except Exception as exc:
        db.rollback()
        print(f"  ❌ DB error: {exc}")
        raise
    finally:
        db.close()


def main() -> None:
    srt_files = sorted(
        list(INGEST_DIR.glob("*.SRT")) + list(INGEST_DIR.glob("*.srt"))
    )

    if not srt_files:
        print("No .SRT files found in tools/ingest/ — place your SRT here and re-run.")
        return

    print(f"Found {len(srt_files)} SRT file(s) to ingest.")
    for f in srt_files:
        ingest_srt_file(f, overwrite=True)

    print("\nAll ingests done.")


if __name__ == "__main__":
    main()
