"""
Video Service - Video streaming and frame extraction.

Handles:
- Video streaming from S3 or local files
- Frame extraction using OpenCV
- Byte-range streaming for video playback
"""

import os
from pathlib import Path
from typing import Optional, Tuple

import boto3
import cv2
import numpy as np

from app.config import (
    BASE_DIR,
    S3_BUCKET,
    AWS_REGION,
    VIDEO_CDN_URL,
    VIDEO_S3_KEY,
    VIDEO_WIDTH_PX,
    VIDEO_HEIGHT_PX,
    VIDEO_FPS,
    DEFAULT_VIDEO_ID,
    S3_VIDEO_PREFIX,
)


class VideoService:
    """
    Service for video streaming and frame extraction.
    
    Supports:
    - S3 pre-signed URLs for streaming
    - CDN URLs for video delivery
    - Local file streaming with byte-range support
    - Frame extraction at specific timestamps
    """
    
    def __init__(self):
        self.s3_bucket = S3_BUCKET
        self.aws_region = AWS_REGION
        self.video_cdn_url = VIDEO_CDN_URL
        self.video_s3_key = VIDEO_S3_KEY
        self.video_width = VIDEO_WIDTH_PX
        self.video_height = VIDEO_HEIGHT_PX
        self.video_fps = VIDEO_FPS
        self.default_video_id = DEFAULT_VIDEO_ID
        self.s3_video_prefix = S3_VIDEO_PREFIX
        self._s3_client = None
    
    @property
    def s3_client(self):
        """Lazy initialization of S3 client."""
        if self._s3_client is None and self.s3_bucket:
            self._s3_client = boto3.client("s3", region_name=self.aws_region)
        return self._s3_client
    
    # =========================================================================
    # VIDEO SOURCE RESOLUTION
    # =========================================================================
    
    def get_video_source(self, video_id: str) -> Optional[str]:
        """
        Get video source URL (S3 pre-signed or CDN).
        
        Args:
            video_id: Video identifier
        
        Returns:
            Video URL or None for local files
        """
        # Use VIDEO_S3_KEY for the default video (drone)
        if video_id == self.default_video_id and self.video_s3_key:
            s3_key = self.video_s3_key
        else:
            s3_key = f"{self.s3_video_prefix}/{video_id}.mp4"
        
        if self.video_cdn_url:
            # Extract filename from s3_key for CDN URL
            filename = s3_key.split("/")[-1]
            return f"{self.video_cdn_url.rstrip('/')}/{filename}"
        
        if self.s3_bucket and self.s3_client:
            return self.s3_client.generate_presigned_url(
                "get_object",
                Params={"Bucket": self.s3_bucket, "Key": s3_key},
                ExpiresIn=3600,
            )
        
        return None
    
    def get_local_video_path(self, video_id: str) -> Path:
        """Get path to local video file."""
        return BASE_DIR / f"{video_id}.mp4"
    
    # =========================================================================
    # FRAME EXTRACTION
    # =========================================================================
    
    def extract_frame_at_time(
        self,
        time_sec: float,
        video_id: Optional[str] = None
    ) -> Tuple[bool, Optional[np.ndarray], int]:
        """
        Extract a frame from video at specific time.
        
        Args:
            time_sec: Time in seconds
            video_id: Video identifier (uses default if not provided)
        
        Returns:
            Tuple of (success, frame_array, frame_number)
        """
        vid = video_id or self.default_video_id
        frame_num = max(1, round(time_sec * self.video_fps))
        
        # Get video source
        video_source = self.get_video_source(vid)
        
        if isinstance(video_source, str):
            cap = cv2.VideoCapture(video_source)
        else:
            local_path = self.get_local_video_path(vid)
            if not local_path.exists():
                return False, None, frame_num
            cap = cv2.VideoCapture(str(local_path))
        
        if not cap.isOpened():
            cap.release()
            return False, None, frame_num
        
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_num)
        ok, frame = cap.read()
        cap.release()
        
        return ok, frame, frame_num
    
    def extract_frame_bytes_at_time(
        self,
        time_sec: float,
        video_id: Optional[str] = None,
        quality: int = 95
    ) -> Tuple[bool, Optional[bytes], int]:
        """
        Extract frame as JPEG bytes at specific time.
        
        Args:
            time_sec: Time in seconds
            video_id: Video identifier
            quality: JPEG quality (1-100)
        
        Returns:
            Tuple of (success, jpeg_bytes, frame_number)
        """
        ok, frame, frame_num = self.extract_frame_at_time(time_sec, video_id)
        
        if not ok or frame is None:
            return False, None, frame_num
        
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, quality])
        if not ok:
            return False, None, frame_num
        
        return True, buf.tobytes(), frame_num
    
    # =========================================================================
    # S3 VIDEO LISTING
    # =========================================================================
    
    def list_s3_videos(self) -> list:
        """List *.mp4 files under the configured S3 video prefix."""
        if not self.s3_bucket or not self.s3_client:
            return []

        try:
            resp = self.s3_client.list_objects_v2(
                Bucket=self.s3_bucket,
                Prefix=f"{self.s3_video_prefix}/",
            )
            videos = []
            for obj in resp.get("Contents", []):
                key = obj["Key"]
                if key.endswith(".mp4"):
                    video_id = key.split("/")[-1].replace(".mp4", "")
                    videos.append({"video_id": video_id, "s3_key": key, "source": "s3"})
            return videos
        except Exception:
            return []
    
    # =========================================================================
    # STREAMING HELPERS
    # =========================================================================
    
    def get_streaming_info(self, video_id: str) -> dict:
        """
        Get streaming info for a video.
        
        Returns redirect URL for S3/CDN or local file info.
        """
        video_source = self.get_video_source(video_id)
        
        if video_source:
            return {
                "type": "redirect",
                "url": video_source,
                "source": "cdn" if self.video_cdn_url else "s3",
            }
        
        local_path = self.get_local_video_path(video_id)
        if local_path.exists():
            return {
                "type": "local",
                "path": str(local_path),
                "size": local_path.stat().st_size,
                "source": "local",
            }
        
        return {"type": "not_found", "error": f"Video {video_id} not found"}