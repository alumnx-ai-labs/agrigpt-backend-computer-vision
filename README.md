# Drone Frame Intelligence System — Backend API

FastAPI backend for drone video analysis with agricultural insights.

## Features

- **Video Streaming** — byte-range streaming from S3/CDN or local files
- **Frame Capture** — extract JPEG frames at any timestamp
- **Telemetry Sync** — GPS/altitude data from DJI `.SRT` files
- **Area Calculation** — GSD math + GPS/WGS-84 geodesic projection
- **Plant Counting** — OpenCV color segmentation
- **Agricultural Analysis** — fertilizer/manure estimation, crop health scoring
- **LLM Analysis** — optional Gemini-powered frame Q&A

## Project Structure

```
image-query/
├── app/
│   ├── main.py               # FastAPI entry point
│   ├── config.py             # All env-var settings
│   ├── api/routes/
│   │   ├── video.py          # GET /video — streaming
│   │   ├── video_upload.py   # POST /videos/upload
│   │   ├── telemetry.py      # GET /telemetry/{frame_num}
│   │   ├── analysis.py       # POST /calculate
│   │   ├── frames.py         # /image-query/* — capture + query
│   │   └── srt.py            # GET /srt, POST /srt/ingest
│   ├── core/
│   │   ├── database.py       # SQLAlchemy engine + session
│   │   ├── models.py         # ORM models
│   │   └── srt_parser.py     # DJI SRT parser
│   ├── services/
│   │   ├── video_service.py  # Video streaming + frame extraction
│   │   ├── storage_service.py# S3/local frame storage
│   │   └── telemetry_service.py
│   ├── agents/
│   │   ├── drone_agent.py    # LangGraph agent entry point
│   │   ├── cv_tools.py       # OpenCV tools
│   │   └── calc_tools.py     # GSD + area tools
│   └── utils/geo_utils.py    # GPS/UTM conversions
├── scripts/
│   ├── ingest_srt.py         # One-time SRT bulk ingest
│   └── upload_to_s3.py       # Upload drone.mp4 to S3
├── requirements.txt
├── .env.example
└── README.md
```

---

## Deployment Steps

### Prerequisites

- Python 3.13
- PostgreSQL database (local or RDS)
- AWS S3 bucket (optional — local fallback available)
- Gemini API key (optional — only for `use_llm: true` queries)

---

### Step 1 — Clone and enter the directory

```bash
cd image-query
```

### Step 2 — Create and activate the virtual environment

```bash
python3.13 -m venv .venv
source .venv/bin/activate          # macOS/Linux
# .venv\Scripts\activate           # Windows
```

### Step 3 — Install dependencies

```bash
pip install -r requirements.txt
```

### Step 4 — Configure environment variables

```bash
cp .env.example .env
```

Edit `.env` and fill in your values:

| Variable                | Required        | Description                                      |
| ----------------------- | --------------- | ------------------------------------------------ |
| `GEMINI_API_KEY`        | For LLM queries | Gemini API key                                   |
| `DB_HOST`               | Yes             | PostgreSQL host                                  |
| `DB_PORT`               | Yes             | PostgreSQL port (default 5432)                   |
| `DB_NAME`               | Yes             | Database name                                    |
| `DB_USER`               | Yes             | Database user                                    |
| `DB_PASSWORD`           | Yes             | Database password                                |
| `S3_BUCKET`             | For S3 storage  | S3 bucket name                                   |
| `AWS_ACCESS_KEY_ID`     | For S3 storage  | AWS access key                                   |
| `AWS_SECRET_ACCESS_KEY` | For S3 storage  | AWS secret key                                   |
| `AWS_REGION`            | For S3 storage  | AWS region (e.g. `ap-south-1`)                   |
| `VIDEO_S3_KEY`          | For S3 video    | S3 object key for drone video                    |
| `VIDEO_CDN_URL`         | Optional        | CloudFront CDN base URL (overrides S3 presigned) |

> If `S3_BUCKET` is not set, frames are saved locally to `captured_frames/`.

### Step 5 — Place your video and SRT files

Put your drone files in `image-query/`:

```
image-query/
├── drone.mp4
└── drone.SRT
```

Or skip this and use S3 by setting `VIDEO_S3_KEY` in `.env`.

### Step 6 — Initialize the database

Tables are created automatically on first startup. To verify the DB is reachable:

```bash
.venv/bin/python -c "from app.core.database import init_db; init_db()"
```

### Step 7 — Ingest SRT telemetry

The API needs telemetry loaded into the DB before capture/calculate endpoints work.

**Option A — via script (one-time bulk ingest):**

```bash
.venv/bin/python scripts/ingest_srt.py
```

**Option B — via API (recommended, works for any video_id):**

First start the server (Step 8), then:

```bash
curl -X POST http://localhost:8000/srt/ingest \
  -H "Content-Type: application/json" \
  -d '{"srt_url": "http://localhost:8000/srt", "video_id": "drone", "overwrite": true}'
```

### Step 8 — Start the server

**Development:**

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Production:**

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

The API will be live at `http://localhost:8000`.
Interactive docs: `http://localhost:8000/docs`

---

## API Endpoints

| Endpoint                             | Method | Description                  |
| ------------------------------------ | ------ | ---------------------------- |
| `/`                                  | GET    | API info                     |
| `/health`                            | GET    | Health check                 |
| `/video`                             | GET    | Stream default video         |
| `/video/{video_id}`                  | GET    | Stream video by ID           |
| `/video/list/all`                    | GET    | List S3 videos               |
| `/videos/upload`                     | POST   | Upload video + SRT to S3     |
| `/videos/list`                       | GET    | List uploaded videos         |
| `/videos/{video_key}`                | GET    | Video metadata               |
| `/videos/{video_key}`                | DELETE | Delete video                 |
| `/telemetry/{frame_num}`             | GET    | Telemetry for a frame        |
| `/telemetry/video/{video_id}/frames` | GET    | All frames for a video       |
| `/calculate`                         | POST   | Area calculation for polygon |
| `/image-query/capture`               | POST   | Capture frame at timestamp   |
| `/image-query/frames`                | GET    | List captured frames         |
| `/image-query/frame/{frame_id}`      | GET    | Get frame image              |
| `/image-query/query`                 | POST   | Analyze frame with AI        |
| `/srt`                               | GET    | Serve local SRT file         |
| `/srt/ingest`                        | POST   | Ingest SRT from URL into DB  |

---

## Usage Examples

### Capture a frame

```bash
curl -X POST http://localhost:8000/image-query/capture \
  -H "Content-Type: application/json" \
  -d '{"time_sec": 10.5, "video_id": "drone"}'
```

### Calculate ground area

```bash
curl -X POST http://localhost:8000/calculate \
  -H "Content-Type: application/json" \
  -d '{
    "frame": 600,
    "points": [[100, 200], [300, 200], [300, 400], [100, 400]],
    "video_id": "drone"
  }'
```

### Analyze a frame (CV-only, no LLM)

```bash
curl -X POST http://localhost:8000/image-query/query \
  -H "Content-Type: application/json" \
  -d '{
    "frame_id": "<uuid-from-capture>",
    "points": [[100, 200], [300, 400]],
    "question": "how many plants are in this area?",
    "use_llm": false
  }'
```

### Analyze a frame (with Gemini LLM)

```bash
curl -X POST http://localhost:8000/image-query/query \
  -H "Content-Type: application/json" \
  -d '{
    "frame_id": "<uuid-from-capture>",
    "points": [[100, 200], [300, 400]],
    "question": "What crop type is visible and what is its health status?",
    "use_llm": true
  }'
```

---

## Known Limitations / Production Notes

- **No auth** on DELETE endpoints — add API key middleware or a reverse-proxy rule before exposing publicly
- **Video upload** (`POST /videos/upload`) reads the full video file into memory — fine for files <500MB, use multipart/streaming for larger files
- **`@app.on_event("startup")`** is deprecated in FastAPI 0.93+ but still functional; migrate to `lifespan` context manager when convenient
- **Videos uploaded via `POST /videos/upload`** are stored at `videos/{key}/video.mp4` but `GET /video/{key}` resolves to `{S3_VIDEO_PREFIX}/{key}.mp4` — these won't match unless you set `S3_VIDEO_PREFIX=videos` or use the DB-stored `video_s3_key` directly

---

## License

MIT
