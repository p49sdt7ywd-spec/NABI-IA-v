"""
Nabi AI — B-Roll Sourcing Pipeline Module
Downloads royalty-free stock video clips from Pexels API based on EDL search queries.
Minimum 4 clips per minute of video for high-density visual editing.
"""

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Optional

import httpx


PEXELS_API_URL = "https://api.pexels.com/videos/search"


async def source_brolls(
    edl: dict,
    project_dir: str,
    pexels_api_key: str = "",
    on_progress=None,
) -> list[dict]:
    """
    Download B-roll clips from Pexels for all broll_video segments in the EDL.

    Args:
        edl: Edit Decision List with segments containing search_query
        project_dir: Path to the project directory
        pexels_api_key: Pexels API key
        on_progress: Async callback for progress updates

    Returns:
        List of dicts with {segment_index, video_path, search_query, duration, source_url}
    """
    project_path = Path(project_dir)
    broll_dir = project_path / "broll"
    broll_dir.mkdir(parents=True, exist_ok=True)

    # Collect all B-roll segments
    broll_segments = []
    for i, seg in enumerate(edl.get("segments", [])):
        if seg.get("type") == "broll_video" and seg.get("search_query"):
            broll_segments.append((i, seg))

    if not broll_segments:
        if on_progress:
            await on_progress("broll", 100, "Aucun B-roll requis")
        return []

    total = len(broll_segments)
    if on_progress:
        await on_progress("broll", 5, f"Recherche de {total} clips B-roll...")

    if not pexels_api_key:
        if on_progress:
            await on_progress("broll", 100, "⚠️ Clé API Pexels manquante — B-rolls ignorés")
        return _generate_placeholder_brolls(broll_segments, str(broll_dir))

    results = []
    # Track used video IDs to avoid duplicates
    used_video_ids = set()

    async with httpx.AsyncClient(timeout=60) as client:
        for idx, (seg_index, seg) in enumerate(broll_segments):
            query = seg["search_query"]
            needed_duration = seg["end"] - seg["start"]

            if on_progress:
                pct = 5 + int((idx / total) * 85)
                await on_progress("broll", pct, f"B-roll {idx + 1}/{total} : \"{query}\"")

            try:
                clip = await _search_and_download(
                    client=client,
                    query=query,
                    needed_duration=needed_duration,
                    output_dir=str(broll_dir),
                    seg_index=seg_index,
                    api_key=pexels_api_key,
                    used_ids=used_video_ids,
                )

                if clip:
                    used_video_ids.add(clip["pexels_id"])
                    results.append({
                        "segment_index": seg_index,
                        "video_path": clip["video_path"],
                        "search_query": query,
                        "duration": clip["duration"],
                        "source_url": clip["source_url"],
                        "pexels_id": clip["pexels_id"],
                        "attribution": clip["attribution"],
                    })

                    if on_progress:
                        pct = 5 + int(((idx + 1) / total) * 85)
                        await on_progress("broll", pct, f"B-roll {idx + 1}/{total} ✓")
                else:
                    print(f"⚠️ No suitable B-roll found for: {query}")

            except Exception as e:
                print(f"⚠️ B-roll download failed for segment {seg_index}: {e}")

    # Save manifest
    manifest_path = project_path / "broll_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    if on_progress:
        await on_progress("broll", 100, f"✓ {len(results)}/{total} clips B-roll téléchargés")

    return results


async def _search_and_download(
    client: httpx.AsyncClient,
    query: str,
    needed_duration: float,
    output_dir: str,
    seg_index: int,
    api_key: str,
    used_ids: set,
) -> Optional[dict]:
    """
    Search Pexels for a video matching the query and download it.

    Prefers:
    - Landscape orientation
    - HD quality
    - Duration close to needed_duration (or longer to trim)
    - Not already used
    """
    # Search Pexels
    response = await client.get(
        PEXELS_API_URL,
        headers={"Authorization": api_key},
        params={
            "query": query,
            "orientation": "landscape",
            "size": "medium",
            "per_page": 15,
        },
    )
    response.raise_for_status()
    data = response.json()

    videos = data.get("videos", [])
    if not videos:
        # Try with simplified query (first 2 words)
        simplified = " ".join(query.split()[:2])
        response = await client.get(
            PEXELS_API_URL,
            headers={"Authorization": api_key},
            params={
                "query": simplified,
                "orientation": "landscape",
                "size": "medium",
                "per_page": 10,
            },
        )
        response.raise_for_status()
        data = response.json()
        videos = data.get("videos", [])

    if not videos:
        return None

    # Score and rank videos
    best_video = None
    best_score = -1

    for video in videos:
        vid_id = video.get("id")
        if vid_id in used_ids:
            continue

        vid_duration = video.get("duration", 0)
        vid_width = video.get("width", 0)
        vid_height = video.get("height", 0)

        # Score: prefer landscape, close to needed duration, HD
        score = 0

        # Landscape bonus
        if vid_width > vid_height:
            score += 10

        # HD bonus
        if vid_width >= 1920:
            score += 5
        elif vid_width >= 1280:
            score += 3

        # Duration score: prefer clips that are >= needed duration
        if vid_duration >= needed_duration:
            score += 8
        elif vid_duration >= needed_duration * 0.5:
            score += 4

        # Penalty for extremely long clips (>30s)
        if vid_duration > 30:
            score -= 2

        if score > best_score:
            best_score = score
            best_video = video

    if not best_video:
        # Fallback: take the first unused video
        for video in videos:
            if video.get("id") not in used_ids:
                best_video = video
                break

    if not best_video:
        return None

    # Find the best video file (prefer HD mp4)
    video_files = best_video.get("video_files", [])
    download_url = _pick_best_file(video_files)

    if not download_url:
        return None

    # Download the video clip
    filename = f"broll_{seg_index:03d}.mp4"
    output_path = os.path.join(output_dir, filename)

    download_response = await client.get(download_url, follow_redirects=True)
    download_response.raise_for_status()

    with open(output_path, "wb") as f:
        f.write(download_response.content)

    # Build attribution
    user = best_video.get("user", {})
    attribution = f"Video by {user.get('name', 'Unknown')} from Pexels"

    return {
        "video_path": output_path,
        "duration": best_video.get("duration", 0),
        "source_url": best_video.get("url", ""),
        "pexels_id": best_video.get("id"),
        "attribution": attribution,
    }


def _pick_best_file(video_files: list) -> Optional[str]:
    """Pick the best video file from Pexels options (prefer 1080p or 720p)."""
    # Sort by preference: 1080p > 720p > others
    preferred_heights = [1080, 720, 480]

    for target_h in preferred_heights:
        for vf in video_files:
            h = vf.get("height", 0)
            quality = vf.get("quality", "")
            file_type = vf.get("file_type", "")

            if h == target_h and "mp4" in file_type:
                return vf.get("link")

    # Fallback: any HD mp4
    for vf in video_files:
        if "mp4" in vf.get("file_type", ""):
            return vf.get("link")

    # Last resort: first file
    if video_files:
        return video_files[0].get("link")

    return None


def _generate_placeholder_brolls(broll_segments: list, broll_dir: str) -> list[dict]:
    """Generate placeholder entries when no Pexels API key is available."""
    results = []
    for seg_index, seg in broll_segments:
        results.append({
            "segment_index": seg_index,
            "video_path": "",
            "search_query": seg.get("search_query", ""),
            "duration": seg["end"] - seg["start"],
            "source_url": "",
            "pexels_id": None,
            "error": "No Pexels API key configured",
        })
    return results
