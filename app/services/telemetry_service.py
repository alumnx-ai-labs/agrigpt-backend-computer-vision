"""
Telemetry Service - Telemetry data lookup and resolution.

Handles:
- Fetching telemetry from database
- Resolving telemetry for video frames
- GPS coordinate calculations
"""

from typing import Optional, Dict, Any

from sqlalchemy.orm import Session

from app.core.models import DroneFrame
from app.core.srt_parser import get_closest_frame_by_timestamp, get_telemetry_for_frame
from app.agents.calc_tools import calculate_gsd


class TelemetryService:
    """
    Service for telemetry data operations.
    
    Provides high-level telemetry lookup and conversion functions.
    """
    
    @staticmethod
    def frame_to_telem(frame: DroneFrame) -> Dict[str, Any]:
        """
        Convert DroneFrame model to telemetry dict.
        
        Args:
            frame: DroneFrame database model
        
        Returns:
            Dict with telemetry data
        """
        return {
            "rel_alt_m": frame.altitude,
            "lat": frame.latitude,
            "lon": frame.longitude,
            "frame_num": frame.frame_number,
        }
    
    @staticmethod
    def get_telemetry(db: Session, video_id: str, frame_num: int) -> Optional[Dict[str, Any]]:
        """
        Get telemetry for exact frame number.
        
        Args:
            db: Database session
            video_id: Video identifier
            frame_num: Frame number
        
        Returns:
            Telemetry dict or None
        """
        frame = get_telemetry_for_frame(db, video_id, frame_num)
        return TelemetryService.frame_to_telem(frame) if frame else None
    
    @staticmethod
    def get_telemetry_at_time(
        db: Session,
        video_id: str,
        time_sec: float,
        video_fps: float = 59.94005994005994
    ) -> Optional[Dict[str, Any]]:
        """
        Get telemetry for video timestamp.
        
        Uses closest frame matching for reliable telemetry.
        
        Args:
            db: Database session
            video_id: Video identifier
            time_sec: Time in seconds
            video_fps: Video FPS for frame calculation
        
        Returns:
            Telemetry dict or None
        """
        frame = get_closest_frame_by_timestamp(db, video_id, time_sec)
        return TelemetryService.frame_to_telem(frame) if frame else None
    
    @staticmethod
    def resolve_telemetry(
        db: Session,
        frame_num: int,
        video_id: str,
        video_fps: float = 59.94005994005994
    ) -> Optional[Dict[str, Any]]:
        """
        Resolve telemetry from database using frame number.
        
        Args:
            db: Database session
            frame_num: Frame number
            video_id: Video identifier
            video_fps: Video FPS
        
        Returns:
            Telemetry dict or None
        """
        frame_time = frame_num / video_fps
        return TelemetryService.get_telemetry_at_time(db, video_id, frame_time, video_fps)
    
    @staticmethod
    def calculate_gsd_for_telemetry(telemetry: Dict[str, Any]) -> float:
        """
        Calculate GSD for given telemetry.
        
        Args:
            telemetry: Telemetry dict with altitude
        
        Returns:
            GSD in metres per pixel
        """
        altitude = telemetry.get("rel_alt_m") or telemetry.get("altitude_m")
        if not altitude:
            return 0.0
        return calculate_gsd(altitude)