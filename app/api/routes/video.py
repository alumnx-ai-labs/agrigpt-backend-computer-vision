"""
Video API Routes - Video streaming and listing endpoints.
"""

from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import StreamingResponse, RedirectResponse
from sqlalchemy.orm import Session
from sqlalchemy import distinct

from app.core.database import get_db
from app.core.models import DroneFrame
from app.services.video_service import VideoService
from app.config import DEFAULT_VIDEO_ID

router = APIRouter(prefix="/video", tags=["Video"])

video_service = VideoService()


@router.get("")
async def stream_default_video(request: Request):
    """Stream the default video — delegates to /video/{DEFAULT_VIDEO_ID}."""
    return await stream_video_by_id(DEFAULT_VIDEO_ID, request)


@router.get("/{video_id}")
async def stream_video_by_id(video_id: str, request: Request):
    """Stream a specific video by video_id — redirects to S3/CDN or streams local."""
    streaming_info = video_service.get_streaming_info(video_id)
    
    if streaming_info["type"] == "redirect":
        return RedirectResponse(url=streaming_info["url"], status_code=302)
    
    if streaming_info["type"] == "local":
        return await _stream_local_video(streaming_info["path"], streaming_info["size"], request)
    
    raise HTTPException(404, f"Video {video_id} not found")


@router.get("/list/all")
def list_videos(db: Session = Depends(get_db)):
    """List available videos: from S3 + any ingested into DB."""
    s3_videos = video_service.list_s3_videos()
    return {"videos": s3_videos}


async def _stream_local_video(path: str, file_size: int, request: Request):
    """Byte-range streaming helper for a local mp4 file."""
    range_header = request.headers.get("range")
    
    if not range_header:
        def iterfile_full():
            with open(path, "rb") as f:
                yield from iter(lambda: f.read(65536), b"")
        
        return StreamingResponse(
            iterfile_full(),
            media_type="video/mp4",
            headers={"Content-Length": str(file_size), "Accept-Ranges": "bytes"},
        )
    
    start, _, end = range_header.replace("bytes=", "").partition("-")
    
    try:
        start = int(start)
    except ValueError:
        from fastapi.responses import Response as _R
        return _R(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})
    
    if start >= file_size:
        from fastapi.responses import Response as _R
        return _R(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})
    
    try:
        end = int(end) if end else file_size - 1
    except ValueError:
        from fastapi.responses import Response as _R
        return _R(status_code=416, headers={"Content-Range": f"bytes */{file_size}"})
    
    end = min(end, file_size - 1)
    length = end - start + 1

    def iterfile():
        with open(path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                data = f.read(min(1 << 20, remaining))
                if not data:
                    break
                remaining -= len(data)
                yield data

    return StreamingResponse(
        iterfile(),
        status_code=206,
        media_type="video/mp4",
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Content-Length": str(length),
            "Accept-Ranges": "bytes",
        },
    )