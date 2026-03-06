"""
Storage Service - S3 and local file storage operations.

Handles:
- Uploading frames to S3 or local storage
- Fetching stored frames
- Managing frame metadata in PostgreSQL (replaces frames_index.json)
"""

import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, List, Dict, Any

import boto3
from sqlalchemy.orm import Session

from app.config import (
    S3_BUCKET,
    AWS_REGION,
    FRAMES_DIR,
    S3_FRAMES_PREFIX,
)
from app.core.models import CapturedFrame


class StorageService:
    """
    Service for managing frame storage in S3 or local filesystem.

    Frame metadata is persisted in PostgreSQL (captured_frames table).
    Prioritizes S3 storage when configured, falls back to local storage.
    """

    def __init__(self):
        self.s3_bucket = S3_BUCKET
        self.aws_region = AWS_REGION
        self.frames_dir = FRAMES_DIR
        self.s3_frames_prefix = S3_FRAMES_PREFIX
        self._s3_client = None

    @property
    def s3_client(self):
        """Lazy initialization of S3 client."""
        if self._s3_client is None and self.s3_bucket:
            self._s3_client = boto3.client("s3", region_name=self.aws_region)
        return self._s3_client

    # =========================================================================
    # FRAME METADATA (PostgreSQL)
    # =========================================================================

    def get_frame_entry(self, frame_id: str, db: Session) -> Optional[Dict[str, Any]]:
        """Get a frame entry from the database."""
        row = db.query(CapturedFrame).filter(CapturedFrame.frame_id == frame_id).first()
        return self._row_to_dict(row) if row else None

    def get_frames_by_video(self, video_id: str, db: Session) -> List[Dict[str, Any]]:
        """Get all frame entries for a video, newest first."""
        rows = (
            db.query(CapturedFrame)
            .filter(CapturedFrame.video_id == video_id)
            .order_by(CapturedFrame.captured_at.desc())
            .all()
        )
        return [self._row_to_dict(r) for r in rows]

    def _add_frame_to_db(self, db: Session, entry: Dict[str, Any]) -> None:
        """Insert a frame entry into the database."""
        row = CapturedFrame(
            frame_id=entry["frame_id"],
            video_id=entry["video_id"],
            frame_num=entry["frame_num"],
            time_sec=entry["time_sec"],
            s3_key=entry.get("s3_key"),
            storage=entry.get("storage", "local"),
            telemetry=entry.get("telemetry"),
            gsd_cm_px=entry.get("gsd_cm_px"),
        )
        db.add(row)
        db.commit()
        db.refresh(row)

    @staticmethod
    def _row_to_dict(row: CapturedFrame) -> Dict[str, Any]:
        return {
            "frame_id": row.frame_id,
            "video_id": row.video_id,
            "frame_num": row.frame_num,
            "time_sec": row.time_sec,
            "s3_key": row.s3_key,
            "storage": row.storage,
            "telemetry": row.telemetry,
            "gsd_cm_px": row.gsd_cm_px,
            "captured_at": row.captured_at.isoformat() if row.captured_at else None,
        }

    # =========================================================================
    # S3 OPERATIONS
    # =========================================================================

    def upload_frame(self, data: bytes, key: str) -> bool:
        """Upload frame bytes to S3. Returns True on success."""
        if not self.s3_client:
            return False
        try:
            self.s3_client.put_object(
                Bucket=self.s3_bucket,
                Key=key,
                Body=data,
                ContentType="image/jpeg",
            )
            return True
        except Exception as exc:
            print(f"[StorageService] S3 upload failed: {exc}")
            return False

    def fetch_frame(self, key: str) -> Optional[bytes]:
        """Fetch frame bytes from S3. Returns None on failure."""
        if not self.s3_client:
            return None
        try:
            resp = self.s3_client.get_object(Bucket=self.s3_bucket, Key=key)
            return resp["Body"].read()
        except Exception as exc:
            print(f"[StorageService] S3 fetch failed: {exc}")
            return None

    # =========================================================================
    # LOCAL FALLBACK
    # =========================================================================

    def store_frame_local(self, data: bytes, frame_id: str) -> Path:
        """Store frame bytes on local disk. Returns file path."""
        self.frames_dir.mkdir(exist_ok=True, parents=True)
        local_path = self.frames_dir / f"{frame_id}.jpg"
        local_path.write_bytes(data)
        return local_path

    def fetch_frame_local(self, frame_id: str) -> Optional[bytes]:
        """Fetch frame bytes from local disk. Returns None if not found."""
        local_path = self.frames_dir / f"{frame_id}.jpg"
        if local_path.exists():
            return local_path.read_bytes()
        return None

    # =========================================================================
    # HIGH-LEVEL FRAME STORAGE
    # =========================================================================

    def get_frame_bytes(self, frame_id: str, db: Session) -> Optional[bytes]:
        """
        Get frame bytes from S3 or local storage.

        Looks up storage location from DB, tries S3 first, falls back to local.
        """
        entry = self.get_frame_entry(frame_id, db)
        if not entry:
            return None

        if entry.get("storage") == "s3" and entry.get("s3_key"):
            data = self.fetch_frame(entry["s3_key"])
            if data:
                return data

        return self.fetch_frame_local(frame_id)

    def store_frame(
        self,
        jpeg_bytes: bytes,
        frame_id: str,
        video_id: str,
        frame_num: int,
        time_sec: float,
        telemetry: Dict[str, Any],
        gsd_cm_px: float,
        db: Session,
    ) -> Dict[str, Any]:
        """
        Store a captured frame with metadata.

        Uploads to S3 (or local fallback), then persists metadata to Postgres.

        Returns the frame entry dict.
        """
        storage = "local"
        s3_key = None

        if self.s3_bucket:
            s3_key = f"{self.s3_frames_prefix}/{video_id}/{frame_id}.jpg"
            if self.upload_frame(jpeg_bytes, s3_key):
                storage = "s3"
                print(f"[StorageService] Stored {frame_id} in S3")

        if storage == "local":
            self.store_frame_local(jpeg_bytes, frame_id)
            print(f"[StorageService] Stored {frame_id} locally")

        entry = {
            "frame_id": frame_id,
            "video_id": video_id,
            "frame_num": frame_num,
            "time_sec": time_sec,
            "s3_key": s3_key,
            "storage": storage,
            "captured_at": datetime.now(timezone.utc).isoformat(),
            "telemetry": telemetry,
            "gsd_cm_px": gsd_cm_px,
        }

        self._add_frame_to_db(db, entry)
        return entry
