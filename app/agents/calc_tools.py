"""
Calculation tools - Area, fertilizer, manure, and GSD calculations.

Pure math functions - NO LLM needed. These provide fast, free computations
for agricultural analysis based on drone imagery.
"""

from typing import List, Dict, Any, Optional

from app.utils.geo_utils import pixel_to_gps, geodesic_area
from app.config import (
    IMAGE_WIDTH_PX,
    IMAGE_HEIGHT_PX,
    FOCAL_LEN_35MM,
    CROP_FACTOR,
    SENSOR_WIDTH_MM,
    FERTILIZER_RATE,
    MANURE_RATE,
)


# =============================================================================
# GSD (GROUND SAMPLING DISTANCE) CALCULATION
# =============================================================================

def calculate_gsd(
    altitude_m: float,
    image_width_px: int = IMAGE_WIDTH_PX,
    focal_len_35mm: float = FOCAL_LEN_35MM,
    crop_factor: float = CROP_FACTOR,
    sensor_width_mm: float = SENSOR_WIDTH_MM,
) -> float:
    """
    Calculate Ground Sampling Distance (metres per pixel).
    
    GSD = (altitude_mm * sensor_width_mm) / (actual_fl_mm * image_width_px)
    
    Args:
        altitude_m: Altitude in metres
        image_width_px: Image width in pixels
        focal_len_35mm: 35mm-equivalent focal length (mm)
        crop_factor: Sensor crop factor
        sensor_width_mm: Physical sensor width (mm)
    
    Returns:
        GSD in metres per pixel
    """
    actual_fl_mm = focal_len_35mm / crop_factor
    altitude_mm = altitude_m * 1000
    return (altitude_mm * sensor_width_mm) / (actual_fl_mm * image_width_px) / 1000


# =============================================================================
# PIXEL TO METRE CONVERSION
# =============================================================================

def pixels_to_meters(
    markers: List[List[float]],
    gsd: float
) -> List[tuple]:
    """
    Convert pixel coordinates to real-world metre coordinates.
    
    Args:
        markers: List of [x, y] pixel coordinates
        gsd: Ground Sampling Distance (metres per pixel)
    
    Returns:
        List of (x_metres, y_metres) tuples
    """
    return [(x * gsd, y * gsd) for x, y in markers]


# =============================================================================
# AREA CALCULATION (SHOELACE FORMULA)
# =============================================================================

def shoelace_area(points_m: List[tuple]) -> float:
    """
    Calculate polygon area in m² using the Shoelace formula.
    
    Args:
        points_m: List of (x, y) coordinates in metres
    
    Returns:
        Area in square metres
    """
    n = len(points_m)
    area = 0.0
    for i in range(n):
        x1, y1 = points_m[i]
        x2, y2 = points_m[(i + 1) % n]
        area += x1 * y2 - x2 * y1
    return abs(area) / 2.0


# =============================================================================
# AREA CALCULATION (HIGH-LEVEL)
# =============================================================================

def calculate_area_pure(
    points: List[List[float]],
    telemetry: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Calculate ground area for a polygon of n >= 3 pixel points.

    Uses GPS+Geodesic (pyproj.Geod WGS-84) when lat/lon is available — the
    most accurate method, no UTM zone selection, correct for non-convex
    polygons and any n-gon.  Falls back to GSD pixel-to-metre Shoelace when
    GPS is absent.

    Args:
        points: List of [x, y] pixel coordinates (user order, n >= 3)
        telemetry: Dict with keys rel_alt_m/altitude_m, lat, lon

    Returns:
        Dict with area in multiple units, GSD, and method info
    """
    altitude = telemetry.get("rel_alt_m") or telemetry.get("altitude_m")
    if not altitude:
        return {"error": "Altitude missing from telemetry — ensure SRT is ingested into DB"}

    gsd = calculate_gsd(altitude)
    clat = telemetry.get("lat")
    clon = telemetry.get("lon")
    has_gps = clat and clon and not (clat == 0.0 and clon == 0.0)

    if has_gps:
        gps_pts = [
            pixel_to_gps(p[0], p[1], IMAGE_WIDTH_PX, IMAGE_HEIGHT_PX, gsd, clat, clon)
            for p in points
        ]
        area_m2 = geodesic_area(gps_pts)
        method = "GPS_Geodesic_WGS84"
    else:
        points_m = pixels_to_meters(points, gsd)
        area_m2 = shoelace_area(points_m)
        gps_pts = None
        method = "GSD_Shoelace"

    return {
        "area_m2": round(area_m2, 4),
        "area_sqft": round(area_m2 * 10.7639, 2),
        "area_sq_yards": round(area_m2 * 1.19599, 2),
        "area_cents": round(area_m2 / 40.4686, 6),
        "area_acres": round(area_m2 / 4046.86, 6),
        "gsd_cm_px": round(gsd * 100, 4),
        "method": method,
        "gps_markers": [[lat, lon] for lat, lon in gps_pts] if gps_pts else None,
        "llm_used": False,
    }


# =============================================================================
# FERTILIZER CALCULATION
# =============================================================================

# Fertilizer recommendations (kg per acre)
FERTILIZER_RATES = {
    "general": {"urea": 50, "dap": 100, "potash": 50, "manure": 2000},
    "mango": {"urea_per_plant": 2, "dap_per_plant": 1, "potash_per_plant": 1, "manure_per_plant": 15},
    "paddy": {"urea": 100, "dap": 50, "potash": 50, "manure": 5000},
    "wheat": {"urea": 75, "dap": 50, "potash": 25, "manure": 3000},
    "vegetables": {"urea": 60, "dap": 80, "potash": 40, "manure": 4000},
    "cotton": {"urea": 100, "dap": 50, "potash": 50, "manure": 4000},
}


def calculate_fertilizer_pure(
    area_m2: float,
    plant_count: int = 0,
    crop_type: str = "general"
) -> Dict[str, Any]:
    """
    Calculate fertilizer requirements based on area and crop type.
    
    Uses standard agricultural formulas - NO LLM needed.
    
    Standard NPK recommendations per acre for different crops:
    - General vegetables: Urea 50kg, DAP 100kg, Potash 50kg
    - Mango: Urea 2kg/tree, DAP 1kg/tree
    - Paddy/Rice: Urea 100kg, DAP 50kg, Potash 50kg
    
    Args:
        area_m2: Area in square metres
        plant_count: Number of plants (for tree crops)
        crop_type: Type of crop (general, mango, paddy, wheat, vegetables, cotton)
    
    Returns:
        Dict with fertilizer amounts and notes
    """
    area_acres = area_m2 / 4046.86
    area_hectares = area_m2 / 10000
    
    crop_lower = crop_type.lower()
    rates = FERTILIZER_RATES.get(crop_lower, FERTILIZER_RATES["general"])
    
    result = {
        "crop_type": crop_type,
        "area_m2": round(area_m2, 2),
        "area_acres": round(area_acres, 4),
        "plant_count": plant_count,
        "method": "agricultural_standard_formula",
        "llm_used": False,
        "fertilizers": {}
    }
    
    if "per_plant" in str(rates):
        # Tree crops like mango - calculate per plant
        if plant_count > 0:
            result["fertilizers"] = {
                "urea_kg": round(rates.get("urea_per_plant", 2) * plant_count, 2),
                "dap_kg": round(rates.get("dap_per_plant", 1) * plant_count, 2),
                "potash_kg": round(rates.get("potash_per_plant", 1) * plant_count, 2),
                "manure_kg": round(rates.get("manure_per_plant", 15) * plant_count, 2),
            }
            result["note"] = f"Fertilizer calculated per plant for {plant_count} {crop_type} plants"
        else:
            result["fertilizers"] = {
                "urea_kg_per_plant": rates.get("urea_per_plant", 2),
                "dap_kg_per_plant": rates.get("dap_per_plant", 1),
                "potash_kg_per_plant": rates.get("potash_per_plant", 1),
                "manure_kg_per_plant": rates.get("manure_per_plant", 15),
            }
            result["note"] = "Per-plant rates provided (no plant count available)"
    else:
        # Field crops - calculate per area
        result["fertilizers"] = {
            "urea_kg": round(rates.get("urea", 50) * area_acres, 2),
            "dap_kg": round(rates.get("dap", 100) * area_acres, 2),
            "potash_kg": round(rates.get("potash", 50) * area_acres, 2),
            "manure_kg": round(rates.get("manure", 2000) * area_acres, 2),
        }
        result["note"] = f"Fertilizer calculated per acre for {crop_type}"
    
    return result


# =============================================================================
# MANURE CALCULATION
# =============================================================================

# Manure recommendations per plant type
MANURE_RATES = {
    "mango": {"kg_per_plant": 12, "range": "10-15"},
    "guava": {"kg_per_plant": 10, "range": "8-12"},
    "papaya": {"kg_per_plant": 8, "range": "6-10"},
    "banana": {"kg_per_plant": 5, "range": "4-6"},
    "fruit_tree": {"kg_per_plant": 10, "range": "8-12"},
    "general": {"kg_per_plant": 10, "range": "8-12"},
}


def calculate_manure_pure(
    plant_count: int,
    area_m2: float = 0,
    plant_type: str = "general"
) -> Dict[str, Any]:
    """
    Calculate manure requirements based on plant count or area.
    
    Uses standard agricultural formulas - NO LLM needed.
    
    Standard manure recommendations:
    - Mango tree: 10-15 kg/year
    - General fruit tree: 10 kg/year
    - Vegetables: 4-5 tonnes/acre
    
    Args:
        plant_count: Number of plants
        area_m2: Area in square metres (alternative to plant count)
        plant_type: Type of plant (mango, guava, papaya, banana, general)
    
    Returns:
        Dict with manure requirements
    """
    area_acres = area_m2 / 4046.86
    
    plant_lower = plant_type.lower()
    rates = MANURE_RATES.get(plant_lower, MANURE_RATES["general"])
    
    result = {
        "plant_type": plant_type,
        "plant_count": plant_count,
        "area_acres": round(area_acres, 4),
        "method": "agricultural_standard_formula",
        "llm_used": False,
    }
    
    if plant_count > 0:
        total_manure = rates["kg_per_plant"] * plant_count
        result.update({
            "manure_kg": round(total_manure, 2),
            "manure_tonnes": round(total_manure / 1000, 3),
            "kg_per_plant": rates["kg_per_plant"],
            "recommended_range": f"{rates['range']} kg per {plant_type} plant",
            "application_note": "Apply during onset of monsoon or before flowering season"
        })
    elif area_m2 > 0:
        # Field crops - per acre recommendation
        manure_per_acre = 4000  # 4 tonnes per acre for general crops
        result.update({
            "manure_kg": round(manure_per_acre * area_acres, 2),
            "manure_tonnes": round(manure_per_acre * area_acres / 1000, 3),
            "kg_per_acre": manure_per_acre,
            "note": "Based on standard field crop recommendation of 4 tonnes/acre"
        })
    else:
        result["error"] = "Need either plant_count or area_m2"
    
    return result