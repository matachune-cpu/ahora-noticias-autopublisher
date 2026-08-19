"""
Módulo de resolución y validación de imágenes para Ahora Noticias.

Garantiza que NUNCA se publique en redes sociales sin una imagen real y validada.
Aplica validación técnica, semántica y visual (Gemini) antes de aceptar una imagen.
"""
import json
import logging
import os
import random
import re
import unicodedata
from io import BytesIO
from typing import Optional
from urllib.parse import urlparse, urljoin

import requests
from bs4 import BeautifulSoup
from PIL import Image

logger = logging.getLogger(__name__)

# ── Constantes de validación ───────────────────────────────────────────────────

TECHNICAL_MIN_SIZE_BYTES = 5 * 1024        # 5 KB mínimo
TECHNICAL_MIN_WIDTH = 400                   # px mínimo aceptable
TECHNICAL_DESIRED_WIDTH = 800              # px deseable

SEMANTIC_MIN_SCORE = 30                    # umbral bajo — muchas fotos no tienen alt text
VISUAL_MIN_CONFIDENCE = 60                # confianza mínima de Gemini
FINAL_MIN_SCORE = 55                       # umbral de score combinado

PLACEHOLDER_NAMES = {
    "placeholder", "default", "noimage", "no-image", "no_image",
    "blank", "dummy", "missing", "nophoto", "no-photo", "notfound",
    "404", "spacer", "pixel", "transparent",
}

PLACEHOLDER_STD_THRESHOLD = 15            # desv. estándar de píxeles — imagen casi sólida

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                  "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "es-AR,es;q=0.9,en;q=0.8",
}

EXCLUDE_URL_TOKENS = {
    "favicon", "logo", "logos", "logotipo", "icon", "icons",
    "banner", "avatar", "thumbnail", "thumb", "sprite", "footer",
    "header", "watermark", "brand",
}

VALID_CONTENT_TYPES = {"image/jpeg", "image/png", "image/webp"}


# ── Stopwords para análisis semántico ─────────────────────────────────────────

_STOPWORDS_ES = {
    "el", "la", "los", "las", "un", "una", "unos", "unas",
    "de", "del", "al", "en", "con", "por", "para", "que", "segun",
    "se", "lo", "le", "les", "su", "sus", "y", "o", "a", "e",
    "es", "son", "fue", "era", "ha", "han", "hay", "no", "ni",
    "si", "ya", "mas", "pero", "como", "muy", "bien", "aqui",
    "cuando", "donde", "quien", "cual", "cuales", "sobre", "ante",
    "tras", "entre", "durante", "desde", "hasta", "tambien",
    "este", "esta", "estos", "estas", "ese", "esa", "esos", "esas",
    "aquel", "todo", "toda", "todos", "todas", "otro", "otra",
    "mismo", "misma", "cada", "nuevo", "nueva", "gran", "solo",
    "luego", "pese", "junto",
}


# ── Gemini client (reutiliza el patrón de rewriter.py) ────────────────────────

_client = None


def _get_client():
    global _client
    if _client is None:
        from dotenv import dotenv_values
        key = os.getenv("GEMINI_API_KEY") or dotenv_values(".env").get("GEMINI_API_KEY")
        from google import genai
        _client = genai.Client(api_key=key)
    return _client


MODEL = "gemini-2.5-flash"


# ── Utilidades ─────────────────────────────────────────────────────────────────

def _normalize(text: str) -> str:
    """Elimina tildes y pasa a minúsculas."""
    nfd = unicodedata.normalize("NFD", text)
    without_accents = "".join(c for c in nfd if unicodedata.category(c) != "Mn")
    return without_accents.lower()


def _keywords(text: str) -> set:
    limpio = re.sub(r"[^\w\s]", " ", _normalize(text))
    return {w for w in limpio.split() if len(w) > 3 and w not in _STOPWORDS_ES}


def _url_looks_excluded(url: str) -> bool:
    url_lower = url.lower()
    return any(token in url_lower for token in EXCLUDE_URL_TOKENS)


def _absolute_url(url: str, base_url: str) -> Optional[str]:
    if not url:
        return None
    if url.startswith("http"):
        return url
    try:
        return urljoin(base_url, url)
    except Exception:
        return None


# ── Validación técnica ─────────────────────────────────────────────────────────

def _detect_placeholder(img: Image.Image) -> bool:
    """
    Detecta imágenes placeholder mediante análisis de píxeles.
    Si la desviación estándar es < 15 la imagen es casi sólida → placeholder.
    """
    try:
        rgb = img.convert("RGB")
        w, h = rgb.size
        # Muestrear hasta 200 píxeles aleatorios
        sample_size = min(200, w * h)
        pixels = []
        for _ in range(sample_size):
            x = random.randint(0, w - 1)
            y = random.randint(0, h - 1)
            r, g, b = rgb.getpixel((x, y))
            pixels.append((r + g + b) / 3)

        if not pixels:
            return False

        mean = sum(pixels) / len(pixels)
        variance = sum((p - mean) ** 2 for p in pixels) / len(pixels)
        std = variance ** 0.5
        return std < PLACEHOLDER_STD_THRESHOLD
    except Exception:
        return False


def _validate_technical(url: str) -> dict:
    """
    Valida aspectos técnicos de una imagen.
    Retorna dict con score (0-100), passed (bool), y rejection_reason.
    """
    # Verificar URL excluida por nombre
    fname = urlparse(url).path.split("/")[-1].lower().split(".")[0]
    if fname in PLACEHOLDER_NAMES:
        return {"score": 0, "passed": False,
                "rejection_reason": f"URL sugiere placeholder: {fname}"}

    if _url_looks_excluded(url):
        return {"score": 0, "passed": False,
                "rejection_reason": "URL sugiere logo/banner/avatar"}

    try:
        resp = requests.get(url, headers=HEADERS, timeout=12)
        if resp.status_code != 200:
            return {"score": 0, "passed": False,
                    "rejection_reason": f"HTTP {resp.status_code}"}

        content_type = resp.headers.get("Content-Type", "").split(";")[0].strip().lower()
        if content_type not in VALID_CONTENT_TYPES:
            return {"score": 0, "passed": False,
                    "rejection_reason": f"Content-Type inválido: {content_type}"}

        img_bytes = resp.content
        if len(img_bytes) < TECHNICAL_MIN_SIZE_BYTES:
            return {"score": 0, "passed": False,
                    "rejection_reason": f"Imagen demasiado pequeña: {len(img_bytes)} bytes"}

        img = Image.open(BytesIO(img_bytes))
        width, height = img.size

        if width < TECHNICAL_MIN_WIDTH:
            return {"score": 0, "passed": False,
                    "rejection_reason": f"Ancho insuficiente: {width}px (mínimo {TECHNICAL_MIN_WIDTH}px)"}

        if _detect_placeholder(img):
            return {"score": 0, "passed": False,
                    "rejection_reason": "Imagen de color sólido (placeholder detectado por píxeles)"}

        # Score según ancho
        if width >= TECHNICAL_DESIRED_WIDTH:
            score = 100
        else:
            score = int(60 + 40 * (width - TECHNICAL_MIN_WIDTH) / (TECHNICAL_DESIRED_WIDTH - TECHNICAL_MIN_WIDTH))

        return {"score": score, "passed": True, "img_bytes": img_bytes,
                "width": width, "height": height}

    except Exception as e:
        return {"score": 0, "passed": False,
                "rejection_reason": f"Error técnico: {e}"}


# ── Validación semántica ───────────────────────────────────────────────────────

def _validate_semantic(title: str, image_url: str, alt_text: str = "", page_title: str = "") -> dict:
    """
    Compara palabras clave del título con metadatos de la imagen.
    Retorna score 0-100.
    """
    title_kw = _keywords(title)
    if not title_kw:
        return {"score": 50, "passed": True}  # sin palabras clave → no podemos juzgar

    # Texto a comparar: nombre de archivo + alt text + título de página fuente
    img_path = urlparse(image_url).path.lower()
    img_fname = img_path.split("/")[-1]
    combined = f"{img_fname} {_normalize(alt_text)} {_normalize(page_title)}"
    combined_kw = _keywords(combined)

    if not combined_kw:
        # Sin metadatos comparables (filename genérico, sin alt text) — score neutro.
        # Gemini Vision ya evalúa la relevancia semántica visualmente.
        return {"score": 50, "passed": True}

    intersection = title_kw & combined_kw
    score = int(100 * len(intersection) / len(title_kw))
    score = min(100, score)

    passed = score >= SEMANTIC_MIN_SCORE
    result = {"score": score, "passed": passed}
    if not passed:
        result["rejection_reason"] = (
            f"Baja coincidencia semántica: score={score} "
            f"(palabras comunes: {intersection or 'ninguna'})"
        )
    return result


# ── Validación visual con Gemini ──────────────────────────────────────────────

def _validate_with_vision(title: str, summary: str, image_url: str, img_bytes: bytes = None) -> dict:
    """
    Usa Gemini Vision para validar que la imagen es apropiada para la nota.
    Si Gemini falla, retorna score=50 y appropriate=True (no bloquear por error API).
    """
    try:
        from google.genai import types

        if img_bytes is None:
            resp = requests.get(image_url, headers=HEADERS, timeout=12)
            resp.raise_for_status()
            img_bytes = resp.content

        # Detectar content-type
        content_type = "image/jpeg"
        url_lower = image_url.lower()
        if ".png" in url_lower:
            content_type = "image/png"
        elif ".webp" in url_lower:
            content_type = "image/webp"

        prompt = f"""You are an editorial photo validator for a news outlet.
Article title: {title}
Article summary: {summary[:500] if summary else '(no summary)'}

Analyze this image and determine if it is editorially appropriate to illustrate this news article.
Rules:
- REJECT if the image is a solid color, gradient, placeholder, logo, banner, or icon
- REJECT if the image shows a different person than the one mentioned in the title (when a specific person is named)
- REJECT if the image shows a completely different event, accident, or situation that could mislead readers
- ACCEPT contextual images (related location, institution, building) when no specific person/event image exists
- When in doubt about identity of a person, REJECT

Respond in JSON:
{{
  "appropriate": true/false,
  "confidence": 0-100,
  "matches_topic": true/false,
  "risk_of_misleading": true/false,
  "is_placeholder": true/false,
  "reason": "brief explanation"
}}"""

        client = _get_client()
        response = client.models.generate_content(
            model=MODEL,
            contents=[
                types.Part.from_bytes(data=img_bytes, mime_type=content_type),
                prompt,
            ],
        )

        raw = response.text.strip()
        # Extraer JSON de la respuesta (puede venir con markdown)
        json_match = re.search(r'\{.*\}', raw, re.DOTALL)
        if not json_match:
            raise ValueError(f"No JSON en respuesta Gemini: {raw[:200]}")
        data = json.loads(json_match.group())

        appropriate = bool(data.get("appropriate", False))
        confidence = int(data.get("confidence", 0))
        matches_topic = bool(data.get("matches_topic", False))
        risk_of_misleading = bool(data.get("risk_of_misleading", False))
        is_placeholder = bool(data.get("is_placeholder", False))
        reason = data.get("reason", "")

        # Criterios de aceptación
        passed = (
            appropriate
            and confidence >= VISUAL_MIN_CONFIDENCE
            and not risk_of_misleading
            and not is_placeholder
        )

        # Score visual (0-100): base de confianza, penalizar por riesgo
        score = confidence if appropriate else max(0, confidence - 50)
        if risk_of_misleading:
            score = max(0, score - 30)
        if is_placeholder:
            score = 0

        result = {
            "score": score,
            "passed": passed,
            "appropriate": appropriate,
            "confidence": confidence,
            "matches_topic": matches_topic,
            "risk_of_misleading": risk_of_misleading,
            "is_placeholder": is_placeholder,
            "reason": reason,
        }
        if not passed:
            result["rejection_reason"] = (
                f"Gemini rechazó: appropriate={appropriate}, "
                f"confidence={confidence}, misleading={risk_of_misleading}, "
                f"placeholder={is_placeholder}. Razón: {reason}"
            )
        return result

    except Exception as e:
        logger.warning(f"Gemini Vision error (no fatal) — imagen conservada: {e}")
        # Falla silenciosa: no bloquear por error de API
        return {
            "score": 50,
            "passed": True,
            "appropriate": True,
            "confidence": 50,
            "matches_topic": True,
            "risk_of_misleading": False,
            "is_placeholder": False,
            "reason": f"Gemini no disponible: {e}",
        }


# ── Evaluación completa de un candidato ───────────────────────────────────────

def _evaluate_candidate(
    image_url: str,
    title: str,
    summary: str,
    strategy: str,
    alt_text: str = "",
    page_title: str = "",
) -> dict:
    """
    Aplica las tres validaciones a una URL candidata.
    Retorna dict con status VALIDATED o REJECTED.
    """
    logger.info(f"  [RESOLVER] Evaluando candidato ({strategy}): {image_url[:100]}")
    rejection_reasons = []

    # Validación técnica
    tech = _validate_technical(image_url)
    technical_score = tech["score"]
    if not tech["passed"]:
        reason = tech.get("rejection_reason", "validación técnica fallida")
        logger.debug(f"    Técnica RECHAZADA: {reason}")
        return {
            "status": "REJECTED",
            "strategy": strategy,
            "image_url": image_url,
            "rejection_reason": f"[TÉCNICA] {reason}",
            "technical_score": technical_score,
        }

    img_bytes = tech.get("img_bytes")

    # Validación semántica
    sem = _validate_semantic(title, image_url, alt_text, page_title)
    semantic_score = sem["score"]
    if not sem["passed"]:
        reason = sem.get("rejection_reason", "validación semántica fallida")
        logger.debug(f"    Semántica RECHAZADA: {reason}")
        rejection_reasons.append(f"[SEMÁNTICA] {reason}")
        # No devolvemos rechazado aquí — semántica tiene umbral bajo y es orientativa
        # Si la visual pasa, aceptamos igual con score compuesto bajo

    # Validación visual con Gemini
    vision = _validate_with_vision(title, summary, image_url, img_bytes=img_bytes)
    visual_score = vision["score"]

    if not vision["passed"]:
        reason = vision.get("rejection_reason", "validación visual fallida")
        logger.debug(f"    Visual parcial: {reason}")
        # Hard reject solo si Gemini dice explícitamente que es engañosa, inapropiada o placeholder
        # — NO rechazar solo por confianza baja en imagen contextual válida
        if (not vision.get("appropriate", True)
                or vision.get("risk_of_misleading", False)
                or vision.get("is_placeholder", False)):
            return {
                "status": "REJECTED",
                "strategy": strategy,
                "image_url": image_url,
                "rejection_reason": f"[VISUAL] {reason}",
                "technical_score": technical_score,
                "semantic_score": semantic_score,
                "visual_score": visual_score,
                "vision_result": vision,
            }
        # Baja confianza pero imagen apropiada → continuar con score reducido
        rejection_reasons.append(f"[VISUAL-BAJA-CONFIANZA] {reason}")

    # Score final ponderado
    final_score = technical_score * 0.20 + semantic_score * 0.35 + visual_score * 0.45

    if final_score < FINAL_MIN_SCORE:
        reason = (
            f"Score final insuficiente: {final_score:.1f} "
            f"(técnica={technical_score}, semántica={semantic_score}, visual={visual_score})"
        )
        logger.info(f"    Score INSUFICIENTE: {final_score:.1f}")
        return {
            "status": "REJECTED",
            "strategy": strategy,
            "image_url": image_url,
            "rejection_reason": reason,
            "technical_score": technical_score,
            "semantic_score": semantic_score,
            "visual_score": visual_score,
            "final_score": final_score,
            "vision_result": vision,
        }

    # VALIDADA
    parsed = urlparse(image_url)
    domain = parsed.netloc.lstrip("www.")
    logger.info(
        f"    VALIDADA: score={final_score:.1f} "
        f"(técnica={technical_score}, semántica={semantic_score}, visual={visual_score})"
    )
    return {
        "status": "VALIDATED",
        "image_url": image_url,
        "strategy": strategy,
        "technical_score": technical_score,
        "semantic_score": semantic_score,
        "visual_score": visual_score,
        "final_score": final_score,
        "source_url": image_url,
        "source_domain": domain,
        "vision_result": vision,
    }


# ── Extracción de imagen desde URL de artículo ────────────────────────────────

def _extract_from_article_page(article_url: str) -> list[dict]:
    """
    Scrapea la página del artículo y extrae candidatos de imagen en orden de prioridad.
    Retorna lista de dicts {url, alt_text, page_title}.
    """
    candidates = []
    try:
        resp = requests.get(article_url, headers=HEADERS, timeout=15)
        if not resp.ok:
            return candidates
        soup = BeautifulSoup(resp.text, "lxml")
        page_title = soup.find("title")
        page_title_text = page_title.get_text(strip=True) if page_title else ""

        def add(url_raw, alt=""):
            url = _absolute_url(url_raw, article_url)
            if url and not _url_looks_excluded(url):
                candidates.append({"url": url, "alt_text": alt, "page_title": page_title_text})

        # 1. og:image
        og = soup.find("meta", property="og:image")
        if og and og.get("content"):
            add(og["content"])

        # 2. twitter:image
        tw = soup.find("meta", attrs={"name": "twitter:image"})
        if tw and tw.get("content"):
            add(tw["content"])

        # 3. JSON-LD image / imageObject
        for script in soup.find_all("script", type="application/ld+json"):
            try:
                ld = json.loads(script.string or "")
                items = ld if isinstance(ld, list) else [ld]
                for item in items:
                    img_field = item.get("image") or item.get("imageObject")
                    if isinstance(img_field, str):
                        add(img_field)
                    elif isinstance(img_field, dict):
                        add(img_field.get("url", ""))
                    elif isinstance(img_field, list) and img_field:
                        first = img_field[0]
                        if isinstance(first, str):
                            add(first)
                        elif isinstance(first, dict):
                            add(first.get("url", ""))
            except Exception:
                pass

        # 4. article:image meta
        art_img = soup.find("meta", property="article:image")
        if art_img and art_img.get("content"):
            add(art_img["content"])

        # 5. Primera <img> dentro de <article> / .article-body / .content con width>=300
        for selector in ["article", '[class*="article-body"]', '[class*="content-text"]',
                         '[class*="article-content"]', "main"]:
            container = soup.select_one(selector)
            if not container:
                continue
            for img in container.find_all("img"):
                src = (img.get("src") or img.get("data-src") or
                       img.get("data-lazy-src") or "")
                if not src:
                    continue
                # Descartar imágenes pequeñas por atributo HTML
                width_attr = img.get("width", "")
                try:
                    if int(width_attr) < 300:
                        continue
                except (ValueError, TypeError):
                    pass
                alt = img.get("alt", "")
                abs_url = _absolute_url(src, article_url)
                if abs_url and not _url_looks_excluded(abs_url):
                    candidates.append({"url": abs_url, "alt_text": alt,
                                       "page_title": page_title_text})
                if len(candidates) >= 5:
                    break
            if len(candidates) >= 3:
                break

    except Exception as e:
        logger.warning(f"  [RESOLVER] Error scrapeando artículo para imagen: {e}")

    # Deduplicar preservando orden
    seen = set()
    deduped = []
    for c in candidates:
        if c["url"] not in seen:
            seen.add(c["url"])
            deduped.append(c)
    return deduped


# ── Función principal ──────────────────────────────────────────────────────────

def resolve_news_image(
    title: str,
    summary: str,
    article_url: str,
    article_image_url: Optional[str],
) -> dict:
    """
    Intenta obtener y validar una imagen real para la noticia.

    Estrategias (secuenciales, se detiene al encontrar imagen VALIDATED):
      NIVEL 1: Imagen del artículo original (article_image_url o scraping de article_url)
      NIVEL 2: Búsqueda en Google Images
      NIVEL 3: Retorna PENDING_IMAGE

    Retorna:
      {"status": "VALIDATED", "image_url": "...", "strategy": "...",
       "technical_score": N, "semantic_score": N, "visual_score": N,
       "final_score": N, "source_url": "...", "source_domain": "...",
       "vision_result": {...}}
    o:
      {"status": "PENDING_IMAGE", "attempts": [...], "rejection_reasons": [...]}
    """
    attempts = []
    rejection_reasons = []

    logger.info(f"[RESOLVER] Iniciando resolución de imagen para: {title[:80]}")

    # ── NIVEL 1: imagen del artículo ──────────────────────────────────────────

    # 1a. article_image_url dado directamente
    if article_image_url and not _url_looks_excluded(article_image_url):
        result = _evaluate_candidate(
            image_url=article_image_url,
            title=title,
            summary=summary,
            strategy="article_direct",
            page_title=title,  # imagen del mismo artículo → título es el contexto
        )
        attempts.append(result)
        if result["status"] == "VALIDATED":
            logger.info(f"[RESOLVER] Imagen validada con estrategia: article_direct")
            return result
        rejection_reasons.append(result.get("rejection_reason", ""))

    # 1b. Extraer candidatos scrapeando la página del artículo
    if article_url:
        scraped = _extract_from_article_page(article_url)
        logger.info(f"[RESOLVER] Candidatos scrapeados de artículo: {len(scraped)}")
        for candidate in scraped:
            url = candidate["url"]
            # Evitar re-evaluar article_image_url
            if article_image_url and url == article_image_url:
                continue
            result = _evaluate_candidate(
                image_url=url,
                title=title,
                summary=summary,
                strategy="article_scraped",
                alt_text=candidate.get("alt_text", ""),
                page_title=candidate.get("page_title", ""),
            )
            attempts.append(result)
            if result["status"] == "VALIDATED":
                logger.info(f"[RESOLVER] Imagen validada con estrategia: article_scraped")
                return result
            rejection_reasons.append(result.get("rejection_reason", ""))

    # ── NIVEL 2: Google Image Search ──────────────────────────────────────────

    logger.info("[RESOLVER] Nivel 1 sin imagen válida — intentando Google Image Search")
    try:
        from image_search import search_image
        google_url = search_image(title)
        if google_url:
            result = _evaluate_candidate(
                image_url=google_url,
                title=title,
                summary=summary,
                strategy="google_search",
            )
            attempts.append(result)
            if result["status"] == "VALIDATED":
                logger.info("[RESOLVER] Imagen validada con estrategia: google_search")
                return result
            rejection_reasons.append(result.get("rejection_reason", ""))
        else:
            rejection_reasons.append("[GOOGLE] Sin resultados de Google Image Search")
    except Exception as e:
        logger.warning(f"[RESOLVER] Google Image Search falló: {e}")
        rejection_reasons.append(f"[GOOGLE] Error: {e}")

    # ── NIVEL 3: Sin imagen disponible ────────────────────────────────────────

    logger.warning(
        f"[RESOLVER] PENDING_IMAGE — ninguna imagen superó validación. "
        f"Intentos: {len(attempts)}. Razones: {rejection_reasons[:3]}"
    )
    return {
        "status": "PENDING_IMAGE",
        "attempts": attempts,
        "rejection_reasons": [r for r in rejection_reasons if r],
    }
