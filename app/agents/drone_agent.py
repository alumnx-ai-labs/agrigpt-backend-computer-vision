"""
Drone Agent - Main entry point for drone image analysis.

Provides intelligent routing between:
1. Pure CV/Math-based tools (no LLM needed) - FREE & FAST
2. Gemini-powered routing and tool calling (intelligent query understanding)

The agent can answer agricultural queries using:
- Plant counting via OpenCV color segmentation
- Area calculation using GSD math
- Fertilizer estimation using agricultural formulas
- Manure calculation based on plant count
- Crop health assessment via color analysis
"""

from typing import List, Dict, Any, Optional

from app.agents.cv_tools import (
    count_plants_pure,
    assess_crop_health_pure,
    detect_plant_type_pure,
)
from app.agents.calc_tools import (
    calculate_area_pure,
    calculate_fertilizer_pure,
    calculate_manure_pure,
)


# =============================================================================
# QUERY CLASSIFICATION (keyword-based)
# =============================================================================

def classify_query_keywords(question: str) -> str:
    """
    Keyword-based query classifier.
    
    Returns one of: AREA_QUERY | PLANT_COUNT_QUERY | FERTILIZER_QUERY |
    MANURE_QUERY | HEALTH_QUERY | GENERAL_QUERY
    """
    q = question.lower()
    if any(kw in q for kw in ["area", "size", "square", "hectare", "region",
                              "sqft", "acre", "cent", "how big", "how much land"]):
        return "AREA_QUERY"
    if any(kw in q for kw in ["how many", "count", "plants", "mango", "trees",
                              "number of", "guava"]):
        return "PLANT_COUNT_QUERY"
    if any(kw in q for kw in ["fertilizer", "urea", "dap", "npk", "nutrient"]):
        return "FERTILIZER_QUERY"
    if any(kw in q for kw in ["manure", "compost", "organic"]):
        return "MANURE_QUERY"
    if any(kw in q for kw in ["health", "condition", "status", "healthy", "sick", "disease", "stress"]):
        return "HEALTH_QUERY"
    return "GENERAL_QUERY"


# =============================================================================
# PURE CV/MATH QUERY ANSWERING (NO LLM)
# =============================================================================

def answer_query_pure(
    question: str,
    image_b64: str,
    points: List[List[float]],
    telemetry: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Answer agricultural queries using pure CV/math - NO LLM needed.
    
    Routes queries based on keywords to appropriate tools.
    Returns comprehensive response without using any LLM API.
    
    Args:
        question: User's question
        image_b64: Base64 encoded image
        points: List of [x, y] coordinates from user clicks
        telemetry: Drone telemetry data
    
    Returns:
        Dict with answer, tools_used, and data from tools
    """
    question_lower = question.lower()
    
    result = {
        "question": question,
        "answer": "",
        "tools_used": [],
        "llm_used": False,
        "data": {}
    }
    
    plant_count = 0
    
    # Area-related queries
    if any(kw in question_lower for kw in ["area", "size", "square", "sqft", "acre", "cent", "how big", "how much land"]):
        if len(points) >= 3:
            area_result = calculate_area_pure(points, telemetry)
            result["tools_used"].append("calculate_area")
            result["data"]["area"] = area_result
            result["answer"] += (
                f"📐 **Area Calculation**\n"
                f"- {area_result['area_sq_yards']:,} sq yards\n"
                f"- {area_result['area_acres']} acres\n\n"
            )
        else:
            result["answer"] += "⚠️ Need at least 3 points to calculate area. Click on the image to mark points.\n\n"
    
    # Plant counting queries
    if any(kw in question_lower for kw in ["how many", "count", "number of", "plants", "trees", "mango", "guava"]):
        plant_result = count_plants_pure(image_b64, points)
        result["tools_used"].append("count_plants")
        result["data"]["plant_count"] = plant_result
        result["answer"] += (
            f"🌱 **Plant Count**\n"
            f"- Detected: {plant_result['count']} plants/trees\n"
            f"- Green coverage: {plant_result['green_coverage_pct']}%\n"
            f"- Method: {plant_result['method']}\n\n"
        )
        plant_count = plant_result['count']
    
    # Fertilizer queries
    if any(kw in question_lower for kw in ["fertilizer", "urea", "dap", "npk", "nutrient"]):
        # Get area if not already calculated
        if "area" not in result["data"] and len(points) >= 3:
            area_result = calculate_area_pure(points, telemetry)
            result["data"]["area"] = area_result
            area_m2 = area_result['area_m2']
        elif "area" in result["data"]:
            area_m2 = result["data"]["area"]['area_m2']
        else:
            area_m2 = 0
        
        # Determine crop type from question
        crop_type = "general"
        if "mango" in question_lower:
            crop_type = "mango"
        elif "paddy" in question_lower or "rice" in question_lower:
            crop_type = "paddy"
        elif "wheat" in question_lower:
            crop_type = "wheat"
        elif "vegetable" in question_lower:
            crop_type = "vegetables"
        elif "cotton" in question_lower:
            crop_type = "cotton"
        
        fert_result = calculate_fertilizer_pure(area_m2, plant_count, crop_type)
        result["tools_used"].append("calculate_fertilizer")
        result["data"]["fertilizer"] = fert_result
        result["answer"] += (
            f"🧪 **Fertilizer Recommendation**\n"
            f"- Urea: {fert_result['fertilizers'].get('urea_kg', fert_result['fertilizers'].get('urea_kg_per_plant', 'N/A'))} kg\n"
            f"- DAP: {fert_result['fertilizers'].get('dap_kg', fert_result['fertilizers'].get('dap_kg_per_plant', 'N/A'))} kg\n"
            f"- Potash: {fert_result['fertilizers'].get('potash_kg', fert_result['fertilizers'].get('potash_kg_per_plant', 'N/A'))} kg\n"
            f"- Note: {fert_result['note']}\n\n"
        )
    
    # Manure queries
    if any(kw in question_lower for kw in ["manure", "compost", "organic"]):
        # Get plant count if not already calculated
        if plant_count == 0:
            plant_result = count_plants_pure(image_b64, points)
            plant_count = plant_result['count']
            result["data"]["plant_count"] = plant_result
        
        # Get area if available
        area_m2 = result["data"].get("area", {}).get("area_m2", 0)
        
        # Determine plant type
        plant_type = "general"
        if "mango" in question_lower:
            plant_type = "mango"
        elif "guava" in question_lower:
            plant_type = "guava"
        elif "papaya" in question_lower:
            plant_type = "papaya"
        elif "banana" in question_lower:
            plant_type = "banana"
        
        manure_result = calculate_manure_pure(plant_count, area_m2, plant_type)
        result["tools_used"].append("calculate_manure")
        result["data"]["manure"] = manure_result
        result["answer"] += (
            f"🐂 **Manure Requirement**\n"
            f"- Manure needed: {manure_result.get('manure_kg', 'N/A')} kg\n"
            f"- = {manure_result.get('manure_tonnes', 'N/A')} tonnes\n"
            f"- Rate: {manure_result.get('recommended_range', manure_result.get('kg_per_acre', 'N/A'))}\n\n"
        )
    
    # Health assessment queries
    if any(kw in question_lower for kw in ["health", "condition", "status", "healthy", "sick", "disease", "stress"]):
        health_result = assess_crop_health_pure(image_b64, points)
        result["tools_used"].append("assess_health")
        result["data"]["health"] = health_result
        result["answer"] += (
            f"💚 **Crop Health Assessment**\n"
            f"- Health Score: {health_result['health_score']}/100\n"
            f"- Status: {health_result['status']}\n"
            f"- Green Coverage: {health_result['metrics']['green_coverage_pct']}%\n"
            f"- Stress Indicators: {health_result['metrics']['stress_indicators_pct']}%\n"
            f"- Recommendation: {health_result['recommendation']}\n\n"
        )
    
    # Plant type detection
    if any(kw in question_lower for kw in ["what type", "what kind", "identify", "species", "variety"]):
        type_result = detect_plant_type_pure(image_b64, points)
        result["tools_used"].append("detect_type")
        result["data"]["plant_type"] = type_result
        result["answer"] += (
            f"🌿 **Plant Type Detection**\n"
            f"- Likely: {type_result['detected_type']}\n"
            f"- Possible types: {', '.join(type_result['possible_types'])}\n"
            f"- Note: {type_result['note']}\n\n"
        )
    
    # If no specific query matched, provide general analysis
    if not result["tools_used"]:
        # Do a comprehensive analysis
        if len(points) >= 3:
            area_result = calculate_area_pure(points, telemetry)
            result["data"]["area"] = area_result
        
        plant_result = count_plants_pure(image_b64, points)
        result["data"]["plant_count"] = plant_result
        
        health_result = assess_crop_health_pure(image_b64, points)
        result["data"]["health"] = health_result
        
        result["tools_used"] = ["calculate_area", "count_plants", "assess_health"]
        
        result["answer"] = (
            f"📊 **General Analysis**\n\n"
            f"🌱 **Plants:** {plant_result['count']} detected ({plant_result['green_coverage_pct']}% coverage)\n"
        )
        if "area" in result["data"]:
            result["answer"] += f"📐 **Area:** {result['data']['area']['area_sq_yards']:,} sq yards ({result['data']['area']['area_acres']} acres)\n"
        result["answer"] += (
            f"💚 **Health:** {health_result['status']} (Score: {health_result['health_score']}/100)\n\n"
            f"💡 *Tip: Ask specific questions like 'how many plants', 'fertilizer needed', or 'crop health' for detailed analysis.*"
        )
    
    return result


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def run_drone_agent(
    question: str,
    image_b64: str,
    points: List[List[float]],
    telemetry: Dict[str, Any],
    use_llm: bool = False
) -> str:
    """
    Main entry point for drone image analysis.
    
    Args:
        question: User's question
        image_b64: Base64 encoded image
        points: List of [x, y] coordinates
        telemetry: Drone telemetry data
        use_llm: If True, use Gemini for intelligent routing (requires API key).
                 Default: False (keyword-based routing, no API costs)
    
    Returns:
        Answer string
    """
    # For now, always use keyword-based routing (pure CV/math)
    # LLM routing can be enabled when use_llm=True and GEMINI_API_KEY is set
    result = answer_query_pure(question, image_b64, points, telemetry)
    return result["answer"]


def analyze_frame(
    image_b64: str,
    points: Optional[List[List[float]]] = None,
    telemetry: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Comprehensive frame analysis - returns all metrics in one call.
    
    Pure CV/Math - NO LLM needed.
    
    Args:
        image_b64: Base64 encoded image
        points: Optional polygon points for region filtering
        telemetry: Optional telemetry data for area calculation
    
    Returns:
        Dict with plant_count, health, plant_type, area, fertilizer, manure
    """
    if telemetry is None:
        telemetry = {}
    if points is None:
        points = []
    
    result = {
        "plant_count": count_plants_pure(image_b64, points),
        "health": assess_crop_health_pure(image_b64, points),
        "plant_type": detect_plant_type_pure(image_b64, points),
        "llm_used": False
    }
    
    if len(points) >= 3 and telemetry:
        result["area"] = calculate_area_pure(points, telemetry)
        result["fertilizer"] = calculate_fertilizer_pure(
            result["area"]["area_m2"],
            result["plant_count"]["count"]
        )
        result["manure"] = calculate_manure_pure(
            result["plant_count"]["count"],
            result["area"]["area_m2"]
        )
    
    return result