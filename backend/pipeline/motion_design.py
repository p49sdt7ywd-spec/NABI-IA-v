"""
Nabi AI — Motion Design Generator via HyperFrames
Generates animated motion design clips using LLM + HyperFrames.

Flow:
  1. Ollama (LLM orchestrateur) generates HyperFrames-compatible HTML compositions
     based on the transcript content and DA color palette
  2. HyperFrames CLI renders each HTML to MP4
  3. The clips are overlaid in the final video as motion design segments

The LLM is guided by a system prompt containing:
  - HyperFrames HTML schema (data attributes, GSAP timelines)
  - Example patterns from the catalog (data-chart, flowchart, etc.)
  - The user's DA color palette
  - The exact transcript text to illustrate
"""

import asyncio
import json
import os
import subprocess
import time
from pathlib import Path
from typing import Optional

import httpx

OLLAMA_URL = "http://localhost:11434"

# ── Default DA (Direction Artistique) ──
DEFAULT_DA = {
    "primary": "#FF7820",       # Orange accent
    "secondary": "#1E1E28",     # Dark text
    "background": "#FFFFFF",    # White background
    "surface": "#F8F8FC",       # Light gray cards
    "text_primary": "#1E1E28",  # Main text
    "text_secondary": "#6E6E78",# Secondary text
    "accent_2": "#326FA8",      # Blue accent for data/lines
    "font_family": "Inter",
}

# ── System Prompt for Ollama ──
# This teaches the LLM how to write HyperFrames HTML compositions.

MOTION_DESIGN_SYSTEM_PROMPT = """Tu es un motion designer expert qui génère des compositions HTML animées pour HyperFrames.

HyperFrames rend du HTML/CSS/JS animé en vidéo MP4. Tu dois générer du HTML valide qui suit ces règles :

═══ STRUCTURE HYPERFRAMES ═══

1. L'élément racine DOIT avoir ces attributs :
   - data-composition-id="motion-{index}"
   - data-width="1920"
   - data-height="1080" 
   - data-start="0"
   - data-duration="{duration}"

2. Utilise GSAP pour les animations. Inclus le CDN :
   <script src="https://cdn.jsdelivr.net/npm/gsap@3.14.2/dist/gsap.min.js"></script>

3. La timeline GSAP DOIT être enregistrée comme :
   window.__timelines = window.__timelines || {};
   window.__timelines["motion-{index}"] = tl;

4. Crée la timeline en mode paused : gsap.timeline({ paused: true })

═══ TYPES DE COMPOSITIONS ═══

Choisis le type de composition le plus adapté au contenu :

TYPE A — INFOGRAPHIE DATA : Quand le texte mentionne des chiffres, statistiques, comparaisons.
- Barres animées, compteurs qui s'incrémentent, graphiques
- Gridlines fines, labels typographiques propres
- Inspiration : NYT-style data visualization

TYPE B — FLOWCHART / PROCESS : Quand le texte décrit un processus, des étapes, une méthode.
- Nodes connectés par des lignes SVG animées
- Révélation séquentielle nœud par nœud
- Flèches et connecteurs animés

TYPE C — POINTS CLÉS / CARDS : Quand le texte présente des concepts, arguments, idées.
- Cards avec icônes (emoji), titres bold, descriptions courtes
- Stagger animation (apparition séquentielle)
- Layout en grid ou en colonnes

TYPE D — TEXTE KINÉTIQUE : Quand le texte a un impact émotionnel ou rhétorique.
- Mots-clés qui apparaissent en grand avec animation
- Effets : fade-in, slide-up, scale-pop
- Typographie dramatique (gros/petit contraste)

TYPE E — TIMELINE / CHRONOLOGIE : Quand le texte parle d'histoire, évolution, étapes temporelles.
- Ligne horizontale ou verticale avec marqueurs
- Dates/labels qui apparaissent séquentiellement
- Connecteurs animés

═══ PALETTE DE COULEURS (DA) ═══
{da_colors}

═══ RÈGLES STRICTES ═══
- body { width: 1920px; height: 1080px; overflow: hidden; }
- TOUTES les animations doivent être dans la timeline GSAP (pas de CSS animation)
- Utilise Google Fonts (Inter, Libre Franklin, ou Libre Baskerville)
- Le texte doit être LISIBLE (taille minimum 20px pour body, 36px+ pour titres)
- Pas de scrolling, tout doit tenir dans 1920x1080
- Durée des animations : adapte au data-duration du segment
- Commence par opacity: 0 ou clip-path: inset(0 100% 0 0), puis anime
- Source le GSAP via CDN

═══ SORTIE ═══
Réponds UNIQUEMENT avec le code HTML complet (<!doctype html>...). Pas de markdown, pas de ```html, pas d'explication. JUSTE le HTML."""


async def generate_motion_clips(
    edl: dict,
    project_dir: str,
    transcription: dict,
    mode: str = "hyperframes",
    on_progress=None,
    da_colors: dict = None,
) -> list[dict]:
    """
    Generate motion design clips for all ai_image/motion_design segments.
    
    1. For each segment, ask Ollama to generate HyperFrames HTML
    2. Render each HTML to MP4 via `npx hyperframes render`
    3. Return list of clip paths for the renderer
    """
    project_path = Path(project_dir)
    motion_dir = project_path / "motion_clips"
    motion_dir.mkdir(parents=True, exist_ok=True)

    # Load DA colors
    da = {**DEFAULT_DA, **(da_colors or {})}

    # Collect motion design segments
    motion_segments = []
    for i, seg in enumerate(edl.get("segments", [])):
        if seg.get("type") in ("ai_image", "motion_design"):
            motion_segments.append((i, seg))

    if not motion_segments:
        if on_progress:
            await on_progress("motion_design", 100, "Aucun motion design requis")
        return []

    total = len(motion_segments)
    if on_progress:
        await on_progress("motion_design", 5, f"Création de {total} clips motion design...")

    # Check HyperFrames availability
    hf_available = await _check_hyperframes() if mode == "hyperframes" else False

    results = []

    for idx, (seg_index, seg) in enumerate(motion_segments):
        start_time = time.time()
        duration = round(seg["end"] - seg["start"], 2)
        if duration < 0.5:
            duration = 1.5  # Minimum duration

        # Get transcript text for this segment
        segment_text = _get_text_at_timestamp(transcription, seg["start"], seg["end"])
        if not segment_text:
            segment_text = seg.get("image_prompt", seg.get("notes", "Information clé"))

        if on_progress:
            pct = 5 + int((idx / total) * 85)
            await on_progress("motion_design", pct, f"Motion design {idx + 1}/{total} — LLM génère le HTML...")

        clip_dir = motion_dir / f"clip_{seg_index:03d}"
        clip_dir.mkdir(parents=True, exist_ok=True)

        try:
            # Step 1: Ask Ollama to generate HyperFrames HTML
            html_content = await _generate_html_with_ollama(
                seg_index, segment_text, duration, da
            )

            if not html_content:
                raise RuntimeError("Ollama returned empty HTML")

            # Write HTML file
            html_path = clip_dir / "index.html"
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)

            # Step 2: Render with HyperFrames
            if hf_available:
                if on_progress:
                    pct = 5 + int(((idx + 0.6) / total) * 85)
                    await on_progress("motion_design", pct, f"Motion design {idx + 1}/{total} — HyperFrames render...")

                video_path = await _render_with_hyperframes(clip_dir, html_path)
            else:
                # Fallback: generate static image with Pillow
                video_path = await _generate_pillow_fallback(
                    clip_dir, seg_index, segment_text
                )

            gen_time = round(time.time() - start_time, 1)

            results.append({
                "segment_index": seg_index,
                "video_path": str(video_path) if video_path and str(video_path).endswith(".mp4") else None,
                "image_path": str(video_path) if video_path and not str(video_path).endswith(".mp4") else None,
                "type": "motion_clip" if hf_available and str(video_path).endswith(".mp4") else "image",
                "generation_time": gen_time,
            })

            if on_progress:
                pct = 5 + int(((idx + 1) / total) * 85)
                await on_progress("motion_design", pct, f"Motion design {idx + 1}/{total} ✓ ({gen_time}s)")

        except Exception as e:
            print(f"⚠️ Motion design failed for segment {seg_index}: {e}")
            # Pillow fallback
            try:
                fallback_path = await _generate_pillow_fallback(
                    clip_dir, seg_index, segment_text
                )
                results.append({
                    "segment_index": seg_index,
                    "video_path": None,
                    "image_path": str(fallback_path),
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
        ok_count = sum(1 for r in results if r.get("video_path") or r.get("image_path"))
        await on_progress("motion_design", 100, f"✓ {ok_count}/{total} clips motion design ({mode_label})")

    return results


# ── LLM HTML Generation ──

async def _generate_html_with_ollama(
    seg_index: int, segment_text: str, duration: float, da: dict
) -> str:
    """Use Ollama to generate a HyperFrames HTML composition."""

    da_colors_text = f"""
- Couleur primaire (accents, icônes) : {da['primary']}
- Couleur secondaire (texte principal) : {da['secondary']}
- Fond : {da['background']}
- Surface (cards) : {da['surface']}
- Texte secondaire : {da['text_secondary']}
- Accent données/graphiques : {da['accent_2']}
- Police : {da['font_family']}"""

    system = MOTION_DESIGN_SYSTEM_PROMPT.replace("{da_colors}", da_colors_text)

    user_prompt = f"""Génère une composition HyperFrames HTML pour ce segment de vidéo.

INDEX DU SEGMENT : {seg_index}
DURÉE : {duration} secondes
TEXTE DE LA TRANSCRIPTION :
\"{segment_text}\"

Choisis le type de composition le plus adapté (data chart, flowchart, cards, texte kinétique, timeline) en fonction du contenu du texte. La composition doit illustrer visuellement ce que dit le speaker de manière instructive et engageante.

Rappel :
- data-composition-id="motion-{seg_index}"
- data-duration="{duration}"
- Enregistre la timeline dans window.__timelines["motion-{seg_index}"]
- UNIQUEMENT du HTML, pas de markdown."""

    try:
        async with httpx.AsyncClient(timeout=120) as client:
            response = await client.post(
                f"{OLLAMA_URL}/api/generate",
                json={
                    "model": "qwen3:4b",
                    "prompt": user_prompt,
                    "system": system,
                    "stream": False,
                    "options": {
                        "temperature": 0.7,
                        "num_predict": 4096,
                    },
                },
            )

            if response.status_code != 200:
                raise RuntimeError(f"Ollama error: {response.status_code}")

            data = response.json()
            raw = data.get("response", "")

            # Clean response — extract HTML
            html = _extract_html(raw)
            return html

    except httpx.TimeoutException:
        raise RuntimeError("Ollama timeout (120s)")
    except httpx.ConnectError:
        raise RuntimeError("Ollama not running (localhost:11434)")


def _extract_html(raw: str) -> str:
    """Extract clean HTML from LLM response (remove markdown fences, thinking tags, etc.)."""
    text = raw.strip()

    # Remove <think>...</think> blocks (Qwen3 thinking mode)
    import re
    text = re.sub(r'<think>.*?</think>', '', text, flags=re.DOTALL)

    # Remove markdown code fences
    text = re.sub(r'^```html?\s*\n?', '', text, flags=re.MULTILINE)
    text = re.sub(r'\n?```\s*$', '', text, flags=re.MULTILINE)

    text = text.strip()

    # Find the HTML document
    if '<!doctype' in text.lower() or '<!DOCTYPE' in text:
        start = text.lower().find('<!doctype')
        if start == -1:
            start = text.lower().find('<!DOCTYPE')
        end = text.rfind('</html>')
        if end != -1:
            text = text[start:end + 7]

    elif '<html' in text.lower():
        start = text.lower().find('<html')
        end = text.rfind('</html>')
        if end != -1:
            text = text[start:end + 7]

    return text


# ── HyperFrames Rendering ──

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


async def _render_with_hyperframes(clip_dir: Path, html_path: Path) -> str:
    """Render HTML composition to MP4 using HyperFrames CLI."""
    output_path = clip_dir / "output.mp4"

    cmd = [
        "npx", "hyperframes", "render",
        str(html_path),
        "-o", str(output_path),
        "--resolution", "landscape",
    ]

    result = await asyncio.to_thread(
        subprocess.run, cmd,
        capture_output=True, text=True,
        cwd=str(clip_dir),
        timeout=120,
    )

    if result.returncode != 0:
        stderr = result.stderr[-500:] if result.stderr else "No stderr"
        raise RuntimeError(f"HyperFrames render failed: {stderr}")

    if not output_path.exists():
        raise FileNotFoundError(f"Output not found: {output_path}")

    return str(output_path)


# ── Transcript Extraction ──

def _get_text_at_timestamp(transcription: dict, start: float, end: float) -> str:
    """Extract transcript text for a given time range."""
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


# ── Pillow Fallback ──

async def _generate_pillow_fallback(
    clip_dir: Path, seg_index: int, segment_text: str
) -> str:
    """Generate a static editorial image as fallback."""
    output_path = clip_dir / f"frame_{seg_index:03d}.png"
    await asyncio.to_thread(_generate_editorial_image, segment_text, str(output_path))
    return str(output_path)


def _extract_key_concepts(text: str) -> list[str]:
    """Extract key concepts from text for infographic cards."""
    stop_words = {
        "le", "la", "les", "de", "du", "des", "un", "une", "et", "en", "est", "que",
        "qui", "dans", "ce", "il", "ne", "pas", "pour", "sur", "avec", "plus", "par",
        "son", "se", "sont", "au", "nous", "vous", "ils", "on", "a", "je", "tu", "sa",
        "cette", "ces", "mais", "ou", "donc", "car", "si", "tout", "bien", "très",
        "aussi", "fait", "faire", "être", "avoir", "c'est", "ça", "là", "y", "te", "me",
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
