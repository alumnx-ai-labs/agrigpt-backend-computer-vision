"""
One-shot pipeline script:
  1. List objects under computer-vision/ and delete any duplicate video.mp4
  2. Upload image-query/video.MP4 to S3
  3. Read image-query/video.SRT from disk, parse + store all frames to PostgreSQL

Run:
    cd image-query
    python scripts/upload_to_s3.py
"""

import os
import sys
import re
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import boto3
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.config import BASE_DIR, AWS_REGION
from app.core.models import Base, DroneFrame
from app.core.srt_parser import parse_srt_content

# Load environment
load_dotenv()

# Paths
LOCAL_MP4 = BASE_DIR / "video.MP4"
LOCAL_SRT = BASE_DIR / "video.SRT"

# S3 config
BUCKET = os.getenv("S3_BUCKET", "alumnx-agrigpt-computer-vision")
S3_KEY = "computer-vision/video.mp4"
REGION = AWS_REGION

# DB config
from urllib.parse import quote_plus
DB_URL = "postgresql://{user}:{pw}@{host}:{port}/{db}".format(
    user=quote_plus(os.getenv("DB_USER", "postgres")),
    pw=quote_plus(os.getenv("DB_PASSWORD", "password")),
    host=os.getenv("DB_HOST", "localhost"),
    port=os.getenv("DB_PORT", "5432"),
    db=os.getenv("DB_NAME", "drone_db"),
)

VIDEO_ID = "video_001"

# S3 client
s3 = boto3.client(
    "s3",
    region_name=REGION,
    aws_access_key_id=os.getenv("AWS_ACCESS_KEY_ID"),
    aws_secret_access_key=os.getenv("AWS_SECRET_ACCESS_KEY"),
)


def delete_duplicates():
    """Delete duplicate MP4 files in S3."""
    print(f"Listing s3://{BUCKET}/computer-vision/ ...")
    resp = s3.list_objects_v2(Bucket=BUCKET, Prefix="computer-vision/")
    objects = resp.get("Contents", [])

    mp4_keys = [o["Key"] for o in objects if o["Key"].endswith(".mp4") or o["Key"].endswith(".MP4")]
    print(f"  Found {len(mp4_keys)} MP4 object(s): {mp4_keys}")

    if len(mp4_keys) > 1:
        to_delete = [k for k in mp4_keys if k != S3_KEY]
        for key in to_delete:
            s3.delete_object(Bucket=BUCKET, Key=key)
            print(f"  Deleted duplicate: s3://{BUCKET}/{key}")
    else:
        print("  No duplicates found.")


def upload_video():
    """Upload video.MP4 to S3."""
    if not LOCAL_MP4.exists():
        print(f"ERROR: {LOCAL_MP4} not found", file=sys.stderr)
        sys.exit(1)

    uploaded = 0

    def _progress(chunk):
        nonlocal uploaded
        uploaded += chunk
        size_mb = uploaded / 1_048_576
        print(f"  {size_mb:.1f} MB uploaded", end="\r")

    print(f"\nUploading {LOCAL_MP4.name} → s3://{BUCKET}/{S3_KEY} ...")
    s3.upload_file(
        str(LOCAL_MP4), BUCKET, S3_KEY,
        ExtraArgs={"ContentType": "video/mp4"},
        Callback=_progress,
    )
    s3_url = f"https://{BUCKET}.s3.{REGION}.amazonaws.com/{S3_KEY}"
    print(f"\nDone! {s3_url}")
    return s3_url


def ingest_srt(s3_url: str):
    """Parse SRT and store to database."""
    if not LOCAL_SRT.exists():
        print(f"ERROR: {LOCAL_SRT} not found", file=sys.stderr)
        sys.exit(1)

    print(f"\nParsing {LOCAL_SRT.name} ...")
    srt_content = LOCAL_SRT.read_text(encoding="utf-8", errors="replace")
    records = parse_srt_content(srt_content)
    print(f"  Parsed {len(records)} frames")

    engine = create_engine(DB_URL, echo=False)
    Base.metadata.create_all(bind=engine)
    Session = sessionmaker(bind=engine)
    db = Session()

    deleted = db.query(DroneFrame).filter(DroneFrame.video_id == VIDEO_ID).delete()
    if deleted:
        print(f"  Removed {deleted} old rows for video_id={VIDEO_ID}")
    db.commit()

    print(f"  Inserting {len(records)} frames into drone_frames ...")
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

    print(f"  Done! {len(frames)} frames stored for video_id={VIDEO_ID}")


if __name__ == "__main__":
    delete_duplicates()
    s3_url = upload_video()
    ingest_srt(s3_url)