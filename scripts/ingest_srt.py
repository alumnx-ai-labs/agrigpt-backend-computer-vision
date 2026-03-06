"""
One-time SRT ingestion script.

Run:
    cd image-query
    python scripts/ingest_srt.py
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from app.core.srt_parser import parse_srt_content
from app.core.models import DroneFrame, Base
from app.core.database import engine, SessionLocal
from app.config import SRT_PATH, DEFAULT_VIDEO_ID

# Configuration
VIDEO_ID = DEFAULT_VIDEO_ID
S3_URL = f"https://alumnx-agrigpt-computer-vision.s3.ap-south-1.amazonaws.com/computer-vision/{VIDEO_ID}.mp4"


def main():
    """Parse and ingest SRT file into database."""
    if not SRT_PATH.exists():
        print(f"ERROR: {SRT_PATH} not found")
        sys.exit(1)

    print(f"Parsing {SRT_PATH} ...")
    srt_content = SRT_PATH.read_text(encoding="utf-8", errors="replace")
    records = parse_srt_content(srt_content)
    print(f"  {len(records)} frames parsed")

    # Create tables
    Base.metadata.create_all(bind=engine)
    
    db = SessionLocal()

    # Delete existing records
    deleted = db.query(DroneFrame).filter(DroneFrame.video_id == VIDEO_ID).delete()
    if deleted:
        print(f"  Removed {deleted} existing rows for video_id={VIDEO_ID}")
    db.commit()

    # Insert new records
    frames = [
        DroneFrame(
            video_id=VIDEO_ID,
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
    db.close()

    print(f"Done! {len(frames)} frames stored for video_id={VIDEO_ID}")


if __name__ == "__main__":
    main()