"""
Agents module - AI-powered drone image analysis.

Provides:
- CV tools for plant counting and health assessment
- Calculation tools for area, fertilizer, manure
- Query routing and classification
- Main drone agent entry point
"""

from .drone_agent import run_drone_agent, analyze_frame
from .cv_tools import count_plants_pure, assess_crop_health_pure, detect_plant_type_pure
from .calc_tools import (
    calculate_area_pure,
    calculate_fertilizer_pure,
    calculate_manure_pure,
    calculate_gsd,
    pixels_to_meters,
    shoelace_area,
)

__all__ = [
    # Main agent
    "run_drone_agent",
    "analyze_frame",
    # CV tools
    "count_plants_pure",
    "assess_crop_health_pure",
    "detect_plant_type_pure",
    # Calc tools
    "calculate_area_pure",
    "calculate_fertilizer_pure",
    "calculate_manure_pure",
    "calculate_gsd",
    "pixels_to_meters",
    "shoelace_area",
]