"""
Drone Agent - Main entry point for drone image analysis.

Provides intelligent routing between:
1. Pure CV/Math-based tools (no LLM needed) - FREE & FAST
2. Gemini-powered natural language formatting (conversational responses)

The agent can answer agricultural queries using:
- Plant counting via OpenCV color segmentation
- Area calculation using GSD math with dynamic focal length from SRT
- Fertilizer estimation using agricultural formulas
- Manure calculation based on plant count
- Crop health assessment via color analysis

All responses are formatted in natural language using Gemini LLM.
"""

import json
import re
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
from app.config import GEMINI_API_KEY

# Optional Gemini LLM import
try:
    from langchain_google_genai import ChatGoogleGenerativeAI
    from langchain_core.messages import HumanMessage, SystemMessage
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


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
                f"The area of the selected region is {area_result['area_sq_yards']:,.2f} square yards "
                f"({area_result['area_acres']:.4f} acres or {area_result['area_sqft']:.2f} sq ft). "
                f"This was calculated using GPS-geodesic computation at an altitude of {area_result.get('alt_m', 'N/A')} meters.\n\n"
            )
        else:
            result["answer"] += "I need at least 3 points to calculate the area. Please click on the image to mark the boundary points of the region you want to measure.\n\n"
    
    # Plant counting queries
    if any(kw in question_lower for kw in ["how many", "count", "number of", "plants", "trees", "mango", "guava"]):
        plant_result = count_plants_pure(image_b64, points)
        result["tools_used"].append("count_plants")
        result["data"]["plant_count"] = plant_result
        result["answer"] += (
            f"I detected {plant_result['count']} plants/trees in the selected region. "
            f"The green coverage is approximately {plant_result['green_coverage_pct']}% of the area, "
            f"analyzed using {plant_result['method']}.\n\n"
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
        urea = fert_result['fertilizers'].get('urea_kg', fert_result['fertilizers'].get('urea_kg_per_plant', 'N/A'))
        dap = fert_result['fertilizers'].get('dap_kg', fert_result['fertilizers'].get('dap_kg_per_plant', 'N/A'))
        potash = fert_result['fertilizers'].get('potash_kg', fert_result['fertilizers'].get('potash_kg_per_plant', 'N/A'))
        result["answer"] += (
            f"For the selected area with {crop_type} crop, I recommend the following fertilizer application: "
            f"Urea: {urea} kg, DAP: {dap} kg, and Potash: {potash} kg. "
            f"{fert_result['note']}\n\n"
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
        manure_kg = manure_result.get('manure_kg', 'N/A')
        manure_tonnes = manure_result.get('manure_tonnes', 'N/A')
        rate = manure_result.get('recommended_range', manure_result.get('kg_per_acre', 'N/A'))
        result["answer"] += (
            f"For the {plant_type} plants in this region, you will need approximately {manure_kg} kg "
            f"({manure_tonnes} tonnes) of organic manure. The recommended application rate is {rate}.\n\n"
        )
    
    # Health assessment queries
    if any(kw in question_lower for kw in ["health", "condition", "status", "healthy", "sick", "disease", "stress"]):
        health_result = assess_crop_health_pure(image_b64, points)
        result["tools_used"].append("assess_health")
        result["data"]["health"] = health_result
        status_emoji = "healthy" if health_result['health_score'] >= 70 else "moderately healthy" if health_result['health_score'] >= 40 else "stressed"
        result["answer"] += (
            f"The crop health in the selected region is {status_emoji} with a score of {health_result['health_score']}/100. "
            f"The green coverage is {health_result['metrics']['green_coverage_pct']}% and stress indicators show {health_result['metrics']['stress_indicators_pct']}%. "
            f"Recommendation: {health_result['recommendation']}\n\n"
        )
    
    # Plant type detection
    if any(kw in question_lower for kw in ["what type", "what kind", "identify", "species", "variety"]):
        type_result = detect_plant_type_pure(image_b64, points)
        result["tools_used"].append("detect_type")
        result["data"]["plant_type"] = type_result
        result["answer"] += (
            f"Based on visual analysis, the plants in this region appear to be {type_result['detected_type']}. "
            f"Other possible types include: {', '.join(type_result['possible_types'])}. "
            f"{type_result['note']}\n\n"
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
            f"Here is a general analysis of the selected region:\n\n"
            f"Plants: I detected {plant_result['count']} plants with {plant_result['green_coverage_pct']}% green coverage.\n"
        )
        if "area" in result["data"]:
            result["answer"] += f"Area: The region spans {result['data']['area']['area_sq_yards']:,.2f} sq yards ({result['data']['area']['area_acres']:.4f} acres).\n"
        result["answer"] += (
            f"Health: The crop health status is {health_result['status']} with a score of {health_result['health_score']}/100.\n\n"
            f"Tip: You can ask specific questions like 'how many plants', 'fertilizer needed', or 'crop health' for more detailed analysis."
        )
    
    return result


# =============================================================================
# GEMINI LLM NATURAL LANGUAGE FORMATTING
# =============================================================================

def format_response_with_gemini(
    question: str,
    tool_data: Dict[str, Any],
    tools_used: List[str]
) -> str:
    """
    Use Gemini LLM to format tool results into natural, conversational language.
    
    Transforms raw calculation output like:
    "The area of the selected region is 1234.5678 square yards (0.123456 acres)"
    
    Into natural language like:
    "The area you selected covers approximately 1,234.57 square yards, which is 
    about 0.12 acres. This was calculated using GPS coordinates from your drone's 
    telemetry data."
    
    Args:
        question: Original user question
        tool_data: Dictionary of tool results
        tools_used: List of tool names that were executed
    
    Returns:
        Natural language response string
    """
    if not GEMINI_AVAILABLE or not GEMINI_API_KEY:
        return None
    
    try:
        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0.3,
            google_api_key=GEMINI_API_KEY,
        )
        
        system_prompt = """You are an expert agricultural drone analyst. Your job is to convert raw analysis data into clear, helpful, conversational responses.

RESPONSE RULES:
1. Write in PLAIN TEXT only - NO markdown formatting (no **, *, #, backticks, code blocks)
2. Be conversational and helpful, like a knowledgeable farm advisor
3. All numeric values should be rounded to 2 decimal places
4. Use clear structure with:
   - Brief direct answer first (2-3 sentences)
   - Key details in simple bullet points using dashes (-)
   - Practical recommendations when applicable
5. Keep responses concise but informative (100-200 words)
6. Mention the tool/analysis method used
7. If area is mentioned, include both square yards and acres for farmer convenience

DATA FORMAT:
- Area: always show sq_yards and acres
- Fertilizer: show kg values
- Plant count: show count and coverage %
- Health: show score and status

Remember: You're helping a farmer understand their drone analysis results. Be clear, practical, and friendly."""

        # Build a summary of the analysis results
        data_summary = []
        
        if "area" in tool_data:
            area = tool_data["area"]
            data_summary.append(f"AREA: {area.get('area_sq_yards', 0):.2f} sq yards ({area.get('area_acres', 0):.2f} acres)")
            if "method" in area:
                data_summary.append(f"Method: {area['method']}")
            if "focal_len_mm" in area:
                data_summary.append(f"Focal length: {area['focal_len_mm']} mm")
        
        if "plant_count" in tool_data:
            pc = tool_data["plant_count"]
            data_summary.append(f"PLANTS: {pc.get('count', 0)} detected, {pc.get('green_coverage_pct', 0)}% green coverage")
        
        if "fertilizer" in tool_data:
            fert = tool_data["fertilizer"]
            ferts = fert.get("fertilizers", {})
            data_summary.append(f"FERTILIZER: Urea {ferts.get('urea_kg', 'N/A')} kg, DAP {ferts.get('dap_kg', 'N/A')} kg, Potash {ferts.get('potash_kg', 'N/A')} kg")
        
        if "manure" in tool_data:
            man = tool_data["manure"]
            data_summary.append(f"MANURE: {man.get('manure_kg', 'N/A')} kg ({man.get('manure_tonnes', 'N/A')} tonnes)")
        
        if "health" in tool_data:
            health = tool_data["health"]
            data_summary.append(f"HEALTH: Score {health.get('health_score', 0)}/100, Status: {health.get('status', 'unknown')}")
        
        user_message = f"""User's Question: {question}

Tools Used: {', '.join(tools_used)}

Analysis Results:
{chr(10).join('- ' + d for d in data_summary)}

Full Data:
{json.dumps(tool_data, indent=2, default=str)}

Please provide a clear, helpful response to the user's question based on this analysis data."""

        response = llm.invoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message)
        ])
        
        # Clean response - remove any markdown that might have slipped through
        answer = response.content if hasattr(response, 'content') else str(response)
        answer = re.sub(r'\*\*([^*]+)\*\*', r'\1', answer)  # Remove bold
        answer = re.sub(r'\*([^*]+)\*', r'\1', answer)  # Remove italic
        answer = re.sub(r'`([^`]+)`', r'\1', answer)  # Remove code
        answer = re.sub(r'^#+\s+', '', answer, flags=re.MULTILINE)  # Remove headers
        
        return answer.strip()
        
    except Exception as e:
        print(f"[Gemini LLM] Error formatting response: {e}")
        return None


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def run_drone_agent(
    question: str,
    image_b64: str,
    points: List[List[float]],
    telemetry: Dict[str, Any],
    use_llm: bool = True  # Now defaults to True for natural language
) -> Dict[str, Any]:
    """
    Main entry point for drone image analysis.
    
    Flow:
    1. Execute CV/Math tools for calculations (pure, no LLM)
    2. If use_llm=True and GEMINI_API_KEY available, format response naturally
    3. Otherwise, return direct tool output
    
    Args:
        question: User's question
        image_b64: Base64 encoded image
        points: List of [x, y] coordinates
        telemetry: Drone telemetry data (includes focal_len from SRT)
        use_llm: If True, use Gemini for natural language formatting.
                 Default: True
    
    Returns:
        Dict with answer string, sources (tools used), and data
    """
    # Step 1: Execute CV/Math tools (always pure, no LLM needed)
    result = answer_query_pure(question, image_b64, points, telemetry)
    
    # Step 2: Format tools_used as human-readable sources
    tools_used = result.get("tools_used", [])
    source_names = {
        "calculate_area": "Area Calculator",
        "count_plants": "Plant Detection (OpenCV)",
        "calculate_fertilizer": "Fertilizer Estimator",
        "calculate_manure": "Manure Calculator",
        "assess_health": "Health Assessment (CV)",
        "detect_type": "Plant Type Detection"
    }
    sources = [source_names.get(tool, tool) for tool in tools_used]
    
    # Step 3: Use Gemini LLM for natural language formatting (if enabled)
    final_answer = result["answer"]
    llm_used = False
    
    if use_llm and GEMINI_AVAILABLE and GEMINI_API_KEY:
        natural_response = format_response_with_gemini(
            question,
            result.get("data", {}),
            tools_used
        )
        if natural_response:
            final_answer = natural_response
            llm_used = True
            print("[run_drone_agent] ✓ Used Gemini LLM for natural language response")
        else:
            print("[run_drone_agent] ⚠ Gemini formatting failed, using direct output")
    else:
        if use_llm:
            print("[run_drone_agent] ⚠ Gemini not available, using direct output")
    
    return {
        "answer": final_answer,
        "sources": sources,
        "tools_used": tools_used,
        "data": result.get("data", {}),
        "llm_used": llm_used
    }


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