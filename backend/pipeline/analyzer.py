"""
Nabi AI — LLM Analyzer Pipeline Module
Uses Ollama (local LLM) to analyze transcriptions and generate an Edit Decision List (EDL).
The EDL contains all the editing decisions: zooms, B-roll placements, AI image prompts, transitions.
"""

import json
import httpx
from typing import Optional

OLLAMA_URL = "http://localhost:11434"

SYSTEM_PROMPT = """Tu es un réalisateur et monteur vidéo professionnel de niveau mondial, spécialisé dans le montage ultra-dynamique de vidéos YouTube face-caméra (talking head).

Tu reçois la transcription horodatée d'une vidéo. Ta mission est de créer un "Edit Decision List" (EDL) qui transforme cette vidéo brute en un montage captivant, dynamique et premium.

═══ RÈGLES DE MONTAGE STRICTES ═══

1. INTRO ULTRA-DYNAMIQUE AVEC MOTION DESIGN (Hook) :
   - La vidéo DOIT commencer DIRECTEMENT par la facecam du speaker qui parle (2-3 premières secondes). PAS de B-roll ou animation à la toute première seconde.
   - JUSTE APRÈS ce hook facecam initial, intègre immédiatement des animations, B-rolls et motion design de manière très dynamique pour retenir l'attention.

2. RYTHME ÉNERGÉTIQUE ET ZOOMS INTÉGRÉS (Obligatoire) :
   - Maintiens un rythme rapide avec des coupes franches.
   - Élimine TOUTES les pauses et temps morts.
   - Applique des zooms stratégiquement sur les mots-clés, expressions marquantes et transitions pour dynamiser.
   - Alterne zoom_in et zoom_out pour varier le rythme.

3. B-ROLL HAUTE DENSITÉ ET MOTION DESIGN ABONDANT (Crucial) :
   - Volume très élevé de visuels : pour 5 minutes de vidéo = MINIMUM 20 B-rolls différents (4 par minute minimum).
   - Tu PEUX et DOIS enchaîner plusieurs B-rolls directement sans revenir à la facecam (back-to-back).
   - Les search_query DOIVENT être en ANGLAIS, descriptifs et premium (ex: "modern office team collaboration", "AI technology neural network", "professional training workshop").

4. PICTURE-IN-PICTURE (PiP) — OBLIGATOIRE :
   - Pendant TOUS les B-rolls, images IA et animations : affiche le speaker en overlay.
   - Le cadre PiP doit être grand, clair, facilement lisible, rectangulaire.
   - pip=true est OBLIGATOIRE pour tout segment qui n'est pas "facecam".

5. IMAGES IA EXPLICATIVES :
   - Génère des prompts pour des infographies style éditorial premium.
   - Style : fond blanc/très clair, texte noir, orange uniquement pour accents/flèches/icônes.
   - Typographie propre, style infographique avec diagrammes, labels, graphiques.
   - Minimum 2 images IA par minute de vidéo.

6. COHÉRENCE GLOBALE DE LA TIMELINE :
   - Planifie soigneusement la structure entière.
   - Transitions fluides et synchronisées avec le discours.
   - Le flux doit être logique, cohérent, sans incohérences visuelles.

7. PAS DE MUSIQUE DE FOND.

8. AUDIO : Garde uniquement les meilleurs passages pour un flux professionnel et naturel.

═══ FORMAT DE SORTIE ═══

Réponds UNIQUEMENT en JSON valide :
{
  "segments": [
    {
      "start": float,
      "end": float,
      "type": "facecam" | "broll_video" | "ai_image",
      "effect": "none" | "zoom_in" | "zoom_out" | "smooth_zoom_in",
      "pip": boolean,
      "search_query": "english query for pexels" | null,
      "image_prompt": "detailed FLUX prompt" | null,
      "transition": "cut" | "crossfade",
      "notes": "editing rationale"
    }
  ],
  "summary": "Description du plan de montage",
  "total_brolls": int,
  "total_ai_images": int
}

═══ CONTRAINTES CRITIQUES ═══
- JSON valide UNIQUEMENT, pas de texte avant/après.
- Timestamps alignés sur la transcription.
- search_query en ANGLAIS, descriptif et premium.
- pip=true pour TOUS les segments broll_video et ai_image.
- Minimum 4 B-rolls + 2 images IA par minute.
- Enchaîne des B-rolls back-to-back quand le contenu s'y prête.
- Commence TOUJOURS par facecam (hook), puis B-roll/motion design immédiatement après."""


async def analyze_transcript(
    transcription: dict,
    project_dir: str,
    model: str = "qwen3:4b",
    on_progress=None,
) -> dict:
    """
    Analyze a transcription using a local LLM via Ollama to generate an EDL.
    
    Args:
        transcription: The transcription dict with segments and word timestamps
        project_dir: Path to the project directory
        model: Ollama model name to use
        on_progress: Async callback for progress updates
    
    Returns:
        Edit Decision List (EDL) as a dict
    """
    if on_progress:
        await on_progress("analysis", 10, "Préparation de l'analyse...")
    
    # Build the user prompt with the transcription
    transcript_text = _format_transcript_for_llm(transcription)
    
    user_prompt = f"""Voici la transcription horodatée de la vidéo à monter :

{transcript_text}

Durée totale : {transcription.get('duration', 0):.1f} secondes

Analyse cette transcription et génère l'Edit Decision List (EDL) en JSON.
Assure-toi d'avoir au minimum 4 B-rolls par minute de vidéo.
Fais des choix de montage dynamiques et variés."""

    if on_progress:
        await on_progress("analysis", 30, "Analyse IA en cours...")
    
    # Call Ollama API
    try:
        edl = await _call_ollama(model, SYSTEM_PROMPT, user_prompt)
    except Exception as e:
        # Fallback: generate a basic EDL from the transcription
        if on_progress:
            await on_progress("analysis", 50, f"Ollama indisponible, EDL basique généré...")
        edl = _generate_fallback_edl(transcription)
    
    if on_progress:
        await on_progress("analysis", 90, "Sauvegarde de l'EDL...")
    
    # Save EDL
    from pathlib import Path
    edl_path = Path(project_dir) / "edl.json"
    with open(edl_path, "w", encoding="utf-8") as f:
        json.dump(edl, f, ensure_ascii=False, indent=2)
    
    if on_progress:
        await on_progress("analysis", 100, "Analyse terminée ✓")
    
    return edl


async def _call_ollama(model: str, system_prompt: str, user_prompt: str) -> dict:
    """Call Ollama API and parse JSON response."""
    async with httpx.AsyncClient(timeout=300) as client:
        response = await client.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0.3,
                    "num_predict": 8192,
                },
            },
        )
        response.raise_for_status()
        
        data = response.json()
        content = data.get("message", {}).get("content", "")
        
        # Parse the JSON response
        edl = json.loads(content)
        
        # Validate required fields
        if "segments" not in edl:
            raise ValueError("EDL missing 'segments' field")
        
        return edl


def _format_transcript_for_llm(transcription: dict) -> str:
    """Format transcription segments for the LLM prompt."""
    lines = []
    for seg in transcription.get("segments", []):
        start = seg["start"]
        end = seg["end"]
        text = seg["text"]
        lines.append(f"[{start:.1f}s - {end:.1f}s] {text}")
    return "\n".join(lines)


def _generate_fallback_edl(transcription: dict) -> dict:
    """
    Generate a rich EDL when Ollama is not available.
    Sub-divides transcription into fine-grained editing segments to ensure
    high visual density: minimum 4 B-rolls + 2 images per minute.
    """
    segments = transcription.get("segments", [])
    if not segments:
        return {"segments": [], "summary": "Empty transcription", "total_brolls": 0, "total_ai_images": 0}

    total_duration = transcription.get("duration", segments[-1]["end"])

    # Adaptive target: shorter sub-segments for short videos to ensure visual density
    if total_duration < 30:
        target_dur = 1.5
    elif total_duration < 60:
        target_dur = 2.0
    elif total_duration < 180:
        target_dur = 2.5
    else:
        target_dur = 3.0

    # Build sub-segments using word timestamps
    sub_segments = _build_sub_segments(segments, target_duration=target_dur)

    edl_segments = []
    broll_count = 0
    image_count = 0
    total_subs = len(sub_segments)

    # Ultra-dense pattern following the editing rules:
    # Position 0: FACECAM (hook) with zoom_in
    # Position 1: BROLL (immediate dynamic after hook)
    # Position 2: BROLL (back-to-back chain for energy)
    # Position 3: FACECAM with zoom effect
    # Position 4: BROLL
    # Position 5: AI_IMAGE
    # Position 6: BROLL
    # Position 7: FACECAM with zoom
    # ... repeat from position 1 pattern
    #
    # This gives ~5 B-rolls + 1 AI image per 8 segments = very high density

    for i, sub in enumerate(sub_segments):
        if i == 0:
            # RULE 1: First segment = facecam hook, always
            edl_segments.append(_make_segment(
                sub, "facecam", effect="zoom_in",
                notes="Hook - facecam opening (speaker visible first)",
            ))
        elif i == 1:
            # RULE 1: Immediately after hook = B-roll for ultra-dynamic intro
            keywords = _extract_keywords_en(sub["text"])
            edl_segments.append(_make_segment(
                sub, "broll_video", pip=True,
                search_query=keywords,
                transition="crossfade",
                notes="Post-hook B-roll (ultra-dynamic intro)",
            ))
            broll_count += 1
        elif i == 2 and total_subs > 4:
            # RULE 3: Back-to-back B-roll chain after hook
            keywords = _extract_keywords_en(sub["text"])
            edl_segments.append(_make_segment(
                sub, "broll_video", pip=True,
                search_query=keywords,
                transition="cut",
                notes="Back-to-back B-roll (dynamic intro chain)",
            ))
            broll_count += 1
        else:
            # Repeating pattern for the rest of the video
            pos = (i - 3) % 6 if i >= 3 else i

            if pos == 0 or pos == 3:
                # Facecam with zoom effect
                effect = "zoom_in" if (i % 3 == 0) else "zoom_out"
                edl_segments.append(_make_segment(
                    sub, "facecam", effect=effect,
                    notes="Facecam with dynamic zoom",
                ))
            elif pos == 1 or pos == 2 or pos == 4:
                # B-roll (3 out of 6 = 50% visual coverage)
                keywords = _extract_keywords_en(sub["text"])
                edl_segments.append(_make_segment(
                    sub, "broll_video", pip=True,
                    search_query=keywords,
                    transition="crossfade" if pos == 1 else "cut",
                    notes=f"B-roll {'back-to-back' if pos == 2 else ''}: {sub['text'][:40]}",
                ))
                broll_count += 1
            elif pos == 5:
                # AI image with smooth zoom
                edl_segments.append(_make_segment(
                    sub, "ai_image", pip=True,
                    effect="smooth_zoom_in",
                    image_prompt=_generate_image_prompt(sub["text"]),
                    transition="crossfade",
                    notes=f"AI infographic: {sub['text'][:40]}",
                ))
                image_count += 1

    # Ensure minimum visuals even for very short videos
    if broll_count == 0 and total_subs >= 2:
        edl_segments[1]["type"] = "broll_video"
        edl_segments[1]["pip"] = True
        edl_segments[1]["search_query"] = _extract_keywords_en(sub_segments[1]["text"])
        edl_segments[1]["transition"] = "crossfade"
        broll_count = 1

    # Ensure at least 1 AI image — convert a middle B-roll to ai_image
    if image_count == 0 and broll_count >= 2:
        # Find the best candidate: a B-roll near the middle of the video
        mid_idx = len(edl_segments) // 2
        for offset in range(len(edl_segments)):
            for check_idx in [mid_idx + offset, mid_idx - offset]:
                if 0 <= check_idx < len(edl_segments) and edl_segments[check_idx]["type"] == "broll_video":
                    edl_segments[check_idx]["type"] = "ai_image"
                    edl_segments[check_idx]["effect"] = "smooth_zoom_in"
                    edl_segments[check_idx]["search_query"] = None
                    edl_segments[check_idx]["image_prompt"] = _generate_image_prompt(
                        sub_segments[min(check_idx, len(sub_segments) - 1)]["text"]
                    )
                    broll_count -= 1
                    image_count += 1
                    break
            if image_count > 0:
                break

    return {
        "segments": edl_segments,
        "summary": f"Auto-generated EDL: {len(edl_segments)} segments, {broll_count} B-rolls, {image_count} AI images ({total_duration:.0f}s)",
        "total_brolls": broll_count,
        "total_ai_images": image_count,
    }


def _build_sub_segments(segments: list, target_duration: float = 3.0) -> list[dict]:
    """
    Split transcription segments into smaller sub-segments of ~target_duration seconds.
    Uses word timestamps for precise splitting.
    """
    sub_segments = []

    for seg in segments:
        duration = seg["end"] - seg["start"]
        words = seg.get("words", [])

        if duration <= target_duration * 1.5 or len(words) < 4:
            # Short enough, keep as-is
            sub_segments.append({
                "start": seg["start"],
                "end": seg["end"],
                "text": seg["text"],
            })
            continue

        # Split into chunks using word boundaries
        num_splits = max(2, round(duration / target_duration))
        words_per_split = max(1, len(words) // num_splits)

        for chunk_idx in range(num_splits):
            start_word_idx = chunk_idx * words_per_split
            end_word_idx = min((chunk_idx + 1) * words_per_split, len(words))

            if chunk_idx == num_splits - 1:
                end_word_idx = len(words)  # Last chunk gets remaining words

            if start_word_idx >= len(words):
                break

            chunk_words = words[start_word_idx:end_word_idx]
            if not chunk_words:
                continue

            sub_segments.append({
                "start": chunk_words[0]["start"],
                "end": chunk_words[-1]["end"],
                "text": " ".join(w["word"] for w in chunk_words),
            })

    return sub_segments


def _make_segment(
    sub: dict, seg_type: str,
    effect: str = "none", pip: bool = False,
    search_query: str | None = None,
    image_prompt: str | None = None,
    transition: str = "cut",
    notes: str = "",
) -> dict:
    """Create a standardized EDL segment dict."""
    return {
        "start": sub["start"],
        "end": sub["end"],
        "type": seg_type,
        "effect": effect,
        "pip": pip,
        "search_query": search_query,
        "image_prompt": image_prompt,
        "transition": transition,
        "notes": notes,
    }


# ── French → English keyword mapping for Pexels ──

_FR_EN_KEYWORDS = {
    "formation": "training course education",
    "certifiante": "certificate diploma",
    "compétences": "skills expertise",
    "professionnelles": "professional business",
    "développer": "develop growth",
    "automatisation": "automation technology",
    "automatisations": "automation robot technology",
    "intelligence": "artificial intelligence AI",
    "artificielle": "artificial intelligence brain",
    "expert": "expert consultant meeting",
    "entreprise": "business company office",
    "argent": "money finance wealth",
    "revenus": "income revenue money",
    "clients": "clients customers meeting",
    "vendre": "selling sales marketing",
    "marketing": "digital marketing strategy",
    "produit": "product launch tech",
    "service": "customer service support",
    "réseaux": "social media network",
    "sociaux": "social media internet",
    "internet": "internet technology digital",
    "travail": "work office professional",
    "succès": "success achievement goal",
    "objectif": "goal target planning",
    "stratégie": "strategy planning business",
    "investir": "investment finance growth",
    "apprendre": "learning education study",
    "réserver": "booking appointment schedule",
    "appel": "phone call meeting consultation",
}


def _extract_keywords_en(text: str) -> str:
    """Extract keywords from French text and translate to English for Pexels search."""
    stop_words = {
        "le", "la", "les", "de", "du", "des", "un", "une", "et", "en", "est", "que",
        "qui", "dans", "ce", "il", "ne", "pas", "pour", "sur", "avec", "plus", "par",
        "son", "se", "sont", "au", "nous", "vous", "ils", "on", "a", "je", "tu", "sa",
        "cette", "ces", "mais", "ou", "donc", "car", "si", "tout", "bien", "très",
        "aussi", "fait", "faire", "être", "avoir", "c'est", "ça", "là", "y", "te", "me",
        "j'ai", "m'a", "mon", "mes", "l'ia", "pu", "aux",
    }

    words = text.lower().replace("'", " ").replace("'", " ").split()
    keywords = [w for w in words if len(w) > 2 and w not in stop_words]

    # Translate to English
    english_terms = []
    for kw in keywords[:6]:
        if kw in _FR_EN_KEYWORDS:
            english_terms.append(_FR_EN_KEYWORDS[kw].split()[0])
        else:
            english_terms.append(kw)

    result = " ".join(english_terms[:4])
    return result if result.strip() else "business technology modern professional"


def _generate_image_prompt(text: str) -> str:
    """Generate a FLUX image prompt from segment text."""
    return (
        f"Clean editorial explainer visual about: {text[:100]}. "
        "White or very light paper-like background. Black text as main color, "
        "orange used only for highlights, emphasis, arrows, icons. "
        "Clean typography, simple infographic style with charts, labels, or diagrams. "
        "Premium, minimal, educational, easy to read. 16:9 horizontal format."
    )

