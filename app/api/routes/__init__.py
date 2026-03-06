"""
API Routes - FastAPI routers for each endpoint group.
"""

from .video import router as video_router
from .telemetry import router as telemetry_router
from .analysis import router as analysis_router
from .frames import router as frames_router
from .srt import router as srt_router
from .video_upload import router as video_upload_router

__all__ = [
    "video_router",
    "telemetry_router",
    "analysis_router",
    "frames_router",
    "srt_router",
    "video_upload_router",
]
