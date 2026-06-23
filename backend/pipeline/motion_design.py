"""
Nabi AI — Motion Design Generator (HyperFrames)
Generates animated HTML/CSS/JS compositions rendered to MP4 clips via HyperFrames.

Instead of static AI images, this module creates motion design clips that:
  - Are adapted to the exact transcript content at each timestamp
  - Use GSAP animations (fade-in, slide-up, counters)
  - Follow the editorial style: white bg, black text, orange accents
  - Are rendered to 1920x1080 MP4 at 30fps

Modes:
  - hyperframes: Full animated clips via HyperFrames CLI (requires Node.js 22+)
  - pillow: Fallback static images when HyperFrames is not available
"""

import asyncio
import json
import os
import shutil
import subprocess
import textwrap
import time
from pathlib import Path
from typing import Optional


# ── HTML Template for Motion Design ──
# Each clip is a self-contained HTML file with GSAP animations.
# HyperFrames renders it frame-by-frame to produce a deterministic MP4.

MOTION_HTML_TEMPLATE = """\
<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <style>
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800;900&display=swap');

    * {{ margin: 0; padding: 0; box-sizing: border-box; }}

    body {{
      width: 1920px;
      height: 1080px;
      overflow: hidden;
      background: #FFFFFF;
      font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
      color: #1E1E28;
    }}

    .stage {{
      width: 1920px;
      height: 1080px;
      position: relative;
      overflow: hidden;
    }}

    /* Top orange accent bar */
    .top-bar {{
      position: absolute;
      top: 0; left: 0; right: 0;
      height: 6px;
      background: #FF7820;
      transform-origin: left;
    }}

    /* Left accent stripe */
    .left-stripe {{
      position: absolute;
      top: 0; left: 0; bottom: 0;
      width: 6px;
      background: #FF7820;
      transform-origin: top;
    }}

    /* Bottom bar */
    .bottom-bar {{
      position: absolute;
      bottom: 0; left: 0; right: 0;
      height: 6px;
      background: #FF7820;
      transform-origin: right;
    }}

    /* Header section */
    .header {{
      position: absolute;
      top: 60px;
      left: 80px;
      right: 80px;
      display: flex;
      align-items: flex-start;
      gap: 24px;
    }}

    .icon-circle {{
      width: 56px;
      height: 56px;
      border-radius: 50%;
      background: #FF7820;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 24px;
      flex-shrink: 0;
    }}

    .headline {{
      font-size: 48px;
      font-weight: 800;
      line-height: 1.2;
      letter-spacing: -0.02em;
      color: #1E1E28;
    }}

    .headline .highlight {{
      color: #FF7820;
    }}

    /* Divider */
    .divider {{
      position: absolute;
      top: 210px;
      left: 80px;
      right: 80px;
      height: 2px;
      background: #E8E8EC;
      transform-origin: left;
    }}

    /* Cards section */
    .cards-container {{
      position: absolute;
      top: 260px;
      left: 80px;
      right: 80px;
      display: flex;
      gap: 40px;
      justify-content: center;
    }}

    .card {{
      flex: 1;
      max-width: 520px;
      background: #F8F8FC;
      border: 1px solid #E0E0E5;
      border-radius: 16px;
      padding: 32px;
      position: relative;
    }}

    .card-badge {{
      width: 48px;
      height: 48px;
      border-radius: 10px;
      background: #FF7820;
      color: white;
      font-size: 24px;
      font-weight: 700;
      display: flex;
      align-items: center;
      justify-content: center;
      margin-bottom: 20px;
    }}

    .card-title {{
      font-size: 28px;
      font-weight: 700;
      margin-bottom: 12px;
      line-height: 1.3;
    }}

    .card-text {{
      font-size: 20px;
      font-weight: 400;
      color: #6E6E78;
      line-height: 1.5;
    }}

    .card-dot {{
      position: absolute;
      bottom: 16px;
      right: 16px;
      width: 12px;
      height: 12px;
      border-radius: 50%;
      background: #FF7820;
    }}

    /* Bottom transcript */
    .transcript {{
      position: absolute;
      bottom: 40px;
      left: 80px;
      right: 80px;
      text-align: center;
    }}

    .transcript-divider {{
      height: 1px;
      background: #E8E8EC;
      margin-bottom: 20px;
    }}

    .transcript-text {{
      font-size: 20px;
      color: #9898A0;
      line-height: 1.5;
    }}

    /* Watermark */
    .watermark {{
      position: absolute;
      bottom: 20px;
      right: 40px;
      font-size: 16px;
      color: #D0D0D5;
      font-weight: 500;
    }}
  </style>
</head>
<body>
  <div class="stage" id="stage"
       data-composition-id="motion-{seg_index}"
       data-start="0"
       data-width="1920"
       data-height="1080">

    <!-- Accent bars -->
    <div class="top-bar clip" id="top-bar"
         data-start="0" data-duration="{duration}" data-track-index="0"></div>
    <div class="left-stripe clip" id="left-stripe"
         data-start="0" data-duration="{duration}" data-track-index="0"></div>
    <div class="bottom-bar clip" id="bottom-bar"
         data-start="0" data-duration="{duration}" data-track-index="0"></div>

    <!-- Header -->
    <div class="header clip" id="header"
         data-start="0" data-duration="{duration}" data-track-index="1">
      <div class="icon-circle" id="icon">💡</div>
      <h1 class="headline" id="headline">{headline_html}</h1>
    </div>

    <!-- Divider -->
    <div class="divider clip" id="divider"
         data-start="0" data-duration="{duration}" data-track-index="1"></div>

    <!-- Cards -->
    <div class="cards-container clip" id="cards"
         data-start="0" data-duration="{duration}" data-track-index="2">
      {cards_html}
    </div>

    <!-- Bottom transcript -->
    <div class="transcript clip" id="transcript"
         data-start="0" data-duration="{duration}" data-track-index="3">
      <div class="transcript-divider"></div>
      <p class="transcript-text">{transcript_text}</p>
    </div>

    <div class="watermark" id="watermark">Nabi AI</div>

    <!-- GSAP Animation -->
    <script src="https://cdn.jsdelivr.net/npm/gsap@3/dist/gsap.min.js"></script>
    <script>
      const tl = gsap.timeline({{ paused: true }});

      // Accent bars animate in
      tl.from("#top-bar", {{ scaleX: 0, duration: 0.3, ease: "power2.out" }}, 0);
      tl.from("#left-stripe", {{ scaleY: 0, duration: 0.3, ease: "power2.out" }}, 0.1);
      tl.from("#bottom-bar", {{ scaleX: 0, duration: 0.3, ease: "power2.out" }}, 0.15);

      // Icon pops in
      tl.from("#icon", {{ scale: 0, opacity: 0, duration: 0.4, ease: "back.out(2)" }}, 0.2);

      // Headline slides up
      tl.from("#headline", {{ y: 40, opacity: 0, duration: 0.5, ease: "power3.out" }}, 0.3);

      // Divider draws in
      tl.from("#divider", {{ scaleX: 0, duration: 0.4, ease: "power2.out" }}, 0.5);

      // Cards stagger in
      tl.from(".card", {{
        y: 60, opacity: 0, duration: 0.5,
        ease: "power3.out",
        stagger: 0.15
      }}, 0.6);

      // Card badges pop
      tl.from(".card-badge", {{
        scale: 0, duration: 0.3,
        ease: "back.out(2)",
        stagger: 0.1
      }}, 0.9);

      // Card dots fade in
      tl.from(".card-dot", {{
        scale: 0, opacity: 0, duration: 0.2,
        stagger: 0.1
      }}, 1.1);

      // Transcript fades in
      tl.from("#transcript", {{ y: 20, opacity: 0, duration: 0.4 }}, 1.0);

      // Watermark
      tl.from("#watermark", {{ opacity: 0, duration: 0.3 }}, 1.2);

      window.__timelines = window.__timelines || {{}};
      window.__timelines["motion-{seg_index}"] = tl;
    </script>
  </div>
</body>
</html>
"""


async def generate_motion_clips(
    edl: dict,
    project_dir: str,
    transcription: dict,
    mode: str = "hyperframes",
    on_progress=None,
) -> list[dict]:
    """
    Generate motion design clips for all ai_image/motion_design segments in the EDL.

    Args:
        edl: Edit Decision List
        project_dir: Path to the project directory
        transcription: Full transcription data
        mode: 'hyperframes' or 'pillow'
        on_progress: Async callback

    Returns:
        List of dicts with {segment_index, video_path, ...}
    """
    project_path = Path(project_dir)
    motion_dir = project_path / "motion_clips"
    motion_dir.mkdir(parents=True, exist_ok=True)

    # Collect motion design segments
    motion_segments = []
    for i, seg in enumerate(edl.get("segments", [])):
        if seg.get("type") in ("ai_image", "motion_design"):
            motion_segments.append((i, seg))

    if not motion_segments:
        if on_progress:
            await on_progress("images", 100, "Aucun motion design requis")
        return []

    total = len(motion_segments)
    if on_progress:
        await on_progress("images", 5, f"Création de {total} clips motion design...")

    # Check if HyperFrames is available
    hf_available = await _check_hyperframes() if mode == "hyperframes" else False

    results = []

    for idx, (seg_index, seg) in enumerate(motion_segments):
        start_time = time.time()
        duration = round(seg["end"] - seg["start"], 2)

        # Get transcript text for this timestamp
        segment_text = _get_text_at_timestamp(transcription, seg["start"], seg["end"])

        if on_progress:
            pct = 5 + int((idx / total) * 85)
            await on_progress("images", pct, f"Motion design {idx + 1}/{total}...")

        clip_dir = motion_dir / f"clip_{seg_index:03d}"
        clip_dir.mkdir(parents=True, exist_ok=True)

        try:
            if hf_available:
                # Generate HTML composition and render with HyperFrames
                video_path = await _generate_hyperframes_clip(
                    clip_dir, seg_index, segment_text, duration
                )
            else:
                # Fallback: generate a static image with Pillow
                video_path = await _generate_pillow_fallback(
                    clip_dir, seg_index, segment_text, duration
                )

            gen_time = round(time.time() - start_time, 1)

            results.append({
                "segment_index": seg_index,
                "video_path": str(video_path) if video_path else None,
                "image_path": str(video_path) if video_path else None,
                "type": "motion_clip" if hf_available else "image",
                "generation_time": gen_time,
            })

            if on_progress:
                pct = 5 + int(((idx + 1) / total) * 85)
                await on_progress("images", pct, f"Motion design {idx + 1}/{total} ✓ ({gen_time}s)")

        except Exception as e:
            print(f"⚠️ Motion design failed for segment {seg_index}: {e}")
            # Try Pillow fallback
            try:
                video_path = await _generate_pillow_fallback(
                    clip_dir, seg_index, segment_text, duration
                )
                results.append({
                    "segment_index": seg_index,
                    "video_path": str(video_path),
                    "image_path": str(video_path),
                    "type": "image_fallback",
                    "generation_time": 0,
                    "error": str(e),
                })
            except Exception:
                results.append({
                    "segment_index": seg_index,
                    "video_path": None,
                    "image_path": None,
                    "type": "failed",
                    "error": str(e),
                })

    # Save manifest
    manifest_path = project_path / "motion_manifest.json"
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    if on_progress:
        mode_label = "HyperFrames" if hf_available else "Pillow (fallback)"
        await on_progress("images", 100, f"✓ {len(results)} clips motion design ({mode_label})")

    return results


async def _check_hyperframes() -> bool:
    """Check if HyperFrames CLI is available."""
    try:
        result = await asyncio.to_thread(
            subprocess.run,
            ["npx", "hyperframes", "--version"],
            capture_output=True, text=True, timeout=15,
        )
        return result.returncode == 0
    except Exception:
        return False


async def _generate_hyperframes_clip(
    clip_dir: Path, seg_index: int, segment_text: str, duration: float
) -> str:
    """Generate an animated HTML composition and render it with HyperFrames."""

    # Build the HTML content
    html_content = _build_motion_html(seg_index, segment_text, duration)

    # Write HTML file
    html_path = clip_dir / "index.html"
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(html_content)

    # Render with HyperFrames
    output_path = clip_dir / "output.mp4"

    cmd = [
        "npx", "hyperframes", "render",
        str(html_path),
        "--output", str(output_path),
        "--width", "1920",
        "--height", "1080",
        "--fps", "30",
    ]

    result = await asyncio.to_thread(
        subprocess.run, cmd,
        capture_output=True, text=True,
        cwd=str(clip_dir),
        timeout=60,
    )

    if result.returncode != 0:
        raise RuntimeError(f"HyperFrames render failed: {result.stderr[-300:]}")

    if not output_path.exists():
        raise FileNotFoundError(f"HyperFrames output not found: {output_path}")

    return str(output_path)


async def _generate_pillow_fallback(
    clip_dir: Path, seg_index: int, segment_text: str, duration: float
) -> str:
    """Generate a static editorial image as fallback (when HyperFrames not available)."""
    output_path = clip_dir / f"frame_{seg_index:03d}.png"

    await asyncio.to_thread(
        _generate_editorial_image, segment_text, str(output_path)
    )

    return str(output_path)


def _build_motion_html(seg_index: int, segment_text: str, duration: float) -> str:
    """Build the HTML composition for a motion design clip."""

    # Extract key concepts for cards
    concepts = _extract_key_concepts(segment_text)

    # Build headline — first sentence or first 80 chars
    headline = segment_text.strip()
    if len(headline) > 80:
        if "," in headline[:80]:
            headline = headline[:headline.rindex(",", 0, 80)]
        elif " " in headline[60:80]:
            headline = headline[:headline.rindex(" ", 60, 80)]
        else:
            headline = headline[:77] + "..."

    # Highlight key words in orange
    headline_html = headline
    if concepts:
        # Highlight the first concept word in the headline
        for concept in concepts[:1]:
            first_word = concept.split()[0] if concept else ""
            if first_word and first_word.lower() in headline_html.lower():
                idx = headline_html.lower().find(first_word.lower())
                original = headline_html[idx:idx + len(first_word)]
                headline_html = (
                    headline_html[:idx]
                    + f'<span class="highlight">{original}</span>'
                    + headline_html[idx + len(first_word):]
                )
                break

    # Build cards HTML
    cards_html = ""
    for i, concept in enumerate(concepts[:3]):
        cards_html += f"""
      <div class="card" id="card-{i}">
        <div class="card-badge">{i + 1}</div>
        <div class="card-title">{concept.capitalize()}</div>
        <div class="card-text">Point clé du discours</div>
        <div class="card-dot"></div>
      </div>"""

    # Truncate transcript text for bottom display
    transcript_text = segment_text[:120] + ("..." if len(segment_text) > 120 else "")

    return MOTION_HTML_TEMPLATE.format(
        seg_index=seg_index,
        duration=duration,
        headline_html=headline_html,
        cards_html=cards_html,
        transcript_text=transcript_text,
    )


def _get_text_at_timestamp(transcription: dict, start: float, end: float) -> str:
    """Extract the exact transcript text for a given timestamp range."""
    segments = transcription.get("segments", [])
    texts = []

    for seg in segments:
        seg_start = seg.get("start", 0)
        seg_end = seg.get("end", 0)

        if seg_start < end and seg_end > start:
            words = seg.get("words", [])
            if words:
                for w in words:
                    if w.get("start", 0) >= start - 0.5 and w.get("end", 0) <= end + 0.5:
                        texts.append(w.get("word", ""))
            else:
                texts.append(seg.get("text", ""))

    return " ".join(texts).strip() if texts else ""


def _extract_key_concepts(text: str) -> list[str]:
    """Extract 3 key concepts from the text for infographic cards."""
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

    concepts = []
    i = 0
    while i < len(meaningful) and len(concepts) < 3:
        if i + 1 < len(meaningful):
            concepts.append(f"{meaningful[i]} {meaningful[i + 1]}")
            i += 2
        else:
            concepts.append(meaningful[i])
            i += 1

    while len(concepts) < 3 and meaningful:
        concepts.append(meaningful[len(concepts) % len(meaningful)])

    return concepts


# ── Pillow Fallback ──

def _generate_editorial_image(segment_text: str, output_path: str):
    """Generate a clean editorial-style image using Pillow (fallback)."""
    from PIL import Image, ImageDraw, ImageFont

    W, H = 1920, 1080
    img = Image.new("RGB", (W, H), color=(255, 255, 255))
    draw = ImageDraw.Draw(img)

    ORANGE = (255, 120, 30)
    BLACK = (30, 30, 40)
    GRAY = (120, 120, 130)
    LIGHT_GRAY = (248, 248, 252)
    BORDER_GRAY = (220, 220, 225)

    try:
        title_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 48)
        body_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 26)
        small_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 20)
        subtitle_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 32)
    except Exception:
        title_font = ImageFont.load_default()
        body_font = title_font
        small_font = title_font
        subtitle_font = title_font

    # Bars
    draw.rectangle([0, 0, W, 6], fill=ORANGE)
    draw.rectangle([0, 0, 6, H], fill=ORANGE)
    draw.rectangle([0, H - 6, W, H], fill=ORANGE)

    # Headline
    headline = segment_text[:80] if len(segment_text) > 80 else segment_text
    draw.ellipse([80, 60, 130, 110], fill=ORANGE)
    draw.text((160, 70), headline, fill=BLACK, font=title_font)

    # Divider
    draw.rectangle([80, 200, W - 80, 202], fill=(230, 230, 235))

    # Cards
    keywords = _extract_key_concepts(segment_text)
    card_w = 480
    start_x = (W - (card_w * 3 + 80)) // 2
    for idx, kw in enumerate(keywords[:3]):
        cx = start_x + idx * (card_w + 40)
        cy = 260
        draw.rounded_rectangle([cx, cy, cx + card_w, cy + 280], radius=16, fill=LIGHT_GRAY, outline=BORDER_GRAY)
        draw.rounded_rectangle([cx + 30, cy + 25, cx + 78, cy + 73], radius=8, fill=ORANGE)
        draw.text((cx + 54, cy + 49), str(idx + 1), fill=(255, 255, 255), font=subtitle_font, anchor="mm")
        draw.text((cx + 30, cy + 90), kw.capitalize(), fill=BLACK, font=body_font)
        draw.ellipse([cx + card_w - 28, cy + 252, cx + card_w - 14, cy + 266], fill=ORANGE)

    # Transcript
    draw.rectangle([80, H - 100, W - 80, H - 98], fill=(230, 230, 235))
    draw.text((W // 2, H - 60), segment_text[:100], fill=GRAY, font=small_font, anchor="mt")

    draw.text((W - 100, H - 30), "Nabi AI", fill=(200, 200, 205), font=small_font, anchor="mm")

    img.save(output_path, quality=95)
