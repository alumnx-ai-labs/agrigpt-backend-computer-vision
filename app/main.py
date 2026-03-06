"""
Main FastAPI Application - Drone Frame Intelligence System.

Entry point for the API server.

Run:
    cd image-query
    uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
"""

import os
import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import APP_TITLE, APP_VERSION, APP_DESCRIPTION
from app.core.database import init_db
from app.api.routes import (
    video_router,
    telemetry_router,
    analysis_router,
    frames_router,
    srt_router,
    video_upload_router,
)

# Create FastAPI app
app = FastAPI(
    title=APP_TITLE,
    version=APP_VERSION,
    description=APP_DESCRIPTION,
)

# CORS middleware
# Set ALLOWED_ORIGINS in .env as comma-separated domains, e.g.:
#   ALLOWED_ORIGINS=https://app.yourdomain.com,https://admin.yourdomain.com
# Leave unset (or set to *) only for local development.
_origins_env = os.environ.get("ALLOWED_ORIGINS", "*")
allowed_origins = [o.strip() for o in _origins_env.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Include routers
app.include_router(video_router)
app.include_router(telemetry_router)
app.include_router(analysis_router)
app.include_router(frames_router)
app.include_router(srt_router)
app.include_router(video_upload_router)

@app.on_event("startup")
def on_startup():
    """Initialize database tables on startup."""
    try:
        init_db()
    except Exception as exc:
        print(f"⚠️  DB init failed (DB may be down): {exc}")


@app.get("/")
def root():
    """Root endpoint - API info."""
    return {
        "name": APP_TITLE,
        "version": APP_VERSION,
        "docs": "/docs",
        "endpoints": {
            "video": "/video",
            "telemetry": "/telemetry",
            "calculate": "/calculate",
            "frames": "/image-query",
            "srt": "/srt",
        }
    }


@app.get("/health")
def health_check():
    """Health check endpoint."""
    return {"status": "healthy"}


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=False)