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
                f"The selected area is {area_result['area_acres']:.2f} acres.\n\n"
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
            result["answer"] += f"Area: {result['data']['area']['area_acres']:.2f} acres.\n"
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
            temperature=0.0,
            google_api_key=GEMINI_API_KEY,
        )

        system_prompt = """You are a farm data terminal. Output ONLY the raw facts from the data provided.

ABSOLUTE RULES — violating any of these is wrong:
1. NO greetings, NO encouragement, NO filler ("It's great", "Continue monitoring", "excellent condition", "Based on our tool")
2. NO markdown — no **, no ##, no -, no bullet points, no backticks
3. NO recommendations or tips unless the question explicitly asks for advice
4. NO restating the question
5. Answer ONLY what was asked — if asked about count, give count only; if asked about yield, give yield only
6. Maximum 3 sentences for any single-topic question
7. For combined questions (e.g. "count and area"), answer each in one sentence, in the order asked
8. Numbers: round to 1 decimal place, use commas for thousands

OUTPUT FORMAT by topic:
- Count: "X mango trees — L large, M medium, S small."
- Area: "X sq yards (Y acres)."
- Health: "X healthy, Y moderate, Z stressed. Avg score: W/100."
- Fertilizer: "Urea X kg, DAP Y kg, Potash Z kg, Manure W kg."
- Yield: "Expected X–Y kg this season (avg Z kg per tree)."
- Flowering: "X high, Y medium, Z low flowering."
- Fruiting: "X mature, Y developing, Z not fruiting."

Read the data. Report the numbers. Nothing else."""

        # Build a summary of the analysis results
        data_summary = []
        
        if "area" in tool_data:
            area = tool_data["area"]
            data_summary.append(f"AREA: {area.get('area_acres', 0):.2f} acres")
            if "method" in area:
                data_summary.append(f"Method: {area['method']}")
            if "focal_len_mm" in area:
                data_summary.append(f"Focal length: {area['focal_len_mm']} mm")
        
        if "plant_count" in tool_data:
            pc = tool_data["plant_count"]
            cb = pc.get("canopy_breakdown", {})
            canopy_str = (
                f" (Large: {cb.get('Large',0)}, Medium: {cb.get('Medium',0)}, Small: {cb.get('Small',0)})"
                if cb else ""
            )
            data_summary.append(
                f"PLANTS: {pc.get('count', 0)} total{canopy_str}, "
                f"{pc.get('green_coverage_pct', 0)}% healthy"
            )

        if "health" in tool_data:
            health = tool_data["health"]
            m = health.get("metrics", {})
            si = m.get("stress_indicators", {})
            si_str = ", ".join(f"{k}:{v}" for k, v in si.items()) if si else "none"
            data_summary.append(
                f"HEALTH: Score {health.get('health_score', 0)}/100, Status: {health.get('status', 'unknown')}, "
                f"Healthy:{m.get('Healthy',0)}, Moderate:{m.get('Moderate',0)}, Stressed:{m.get('Stressed',0)}, "
                f"Stress indicators: {si_str}"
            )

        if "fertilizer" in tool_data:
            ferts = tool_data["fertilizer"].get("fertilizers", {})
            data_summary.append(
                f"FERTILIZER: Urea {ferts.get('urea_kg','N/A')} kg, DAP {ferts.get('dap_kg','N/A')} kg, "
                f"Potash {ferts.get('potash_kg','N/A')} kg, Manure {ferts.get('manure_kg','N/A')} kg"
            )

        if "phenology" in tool_data:
            ph = tool_data["phenology"]
            fl = ph.get("flowering", {})
            fr = ph.get("fruiting", {})
            data_summary.append(
                f"FLOWERING: High:{fl.get('High',0)}, Medium:{fl.get('Medium',0)}, Low:{fl.get('Low',0)}"
            )
            data_summary.append(
                f"FRUITING: Mature:{fr.get('Mature',0)}, Developing:{fr.get('Developing',0)}, None:{fr.get('None',0)}"
            )

        if "physical" in tool_data:
            ph = tool_data["physical"]
            data_summary.append(
                f"HEIGHT: avg {ph.get('avg_height_m','N/A')}m (min {ph.get('min_height_m','N/A')}m, max {ph.get('max_height_m','N/A')}m)"
            )
            data_summary.append(
                f"AGE: avg {ph.get('avg_age_years','N/A')} yrs (min {ph.get('min_age_years','N/A')}, max {ph.get('max_age_years','N/A')})"
            )

        if "yield" in tool_data:
            y = tool_data["yield"]
            data_summary.append(
                f"YIELD: {y.get('min_kg',0)}–{y.get('max_kg',0)} kg total, "
                f"avg {y.get('per_tree_avg_kg',0)} kg/tree"
            )

        user_message = f"""Question: {question}

Data:
{chr(10).join(data_summary)}

Answer the question using only the numbers above. Follow the output format rules exactly."""

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
# DATABASE-BACKED QUERY ANSWERING
# =============================================================================

def answer_query_from_db(
    question: str,
    plants: list,
    points: List[List[float]],
    telemetry: Dict[str, Any]
) -> Dict[str, Any]:
    """
    Fallback plain-text answer from DB (used only when Gemini is unavailable).
    Fields available: canopy_size, flowering_degree.
    Health is inferred from flowering_degree.
    """
    from app.agents.calc_tools import calculate_area_pure

    q = question.lower()
    count = len(plants)

    is_area      = any(kw in q for kw in ["area","square","sqft","acre","cent","how big","how much land","ఏరియా","क्षेत्र"])
    is_count     = any(kw in q for kw in ["how many","count","plant","tree","mango","number","canopy","ఎన్ని","మొక్క","कितने","पौधे"])
    is_flowering = any(kw in q for kw in ["flower","flowering","bloom","fruit","fruiting","harvest","పూత","फूल","फल"])
    is_health    = any(kw in q for kw in ["health","condition","healthy","sick","stress","disease","ఆరోగ్యం","स्वास्थ्य"])
    is_fertilizer= any(kw in q for kw in ["fertilizer","urea","dap","npk","nutrient","manure","compost","organic","ఎరువు","खाद","गोबर"])
    is_yield     = any(kw in q for kw in ["yield","produce","harvest","output","production","income","దిగుబడి","उपज","पैदावार"])

    if not any([is_area, is_count, is_flowering, is_health, is_fertilizer, is_yield]):
        is_count = is_flowering = True
        is_area = len(points) >= 3

    # Canopy aggregation
    large_n  = sum(1 for p in plants if p.canopy_size == "Large")
    medium_n = sum(1 for p in plants if p.canopy_size == "Medium")
    small_n  = sum(1 for p in plants if p.canopy_size == "Small")

    # Flowering aggregation
    fl_high = sum(1 for p in plants if p.flowering_degree == "High")
    fl_med  = sum(1 for p in plants if p.flowering_degree == "Medium")
    fl_low  = sum(1 for p in plants if p.flowering_degree == "Low")

    # Health inferred from flowering
    healthy_n  = fl_high
    moderate_n = fl_med
    stressed_n = fl_low

    # Fertilizer: canopy-weighted benchmarks (urea, dap, potash, manure kg/tree)
    FERT = {"Large": (2.2, 0.9, 1.3, 32), "Medium": (1.8, 0.7, 1.0, 25), "Small": (1.2, 0.5, 0.7, 18)}
    urea   = round(sum(FERT[p.canopy_size][0] for p in plants), 1)
    dap    = round(sum(FERT[p.canopy_size][1] for p in plants), 1)
    potash = round(sum(FERT[p.canopy_size][2] for p in plants), 1)
    manure = round(sum(FERT[p.canopy_size][3] for p in plants), 1)

    yield_data = calculate_yield_from_plants(plants)

    area_data = {}
    if len(points) >= 3:
        area_data = calculate_area_pure(points, telemetry)

    parts = []
    if is_area and area_data:
        parts.append(f"Area: {area_data['area_acres']:.2f} acres.")
    if is_count:
        parts.append(f"{count} mango trees — {large_n} large, {medium_n} medium, {small_n} small canopy.")
    if is_flowering:
        parts.append(f"Flowering: {fl_high} high, {fl_med} medium, {fl_low} low.")
    if is_health:
        parts.append(f"Health (from flowering): {healthy_n} productive, {moderate_n} moderate, {stressed_n} low activity.")
    if is_fertilizer:
        parts.append(f"For {count} trees: Urea {urea} kg, DAP {dap} kg, Potash {potash} kg, Manure {manure} kg.")
    if is_yield:
        parts.append(f"Expected yield: {yield_data['min_kg']}–{yield_data['max_kg']} kg (avg {yield_data['per_tree_avg_kg']} kg/tree).")

    return {
        "question": question,
        "answer": " ".join(parts) or f"{count} mango trees — {large_n} large, {medium_n} medium, {small_n} small.",
        "tools_used": ["query_plants_db"],
        "llm_used": False,
        "data": {"area": area_data, "plant_count": {"count": count}},
    }


# =============================================================================
# IMAGE CROP + GEMINI VISION PLANT COUNT
# =============================================================================

def crop_image_to_polygon(image_b64: str, points: List[List[float]]) -> Optional[str]:
    """
    Crop the drone image to the bounding box of the polygon and darken
    everything outside the polygon so Gemini only sees the selected region.
    Returns a base64-encoded JPEG of the cropped region, or None on failure.
    """
    try:
        import base64
        import numpy as np
        import cv2

        img_bytes = base64.b64decode(image_b64)
        nparr = np.frombuffer(img_bytes, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            return None

        pts = np.array([[int(x), int(y)] for x, y in points], dtype=np.int32)
        x, y, w, h = cv2.boundingRect(pts)
        pad = 30
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(img.shape[1], x + w + pad)
        y2 = min(img.shape[0], y + h + pad)

        cropped = img[y1:y2, x1:x2].copy()

        # Shift polygon to cropped coordinate space
        pts_shifted = pts - np.array([x1, y1])

        # Darken everything outside the polygon so Gemini focuses on selected area
        mask = np.zeros(cropped.shape[:2], dtype=np.uint8)
        cv2.fillPoly(mask, [pts_shifted], 255)
        dark = (cropped * 0.25).astype(np.uint8)
        result = np.where(mask[:, :, np.newaxis] == 255, cropped, dark)

        # Draw the polygon boundary
        cv2.polylines(result, [pts_shifted], isClosed=True,
                      color=(0, 255, 128), thickness=2)

        _, buffer = cv2.imencode('.jpg', result, [cv2.IMWRITE_JPEG_QUALITY, 90])
        return base64.b64encode(buffer).decode('utf-8')
    except Exception as e:
        print(f"[crop_image] Failed: {e}")
        return None


def count_plants_with_vision(image_b64: str, points: List[List[float]]) -> Optional[int]:
    """
    Crop the drone image to the selected polygon and use Gemini vision to count
    tree canopies precisely within that region.
    Returns integer count, or None if unavailable.
    """
    if not GEMINI_AVAILABLE or not GEMINI_API_KEY or not image_b64:
        return None
    try:
        # Use cropped image so Gemini only sees the selected region
        cropped_b64 = crop_image_to_polygon(image_b64, points)
        img_b64 = cropped_b64 if cropped_b64 else image_b64

        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash",
            temperature=0.0,
            google_api_key=GEMINI_API_KEY,
        )
        message = HumanMessage(content=[
            {
                "type": "image_url",
                "image_url": {"url": f"data:image/jpeg;base64,{img_b64}"},
            },
            {
                "type": "text",
                "text": (
                    "Aerial drone image of a mango farm. "
                    "The bright region (inside the green polygon border) is the selected area.\n\n"
                    "Task: Count every distinct tree canopy visible in the BRIGHT selected area only. "
                    "Each separate round/oval green canopy cluster = 1 tree. "
                    "Do not count the darkened outside area.\n\n"
                    "Reply with a SINGLE INTEGER ONLY. No words, no explanation."
                ),
            }
        ])
        response = llm.invoke([message])
        match = re.search(r'\d+', response.content.strip())
        if match:
            count = int(match.group())
            print(f"[vision_count] Gemini vision counted {count} plants (cropped polygon)")
            return count
        return None
    except Exception as e:
        print(f"[vision_count] Failed: {e}")
        return None


# =============================================================================
# YIELD ESTIMATION FROM PER-PLANT DB DATA
# =============================================================================

def calculate_yield_from_plants(plants: list) -> Dict[str, Any]:
    """
    Estimate mango yield from flowering_degree.
    High flowering → strong fruiting season → 60-110 kg/tree
    Medium flowering → moderate season    → 30-65  kg/tree
    Low  flowering → limited season       → 10-35  kg/tree
    """
    if not plants:
        return {"min_kg": 0, "max_kg": 0, "per_tree_avg_kg": 0}

    YIELD_RANGE = {"High": (60, 110), "Medium": (30, 65), "Low": (10, 35)}
    total_min = sum(YIELD_RANGE.get(p.flowering_degree or "Medium", (30, 65))[0] for p in plants)
    total_max = sum(YIELD_RANGE.get(p.flowering_degree or "Medium", (30, 65))[1] for p in plants)
    n = len(plants)
    avg = (total_min + total_max) / 2
    return {
        "min_kg": round(total_min),
        "max_kg": round(total_max),
        "per_tree_avg_kg": round(avg / n, 1),
    }


# =============================================================================
# SINGLE GEMINI VISION + DB ANSWER  (1 API call, lowest latency)
# =============================================================================

def _gemini_vision_answer(
    question: str,
    cropped_b64: str,
    area_data: Dict[str, Any],
    db_plants: list,
) -> tuple:
    """
    One Gemini call that simultaneously:
      1. Counts tree canopies from the cropped polygon image (exact visual count)
      2. Scales per-plant DB rates by that visual count (handles any region size)
      3. Answers the farmer's question in pinpoint format

    Returns (answer_str, sources_list)
    """
    # ── Build DB context from 2 stored fields: canopy_size, flowering_degree ──
    n_db = len(db_plants)
    if n_db > 0:
        # Canopy counts and %
        large_n  = sum(1 for p in db_plants if p.canopy_size == "Large")
        medium_n = sum(1 for p in db_plants if p.canopy_size == "Medium")
        small_n  = sum(1 for p in db_plants if p.canopy_size == "Small")
        large_pct  = round(large_n  / n_db * 100)
        medium_pct = round(medium_n / n_db * 100)
        small_pct  = round(small_n  / n_db * 100)

        # Flowering counts and %
        fl_high = sum(1 for p in db_plants if p.flowering_degree == "High")
        fl_med  = sum(1 for p in db_plants if p.flowering_degree == "Medium")
        fl_low  = sum(1 for p in db_plants if p.flowering_degree == "Low")
        fl_high_pct = round(fl_high / n_db * 100)
        fl_med_pct  = round(fl_med  / n_db * 100)
        fl_low_pct  = round(fl_low  / n_db * 100)

        # Per-tree fertilizer (canopy-weighted benchmark)
        FERT = {"Large": (2.2, 0.9, 1.3, 32), "Medium": (1.8, 0.7, 1.0, 25), "Small": (1.2, 0.5, 0.7, 18)}
        urea_per   = round((large_n*FERT["Large"][0] + medium_n*FERT["Medium"][0] + small_n*FERT["Small"][0]) / n_db, 2)
        dap_per    = round((large_n*FERT["Large"][1] + medium_n*FERT["Medium"][1] + small_n*FERT["Small"][1]) / n_db, 2)
        potash_per = round((large_n*FERT["Large"][2] + medium_n*FERT["Medium"][2] + small_n*FERT["Small"][2]) / n_db, 2)
        manure_per = round((large_n*FERT["Large"][3] + medium_n*FERT["Medium"][3] + small_n*FERT["Small"][3]) / n_db, 1)

        # Per-tree yield (flowering-based benchmark)
        yd = calculate_yield_from_plants(db_plants)
        yield_min_per = round(yd["min_kg"] / n_db, 1)
        yield_max_per = round(yd["max_kg"] / n_db, 1)

        db_context = (
            f"FARM DATABASE ({n_db} sample plants near this region):\n"
            f"  Canopy: {large_pct}% Large, {medium_pct}% Medium, {small_pct}% Small\n"
            f"  Flowering: {fl_high_pct}% High, {fl_med_pct}% Medium, {fl_low_pct}% Low\n"
            f"  Per-tree fertilizer (canopy-weighted): Urea {urea_per} kg, DAP {dap_per} kg, Potash {potash_per} kg, Manure {manure_per} kg\n"
            f"  Per-tree yield (flowering-based): {yield_min_per}–{yield_max_per} kg/season\n"
            f"  SCALE RULE: Multiply all per-tree values by N (your visual count from the image)"
        )
        sources = ["Gemini Vision", "Plant Database (PostgreSQL)"]
    else:
        db_context = (
            "No database records for this region. Use standard mango orchard benchmarks:\n"
            "  Canopy: ~30% Large, 50% Medium, 20% Small\n"
            "  Flowering: ~35% High, 40% Medium, 25% Low\n"
            "  Per-tree fertilizer: Urea 1.8 kg, DAP 0.7 kg, Potash 1.0 kg, Manure 25 kg\n"
            "  Per-tree yield: 40–80 kg/season\n"
            "  SCALE RULE: Multiply all per-tree values by N (your visual count from the image)"
        )
        sources = ["Gemini Vision"]

    area_line = ""
    if area_data:
        area_line = f"AREA: {area_data.get('area_acres', 0):.2f} acres"

    # ── Build the strict system prompt ────────────────────────────────────────
    system_prompt = """You are an expert aerial mango farm analyst for a live demo. Accuracy and precision are critical.

You receive: (1) a cropped drone image — bright polygon = selected area, dark = excluded, (2) farm DB context.

━━━ STEP 1 — COUNT (non-negotiable) ━━━
Look ONLY at the bright polygon region. Every distinct round/oval green canopy cluster = 1 mango tree.
- Count each canopy individually, even if partially inside the boundary.
- If only 1 tree is visible, count it as 1. Never say "approximately".
- If nothing is visible in the bright region, count is 0.

━━━ STEP 2 — VISUALLY CLASSIFY (for canopy/flowering queries) ━━━
For each tree you counted, assess directly from the image:
  Canopy:    Large = wide spreading crown clearly larger than others
             Medium = typical mature mango size
             Small = noticeably compact, younger, or stunted
  Flowering: High = visible bright/pale clusters or dense flowering patches on crown
             Medium = few bright patches, mostly green
             Low = fully green, no visible flowering
Use the DB percentage distributions as a sanity reference.
For ≤5 trees: rely more on your direct visual observation than the DB distribution.

━━━ STEP 3 — COMPUTE ━━━
  Fertilizer: per-tree rate × N
  Yield: per-tree yield range × N
  Area: already provided — just report it

━━━ STEP 4 — ANSWER ━━━
Answer ONLY the exact question asked. Nothing more.

ABSOLUTE RULES:
  - EXACTLY ONE LINE. One sentence. Always. No exceptions.
  - Combined queries (e.g. count + area): pack into one line, topics separated by a comma or dash.
  - No greetings, no filler, no "I can see", no "based on", no markdown (**, ##, -, backticks)
  - No restating the question
  - Singular when N=1: "1 mango tree" never "1 mango trees"
  - Round: kg to 2 decimals, acres to 2 decimals, counts whole numbers
  - Out of scope (soil, disease, pest, irrigation, exact age): "Cannot determine [topic] from aerial imagery."

ONE-LINE FORMATS — copy exactly:
  Count:        "N mango trees in the selected area."
  Area:         "X.XX acres."
  Count+Area:   "N mango trees across X.XX acres."
  Canopy:       "N large, M medium, S small canopy trees."
  Flowering:    "N high, M medium, S low flowering trees."
  Fruiting:     "~N trees fruiting or developing (high flowering), M with limited fruit this season."
  Health:       "N trees highly active (high flowering), M moderate, S low activity."
  Fertilizer:   "For N tree(s): Urea X.XX kg, DAP Y.YY kg, Potash Z.ZZ kg, Manure W.WW kg."
  Yield:        "~X kg estimated yield this season (N trees × avg Y.YY kg/tree based on flowering)."
  Combined:     "N trees, X.XX acres — Urea A kg, DAP B kg." (one line, comma/dash separated)
  0 trees:      "No trees detected in the selected area."
  Out of scope: "Cannot determine [topic] from aerial imagery."

LANGUAGE: Always respond in English. Translation is handled separately."""

    user_msg = f"""Question: {question}

{area_line}

{db_context}

Count the trees in the bright polygon region of the image, visually classify their canopy and flowering where relevant, scale the per-tree rates by your count, and answer the question."""

    # ── Single LLM call ───────────────────────────────────────────────────────
    llm = ChatGoogleGenerativeAI(
        model="gemini-2.5-flash",
        temperature=0.0,
        google_api_key=GEMINI_API_KEY,
    )
    response = llm.invoke([
        SystemMessage(content=system_prompt),
        HumanMessage(content=[
            {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{cropped_b64}"}},
            {"type": "text", "text": user_msg},
        ]),
    ])
    answer = response.content.strip()
    # Strip any markdown that slipped through
    answer = re.sub(r'\*\*([^*]+)\*\*', r'\1', answer)
    answer = re.sub(r'\*([^*]+)\*', r'\1', answer)
    answer = re.sub(r'^#+\s+', '', answer, flags=re.MULTILINE)
    answer = re.sub(r'^[-•]\s+', '', answer, flags=re.MULTILINE)

    return answer, sources


# =============================================================================
# MAIN ENTRY POINT
# =============================================================================

def run_drone_agent(
    question: str,
    image_b64: str,
    points: List[List[float]],
    telemetry: Dict[str, Any],
    use_llm: bool = True,
    db=None,
    gps_points: Optional[List[List[float]]] = None,
) -> Dict[str, Any]:
    """
    Main entry point for drone image analysis.

    Fast path (use_llm=True + Gemini available + image):
      1. area — geodesic GPS math (no API, <5ms)
      2. DB query — plants in polygon (no API, <50ms)
      3. crop image — OpenCV polygon crop (no API, <30ms)
      4. ONE Gemini call — counts from image + scales DB rates + answers question

    Fallback (no LLM / no image):
      Uses answer_query_from_db → answer_query_pure (OpenCV HSV)
    """
    # Step 1: Area (pure math, always fast)
    area_data = {}
    if len(points) >= 3:
        area_data = calculate_area_pure(points, telemetry)

    # Step 2: DB query for per-plant agronomic rates
    db_plants = []
    if db is not None and len(points) >= 3:
        try:
            from app.agents.calc_tools import query_plants_in_polygon
            db_plants = query_plants_in_polygon(points, telemetry, db, gps_points=gps_points)
            print(f"[run_drone_agent] DB: {len(db_plants)} nearby plants for rate context")
        except Exception as e:
            print(f"[run_drone_agent] DB query failed: {e}")

    # Step 3: Fast path — single Gemini vision call
    if use_llm and GEMINI_AVAILABLE and GEMINI_API_KEY and image_b64:
        try:
            cropped_b64 = crop_image_to_polygon(image_b64, points) or image_b64
            answer, sources = _gemini_vision_answer(question, cropped_b64, area_data, db_plants)
            print("[run_drone_agent] ✓ Single Gemini vision call completed")
            return {
                "answer": answer,
                "sources": sources,
                "tools_used": ["gemini_vision", "query_plants_db" if db_plants else "area_calculator"],
                "data": {"area": area_data},
                "llm_used": True,
            }
        except Exception as e:
            print(f"[run_drone_agent] Gemini vision failed, falling back: {e}")

    # Step 4: Fallback — pure CV / DB (no LLM)
    print("[run_drone_agent] Using CV fallback (no LLM)")
    if db_plants:
        result = answer_query_from_db(question, db_plants, points, telemetry)
    else:
        result = answer_query_pure(question, image_b64, points, telemetry)

    source_names = {
        "calculate_area": "Area Calculator",
        "count_plants": "Plant Detection (OpenCV)",
        "calculate_fertilizer": "Fertilizer Estimator",
        "calculate_manure": "Manure Calculator",
        "assess_health": "Health Assessment (CV)",
        "detect_type": "Plant Type Detection",
        "query_plants_db": "Plant Database (PostgreSQL)",
    }
    tools_used = result.get("tools_used", [])
    return {
        "answer": result["answer"],
        "sources": [source_names.get(t, t) for t in tools_used],
        "tools_used": tools_used,
        "data": result.get("data", {}),
        "llm_used": False,
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