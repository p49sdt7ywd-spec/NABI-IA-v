"""
Nabi AI — Transcription Pipeline Module
Uses mlx-whisper for Apple Silicon optimized speech-to-text with word-level timestamps.
Falls back to openai-whisper if mlx is not available.
"""

import asyncio
import subprocess
import json
import os
from pathlib import Path


async def transcribe(video_path: str, project_dir: str, model: str = "mlx-community/whisper-large-v3-turbo", on_progress=None) -> dict:
    """
    Transcribe a video file to text with word-level timestamps.
    
    1. Extracts audio from video using FFmpeg
    2. Runs mlx-whisper (or fallback) for transcription
    3. Returns structured transcription with segments and words
    """
    project_path = Path(project_dir)
    audio_path = project_path / "audio.wav"
    
    # Step 1: Extract audio with FFmpeg
    if on_progress:
        await on_progress("transcription", 10, "Extraction audio...")
    
    ffmpeg_bin = _find_ffmpeg()
    
    result = subprocess.run(
        [
            ffmpeg_bin, "-i", video_path,
            "-vn",                    # No video
            "-acodec", "pcm_s16le",   # PCM 16-bit
            "-ar", "16000",           # 16kHz (Whisper standard)
            "-ac", "1",               # Mono
            "-y",                     # Overwrite
            str(audio_path),
        ],
        capture_output=True,
        text=True,
    )
    
    if result.returncode != 0:
        raise RuntimeError(f"FFmpeg audio extraction failed: {result.stderr}")
    
    if on_progress:
        await on_progress("transcription", 30, "Transcription en cours...")
    
    # Step 2: Transcribe with mlx-whisper
    try:
        transcription = await _transcribe_mlx(str(audio_path), model, on_progress)
    except ImportError:
        # Fallback: use openai-whisper
        transcription = await _transcribe_openai_whisper(str(audio_path), on_progress)
    
    # Step 3: Save transcription
    transcription_path = project_path / "transcription.json"
    with open(transcription_path, "w", encoding="utf-8") as f:
        json.dump(transcription, f, ensure_ascii=False, indent=2)
    
    if on_progress:
        await on_progress("transcription", 100, "Transcription terminée ✓")
    
    return transcription


async def _transcribe_mlx(audio_path: str, model: str, on_progress=None) -> dict:
    """Transcribe using mlx-whisper (Apple Silicon optimized)."""
    import mlx_whisper
    
    # Run in thread to avoid blocking the event loop
    result = await asyncio.to_thread(
        mlx_whisper.transcribe,
        audio_path,
        path_or_hf_repo=model,
        word_timestamps=True,
        language="fr",
    )
    
    if on_progress:
        await on_progress("transcription", 80, "Post-traitement...")
    
    # Format output
    segments = []
    for seg in result.get("segments", []):
        words = []
        for w in seg.get("words", []):
            words.append({
                "word": w["word"].strip(),
                "start": round(w["start"], 3),
                "end": round(w["end"], 3),
                "confidence": round(w.get("probability", 0), 3),
            })
        
        segments.append({
            "id": seg.get("id", len(segments)),
            "start": round(seg["start"], 3),
            "end": round(seg["end"], 3),
            "text": seg["text"].strip(),
            "words": words,
        })
    
    return {
        "language": result.get("language", "fr"),
        "duration": segments[-1]["end"] if segments else 0,
        "text": result.get("text", "").strip(),
        "segments": segments,
    }


async def _transcribe_openai_whisper(audio_path: str, on_progress=None) -> dict:
    """Fallback: transcribe using openai-whisper (slower, CPU-based)."""
    import whisper
    
    model = whisper.load_model("medium")
    
    result = whisper.transcribe(
        model,
        audio_path,
        word_timestamps=True,
        language="fr",
    )
    
    if on_progress:
        await on_progress("transcription", 80, "Post-traitement...")
    
    segments = []
    for seg in result.get("segments", []):
        words = []
        for w in seg.get("words", []):
            words.append({
                "word": w["word"].strip(),
                "start": round(w["start"], 3),
                "end": round(w["end"], 3),
                "confidence": round(w.get("probability", 0), 3),
            })
        
        segments.append({
            "id": seg.get("id", len(segments)),
            "start": round(seg["start"], 3),
            "end": round(seg["end"], 3),
            "text": seg["text"].strip(),
            "words": words,
        })
    
    return {
        "language": result.get("language", "fr"),
        "duration": segments[-1]["end"] if segments else 0,
        "text": result.get("text", "").strip(),
        "segments": segments,
    }


def _find_ffmpeg() -> str:
    """Find FFmpeg binary, checking common locations."""
    locations = [
        os.path.expanduser("~/.local/bin/ffmpeg"),
        "/usr/local/bin/ffmpeg",
        "/opt/homebrew/bin/ffmpeg",
        "ffmpeg",  # fallback to PATH
    ]
    for loc in locations:
        if os.path.isfile(loc) and os.access(loc, os.X_OK):
            return loc
    # Try PATH
    import shutil
    found = shutil.which("ffmpeg")
    if found:
        return found
    raise FileNotFoundError(
        "FFmpeg not found. Install it with: brew install ffmpeg"
    )
