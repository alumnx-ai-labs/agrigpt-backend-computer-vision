"""
API module - FastAPI routes and dependencies.
"""

from .routes import (
    video_router,
    telemetry_router,
    analysis_router,
    frames_router,
    srt_router,
)

__all__ = [
    "video_router",
    "telemetry_router",
    "analysis_router",
    "frames_router",
    "srt_router",
]