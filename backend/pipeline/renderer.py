"""
Nabi AI — FFmpeg Renderer Pipeline Module
Builds complex FFmpeg filtergraphs for the final video composition:
  - Facecam with dynamic zooms
  - B-roll overlays with PiP (Picture-in-Picture)
  - AI image overlays with smooth zoom-in
  - Crossfade transitions between segments
  - Silence removal
  - H.264/H.265 export at 1080p
"""

import asyncio
import json
import os
import subprocess
from pathlib import Path
from typing import Optional

from pipeline.transcriber import _find_ffmpeg


async def render(
    edl: dict,
    project_dir: str,
    images: list[dict],
    brolls: list[dict],
    source_video: str,
    resolution: str = "1080p",
    remove_silences: bool = True,
    pip_enabled: bool = True,
    on_progress=None,
) -> str:
    """
    Render the final edited video from the EDL, source video, images, and B-rolls.

    This uses a multi-pass approach for reliability:
      1. Prepare trimmed segments from source video
      2. Apply effects (zoom, PiP) per segment
      3. Concatenate all segments with transitions
      4. Export final MP4

    Args:
        edl: Edit Decision List
        project_dir: Path to the project directory
        images: Image manifest from image_generator
        brolls: B-roll manifest from broll_sourcer
        source_video: Path to the source video
        resolution: Output resolution ('1080p', '720p', '4k')
        remove_silences: Whether to remove silence gaps
        pip_enabled: Whether to enable PiP overlay
        on_progress: Async callback for progress updates

    Returns:
        Path to the final output video
    """
    project_path = Path(project_dir)
    temp_dir = project_path / "render_temp"
    temp_dir.mkdir(parents=True, exist_ok=True)

    ffmpeg = _find_ffmpeg()

    # Resolution settings
    res_map = {
        "4k": (3840, 2160),
        "1080p": (1920, 1080),
        "720p": (1280, 720),
    }
    width, height = res_map.get(resolution, (1920, 1080))

    # Build asset lookup maps
    image_map = {r["segment_index"]: r for r in images if r.get("image_path") and os.path.exists(r["image_path"])}
    broll_map = {r["segment_index"]: r for r in brolls if r.get("video_path") and os.path.exists(r["video_path"])}

    segments = edl.get("segments", [])
    if not segments:
        raise ValueError("EDL has no segments")

    if on_progress:
        await on_progress("render", 5, f"Préparation du rendu ({len(segments)} segments)...")

    # ── Pass 1: Render individual segments ──
    segment_files = []
    total_segs = len(segments)

    for i, seg in enumerate(segments):
        if on_progress:
            pct = 5 + int((i / total_segs) * 60)
            await on_progress("render", pct, f"Rendu segment {i + 1}/{total_segs}...")

        seg_type = seg.get("type", "facecam")
        start = seg["start"]
        end = seg["end"]
        duration = end - start
        effect = seg.get("effect", "none")
        has_pip = seg.get("pip", False) and pip_enabled

        output_seg = str(temp_dir / f"seg_{i:04d}.mp4")

        try:
            if seg_type == "facecam":
                await _render_facecam_segment(
                    ffmpeg, source_video, output_seg,
                    start, duration, width, height, effect,
                )
            elif seg_type == "broll_video" and i in broll_map:
                broll_path = broll_map[i]["video_path"]
                await _render_broll_segment(
                    ffmpeg, source_video, broll_path, output_seg,
                    start, duration, width, height, has_pip,
                )
            elif seg_type == "ai_image" and i in image_map:
                image_path = image_map[i]["image_path"]
                await _render_image_segment(
                    ffmpeg, source_video, image_path, output_seg,
                    start, duration, width, height, effect, has_pip,
                )
            else:
                # Fallback: plain facecam cut
                await _render_facecam_segment(
                    ffmpeg, source_video, output_seg,
                    start, duration, width, height, "none",
                )

            if os.path.exists(output_seg) and os.path.getsize(output_seg) > 0:
                segment_files.append(output_seg)
            else:
                print(f"⚠️ Segment {i} produced empty output, skipping")

        except Exception as e:
            print(f"⚠️ Segment {i} render failed: {e}")
            # Fallback: simple cut from source
            try:
                await _render_facecam_segment(
                    ffmpeg, source_video, output_seg,
                    start, duration, width, height, "none",
                )
                if os.path.exists(output_seg) and os.path.getsize(output_seg) > 0:
                    segment_files.append(output_seg)
            except Exception:
                pass

    if not segment_files:
        raise RuntimeError("No segments were rendered successfully")

    # ── Pass 2: Concatenate all segments ──
    if on_progress:
        await on_progress("render", 75, "Assemblage des segments...")

    output_path = str(project_path / "output.mp4")

    if len(segment_files) == 1:
        # Single segment, just copy
        os.rename(segment_files[0], output_path)
    else:
        await _concatenate_segments(ffmpeg, segment_files, output_path, width, height)

    # ── Pass 3 (optional): Remove silences ──
    if remove_silences and os.path.exists(output_path):
        if on_progress:
            await on_progress("render", 90, "Suppression des silences...")
        
        trimmed_path = str(project_path / "output_trimmed.mp4")
        silence_removed = await _remove_silences(ffmpeg, output_path, trimmed_path)
        
        if silence_removed and os.path.exists(trimmed_path):
            os.replace(trimmed_path, output_path)

    # ── Cleanup temp files ──
    if on_progress:
        await on_progress("render", 95, "Nettoyage...")

    _cleanup_temp(str(temp_dir))

    if on_progress:
        file_size_mb = os.path.getsize(output_path) / (1024 * 1024) if os.path.exists(output_path) else 0
        await on_progress("render", 100, f"✓ Rendu terminé ({file_size_mb:.1f} MB)")

    return output_path


# ── Segment Renderers ─────────────────────────

async def _render_facecam_segment(
    ffmpeg: str, source: str, output: str,
    start: float, duration: float,
    width: int, height: int, effect: str,
):
    """Render a facecam segment with optional zoom effect."""
    filters = [f"scale={width}:{height}:force_original_aspect_ratio=decrease,pad={width}:{height}:(ow-iw)/2:(oh-ih)/2"]

    if effect == "zoom_in":
        # Smooth zoom from 1.0x to 1.15x
        filters.append(
            f"zoompan=z='min(1+0.15*on/{max(duration * 30, 1)},1.15)'"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={int(duration * 30)}:s={width}x{height}:fps=30"
        )
    elif effect == "zoom_out":
        # Smooth zoom from 1.15x to 1.0x
        filters.append(
            f"zoompan=z='max(1.15-0.15*on/{max(duration * 30, 1)},1.0)'"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={int(duration * 30)}:s={width}x{height}:fps=30"
        )

    filter_str = ",".join(filters)

    cmd = [
        ffmpeg, "-y",
        "-ss", str(start),
        "-t", str(duration),
        "-i", source,
        "-vf", filter_str,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-r", "30",
        "-movflags", "+faststart",
        output,
    ]

    await _run_ffmpeg(cmd)


async def _render_broll_segment(
    ffmpeg: str, source: str, broll_path: str, output: str,
    start: float, duration: float,
    width: int, height: int, has_pip: bool,
):
    """Render a B-roll segment, optionally with PiP facecam overlay."""
    if not has_pip:
        # Simple B-roll, use audio from source
        cmd = [
            ffmpeg, "-y",
            "-ss", str(start), "-t", str(duration), "-i", source,       # Audio source
            "-t", str(duration), "-i", broll_path,                       # B-roll video
            "-filter_complex",
            f"[1:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2[broll]",
            "-map", "[broll]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            "-r", "30", "-shortest",
            "-movflags", "+faststart",
            output,
        ]
    else:
        # B-roll with PiP overlay
        pip_w = int(width * 0.28)
        pip_h = int(height * 0.28)
        pip_x = width - pip_w - 30
        pip_y = height - pip_h - 30
        border = 3

        cmd = [
            ffmpeg, "-y",
            "-ss", str(start), "-t", str(duration), "-i", source,
            "-t", str(duration), "-i", broll_path,
            "-filter_complex",
            # Scale B-roll to full frame
            f"[1:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2[broll];"
            # Scale facecam for PiP
            f"[0:v]scale={pip_w}:{pip_h}:force_original_aspect_ratio=decrease,"
            f"pad={pip_w}:{pip_h}:(ow-iw)/2:(oh-ih)/2,"
            f"drawbox=x=0:y=0:w={pip_w}:h={pip_h}:color=white:t={border}[pip];"
            # Overlay PiP on B-roll
            f"[broll][pip]overlay={pip_x}:{pip_y}[out]",
            "-map", "[out]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            "-r", "30", "-shortest",
            "-movflags", "+faststart",
            output,
        ]

    await _run_ffmpeg(cmd)


async def _render_image_segment(
    ffmpeg: str, source: str, image_path: str, output: str,
    start: float, duration: float,
    width: int, height: int, effect: str, has_pip: bool,
):
    """Render an AI image segment with zoom effect and optional PiP."""
    # Build filtergraph
    frames = int(duration * 30)

    if effect == "smooth_zoom_in":
        zoom_filter = (
            f"zoompan=z='min(1+0.08*on/{max(frames, 1)},1.08)'"
            f":x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={frames}:s={width}x{height}:fps=30"
        )
    else:
        zoom_filter = (
            f"zoompan=z='1':x='0':y='0'"
            f":d={frames}:s={width}x{height}:fps=30"
        )

    if not has_pip:
        cmd = [
            ffmpeg, "-y",
            "-ss", str(start), "-t", str(duration), "-i", source,   # Audio
            "-loop", "1", "-t", str(duration), "-i", image_path,     # Image
            "-filter_complex",
            f"[1:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
            f"{zoom_filter}[img]",
            "-map", "[img]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            "-r", "30", "-shortest",
            "-movflags", "+faststart",
            output,
        ]
    else:
        pip_w = int(width * 0.28)
        pip_h = int(height * 0.28)
        pip_x = width - pip_w - 30
        pip_y = height - pip_h - 30
        border = 3

        cmd = [
            ffmpeg, "-y",
            "-ss", str(start), "-t", str(duration), "-i", source,
            "-loop", "1", "-t", str(duration), "-i", image_path,
            "-filter_complex",
            # Scale and zoom image
            f"[1:v]scale={width}:{height}:force_original_aspect_ratio=decrease,"
            f"pad={width}:{height}:(ow-iw)/2:(oh-ih)/2,"
            f"{zoom_filter}[img];"
            # Scale facecam for PiP
            f"[0:v]scale={pip_w}:{pip_h}:force_original_aspect_ratio=decrease,"
            f"pad={pip_w}:{pip_h}:(ow-iw)/2:(oh-ih)/2,"
            f"drawbox=x=0:y=0:w={pip_w}:h={pip_h}:color=white:t={border}[pip];"
            # Overlay PiP on image
            f"[img][pip]overlay={pip_x}:{pip_y}[out]",
            "-map", "[out]", "-map", "0:a?",
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            "-r", "30", "-shortest",
            "-movflags", "+faststart",
            output,
        ]

    await _run_ffmpeg(cmd)


# ── Concatenation ─────────────────────────────

async def _concatenate_segments(
    ffmpeg: str, segment_files: list[str], output: str,
    width: int, height: int,
):
    """Concatenate segment files using the concat demuxer."""
    # Create concat file list
    concat_path = os.path.join(os.path.dirname(segment_files[0]), "concat_list.txt")
    with open(concat_path, "w") as f:
        for seg_file in segment_files:
            # Escape special characters in path
            escaped = seg_file.replace("'", "'\\''")
            f.write(f"file '{escaped}'\n")

    cmd = [
        ffmpeg, "-y",
        "-f", "concat", "-safe", "0",
        "-i", concat_path,
        "-c:v", "libx264", "-preset", "fast", "-crf", "23",
        "-c:a", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        output,
    ]

    await _run_ffmpeg(cmd)


# ── Silence Removal ──────────────────────────

async def _remove_silences(
    ffmpeg: str, input_path: str, output_path: str,
    silence_threshold: str = "-35dB",
    min_silence_duration: float = 0.5,
) -> bool:
    """
    Detect and remove silence gaps from the video.
    Returns True if processing succeeded.
    """
    try:
        # Step 1: Detect silences
        detect_cmd = [
            ffmpeg, "-i", input_path,
            "-af", f"silencedetect=noise={silence_threshold}:d={min_silence_duration}",
            "-f", "null", "-",
        ]

        result = await asyncio.to_thread(
            subprocess.run, detect_cmd,
            capture_output=True, text=True,
        )

        # Parse silence intervals from stderr
        silences = _parse_silence_detection(result.stderr)

        if not silences:
            return False  # No silences found, skip

        # Step 2: Build select filter to keep non-silent parts
        # Get total duration first
        duration = _get_duration_from_ffmpeg(ffmpeg, input_path)
        if duration <= 0:
            return False

        # Build the inverse of silence intervals (speech segments)
        speech_segments = _invert_silences(silences, duration)

        if not speech_segments or len(speech_segments) < 2:
            return False  # Not enough segments to be worth trimming

        # Step 3: Create a concat filter from speech segments
        temp_dir = os.path.dirname(output_path)
        speech_files = []

        for i, (seg_start, seg_end) in enumerate(speech_segments):
            seg_duration = seg_end - seg_start
            if seg_duration < 0.1:
                continue

            seg_path = os.path.join(temp_dir, f"speech_{i:04d}.mp4")
            trim_cmd = [
                ffmpeg, "-y",
                "-ss", str(seg_start),
                "-t", str(seg_duration),
                "-i", input_path,
                "-c:v", "libx264", "-preset", "ultrafast", "-crf", "23",
                "-c:a", "aac", "-b:a", "192k",
                seg_path,
            ]
            await _run_ffmpeg(trim_cmd)
            if os.path.exists(seg_path) and os.path.getsize(seg_path) > 0:
                speech_files.append(seg_path)

        if len(speech_files) < 2:
            # Cleanup
            for f in speech_files:
                _safe_remove(f)
            return False

        # Concatenate speech segments
        concat_list = os.path.join(temp_dir, "silence_concat.txt")
        with open(concat_list, "w") as f:
            for sp in speech_files:
                escaped = sp.replace("'", "'\\''")
                f.write(f"file '{escaped}'\n")

        concat_cmd = [
            ffmpeg, "-y",
            "-f", "concat", "-safe", "0",
            "-i", concat_list,
            "-c:v", "libx264", "-preset", "fast", "-crf", "23",
            "-c:a", "aac", "-b:a", "192k",
            "-movflags", "+faststart",
            output_path,
        ]
        await _run_ffmpeg(concat_cmd)

        # Cleanup temp files
        for f in speech_files:
            _safe_remove(f)
        _safe_remove(concat_list)

        return os.path.exists(output_path) and os.path.getsize(output_path) > 0

    except Exception as e:
        print(f"⚠️ Silence removal failed: {e}")
        return False


def _parse_silence_detection(stderr: str) -> list[tuple[float, float]]:
    """Parse FFmpeg silencedetect output into (start, end) tuples."""
    silences = []
    current_start = None

    for line in stderr.split("\n"):
        if "silence_start:" in line:
            try:
                current_start = float(line.split("silence_start:")[1].strip().split()[0])
            except (ValueError, IndexError):
                current_start = None

        elif "silence_end:" in line and current_start is not None:
            try:
                end = float(line.split("silence_end:")[1].strip().split()[0])
                silences.append((current_start, end))
                current_start = None
            except (ValueError, IndexError):
                pass

    return silences


def _invert_silences(silences: list[tuple[float, float]], total_duration: float) -> list[tuple[float, float]]:
    """Convert silence intervals to speech intervals."""
    if not silences:
        return [(0, total_duration)]

    speech = []
    prev_end = 0.0

    for start, end in sorted(silences):
        if start > prev_end:
            speech.append((prev_end, start))
        prev_end = max(prev_end, end)

    if prev_end < total_duration:
        speech.append((prev_end, total_duration))

    return speech


def _get_duration_from_ffmpeg(ffmpeg: str, video_path: str) -> float:
    """Get video duration using ffmpeg."""
    ffprobe = ffmpeg.replace("ffmpeg", "ffprobe")
    try:
        if os.path.isfile(ffprobe):
            result = subprocess.run(
                [ffprobe, "-v", "quiet", "-show_entries", "format=duration", "-of", "json", video_path],
                capture_output=True, text=True,
            )
            data = json.loads(result.stdout)
            return float(data["format"]["duration"])
    except Exception:
        pass

    # Fallback: parse from ffmpeg
    try:
        result = subprocess.run(
            [ffmpeg, "-i", video_path], capture_output=True, text=True,
        )
        for line in result.stderr.split("\n"):
            if "Duration:" in line:
                time_str = line.split("Duration:")[1].split(",")[0].strip()
                parts = time_str.split(":")
                return float(parts[0]) * 3600 + float(parts[1]) * 60 + float(parts[2])
    except Exception:
        pass

    return 0


# ── Utilities ─────────────────────────────────

async def _run_ffmpeg(cmd: list[str]):
    """Run an FFmpeg command asynchronously."""
    result = await asyncio.to_thread(
        subprocess.run, cmd,
        capture_output=True, text=True,
    )
    if result.returncode != 0:
        # Log stderr but don't include full output in error (can be very long)
        stderr_summary = result.stderr[-500:] if result.stderr else "No error output"
        raise RuntimeError(f"FFmpeg failed (exit {result.returncode}): ...{stderr_summary}")


def _safe_remove(path: str):
    """Remove a file if it exists."""
    try:
        if os.path.exists(path):
            os.remove(path)
    except OSError:
        pass


def _cleanup_temp(temp_dir: str):
    """Remove temporary render directory."""
    import shutil
    try:
        if os.path.isdir(temp_dir):
            shutil.rmtree(temp_dir)
    except OSError as e:
        print(f"⚠️ Temp cleanup failed: {e}")
