"""
Configuration module - Centralized settings for the Drone Frame Intelligence System.

All environment variables and configuration constants are defined here.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file
load_dotenv()

# =============================================================================
# PATHS
# =============================================================================

BASE_DIR = Path(__file__).parent.parent.absolute()
VIDEO_PATH = BASE_DIR / "drone.mp4"
SRT_PATH = BASE_DIR / "drone.SRT"
FRAMES_DIR = BASE_DIR / "captured_frames"
FRAMES_INDEX = BASE_DIR / "frames_index.json"

# =============================================================================
# VIDEO SETTINGS
# =============================================================================

VIDEO_WIDTH_PX = 1920
VIDEO_HEIGHT_PX = 1080
VIDEO_FPS = 59.94005994005994
DEFAULT_VIDEO_ID = os.getenv("DEFAULT_VIDEO_ID", "drone")

# =============================================================================
# CAMERA SETTINGS (DJI Mini 4 Pro)
# =============================================================================

# DJI Mini 4 Pro — 1920×1080, 24mm equiv, 1/1.3" sensor
IMAGE_WIDTH_PX = 1920
IMAGE_HEIGHT_PX = 1080
FOCAL_LEN_35MM = 24.0    # 35mm-equivalent focal length (mm)
CROP_FACTOR = 3.7        # 1/1.3" sensor crop factor
SENSOR_WIDTH_MM = 9.6    # physical sensor width (mm)

# =============================================================================
# AGRICULTURAL RATES
# =============================================================================

FERTILIZER_RATE = 0.021  # kg per m²
MANURE_RATE = 0.043      # kg per m²

# =============================================================================
# DATABASE
# =============================================================================

DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    from urllib.parse import quote_plus
    DATABASE_URL = "postgresql://{user}:{pw}@{host}:{port}/{db}".format(
        user=quote_plus(os.getenv("DB_USER", "postgres")),
        pw=quote_plus(os.getenv("DB_PASSWORD", "password")),
        host=os.getenv("DB_HOST", "localhost"),
        port=os.getenv("DB_PORT", "5432"),
        db=os.getenv("DB_NAME", "drone_db"),
    )

# =============================================================================
# S3 / STORAGE
# =============================================================================

S3_BUCKET = os.environ.get("S3_BUCKET", "")
AWS_REGION = os.environ.get("AWS_REGION", "us-east-1")
VIDEO_S3_KEY = os.environ.get("VIDEO_S3_KEY", "computer-vision/video.mp4")
VIDEO_CDN_URL = os.environ.get("VIDEO_CDN_URL", "")

# S3 path prefixes — override if your bucket layout is different
S3_VIDEO_PREFIX = os.environ.get("S3_VIDEO_PREFIX", "computer-vision")
S3_FRAMES_PREFIX = os.environ.get("S3_FRAMES_PREFIX", "computer-vision/snapshots")

# =============================================================================
# AI / LLM
# =============================================================================

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")

# =============================================================================
# APP METADATA
# =============================================================================

APP_TITLE = "Drone Area API"
APP_VERSION = "1.0.0"
APP_DESCRIPTION = """
Drone Frame Intelligence System - Agricultural analysis from drone imagery.

Features:
- Video frame capture and storage
- Telemetry sync from SRT files
- Area calculation with GPS/UTM projection
- Plant counting via computer vision
- Fertilizer and manure estimation
- Crop health assessment
"""