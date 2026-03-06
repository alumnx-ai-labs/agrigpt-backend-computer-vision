#!/usr/bin/env python3
"""
upload.py — Upload drone videos to S3.

Usage:
  1. Place .mp4 file(s) in this folder  (tools/upload/)
  2. Run from image-query/:
       python tools/upload/upload.py

The video_id is derived from the filename stem:
  drone.mp4  →  video_id "drone"  →  s3://{bucket}/computer-vision/drone.mp4

IMPORTANT: The video_id MUST match the .SRT filename you will ingest.
  drone.mp4  +  drone.SRT  →  video_id "drone"
"""

import os
import sys
from pathlib import Path

# Resolve image-query/ root so we can load .env
ROOT = Path(__file__).resolve().parent.parent.parent  # image-query/
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv
load_dotenv(ROOT / ".env")

import boto3
from botocore.exceptions import BotoCoreError, ClientError

S3_BUCKET  = os.environ.get("S3_BUCKET", "")
AWS_REGION = os.environ.get("AWS_REGION", "ap-south-1")
UPLOAD_DIR = Path(__file__).resolve().parent


def upload_video(mp4_path: Path) -> None:
    video_id = mp4_path.stem
    s3_key   = f"computer-vision/{video_id}.mp4"
    size_mb  = mp4_path.stat().st_size / 1_000_000

    print(f"\n{'─'*55}")
    print(f"  File     : {mp4_path.name}  ({size_mb:.1f} MB)")
    print(f"  video_id : {video_id}")
    print(f"  S3 key   : s3://{S3_BUCKET}/{s3_key}")
    print(f"{'─'*55}")

    s3 = boto3.client("s3", region_name=AWS_REGION)
    try:
        s3.upload_file(
            str(mp4_path),
            S3_BUCKET,
            s3_key,
            ExtraArgs={"ContentType": "video/mp4"},
        )
        print(f"  ✅ Upload complete → video_id: '{video_id}'")
        print(f"     Now ingest its SRT: place {video_id}.SRT in tools/ingest/ and run ingest_srt.py")
    except (BotoCoreError, ClientError) as exc:
        print(f"  ❌ Upload failed: {exc}")


def main() -> None:
    if not S3_BUCKET:
        print("❌  S3_BUCKET not set in .env — cannot upload.")
        sys.exit(1)

    mp4_files = sorted(UPLOAD_DIR.glob("*.mp4"))
    if not mp4_files:
        print("No .mp4 files found in tools/upload/ — place your video here and re-run.")
        return

    print(f"Found {len(mp4_files)} video(s) to upload.")
    for f in mp4_files:
        upload_video(f)

    print("\nAll uploads done.")


if __name__ == "__main__":
    main()
