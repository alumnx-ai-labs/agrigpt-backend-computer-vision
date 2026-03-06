Drone Frame Intelligence System

Product Requirements Document & System Workflow

---

1. Overview

The Drone Frame Intelligence System is an AI-powered geospatial analysis platform that enables users to analyze drone video frames and extract agricultural insights using natural language queries.

The system integrates:

- Drone video playback
- Frame capture and storage
- Geospatial telemetry from SRT data
- Computer vision models
- AI agent orchestration using LangGraph
- Natural language query routing using Gemini

Users can visually select regions in drone imagery and ask questions such as:

- What is the area inside this region?
- How many mango plants are present?
- How much fertilizer is required?
- How much manure is needed?

The system converts drone video data into actionable agricultural intelligence.

---

2. Objectives

Primary objectives of the platform:

1. Enable frame capture from drone video timeline.
2. Allow spatial region selection using markers.
3. Enable natural language queries on selected regions.
4. Integrate AI agents for spatial reasoning.
5. Provide clean and interpretable outputs suitable for demos and presentations.

---

3. High-Level System Architecture

React Frontend
      |
      v
FastAPI Backend API
      |
      v
LangGraph Agent Orchestrator
      |
      v
Tool Execution Layer
      |
      +---------------------+
      |                     |
      v                     v
AWS S3               PostgreSQL
(Frame Storage)      (SRT Telemetry)

      |
      v
Computer Vision Models
(Plant Detection / Analysis)

---

4. Core Data Sources

PostgreSQL

PostgreSQL stores drone telemetry extracted from SRT files.

Telemetry fields include:

timestamp
latitude
longitude
altitude
yaw
pitch
roll

Example record:

timestamp: 12.53
latitude: 17.385
longitude: 78.486
altitude: 41.2
yaw: 120
pitch: -90
roll: 0

---

AWS S3

S3 stores all captured frames.

Example path:

s3://drone-analysis/frames/video_001/frame_360.jpg

Metadata stored with each frame:

frame_id
video_id
frame_number
timestamp
s3_url

---

5. Video Playback Workflow

The frontend provides a video player interface.

Capabilities:

- Play / Pause video
- Seek timeline
- Jump to specific timestamps
- Capture frames

Drone videos include associated SRT telemetry data.

Mapping logic:

frame_number = time * fps
time = frame_number / fps

This mapping allows the system to retrieve telemetry corresponding to any frame.

---

6. Frame Capture Flow

When a user clicks the Capture Frame button:

1. The frontend identifies the current video timestamp.
2. The backend extracts the closest frame.
3. The frame is uploaded to AWS S3.
4. Frame metadata is stored.
5. The frame appears in the captured frames panel.

Example API:

POST /capture-frame

Payload:

video_id
timestamp

Response:

frame_number
s3_url

---

7. Captured Frames Panel

Captured frames appear in the right panel of the interface.

Features:

- Multiple frames can be captured.
- Frames are loaded from S3.
- Frames display as thumbnails.

Each captured frame can be selected for analysis.

---

8. Frame Selection Behavior

When a user clicks a captured frame:

1. The selected frame moves to the main analysis panel.
2. The video moves to the right preview panel.
3. The system enables spatial marker placement.

This interaction allows users to switch between:

- Video exploration
- Frame analysis

---

9. Marker Placement

Users can place four markers on the selected frame.

Markers define a polygon region.

Example marker structure:

P1 (x1, y1)
P2 (x2, y2)
P3 (x3, y3)
P4 (x4, y4)

This polygon defines the region used for analysis.

---

10. Pixel-to-Real-World Conversion

Area calculations require converting pixel distances to real-world measurements.

The system uses telemetry data including:

- Drone altitude
- Camera field of view
- Image resolution

Ground Sampling Distance (GSD):

GSD = (2 * altitude * tan(FOV / 2)) / image_width

This produces:

meters_per_pixel

Pixel distances are converted to meters.

---

11. Polygon Area Calculation

Once pixel coordinates are converted to meters, the polygon area is calculated.

Area calculation uses the Shoelace formula.

Result example:

Area: 152 square meters

---

12. Natural Language Query Interface

Below the image analysis panel is a natural language query input.

Example queries:

What is the area inside these markers?
How many mango plants are present?
How much fertilizer is needed?
How much manure is required?

These queries are processed through LangGraph.

---

13. AI Agent Architecture

The platform uses LangGraph to orchestrate tools.

Agent responsibilities:

1. Understand user query
2. Route query to correct tool
3. Execute analysis
4. Return structured response

---

14. Query Routing with Gemini

Gemini is used to classify user queries.

Possible classifications:

AREA_QUERY
PLANT_COUNT_QUERY
FERTILIZER_QUERY
MANURE_QUERY

Example:

User query:

How many mango plants are inside the region?

Router output:

tool: plant_counter

---

15. LangGraph Tools

Area Calculator Tool

Calculates the area of the marker polygon.

Input:

markers
frame_number
video_id

Process:

1. Retrieve telemetry from PostgreSQL.
2. Convert pixel coordinates to meters.
3. Calculate polygon area.

Output:

Area: 152 m²

---

Plant Detection Tool

Counts plants within the marker region.

Process:

1. Load frame from S3.
2. Run plant detection model.
3. Extract plant bounding boxes.
4. Filter plants inside polygon.

Example logic:

cv2.pointPolygonTest()

Output:

Mango plants detected: 18

---

Fertilizer Estimation Tool

Uses agricultural guidelines.

Example formula:

fertilizer_required = area * fertilizer_rate_per_m2

Example output:

Recommended fertilizer: 3.2 kg

---

Manure Estimation Tool

Example formula:

manure_required = area * manure_rate

Example output:

Required manure: 6.5 kg

---

16. Image Query API

Endpoint:

POST /image-query

Payload:

{
  "s3_url": "...",
  "frame_number": 360,
  "markers": [[x1,y1],[x2,y2],[x3,y3],[x4,y4]],
  "query": "How many plants are inside the markers?"
}

---

17. Complete System Flow

User plays drone video
        |
        v
User captures frame
        |
        v
Frame saved to S3
        |
        v
Frame appears in captured frames panel
        |
        v
User selects frame
        |
        v
Frame opens in analysis panel
        |
        v
User places markers
        |
        v
User enters NLP query
        |
        v
LangGraph agent processes query
        |
        v
Gemini routes query to correct tool
        |
        v
Tool executes analysis
        |
        v
Response returned to frontend

---

18. Deployment Strategy

Recommended deployment stack:

Backend:

FastAPI
Docker

Agent orchestration:

LangGraph service

Infrastructure:

AWS EC2 or Render
PostgreSQL database
AWS S3 storage

ML inference runs within the FastAPI service.

---

19. UI Layout

Recommended UI layout:

----------------------------------------------------
|                 MAIN ANALYSIS PANEL               |
|                                                   |
|          Selected Frame + Marker Overlay          |
|                                                   |
----------------------------------------------------
|                 NLP QUERY INPUT                   |
----------------------------------------------------
| Captured Frames Panel | Video Preview Panel      |
----------------------------------------------------

---

20. Demo Scenario

Demo flow:

1. Open drone video.
2. Navigate timeline.
3. Capture multiple frames.
4. Select a frame.
5. Place four markers.
6. Ask a natural language query.

Example output:

Area: 152 m²
Mango plants: 18
Recommended fertilizer: 3.2 kg
Required manure: 6.5 kg

---

21. Success Criteria

The system should demonstrate:

- Smooth video playback
- Fast frame capture (<1s)
- Accurate spatial calculations
- Correct AI tool routing
- Clean UI visualization
- Response time <5 seconds

---

22. Future Enhancements

Potential improvements:

- Multi-polygon region selection
- Multi-frame analysis
- Crop health detection
- Plant disease detection
- GIS export
- Satellite + drone data fusion

---

End of Document