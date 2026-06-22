"""
Nabi AI — AI Image Generator Pipeline Module
Generates editorial-style explainer images from EDL prompts.
Supports two modes:
  - Replicate API (recommended): Fast (~5s), cheap (~$0.02/image)
  - Local FLUX via diffusers + MPS (Apple Silicon): Slow (~90-180s), free
"""

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Optional

import httpx


REPLICATE_API_URL = "https://api.replicate.com/v1/predictions"


async def generate_images(
    edl: dict,
    project_dir: str,
    mode: str = "replicate",
    replicate_api_key: str = "",
    on_progress=None,
) -> list[dict]:
    """
    Generate all AI images specified in the EDL.

    Args:
        edl: Edit Decision List with segments containing image_prompt
        project_dir: Path to the project directory
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

    results = []

    for idx, (seg_index, seg) in enumerate(image_segments):
        prompt = seg["image_prompt"]
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
                await _generate_local(prompt, str(image_path))

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
            # Create a placeholder so the pipeline can continue
            _create_placeholder_image(str(image_path), prompt)
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


# ── Replicate API Mode ────────────────────────

async def _generate_replicate(prompt: str, output_path: str, api_key: str):
    """Generate image via Replicate API (FLUX schnell — fast & cheap)."""
    async with httpx.AsyncClient(timeout=120) as client:
        # Create prediction
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

        # Handle model identifier format (newer Replicate API)
        if response.status_code == 422:
            # Try with the official model endpoint
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

        response.raise_for_status()
        prediction = response.json()

        # Poll for completion
        prediction_url = prediction.get("urls", {}).get("get") or prediction.get("url")
        if not prediction_url:
            prediction_url = f"{REPLICATE_API_URL}/{prediction['id']}"

        for _ in range(120):  # Max 2 minutes
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

                # Download the image
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


# ── Local FLUX Mode ───────────────────────────

async def _generate_local(prompt: str, output_path: str):
    """
    Generate image locally. First tries FLUX via diffusers, then falls back
    to creating a clean editorial-style image with Pillow.
    """
    try:
        import torch
        from diffusers import FluxPipeline

        def _run():
            pipe = FluxPipeline.from_pretrained(
                "black-forest-labs/FLUX.1-schnell",
                torch_dtype=torch.bfloat16,
            )
            pipe.enable_model_cpu_offload()
            image = pipe(
                prompt,
                height=720, width=1280,
                guidance_scale=0.0,
                num_inference_steps=4,
                max_sequence_length=256,
            ).images[0]
            image.save(output_path)

        await asyncio.to_thread(_run)

    except (ImportError, Exception) as e:
        print(f"ℹ️ FLUX local indisponible, création image Pillow: {e}")
        await asyncio.to_thread(_generate_pillow_editorial, prompt, output_path)


def _generate_pillow_editorial(prompt: str, output_path: str):
    """
    Create a clean editorial-style infographic image with Pillow.
    Style: white background, black text, orange accents.
    """
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1920, 1080
    img = Image.new("RGB", (W, H), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    # Fonts
    try:
        title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 42)
        body_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
        small_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
    except Exception:
        title_font = ImageFont.load_default()
        body_font = title_font
        small_font = title_font

    orange = (255, 120, 30)
    dark = (30, 30, 40)
    gray = (120, 120, 130)

    # Top orange accent bar
    draw.rectangle([0, 0, W, 8], fill=orange)

    # Side accent line
    draw.rectangle([60, 100, 66, H - 100], fill=orange)

    # Extract the topic from the prompt (between "about:" and the first period)
    topic = prompt
    if "about:" in prompt:
        topic = prompt.split("about:")[1].split(".")[0].strip()

    # Title area
    draw.text((100, 130), "📊", fill=dark, font=title_font)
    draw.text((160, 130), topic[:60], fill=dark, font=title_font)

    # Divider
    draw.rectangle([100, 200, W - 100, 202], fill=(230, 230, 235))

    # Body content — wrap text
    body_text = topic
    if len(topic) > 60:
        body_text = topic
    else:
        body_text = prompt.split(".")[0] if "." in prompt else prompt

    # Wrap body text
    lines = _wrap_text(body_text, 65)
    y = 240
    for line in lines[:6]:
        draw.text((100, y), line, fill=dark, font=body_font)
        y += 45

    # Orange highlight box
    box_y = max(y + 40, 520)
    draw.rounded_rectangle(
        [100, box_y, W - 100, box_y + 80],
        radius=12, fill=(255, 245, 235), outline=orange, width=2,
    )
    draw.text((W // 2, box_y + 40), "💡 Infographic — Nabi AI", fill=orange, font=body_font, anchor="mm")

    # Bottom area — decorative elements
    # 3 stat boxes
    box_w = 280
    for idx, (label, val) in enumerate([("Concept", "✓"), ("Impact", "▲"), ("Insight", "★")]):
        bx = 200 + idx * (box_w + 60)
        by = box_y + 130
        draw.rounded_rectangle([bx, by, bx + box_w, by + 120], radius=10, fill=(248, 248, 252), outline=(220, 220, 225))
        draw.text((bx + box_w // 2, by + 40), val, fill=orange, font=title_font, anchor="mm")
        draw.text((bx + box_w // 2, by + 85), label, fill=gray, font=small_font, anchor="mm")

    # Bottom accent bar
    draw.rectangle([0, H - 6, W, H], fill=orange)

    img.save(output_path, quality=95)

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


# ── Placeholder ───────────────────────────────

def _create_placeholder_image(output_path: str, prompt: str):
    """Create a simple placeholder image when generation fails."""
    try:
        from PIL import Image, ImageDraw, ImageFont

        img = Image.new("RGB", (1920, 1080), color=(20, 20, 30))
        draw = ImageDraw.Draw(img)

        # Draw a border
        for i in range(3):
            draw.rectangle(
                [10 + i, 10 + i, 1909 - i, 1069 - i],
                outline=(255, 140, 0),
            )

        # Add text
        try:
            font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 28)
            small_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 18)
        except Exception:
            font = ImageFont.load_default()
            small_font = font

        draw.text((960, 480), "🎨 Image IA", fill=(255, 255, 255), font=font, anchor="mm")
        draw.text((960, 530), "(Génération échouée — placeholder)", fill=(180, 180, 180), font=small_font, anchor="mm")

        # Wrap and display prompt
        max_chars = 80
        wrapped = [prompt[i:i + max_chars] for i in range(0, min(len(prompt), 240), max_chars)]
        for j, line in enumerate(wrapped):
            draw.text((960, 580 + j * 25), line, fill=(120, 120, 140), font=small_font, anchor="mm")

        img.save(output_path)

    except ImportError:
        # If PIL not available, create a minimal PNG
        # Smallest valid 1x1 black PNG
        import struct
        import zlib

        def _minimal_png(width=192, height=108):
            """Generate a minimal valid PNG."""
            raw_data = b""
            for _ in range(height):
                raw_data += b"\x00" + b"\x14\x14\x1e" * width

            def _chunk(chunk_type, data):
                c = chunk_type + data
                return struct.pack(">I", len(data)) + c + struct.pack(">I", zlib.crc32(c) & 0xFFFFFFFF)

            return (
                b"\x89PNG\r\n\x1a\n"
                + _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
                + _chunk(b"IDAT", zlib.compress(raw_data))
                + _chunk(b"IEND", b"")
            )

        with open(output_path, "wb") as f:
            f.write(_minimal_png())
