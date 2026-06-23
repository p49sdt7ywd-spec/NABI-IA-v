"""
Nabi AI — AI Image Generator Pipeline Module (v2)
Generates editorial-style explainer images from EDL prompts.

Modes:
  - Replicate API (recommended): Fast (~5s), uses FLUX schnell
  - Local Pillow (fallback): Creates clean editorial infographic images
    matching the style spec: white bg, black text, orange accents,
    clean typography, simple infographics, diagrams.

Each image is generated to match the EXACT transcript content at that
timestamp, creating clear educational explainer visuals.
"""

import asyncio
import json
import os
import textwrap
import time
from pathlib import Path
from typing import Optional

import httpx


REPLICATE_API_URL = "https://api.replicate.com/v1/predictions"

# ── Master Image Style Prompt ──
# This is appended to every image generation request for consistent style.
IMAGE_STYLE_SUFFIX = (
    "The image must be horizontal 16:9 format. "
    "Use a clean white or very light paper-like background. "
    "Use black text as the main text color. "
    "Use orange (#FF7820) ONLY for highlights, emphasis, arrows, icons, key words, accents, charts, or callouts. "
    "The layout should be clean, minimal, educational, premium, and easy to read. "
    "Style: modern editorial explainer graphic with clean typography, simple icons, labels, arrows, boxes, charts, callouts. "
    "Include paper-card elements, simple infographics, diagrams, or UI boxes when they fit the idea. "
    "Typography should be clean, bold, and readable. Headlines strong and easy to scan. "
    "Focus on ONE clear idea only. Every element should help explain the concept. "
    "No dark backgrounds. No logos or branding. No visual artifacts, glitches, or distorted text. "
    "No crowded layouts. Premium and trustworthy look."
)


async def generate_images(
    edl: dict,
    project_dir: str,
    transcription: dict,
    mode: str = "replicate",
    replicate_api_key: str = "",
    on_progress=None,
) -> list[dict]:
    """
    Generate all AI images specified in the EDL.

    Each image is tailored to the exact transcript content at that timestamp
    for maximum educational value.

    Args:
        edl: Edit Decision List with segments containing image_prompt
        project_dir: Path to the project directory
        transcription: Full transcription data for context
        mode: 'replicate' or 'local'
        replicate_api_key: API key for Replicate (required if mode='replicate')
        on_progress: Async callback for progress updates

    Returns:
        List of dicts with {segment_index, image_path, prompt, generation_time}
    """
    project_path = Path(project_dir)
    images_dir = project_path / "images"
    images_dir.mkdir(parents=True, exist_ok=True)

    # Collect all image segments
    image_segments = []
    for i, seg in enumerate(edl.get("segments", [])):
        if seg.get("type") == "ai_image" and seg.get("image_prompt"):
            image_segments.append((i, seg))

    if not image_segments:
        if on_progress:
            await on_progress("images", 100, "Aucune image IA requise")
        return []

    total = len(image_segments)
    if on_progress:
        await on_progress("images", 5, f"Génération de {total} images IA...")

    # Build transcript context for better image prompts
    transcript_text = transcription.get("text", "")

    results = []

    for idx, (seg_index, seg) in enumerate(image_segments):
        # Get the exact transcript text for this timestamp
        segment_text = _get_text_at_timestamp(
            transcription, seg["start"], seg["end"]
        )

        # Build a rich, context-aware prompt
        prompt = _build_image_prompt(segment_text, seg.get("image_prompt", ""))

        image_filename = f"img_{seg_index:03d}_{seg['start']:.1f}s.png"
        image_path = images_dir / image_filename

        if on_progress:
            pct = 5 + int((idx / total) * 85)
            await on_progress("images", pct, f"Image {idx + 1}/{total} : génération...")

        start_time = time.time()

        try:
            if mode == "replicate" and replicate_api_key:
                await _generate_replicate(prompt, str(image_path), replicate_api_key)
            else:
                await asyncio.to_thread(
                    _generate_editorial_image, prompt, segment_text, str(image_path)
                )

            gen_time = round(time.time() - start_time, 1)

            results.append({
                "segment_index": seg_index,
                "image_path": str(image_path),
                "prompt": prompt,
                "generation_time": gen_time,
            })

            if on_progress:
                pct = 5 + int(((idx + 1) / total) * 85)
                await on_progress("images", pct, f"Image {idx + 1}/{total} ✓ ({gen_time}s)")

        except Exception as e:
            print(f"⚠️ Image generation failed for segment {seg_index}: {e}")
            # Create editorial fallback
            try:
                await asyncio.to_thread(
                    _generate_editorial_image, prompt, segment_text, str(image_path)
                )
            except Exception:
                _create_minimal_placeholder(str(image_path))

            results.append({
                "segment_index": seg_index,
                "image_path": str(image_path),
                "prompt": prompt,
                "generation_time": 0,
                "error": str(e),
            })

    # Save manifest
    manifest_path = project_path / "images_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    if on_progress:
        await on_progress("images", 100, f"✓ {len(results)} images générées")

    return results


def _get_text_at_timestamp(transcription: dict, start: float, end: float) -> str:
    """Extract the exact transcript text for a given timestamp range."""
    segments = transcription.get("segments", [])
    texts = []

    for seg in segments:
        seg_start = seg.get("start", 0)
        seg_end = seg.get("end", 0)

        # Check for overlap
        if seg_start < end and seg_end > start:
            # Use word-level timestamps if available for precision
            words = seg.get("words", [])
            if words:
                for w in words:
                    if w.get("start", 0) >= start - 0.5 and w.get("end", 0) <= end + 0.5:
                        texts.append(w.get("word", ""))
            else:
                texts.append(seg.get("text", ""))

    return " ".join(texts).strip() if texts else ""


def _build_image_prompt(segment_text: str, raw_prompt: str) -> str:
    """
    Build a rich image generation prompt from the transcript segment.
    Combines the segment content with the editorial style specification.
    """
    # Extract the core concept from the raw prompt
    core_concept = raw_prompt
    if "about:" in raw_prompt:
        core_concept = raw_prompt.split("about:")[1].split(".")[0].strip()

    prompt = (
        f"Create a clean editorial explainer infographic about: '{segment_text}'. "
        f"The image should visually explain this concept in a clear, simple way. "
        f"Show the key idea with text labels, icons, and simple diagrams. "
        f"{IMAGE_STYLE_SUFFIX}"
    )

    return prompt


# ── Replicate API Mode ────────────────────────

async def _generate_replicate(prompt: str, output_path: str, api_key: str):
    """Generate image via Replicate API (FLUX schnell)."""
    async with httpx.AsyncClient(timeout=120) as client:
        # Try the model endpoint first (newer API)
        response = await client.post(
            "https://api.replicate.com/v1/models/black-forest-labs/flux-schnell/predictions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
            json={
                "input": {
                    "prompt": prompt,
                    "aspect_ratio": "16:9",
                    "output_format": "png",
                    "output_quality": 90,
                    "num_outputs": 1,
                    "go_fast": True,
                },
            },
        )

        # Fallback to version-based endpoint
        if response.status_code == 422 or response.status_code == 404:
            response = await client.post(
                REPLICATE_API_URL,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "version": "black-forest-labs/flux-schnell",
                    "input": {
                        "prompt": prompt,
                        "aspect_ratio": "16:9",
                        "output_format": "png",
                        "output_quality": 90,
                        "num_outputs": 1,
                        "go_fast": True,
                    },
                },
            )

        response.raise_for_status()
        prediction = response.json()

        # Poll for completion
        prediction_url = prediction.get("urls", {}).get("get") or prediction.get("url")
        if not prediction_url:
            prediction_url = f"{REPLICATE_API_URL}/{prediction['id']}"

        for _ in range(120):
            await asyncio.sleep(1)

            poll_response = await client.get(
                prediction_url,
                headers={"Authorization": f"Bearer {api_key}"},
            )
            poll_response.raise_for_status()
            status_data = poll_response.json()

            status = status_data.get("status")
            if status == "succeeded":
                output = status_data.get("output", [])
                if isinstance(output, list) and output:
                    image_url = output[0]
                elif isinstance(output, str):
                    image_url = output
                else:
                    raise RuntimeError("No output URL in Replicate response")

                img_response = await client.get(image_url)
                img_response.raise_for_status()
                with open(output_path, "wb") as f:
                    f.write(img_response.content)
                return

            elif status == "failed":
                error = status_data.get("error", "Unknown error")
                raise RuntimeError(f"Replicate generation failed: {error}")

            elif status == "canceled":
                raise RuntimeError("Replicate generation was canceled")

        raise TimeoutError("Replicate generation timed out after 2 minutes")


# ── Local Pillow Editorial Image Generator ────

def _generate_editorial_image(prompt: str, segment_text: str, output_path: str):
    """
    Generate a clean editorial-style explainer image using Pillow.

    Style: white background, black text, orange accents.
    The image content is adapted to the actual transcript text,
    showing the key concept being discussed.
    """
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1920, 1080
    img = Image.new("RGB", (W, H), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Colors
    BLACK = (30, 30, 40)
    ORANGE = (255, 120, 30)
    LIGHT_ORANGE = (255, 245, 235)
    GRAY = (120, 120, 130)
    LIGHT_GRAY = (248, 248, 252)
    BORDER_GRAY = (220, 220, 225)
    DIVIDER = (230, 230, 235)

    # Fonts
    try:
        title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 48)
        subtitle_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 32)
        body_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 26)
        small_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
        accent_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 36)
    except Exception:
        title_font = ImageFont.load_default()
        subtitle_font = title_font
        body_font = title_font
        small_font = title_font
        accent_font = title_font

    # Extract the key concept from the transcript text
    headline = segment_text.strip()
    if len(headline) > 80:
        # Find a natural break
        if "," in headline[:80]:
            headline = headline[:headline.rindex(",", 0, 80)]
        elif " " in headline[60:80]:
            headline = headline[:headline.rindex(" ", 60, 80)]
        else:
            headline = headline[:77] + "..."

    # ── Layout ──

    # Top orange accent bar
    draw.rectangle([0, 0, W, 6], fill=ORANGE)

    # Left accent stripe
    draw.rectangle([0, 0, 6, H], fill=ORANGE)

    # ── Header Section ──
    header_y = 60

    # Orange icon circle
    draw.ellipse([80, header_y, 130, header_y + 50], fill=ORANGE)
    draw.text((105, header_y + 12), "💡", fill=(255, 255, 255), font=small_font, anchor="mm")

    # Headline
    headline_lines = _wrap_text(headline, 45)
    y = header_y + 5
    for i, line in enumerate(headline_lines[:2]):
        draw.text((160, y), line, fill=BLACK, font=title_font)
        y += 60

    # Divider line
    div_y = max(y + 20, 200)
    draw.rectangle([80, div_y, W - 80, div_y + 2], fill=DIVIDER)

    # ── Main Content Area ──
    content_y = div_y + 40

    # Extract key words/phrases for the infographic
    keywords = _extract_key_concepts(segment_text)

    if len(keywords) >= 3:
        # Show as a 3-column card layout
        card_w = 480
        card_h = 280
        card_gap = 40
        cards_start_x = (W - (card_w * 3 + card_gap * 2)) // 2

        for idx, keyword in enumerate(keywords[:3]):
            cx = cards_start_x + idx * (card_w + card_gap)
            cy = content_y

            # Card background
            draw.rounded_rectangle(
                [cx, cy, cx + card_w, cy + card_h],
                radius=16, fill=LIGHT_GRAY, outline=BORDER_GRAY, width=1,
            )

            # Orange number badge
            badge_size = 44
            badge_x = cx + 30
            badge_y = cy + 25
            draw.rounded_rectangle(
                [badge_x, badge_y, badge_x + badge_size, badge_y + badge_size],
                radius=8, fill=ORANGE,
            )
            draw.text(
                (badge_x + badge_size // 2, badge_y + badge_size // 2),
                str(idx + 1), fill=(255, 255, 255), font=subtitle_font, anchor="mm",
            )

            # Keyword text
            kw_text = keyword.capitalize()
            kw_lines = _wrap_text(kw_text, 22)
            ky = cy + 90
            for kl in kw_lines[:3]:
                draw.text((cx + 30, ky), kl, fill=BLACK, font=body_font)
                ky += 35

            # Orange accent dot
            draw.ellipse([cx + card_w - 30, cy + card_h - 30, cx + card_w - 14, cy + card_h - 14], fill=ORANGE)

    elif len(keywords) >= 1:
        # Show as a centered highlight box
        box_margin = 120
        box_y = content_y
        box_h = 200

        draw.rounded_rectangle(
            [box_margin, box_y, W - box_margin, box_y + box_h],
            radius=16, fill=LIGHT_ORANGE, outline=ORANGE, width=2,
        )

        # Key concept inside box
        concept_text = keywords[0].capitalize() if keywords else segment_text[:60]
        concept_lines = _wrap_text(concept_text, 50)
        cy = box_y + 40
        for line in concept_lines[:3]:
            draw.text((W // 2, cy), line, fill=BLACK, font=subtitle_font, anchor="mt")
            cy += 45

    # ── Bottom Section ──
    bottom_y = H - 180

    # Full transcript text at bottom (smaller, gray)
    draw.rectangle([80, bottom_y - 20, W - 80, bottom_y - 18], fill=DIVIDER)

    full_lines = _wrap_text(segment_text, 85)
    ty = bottom_y
    for line in full_lines[:3]:
        draw.text((W // 2, ty), line, fill=GRAY, font=small_font, anchor="mt")
        ty += 28

    # Bottom orange bar
    draw.rectangle([0, H - 6, W, H], fill=ORANGE)

    # Bottom right: "Nabi AI" watermark
    draw.text((W - 100, H - 40), "Nabi AI", fill=(200, 200, 205), font=small_font, anchor="mm")

    img.save(output_path, quality=95)


def _extract_key_concepts(text: str) -> list[str]:
    """Extract 3 key concepts/phrases from the text for the infographic cards."""
    # Remove common French stop words
    stop_words = {
        "le", "la", "les", "de", "du", "des", "un", "une", "et", "en", "est", "que",
        "qui", "dans", "ce", "il", "ne", "pas", "pour", "sur", "avec", "plus", "par",
        "son", "se", "sont", "au", "nous", "vous", "ils", "on", "a", "je", "tu", "sa",
        "cette", "ces", "mais", "ou", "donc", "car", "si", "tout", "bien", "très",
        "aussi", "fait", "faire", "être", "avoir", "c'est", "ça", "là", "y", "te", "me",
        "j'ai", "m'a", "mon", "mes", "pu", "aux", "à",
    }

    words = text.lower().replace("'", " ").replace("'", " ").split()
    meaningful = [w for w in words if len(w) > 3 and w not in stop_words]

    # Group into phrases of 2-3 words for card content
    concepts = []
    i = 0
    while i < len(meaningful) and len(concepts) < 3:
        if i + 1 < len(meaningful):
            concepts.append(f"{meaningful[i]} {meaningful[i + 1]}")
            i += 2
        else:
            concepts.append(meaningful[i])
            i += 1

    # If not enough concepts, use simple word splitting
    while len(concepts) < 3 and meaningful:
        concepts.append(meaningful[len(concepts) % len(meaningful)])

    return concepts


def _wrap_text(text: str, max_chars: int) -> list[str]:
    """Wrap text into lines of max_chars characters."""
    words = text.split()
    lines = []
    current_line = ""
    for word in words:
        if len(current_line) + len(word) + 1 <= max_chars:
            current_line = f"{current_line} {word}" if current_line else word
        else:
            if current_line:
                lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines


def _create_minimal_placeholder(output_path: str):
    """Create a minimal placeholder image as last resort."""
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (1920, 1080), color=(255, 255, 255))
        draw = ImageDraw.Draw(img)
        draw.rectangle([0, 0, 1920, 6], fill=(255, 120, 30))
        draw.rectangle([0, 1074, 1920, 1080], fill=(255, 120, 30))
        draw.text((960, 540), "Image en cours de génération", fill=(120, 120, 130), anchor="mm")
        img.save(output_path)
    except Exception:
        # Absolute minimal PNG fallback
        import struct, zlib
        raw_data = b""
        for _ in range(108):
            raw_data += b"\x00" + b"\xff\xff\xff" * 192
        def _chunk(t, d):
            c = t + d
            return struct.pack(">I", len(d)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)
        with open(output_path, "wb") as f:
            f.write(
                b"\x89PNG\r\n\x1a\n"
                + _chunk(b"IHDR", struct.pack(">IIBBBBB", 192, 108, 8, 2, 0, 0, 0))
                + _chunk(b"IDAT", zlib.compress(raw_data))
                + _chunk(b"IEND", b"")
            )
