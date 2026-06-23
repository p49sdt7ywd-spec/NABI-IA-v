"""
Nabi AI — FastAPI Backend Server
Handles video upload, processing pipeline, project management, and real-time progress via WebSocket.
"""

import asyncio
import json
import os
import shutil
import traceback
from contextlib import asynccontextmanager
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
import aiofiles

import database as db
from pipeline import transcriber, analyzer, compositor
from pipeline.analyzer import OLLAMA_URL

# Active WebSocket connections per project
ws_connections: dict[str, list[WebSocket]] = {}

# Active processing tasks
active_tasks: dict[str, asyncio.Task] = {}


# ── App Setup ─────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    db.init_db()
    print("✨ Nabi AI Backend — Ready on http://localhost:8000")
    print(f"📂 Projects directory: {db.PROJECTS_DIR}")
    yield

app = FastAPI(title="Nabi AI", version="0.1.0", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://127.0.0.1:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── WebSocket ─────────────────────────────────

@app.websocket("/ws/{project_id}")
async def websocket_endpoint(websocket: WebSocket, project_id: str):
    """WebSocket endpoint for real-time progress updates."""
    await websocket.accept()
    
    if project_id not in ws_connections:
        ws_connections[project_id] = []
    ws_connections[project_id].append(websocket)
    
    try:
        # Send current project state
        project = db.get_project(project_id)
        if project:
            await websocket.send_json({
                "type": "project_state",
                "data": project,
            })
        
        # Keep connection alive
        while True:
            data = await websocket.receive_text()
            # Handle ping/pong
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        ws_connections[project_id].remove(websocket)
        if not ws_connections[project_id]:
            del ws_connections[project_id]


async def broadcast_progress(project_id: str, step: str, progress: float, message: str):
    """Broadcast progress update to all WebSocket clients for a project."""
    # Update database
    db.update_project(
        project_id,
        current_step=step,
        progress=progress,
        status="processing",
    )
    
    # Broadcast to WebSocket clients
    payload = {
        "type": "progress",
        "data": {
            "step": step,
            "progress": progress,
            "message": message,
        },
    }
    
    if project_id in ws_connections:
        dead = []
        for ws in ws_connections[project_id]:
            try:
                await ws.send_json(payload)
            except Exception:
                dead.append(ws)
        for ws in dead:
            ws_connections[project_id].remove(ws)


# ── Projects API ──────────────────────────────

@app.get("/api/projects")
async def list_projects():
    """List all projects."""
    return db.list_projects()


@app.get("/api/projects/{project_id}")
async def get_project(project_id: str):
    """Get a single project."""
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    return project


@app.delete("/api/projects/{project_id}")
async def delete_project(project_id: str):
    """Delete a project and its files."""
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    # Cancel active task if running
    if project_id in active_tasks:
        active_tasks[project_id].cancel()
        del active_tasks[project_id]
    
    db.delete_project(project_id)
    return {"status": "deleted"}


# ── Upload ────────────────────────────────────

@app.post("/api/upload")
async def upload_video(file: UploadFile = File(...)):
    """
    Upload a video file and create a new project.
    Returns the created project.
    """
    # Validate file type
    allowed_types = {"video/mp4", "video/quicktime", "video/x-matroska", "video/avi", "video/webm"}
    if file.content_type and file.content_type not in allowed_types:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {file.content_type}")
    
    # Create project
    title = Path(file.filename or "Untitled").stem
    project = db.create_project(title=title, source_video_path="")
    project_dir = db.get_project_dir(project["id"])
    
    # Save video file
    video_ext = Path(file.filename or "video.mp4").suffix or ".mp4"
    video_path = project_dir / f"source{video_ext}"
    
    async with aiofiles.open(str(video_path), "wb") as f:
        while chunk := await file.read(1024 * 1024):  # 1MB chunks
            await f.write(chunk)
    
    # Update project with video path
    db.update_project(project["id"], source_video_path=str(video_path))
    
    # Get video duration
    try:
        duration = _get_video_duration(str(video_path))
        db.update_project(project["id"], duration_seconds=duration)
    except Exception:
        pass
    
    return db.get_project(project["id"])


# ── Processing Pipeline ──────────────────────

@app.post("/api/process/{project_id}")
async def start_processing(project_id: str):
    """Start the video processing pipeline for a project."""
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if project_id in active_tasks and not active_tasks[project_id].done():
        raise HTTPException(status_code=409, detail="Project is already being processed")
    
    # Start processing in background
    task = asyncio.create_task(_run_pipeline(project_id))
    active_tasks[project_id] = task
    
    db.update_project(project_id, status="processing", progress=0)
    
    return {"status": "processing", "project_id": project_id}


@app.post("/api/cancel/{project_id}")
async def cancel_processing(project_id: str):
    """Cancel an active processing pipeline."""
    if project_id in active_tasks and not active_tasks[project_id].done():
        active_tasks[project_id].cancel()
        del active_tasks[project_id]
        db.update_project(
            project_id,
            status="queued",
            current_step="",
            progress=0,
            error_message="",
        )
        await broadcast_progress(project_id, "cancelled", 0, "Traitement annulé")
        return {"status": "cancelled"}
    
    raise HTTPException(status_code=404, detail="No active processing for this project")


async def _run_pipeline(project_id: str):
    """Run the full 5-stage processing pipeline for a project."""
    try:
        project = db.get_project(project_id)
        project_dir = str(db.get_project_dir(project_id))
        video_path = project["source_video_path"]
        
        # Get settings
        settings = db.get_all_settings()
        
        # Create progress callback that also updates DB
        async def on_progress(step: str, progress: float, message: str):
            await broadcast_progress(project_id, step, progress, message)
        
        # Run the full pipeline via compositor
        results = await compositor.run_full_pipeline(
            project_id=project_id,
            video_path=video_path,
            project_dir=project_dir,
            settings=settings,
            on_progress=on_progress,
        )
        
        # Update project with results from each stage
        if results.get("transcription"):
            db.update_project(project_id, transcription=results["transcription"])
        
        if results.get("edl"):
            db.update_project(project_id, edit_decision_list=results["edl"])
        
        if results.get("output_path"):
            db.update_project(project_id, output_video_path=results["output_path"])
        
        # Mark as completed
        db.update_project(
            project_id,
            status="completed",
            progress=100,
            current_step="completed",
            completed_at=datetime.utcnow().isoformat(),
        )
        
        stages = ", ".join(results.get("stages_completed", []))
        await broadcast_progress(project_id, "completed", 100, f"Pipeline terminé ✓ ({stages})")
    
    except asyncio.CancelledError:
        db.update_project(project_id, status="failed", error_message="Annulé par l'utilisateur")
        raise
    
    except Exception as e:
        error_msg = f"{type(e).__name__}: {str(e)}"
        print(f"❌ Pipeline error for {project_id}: {error_msg}")
        traceback.print_exc()
        db.update_project(project_id, status="failed", error_message=error_msg)
        await broadcast_progress(project_id, "error", 0, error_msg)
    
    finally:
        if project_id in active_tasks:
            del active_tasks[project_id]


# ── Video Streaming ───────────────────────────

@app.get("/api/video/{project_id}/{video_type}")
async def stream_video(project_id: str, video_type: str):
    """
    Stream a project video for in-browser preview.
    video_type: 'source' or 'output'
    """
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    if video_type == "source":
        video_path = project.get("source_video_path")
    elif video_type == "output":
        video_path = project.get("output_video_path")
    else:
        raise HTTPException(status_code=400, detail="video_type must be 'source' or 'output'")
    
    if not video_path or not os.path.exists(video_path):
        raise HTTPException(status_code=404, detail=f"Video '{video_type}' not available")
    
    return FileResponse(video_path, media_type="video/mp4")


# ── Download ──────────────────────────────────

@app.get("/api/download/{project_id}")
async def download_output(project_id: str):
    """Download the output video."""
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    output_path = project.get("output_video_path")
    if not output_path or not os.path.exists(output_path):
        raise HTTPException(status_code=404, detail="Output video not ready")
    
    return FileResponse(
        output_path,
        media_type="video/mp4",
        filename=f"{project['title']}_nabi.mp4",
    )


# ── Settings API ──────────────────────────────

@app.get("/api/settings")
async def get_settings():
    """Get all settings."""
    defaults = {
        "pexels_api_key": "",
        "ollama_model": "qwen3:4b",
        "whisper_model": "mlx-community/whisper-large-v3-turbo",
        "motion_mode": "hyperframes",
        "da_primary": "#FF7820",
        "da_secondary": "#1E1E28",
        "da_background": "#FFFFFF",
        "da_accent_2": "#326FA8",
        "output_resolution": "1080p",
        "output_dir": str(db.PROJECTS_DIR),
        "pip_enabled": "true",
        "remove_silences": "true",
    }
    saved = db.get_all_settings()
    return {**defaults, **saved}


@app.post("/api/settings")
async def save_settings(settings: dict):
    """Save settings."""
    for key, value in settings.items():
        db.set_setting(key, str(value))
    return {"status": "saved"}


# ── Health Check ──────────────────────────────

@app.get("/api/health")
async def health():
    """Health check endpoint."""
    # Check Ollama availability
    ollama_ok = False
    try:
        import httpx
        async with httpx.AsyncClient(timeout=10) as client:
            r = await client.get(f"{OLLAMA_URL}/")
            ollama_ok = r.status_code == 200
    except Exception:
        pass
    
    # Check FFmpeg
    ffmpeg_ok = False
    try:
        transcriber._find_ffmpeg()
        ffmpeg_ok = True
    except FileNotFoundError:
        pass
    
    # Check API keys / modes
    settings = db.get_all_settings()
    pexels_ok = bool(settings.get("pexels_api_key", ""))
    motion_mode = settings.get("motion_mode", "hyperframes")
    
    # Check HyperFrames availability
    hf_ok = False
    try:
        import subprocess
        r = subprocess.run(["npx", "hyperframes", "--version"], capture_output=True, timeout=10)
        hf_ok = r.returncode == 0
    except Exception:
        pass
    
    return {
        "status": "ok",
        "version": "0.3.0",
        "ffmpeg": ffmpeg_ok,
        "ollama": ollama_ok,
        "pexels_api_key": pexels_ok,
        "motion_mode": motion_mode,
        "hyperframes": hf_ok,
        "projects_dir": str(db.PROJECTS_DIR),
    }


@app.get("/api/estimate/{project_id}")
async def estimate_time(project_id: str):
    """Estimate processing time for a project."""
    project = db.get_project(project_id)
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")
    
    duration = project.get("duration_seconds", 0)
    if not duration:
        raise HTTPException(status_code=400, detail="Video duration unknown")
    
    settings = db.get_all_settings()
    estimate = compositor.estimate_pipeline_time(duration, settings)
    return estimate


# ── Helpers ───────────────────────────────────

def _get_video_duration(video_path: str) -> float:
    """Get video duration in seconds using ffprobe."""
    import subprocess
    ffmpeg_path = transcriber._find_ffmpeg()
    ffprobe_path = ffmpeg_path.replace("ffmpeg", "ffprobe")
    
    # If ffprobe not available, try ffmpeg
    if not os.path.isfile(ffprobe_path):
        result = subprocess.run(
            [ffmpeg_path, "-i", video_path],
            capture_output=True, text=True,
        )
        # Parse duration from stderr
        for line in result.stderr.split("\n"):
            if "Duration:" in line:
                time_str = line.split("Duration:")[1].split(",")[0].strip()
                parts = time_str.split(":")
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
        return 0
    
    result = subprocess.run(
        [
            ffprobe_path, "-v", "quiet",
            "-show_entries", "format=duration",
            "-of", "json", video_path,
        ],
        capture_output=True, text=True,
    )
    data = json.loads(result.stdout)
    return float(data["format"]["duration"])


# ── Run ───────────────────────────────────────

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
