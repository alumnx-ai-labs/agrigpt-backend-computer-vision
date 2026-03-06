"""
Computer Vision tools - Plant detection and health assessment.

Uses OpenCV for image analysis - NO LLM needed. These provide fast, free
image analysis for agricultural applications.
"""

import base64
from typing import List, Dict, Any, Optional

import cv2
import numpy as np


# =============================================================================
# PLANT COUNTING
# =============================================================================

def count_plants_pure(
    image_b64: str,
    points: Optional[List[List[float]]] = None,
    min_area: int = 150
) -> Dict[str, Any]:
    """
    Count plants/trees using OpenCV color segmentation (green foliage detection).
    
    Pure CV - NO LLM needed.
    
    Args:
        image_b64: Base64 encoded image
        points: Optional polygon points to filter region
        min_area: Minimum contour area to count as a plant (default 150 sqpx)
    
    Returns:
        dict with plant count, centers, and detection details
    """
    # 1. Decode image
    img_data = base64.b64decode(image_b64)
    nparr = np.frombuffer(img_data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return {"error": "Failed to decode image", "count": 0}
    
    h, w = img.shape[:2]

    # 2. Mask by polygon if provided
    mask = np.zeros((h, w), dtype=np.uint8)
    if points and len(points) >= 3:
        pts = np.array(points, dtype=np.int32).reshape((-1, 1, 2))
        cv2.fillPoly(mask, [pts], 255)
        img_masked = cv2.bitwise_and(img, img, mask=mask)
    else:
        img_masked = img
        mask.fill(255)

    # 3. HSV Green Detection - optimized for aerial foliage
    hsv = cv2.cvtColor(img_masked, cv2.COLOR_BGR2HSV)
    
    # Multiple green ranges for different foliage types
    # Range 1: Bright green (healthy vegetation)
    lower_green1 = np.array([35, 40, 40])
    upper_green1 = np.array([85, 255, 255])
    
    # Range 2: Darker green (mature trees)
    lower_green2 = np.array([25, 30, 20])
    upper_green2 = np.array([95, 255, 200])
    
    green_mask1 = cv2.inRange(hsv, lower_green1, upper_green1)
    green_mask2 = cv2.inRange(hsv, lower_green2, upper_green2)
    green_mask = cv2.bitwise_or(green_mask1, green_mask2)
    
    # 4. Clean up mask with morphological operations
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
    green_mask = cv2.morphologyEx(green_mask, cv2.MORPH_OPEN, kernel, iterations=1)
    green_mask = cv2.morphologyEx(green_mask, cv2.MORPH_CLOSE, kernel, iterations=2)

    # 5. Find contours (these are our plants)
    contours, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # 6. Filter by size and extract plant centers
    plant_count = 0
    plant_centers = []
    plant_areas = []
    
    for cnt in contours:
        area = cv2.contourArea(cnt)
        if area > min_area:
            plant_count += 1
            M = cv2.moments(cnt)
            if M["m00"] != 0:
                cx = int(M["m10"] / M["m00"])
                cy = int(M["m01"] / M["m00"])
                plant_centers.append((cx, cy))
                plant_areas.append(area)

    # Calculate green coverage percentage
    green_pixels = cv2.countNonZero(green_mask)
    total_pixels = h * w
    coverage_pct = (green_pixels / total_pixels) * 100

    return {
        "count": plant_count,
        "plant_centers": plant_centers,
        "plant_areas": plant_areas,
        "avg_plant_area": round(np.mean(plant_areas), 2) if plant_areas else 0,
        "green_coverage_pct": round(coverage_pct, 2),
        "method": "OpenCV_HSV_Segmentation",
        "detection_params": {
            "min_area_sqpx": min_area,
            "hsv_ranges": ["35-85 (bright green)", "25-95 (dark green)"]
        },
        "area_filtered": bool(points),
        "llm_used": False
    }


# =============================================================================
# CROP HEALTH ASSESSMENT
# =============================================================================

def assess_crop_health_pure(
    image_b64: str,
    points: Optional[List[List[float]]] = None
) -> Dict[str, Any]:
    """
    Assess crop/plant health using color analysis.
    
    Pure CV - NO LLM needed.
    
    Analyzes:
    - Green coverage percentage
    - Color intensity (indicator of chlorophyll)
    - Uniformity of vegetation
    
    Args:
        image_b64: Base64 encoded image
        points: Optional polygon points to filter region
    
    Returns:
        Dict with health score, status, and recommendations
    """
    # Decode image
    img_data = base64.b64decode(image_b64)
    nparr = np.frombuffer(img_data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return {"error": "Failed to decode image"}
    
    h, w = img.shape[:2]
    
    # Apply polygon mask if provided
    mask = np.zeros((h, w), dtype=np.uint8)
    if points and len(points) >= 3:
        pts = np.array(points, dtype=np.int32).reshape((-1, 1, 2))
        cv2.fillPoly(mask, [pts], 255)
    else:
        mask.fill(255)
    
    # Convert to HSV
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # Green detection
    lower_green = np.array([35, 40, 40])
    upper_green = np.array([85, 255, 255])
    green_mask = cv2.inRange(hsv, lower_green, upper_green)
    green_mask = cv2.bitwise_and(green_mask, green_mask, mask=mask)
    
    # Calculate metrics
    total_masked_pixels = cv2.countNonZero(mask)
    green_pixels = cv2.countNonZero(green_mask)
    
    green_coverage = (green_pixels / total_masked_pixels * 100) if total_masked_pixels > 0 else 0
    
    # Analyze green intensity (chlorophyll indicator)
    green_channel = img[:, :, 1]  # Green channel
    masked_green = cv2.bitwise_and(green_channel, green_channel, mask=mask)
    green_intensity = np.mean(masked_green[mask > 0]) if total_masked_pixels > 0 else 0
    
    # Yellow/brown detection (stress indicator)
    lower_yellow = np.array([20, 50, 50])
    upper_yellow = np.array([35, 255, 255])
    yellow_mask = cv2.inRange(hsv, lower_yellow, upper_yellow)
    yellow_mask = cv2.bitwise_and(yellow_mask, yellow_mask, mask=mask)
    yellow_pixels = cv2.countNonZero(yellow_mask)
    stress_ratio = (yellow_pixels / total_masked_pixels * 100) if total_masked_pixels > 0 else 0
    
    # Health score calculation (0-100)
    # Higher green coverage and intensity = healthier
    # Higher yellow/brown = stressed
    health_score = min(100, max(0, 
        (green_coverage * 0.5) + 
        (green_intensity / 255 * 30) - 
        (stress_ratio * 2)
    ))
    
    # Determine health status
    if health_score >= 70:
        status = "Healthy"
        recommendation = "Crops appear healthy. Continue current practices."
    elif health_score >= 40:
        status = "Moderate"
        recommendation = "Some stress detected. Consider additional irrigation or nutrients."
    else:
        status = "Poor"
        recommendation = "Significant stress detected. Investigate for pests, diseases, or nutrient deficiencies."
    
    return {
        "health_score": round(health_score, 1),
        "status": status,
        "recommendation": recommendation,
        "metrics": {
            "green_coverage_pct": round(green_coverage, 2),
            "green_intensity": round(green_intensity, 1),
            "stress_indicators_pct": round(stress_ratio, 2)
        },
        "method": "CV_color_analysis",
        "llm_used": False
    }


# =============================================================================
# PLANT TYPE DETECTION
# =============================================================================

def detect_plant_type_pure(
    image_b64: str,
    points: Optional[List[List[float]]] = None
) -> Dict[str, Any]:
    """
    Detect plant type based on visual characteristics.
    
    Limited capability without LLM - uses color and texture patterns.
    
    Args:
        image_b64: Base64 encoded image
        points: Optional polygon points to filter region
    
    Returns:
        Dict with detected type and confidence
    """
    # Decode image
    img_data = base64.b64decode(image_b64)
    nparr = np.frombuffer(img_data, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        return {"error": "Failed to decode image"}
    
    h, w = img.shape[:2]
    
    # Apply polygon mask if provided
    mask = np.zeros((h, w), dtype=np.uint8)
    if points and len(points) >= 3:
        pts = np.array(points, dtype=np.int32).reshape((-1, 1, 2))
        cv2.fillPoly(mask, [pts], 255)
    else:
        mask.fill(255)
    
    # Convert to HSV
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    
    # Green detection
    lower_green = np.array([35, 40, 40])
    upper_green = np.array([85, 255, 255])
    green_mask = cv2.inRange(hsv, lower_green, upper_green)
    green_mask = cv2.bitwise_and(green_mask, green_mask, mask=mask)
    
    # Find contours
    contours, _ = cv2.findContours(green_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    # Analyze contour characteristics
    contour_areas = [cv2.contourArea(c) for c in contours if cv2.contourArea(c) > 100]
    
    if not contour_areas:
        return {
            "detected_type": "unknown",
            "confidence": "low",
            "note": "No significant vegetation detected",
            "llm_used": False
        }
    
    avg_area = np.mean(contour_areas)
    num_contours = len(contour_areas)
    
    # Heuristic classification based on contour patterns
    # Trees typically have larger, more spread out contours
    # Row crops have smaller, more uniform contours
    
    if avg_area > 1000 and num_contours < 50:
        detected_type = "trees_or_large_shrubs"
        possible_types = ["mango", "guava", "citrus", "other_fruit_trees"]
    elif avg_area > 500 and num_contours < 100:
        detected_type = "medium_shrubs"
        possible_types = ["papaya", "banana", "vegetable_patches"]
    elif num_contours > 100 and avg_area < 500:
        detected_type = "row_crops_or_dense_plantation"
        possible_types = ["paddy", "vegetables", "sugarcane", "cotton"]
    else:
        detected_type = "mixed_vegetation"
        possible_types = ["mixed_farm", "orchard_with_intercrop"]
    
    return {
        "detected_type": detected_type,
        "possible_types": possible_types,
        "confidence": "low",
        "note": "For accurate plant identification, visual AI analysis recommended",
        "analysis": {
            "vegetation_patches": num_contours,
            "avg_patch_area": round(avg_area, 2),
            "total_green_area": round(sum(contour_areas), 2)
        },
        "method": "CV_pattern_heuristics",
        "llm_used": False
    }