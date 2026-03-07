"""
SQLAlchemy models for Drone Frame Intelligence System.

Defines the database schema for:
- Video: Video metadata and S3 storage info
- DroneFrame: Telemetry data from SRT files
- FrameAnalysis: Stored analysis results
"""

from sqlalchemy import Column, Integer, Float, String, Text, DateTime, JSON, UniqueConstraint, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.sql import func

Base = declarative_base()


class Video(Base):
    """
    Video metadata - stores information about uploaded drone videos.
    
    This is the central reference that links videos with their SRT telemetry files.
    Both video and SRT are stored in S3 with a unique key (video_key).
    
    Attributes:
        video_key: Unique identifier for the video/SRT pair (used in both S3 paths and DB)
        title: Human-readable title for the video
        description: Optional description
        video_s3_key: S3 key for the video file (e.g., "videos/{video_key}/video.mp4")
        srt_s3_key: S3 key for the SRT file (e.g., "videos/{video_key}/telemetry.srt")
        video_duration_sec: Duration of the video in seconds
        fps: Frames per second
        width: Video width in pixels
        height: Video height in pixels
        status: Status of the video (uploading, processing, ready, error)
        is_active: Whether this video is available for analysis
    """
    __tablename__ = "videos"
    __table_args__ = (
        UniqueConstraint("video_key", name="uq_video_key"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_key = Column(String(100), nullable=False, unique=True, index=True)
    title = Column(String(255), nullable=True)
    description = Column(Text, nullable=True)
    
    # S3 storage paths
    video_s3_key = Column(String(500), nullable=True)
    srt_s3_key = Column(String(500), nullable=True)
    
    # Video metadata
    video_duration_sec = Column(Float, nullable=True)
    fps = Column(Float, nullable=True, default=59.94)
    width = Column(Integer, nullable=True, default=1920)
    height = Column(Integer, nullable=True, default=1080)
    
    # Status tracking
    status = Column(String(50), nullable=False, default="uploading")
    is_active = Column(Boolean, nullable=False, default=True)
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DroneFrame(Base):
    """
    One row per SRT block — stores the telemetry needed for frame lookup and GSD calculation.
    
    Attributes:
        video_id: Identifier for the video source (links to Video.video_key)
        frame_number: Sequential frame index from SRT
        timestamp: Time in seconds from video start
        latitude: GPS latitude coordinate
        longitude: GPS longitude coordinate
        altitude: Relative altitude in metres
        focal_len: Focal length in mm (35mm equivalent) from SRT - used for GSD calculation
    """
    __tablename__ = "drone_frames"
    __table_args__ = (
        UniqueConstraint("video_id", "frame_number", name="uq_video_frame"),
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    video_id = Column(String(100), nullable=False, index=True)
    frame_number = Column(Integer, nullable=False)
    timestamp = Column(Float, nullable=False)  # seconds into video

    latitude = Column(Float, nullable=False)
    longitude = Column(Float, nullable=False)
    altitude = Column(Float, nullable=False)  # metres (rel_alt)
    focal_len = Column(Float, nullable=True, default=24.0)  # mm (35mm equiv) - dynamic from SRT

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class CapturedFrame(Base):
    """
    Metadata for frames captured from drone videos during analysis sessions.

    Replaces the ephemeral frames_index.json — persists across restarts.
    """
    __tablename__ = "captured_frames"

    id = Column(Integer, primary_key=True, autoincrement=True)
    frame_id = Column(String(36), nullable=False, unique=True, index=True)  # UUID
    video_id = Column(String(100), nullable=False, index=True)
    frame_num = Column(Integer, nullable=False)
    time_sec = Column(Float, nullable=False)
    s3_key = Column(String(500), nullable=True)
    storage = Column(String(20), nullable=False, default="local")
    telemetry = Column(JSON, nullable=True)
    gsd_cm_px = Column(Float, nullable=True)
    captured_at = Column(DateTime(timezone=True), server_default=func.now())


class FrameAnalysis(Base):
    """
    Stores NLP query results tied to a frame + marker polygon.
    
    Attributes:
        frame_id: Reference to the analysed frame
        video_id: Video identifier
        frame_number: Frame number in video
        markers: JSON array of marker coordinates
        query_text: User's query string
        query_type: Classified query type (AREA_QUERY, etc.)
        area_m2: Calculated area in square metres
        plant_count: Counted plants in frame
        fertilizer_kg: Estimated fertilizer in kg
        manure_kg: Estimated manure in kg
        result_json: Full result as JSON
    """
    __tablename__ = "frame_analyses"

    id = Column(Integer, primary_key=True, autoincrement=True)
    frame_id = Column(Integer, nullable=False, index=True)
    video_id = Column(String(100), nullable=False)
    frame_number = Column(Integer, nullable=False)

    markers = Column(JSON, nullable=False)
    query_text = Column(Text, nullable=False)
    query_type = Column(String(50), nullable=True)

    area_m2 = Column(Float, nullable=True)
    plant_count = Column(Integer, nullable=True)
    fertilizer_kg = Column(Float, nullable=True)
    manure_kg = Column(Float, nullable=True)
    result_json = Column(JSON, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())


class Plant(Base):
    __tablename__ = "plants"

    plant_id         = Column(Integer, primary_key=True, autoincrement=True)
    latitude         = Column(Float, nullable=False, index=True)
    longitude        = Column(Float, nullable=False, index=True)
    canopy_size      = Column(String(20), nullable=False)   # Small / Medium / Large
    flowering_degree = Column(String(20), nullable=False)   # Low / Medium / High