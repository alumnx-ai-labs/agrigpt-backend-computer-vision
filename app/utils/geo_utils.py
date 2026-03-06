"""
Geographic utilities - GPS, UTM projection, and area calculations.

Provides functions for:
- Converting pixel coordinates to GPS
- Projecting GPS to UTM for accurate area measurement
- Shoelace formula for polygon area
"""

import math
from typing import List, Tuple

from pyproj import Transformer, Geod

# =============================================================================
# CONSTANTS
# =============================================================================

M_PER_DEG_LAT = 111_320.0  # Metres per degree latitude (approximate)


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def m_per_deg_lon(lat_deg: float) -> float:
    """Calculate metres per degree longitude at a given latitude."""
    return M_PER_DEG_LAT * math.cos(math.radians(lat_deg))


# =============================================================================
# COORDINATE CONVERSIONS
# =============================================================================

def pixel_to_gps(
    px: float,
    py: float,
    img_w: int,
    img_h: int,
    gsd: float,
    clat: float,
    clon: float,
) -> Tuple[float, float]:
    """
    Convert pixel coordinates to GPS coordinates.
    
    Args:
        px, py: Pixel coordinates
        img_w, img_h: Image dimensions
        gsd: Ground Sampling Distance (metres per pixel)
        clat, clon: Center GPS coordinates
    
    Returns:
        Tuple of (latitude, longitude)
    """
    dx_m = (px - img_w / 2) * gsd
    dy_m = -(py - img_h / 2) * gsd
    return (
        clat + dy_m / M_PER_DEG_LAT,
        clon + dx_m / m_per_deg_lon(clat),
    )


def gps_to_utm_metric(gps_pts: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """
    Project GPS (lat, lon) points to UTM metres using pyproj.
    
    Auto-selects the correct UTM zone from the first point.
    Works for both northern and southern hemispheres.
    
    Args:
        gps_pts: List of (latitude, longitude) tuples
    
    Returns:
        List of (easting, northing) tuples in UTM metres
    """
    lat0, lon0 = gps_pts[0]
    zone = int((lon0 + 180) / 6) + 1
    epsg = (32700 if lat0 < 0 else 32600) + zone  # S → 327xx, N → 326xx
    
    transformer = Transformer.from_crs("EPSG:4326", f"EPSG:{epsg}", always_xy=True)
    return [transformer.transform(lon, lat) for lat, lon in gps_pts]


# =============================================================================
# AREA CALCULATIONS
# =============================================================================

def sort_convex(pts: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    """Sort points in convex hull order (angle from centroid)."""
    cx = sum(p[0] for p in pts) / len(pts)
    cy = sum(p[1] for p in pts) / len(pts)
    return sorted(pts, key=lambda p: math.atan2(p[1] - cy, p[0] - cx))


def shoelace_area(pts: List[Tuple[float, float]]) -> float:
    """
    Calculate polygon area using the Shoelace formula.
    Normalises coordinates first to avoid floating-point cancellation errors.

    Args:
        pts: List of (x, y) coordinates in user-provided order (no resorting)

    Returns:
        Area in the same units as the input coordinates
    """
    if len(pts) < 3:
        return 0.0
    # Normalise: subtract min to reduce magnitude and avoid cancellation
    min_x = min(p[0] for p in pts)
    min_y = min(p[1] for p in pts)
    pts = [(p[0] - min_x, p[1] - min_y) for p in pts]
    n = len(pts)
    area = sum(
        pts[i][0] * pts[(i + 1) % n][1] - pts[(i + 1) % n][0] * pts[i][1]
        for i in range(n)
    )
    return abs(area) / 2.0


def geodesic_area(gps_pts: List[Tuple[float, float]]) -> float:
    """
    Calculate polygon area using pyproj.Geod on the WGS-84 ellipsoid.

    This is the most accurate method — no UTM zone selection, works globally,
    handles non-convex polygons correctly, and properly accounts for Earth's
    curvature.

    Args:
        gps_pts: List of (latitude, longitude) tuples in user order

    Returns:
        Area in square metres (always positive)
    """
    if len(gps_pts) < 3:
        return 0.0
    geod = Geod(ellps="WGS84")
    lons = [pt[1] for pt in gps_pts]
    lats = [pt[0] for pt in gps_pts]
    area, _ = geod.polygon_area_perimeter(lons, lats)
    return abs(area)