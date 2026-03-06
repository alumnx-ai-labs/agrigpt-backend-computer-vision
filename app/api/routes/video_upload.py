"""
Video Upload API Routes - Upload video and SRT files to S3 with database tracking.

Provides endpoints for:
- Uploading video + SRT files as a pair
- Tracking video metadata in database
- Listing uploaded videos
"""

import os
import uuid
import tempfile
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session
from pydantic import BaseModel
import boto3

from app.core.database import get_db
from app.core.models import Video, DroneFrame
from app.core.srt_parser import parse_srt_content
from app.config import S3_BUCKET, AWS_REGION

router = APIRouter(prefix="/videos", tags=["Video Upload"])


# S3 client
def get_s3_client():
    """Get S3 client."""
    return boto3.client("s3", region_name=AWS_REGION)


class VideoUploadResponse(BaseModel):
    video_key: str
    title: str
    video_s3_key: str
    srt_s3_key: str
    status: str
    message: str


@router.post("/upload", response_model=VideoUploadResponse)
async def upload_video_and_srt(
    video_file: UploadFile = File(..., description="Video file (MP4)"),
    srt_file: UploadFile = File(..., description="SRT telemetry file"),
    title: str = Form(..., description="Title for the video"),
    description: str = Form(None, description="Optional description"),
    video_key: str = Form(None, description="Unique key (auto-generated if not provided)"),
    db: Session = Depends(get_db)
):
    """
    Upload a video and its corresponding SRT file to S3.
    
    Both files are stored with the same video_key for easy matching:
    - Video: s3://bucket/videos/{video_key}/video.mp4
    - SRT: s3://bucket/videos/{video_key}/telemetry.srt
    
    The video_key is stored in the database to link both files.
    
    Args:
        video_file: MP4 video file
        srt_file: SRT telemetry file with GPS/altitude data
        title: Human-readable title
        description: Optional description
        video_key: Unique identifier (auto-generated UUID if not provided)
    
    Returns:
        VideoUploadResponse with video_key and S3 paths
    """
    # Generate video_key if not provided
    if not video_key:
        video_key = str(uuid.uuid4())[:8]  # Short UUID for readability
    
    # Check if video_key already exists
    existing = db.query(Video).filter(Video.video_key == video_key).first()
    if existing:
        raise HTTPException(400, f"video_key '{video_key}' already exists. Use a different key or omit to auto-generate.")
    
    # Validate file types
    if not video_file.filename.lower().endswith(('.mp4', '.mov', '.avi')):
        raise HTTPException(400, "Video file must be MP4, MOV, or AVI")
    
    if not srt_file.filename.lower().endswith('.srt'):
        raise HTTPException(400, "SRT file must have .srt extension")
    
    # S3 keys
    video_s3_key = f"videos/{video_key}/video.mp4"
    srt_s3_key = f"videos/{video_key}/telemetry.srt"
    
    try:
        s3_client = get_s3_client()
        
        # Upload video to S3
        video_content = await video_file.read()
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=video_s3_key,
            Body=video_content,
            ContentType="video/mp4"
        )
        
        # Upload SRT to S3
        srt_content = await srt_file.read()
        s3_client.put_object(
            Bucket=S3_BUCKET,
            Key=srt_s3_key,
            Body=srt_content,
            ContentType="text/plain"
        )
        
        # Parse SRT to get metadata
        srt_text = srt_content.decode('utf-8', errors='replace')
        frames_data = parse_srt_content(srt_text)
        
        # Calculate video duration from SRT
        video_duration = None
        if frames_data:
            video_duration = frames_data[-1].get('timestamp', 0)
        
        # Create Video record in database
        video_record = Video(
            video_key=video_key,
            title=title,
            description=description,
            video_s3_key=video_s3_key,
            srt_s3_key=srt_s3_key,
            video_duration_sec=video_duration,
            status="ready",
            is_active=True,
        )
        db.add(video_record)
        db.flush()  # Get the ID
        
        # Store all frames in database
        frame_objects = [
            DroneFrame(
                video_id=video_key,
                frame_number=f["frame_number"],
                timestamp=f["timestamp"],
                latitude=f["latitude"],
                longitude=f["longitude"],
                altitude=f["altitude"],
            )
            for f in frames_data
        ]
        db.bulk_save_objects(frame_objects)
        db.commit()
        
        return VideoUploadResponse(
            video_key=video_key,
            title=title,
            video_s3_key=video_s3_key,
            srt_s3_key=srt_s3_key,
            status="ready",
            message=f"Uploaded video with {len(frames_data)} telemetry frames"
        )
        
    except Exception as e:
        db.rollback()
        raise HTTPException(500, f"Upload failed: {str(e)}")


@router.get("/list")
def list_uploaded_videos(
    active_only: bool = True,
    db: Session = Depends(get_db)
):
    """
    List all uploaded videos.
    
    Args:
        active_only: If True, only return active videos
    
    Returns:
        List of video records with metadata
    """
    query = db.query(Video)
    if active_only:
        query = query.filter(Video.is_active == True)
    
    videos = query.order_by(Video.created_at.desc()).all()
    
    return {
        "videos": [
            {
                "video_key": v.video_key,
                "title": v.title,
                "description": v.description,
                "video_s3_key": v.video_s3_key,
                "srt_s3_key": v.srt_s3_key,
                "duration_sec": v.video_duration_sec,
                "fps": v.fps,
                "width": v.width,
                "height": v.height,
                "status": v.status,
                "created_at": v.created_at.isoformat() if v.created_at else None,
            }
            for v in videos
        ],
        "total": len(videos)
    }


@router.get("/{video_key}")
def get_video_info(video_key: str, db: Session = Depends(get_db)):
    """
    Get detailed info for a specific video.
    
    Args:
        video_key: Unique video identifier
    
    Returns:
        Video metadata and frame count
    """
    video = db.query(Video).filter(Video.video_key == video_key).first()
    if not video:
        raise HTTPException(404, f"Video '{video_key}' not found")
    
    # Count frames
    frame_count = db.query(DroneFrame).filter(DroneFrame.video_id == video_key).count()
    
    return {
        "video_key": video.video_key,
        "title": video.title,
        "description": video.description,
        "video_s3_key": video.video_s3_key,
        "srt_s3_key": video.srt_s3_key,
        "duration_sec": video.video_duration_sec,
        "fps": video.fps,
        "width": video.width,
        "height": video.height,
        "status": video.status,
        "is_active": video.is_active,
        "frame_count": frame_count,
        "created_at": video.created_at.isoformat() if video.created_at else None,
        "updated_at": video.updated_at.isoformat() if video.updated_at else None,
    }


@router.delete("/{video_key}")
def delete_video(video_key: str, db: Session = Depends(get_db)):
    """
    Delete a video and its associated data.
    
    Removes:
    - Video record from database
    - All associated frames from database
    - Files from S3 (optional, based on query param)
    
    Args:
        video_key: Unique video identifier
    
    Returns:
        Deletion confirmation
    """
    video = db.query(Video).filter(Video.video_key == video_key).first()
    if not video:
        raise HTTPException(404, f"Video '{video_key}' not found")
    
    # Delete frames from database
    frames_deleted = db.query(DroneFrame).filter(DroneFrame.video_id == video_key).delete()
    
    # Delete video record
    db.delete(video)
    db.commit()
    
    # Optionally delete from S3
    try:
        s3_client = get_s3_client()
        s3_client.delete_object(Bucket=S3_BUCKET, Key=video.video_s3_key)
        s3_client.delete_object(Bucket=S3_BUCKET, Key=video.srt_s3_key)
    except Exception as e:
        print(f"Warning: Could not delete S3 objects: {e}")
    
    return {
        "video_key": video_key,
        "frames_deleted": frames_deleted,
        "message": f"Video '{video_key}' and {frames_deleted} frames deleted"
    }


@router.patch("/{video_key}/status")
def update_video_status(
    video_key: str,
    status: str = Form(...),
    is_active: bool = Form(None),
    db: Session = Depends(get_db)
):
    """
    Update video status or active state.
    
    Args:
        video_key: Unique video identifier
        status: New status (uploading, processing, ready, error)
        is_active: New active state
    
    Returns:
        Updated video info
    """
    video = db.query(Video).filter(Video.video_key == video_key).first()
    if not video:
        raise HTTPException(404, f"Video '{video_key}' not found")
    
    valid_statuses = ["uploading", "processing", "ready", "error"]
    if status not in valid_statuses:
        raise HTTPException(400, f"Invalid status. Must be one of: {valid_statuses}")
    
    video.status = status
    if is_active is not None:
        video.is_active = is_active
    
    db.commit()
    
    return {
        "video_key": video.video_key,
        "status": video.status,
        "is_active": video.is_active,
        "message": "Status updated"
    }