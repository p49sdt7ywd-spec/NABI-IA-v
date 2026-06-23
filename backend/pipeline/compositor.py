"""
Nabi AI — Pipeline Compositor / Orchestrator
Orchestrates the full pipeline from transcription to final render.
Manages the sequential execution of all pipeline stages, resource allocation,
and progress reporting.
"""

import asyncio
import json
import os
from pathlib import Path
from typing import Callable, Optional

from pipeline import transcriber, analyzer, image_generator, broll_sourcer, renderer


async def run_full_pipeline(
    project_id: str,
    video_path: str,
    project_dir: str,
    settings: dict,
    on_progress: Optional[Callable] = None,
) -> dict:
    """
    Run the complete video editing pipeline.

    Stages:
      1. Transcription (mlx-whisper) — Extract and transcribe audio
      2. Analysis (Ollama LLM) — Generate Edit Decision List
      3. Image Generation (FLUX/Replicate) — Generate AI images
      4. B-Roll Sourcing (Pexels) — Download stock clips
      5. Rendering (FFmpeg) — Compose and export final video

    Args:
        project_id: Unique project identifier
        video_path: Path to the source video
        project_dir: Path to the project directory
        settings: User settings dict
        on_progress: Async callback (step, progress, message)

    Returns:
        Dict with pipeline results summary
    """
    results = {
        "transcription": None,
        "edl": None,
        "images": [],
        "brolls": [],
        "output_path": None,
        "stages_completed": [],
    }

    # Extract settings
    whisper_model = settings.get("whisper_model", "mlx-community/whisper-large-v3-turbo")
    ollama_model = settings.get("ollama_model", "qwen3:4b")
    image_mode = settings.get("image_mode", "replicate")
    replicate_api_key = settings.get("replicate_api_key", "")
    pexels_api_key = settings.get("pexels_api_key", "")
    output_resolution = settings.get("output_resolution", "1080p")
    pip_enabled = settings.get("pip_enabled", "true") == "true"
    remove_silences = settings.get("remove_silences", "true") == "true"

    # ── Stage 1: Transcription ──────────────────
    if on_progress:
        await on_progress("transcription", 0, "Démarrage de la transcription...")

    transcription = await transcriber.transcribe(
        video_path=video_path,
        project_dir=project_dir,
        model=whisper_model,
        on_progress=on_progress,
    )
    results["transcription"] = transcription
    results["stages_completed"].append("transcription")

    # ── Stage 2: LLM Analysis ──────────────────
    if on_progress:
        await on_progress("analysis", 0, "Analyse du script par l'IA...")

    edl = await analyzer.analyze_transcript(
        transcription=transcription,
        project_dir=project_dir,
        model=ollama_model,
        on_progress=on_progress,
    )
    results["edl"] = edl
    results["stages_completed"].append("analysis")

    # Log EDL summary
    total_segs = len(edl.get("segments", []))
    total_brolls = edl.get("total_brolls", 0)
    total_images = edl.get("total_ai_images", 0)
    print(f"📋 EDL: {total_segs} segments, {total_brolls} B-rolls, {total_images} AI images")

    # ── Stage 3: Image Generation ──────────────
    if on_progress:
        await on_progress("images", 0, "Génération des images IA...")

    images = await image_generator.generate_images(
        edl=edl,
        project_dir=project_dir,
        transcription=transcription,
        mode=image_mode,
        replicate_api_key=replicate_api_key,
        on_progress=on_progress,
    )
    results["images"] = images
    results["stages_completed"].append("images")

    # ── Stage 4: B-Roll Sourcing ───────────────
    if on_progress:
        await on_progress("broll", 0, "Téléchargement des B-rolls...")

    brolls = await broll_sourcer.source_brolls(
        edl=edl,
        project_dir=project_dir,
        pexels_api_key=pexels_api_key,
        on_progress=on_progress,
    )
    results["brolls"] = brolls
    results["stages_completed"].append("broll")

    # ── Stage 5: Final Render ─────────────────
    if on_progress:
        await on_progress("render", 0, "Rendu final en cours...")

    output_path = await renderer.render(
        edl=edl,
        project_dir=project_dir,
        images=images,
        brolls=brolls,
        source_video=video_path,
        resolution=output_resolution,
        remove_silences=remove_silences,
        pip_enabled=pip_enabled,
        on_progress=on_progress,
    )
    results["output_path"] = output_path
    results["stages_completed"].append("render")

    return results


def validate_edl(edl: dict) -> list[str]:
    """
    Validate an EDL for common issues.
    Returns list of warning messages.
    """
    warnings = []
    segments = edl.get("segments", [])

    if not segments:
        warnings.append("EDL has no segments")
        return warnings

    # Check for overlapping segments
    for i in range(len(segments) - 1):
        if segments[i]["end"] > segments[i + 1]["start"]:
            warnings.append(
                f"Segments {i} and {i + 1} overlap: "
                f"{segments[i]['end']} > {segments[i + 1]['start']}"
            )

    # Check for gaps
    for i in range(len(segments) - 1):
        gap = segments[i + 1]["start"] - segments[i]["end"]
        if gap > 1.0:
            warnings.append(
                f"Gap of {gap:.1f}s between segments {i} and {i + 1}"
            )

    # Check for missing assets references
    for i, seg in enumerate(segments):
        if seg.get("type") == "broll_video" and not seg.get("search_query"):
            warnings.append(f"Segment {i}: broll_video without search_query")
        if seg.get("type") == "ai_image" and not seg.get("image_prompt"):
            warnings.append(f"Segment {i}: ai_image without image_prompt")

    # Check segment types distribution
    type_counts = {}
    for seg in segments:
        t = seg.get("type", "unknown")
        type_counts[t] = type_counts.get(t, 0) + 1

    total_duration = segments[-1]["end"] - segments[0]["start"] if segments else 0
    minutes = total_duration / 60

    broll_count = type_counts.get("broll_video", 0)
    if minutes > 0 and broll_count / minutes < 3:
        warnings.append(
            f"Low B-roll density: {broll_count} for {minutes:.1f} min "
            f"({broll_count / max(minutes, 0.1):.1f}/min, recommend 4+/min)"
        )

    return warnings


def estimate_pipeline_time(
    video_duration_seconds: float,
    settings: dict,
) -> dict:
    """
    Estimate pipeline processing time based on video duration and settings.

    Returns dict with estimated times per stage in seconds.
    """
    # Rough estimates for M3 Pro
    transcription_time = video_duration_seconds * 0.1  # ~10x realtime
    analysis_time = 10  # ~5-10s per LLM call

    # Estimate number of assets
    est_brolls = int(video_duration_seconds / 60 * 4)
    est_images = int(video_duration_seconds / 60 * 2)

    image_mode = settings.get("image_mode", "replicate")
    if image_mode == "replicate":
        image_time = est_images * 5  # ~5s per image
    else:
        image_time = est_images * 120  # ~2 min per image

    broll_time = est_brolls * 3  # ~3s per download

    render_time = video_duration_seconds * 0.5  # ~2x realtime for render

    total = transcription_time + analysis_time + image_time + broll_time + render_time

    return {
        "transcription": round(transcription_time),
        "analysis": round(analysis_time),
        "images": round(image_time),
        "broll": round(broll_time),
        "render": round(render_time),
        "total": round(total),
        "estimated_assets": {
            "brolls": est_brolls,
            "images": est_images,
        },
    }
