import json
import logging
import os
import time
import requests
from io import BytesIO
from PIL import Image
from dotenv import dotenv_values

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

_client = None

# ── Presupuesto diario + circuit breaker para Gemini ─────────────────────────
# Con tier gratuito (20 req/día) esto es crítico para no agotar la cuota.

_QUOTA_FILE = ".gemini_daily_quota.json"
_COOLDOWN_MINUTES = 180  # tiempo de espera tras un 429 (3 horas)


def _today_utc() -> str:
    from datetime import datetime
    return datetime.utcnow().strftime("%Y-%m-%d")


def _load_quota() -> dict:
    today = _today_utc()
    try:
        with open(_QUOTA_FILE) as f:
            data = json.load(f)
        if data.get("date") != today:
            return {"date": today, "count": 0, "cooldown_until": None}
        return data
    except Exception:
        return {"date": today, "count": 0, "cooldown_until": None}


def _save_quota(data: dict):
    try:
        with open(_QUOTA_FILE, "w") as f:
            json.dump(data, f)
    except Exception:
        pass


def _daily_limit() -> int:
    try:
        return int(os.getenv("GEMINI_DAILY_LIMIT", "18"))
    except Exception:
        return 18


def _can_call_gemini() -> tuple:
    """Retorna (puede_llamar: bool, motivo_si_no: str)."""
    q = _load_quota()

    cooldown_until = q.get("cooldown_until")
    if cooldown_until:
        remaining = cooldown_until - time.time()
        if remaining > 0:
            return False, f"429 cooldown — {int(remaining / 60)} min restantes"

    limit = _daily_limit()
    if q["count"] >= limit:
        return False, f"Cuota diaria agotada: {q['count']}/{limit} llamadas hoy"

    return True, ""


def _record_gemini_call():
    q = _load_quota()
    q["count"] = q.get("count", 0) + 1
    _save_quota(q)
    logger.debug(f"[GEMINI] Llamada registrada: {q['count']}/{_daily_limit()} hoy")


def _set_gemini_cooldown():
    q = _load_quota()
    q["cooldown_until"] = time.time() + (_COOLDOWN_MINUTES * 60)
    _save_quota(q)
    logger.warning(
        f"[GEMINI] Circuit breaker activado — cooldown de {_COOLDOWN_MINUTES} min "
        f"(hasta que se reinicie el contador o pasen {_COOLDOWN_MINUTES} min)"
    )


def _is_quota_error(exc: Exception) -> bool:
    msg = str(exc).lower()
    return any(k in msg for k in ("429", "resource_exhausted", "quota", "rate limit"))


def _get_client():
    global _client
    if _client is None:
        import os
        key = os.getenv("GEMINI_API_KEY") or dotenv_values(".env").get("GEMINI_API_KEY")
        _client = genai.Client(api_key=key)
    return _client


MODEL = "gemini-2.5-flash"

# Resultado vacío que main.py interpreta como "no publicar"
_RESULTADO_NO_PUBLICABLE = {
    "es_publicable": False,
    "title": "",
    "body_html": "",
    "instagram_caption": "",
    "whatsapp_text": "",
    "categoria": "",
    "region": "Argentina",
    "ig_relevancia": 1,
}


def check_watermark(image_url: str) -> bool:
    """
    Usa Gemini Vision para detectar si una imagen tiene marca de agua.
    Retorna True si tiene marca de agua, False si está limpia.
    Omite la llamada si la cuota diaria está agotada o hay cooldown activo.
    """
    can_call, reason = _can_call_gemini()
    if not can_call:
        logger.warning(f"[GEMINI] check_watermark omitido — {reason}")
        return False  # conservar la imagen ante la duda

    try:
        resp = requests.get(image_url, timeout=10)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content))

        _record_gemini_call()
        response = _get_client().models.generate_content(
            model=MODEL,
            contents=[
                img,
                "Does this image have a visible watermark from a news agency or media outlet? Answer only YES or NO."
            ],
        )
        answer = response.text.strip().upper()
        has_watermark = answer.startswith("YES")
        if has_watermark:
            logger.info(f"Marca de agua detectada en: {image_url}")
        return has_watermark
    except Exception as e:
        if _is_quota_error(e):
            _set_gemini_cooldown()
        logger.warning(f"No se pudo verificar marca de agua — imagen conservada: {e}")
        return False


def rewrite_article(
    title: str,
    original_text: str,
    source_name: str,
    extra_instructions: str = "",
) -> dict:
    """
    Evalua si el articulo es publicable y, de serlo, lo reescribe con Gemini.

    Retorna dict con 'es_publicable' (bool).
    Si es False, no se publica en ningun canal.
    extra_instructions: instrucciones editoriales adicionales (urgencias manuales).
    """
    can_call, reason = _can_call_gemini()
    if not can_call:
        logger.warning(f"[GEMINI] rewrite_article omitido — {reason}: {title[:60]}")
        return {**_RESULTADO_NO_PUBLICABLE, "quota_exhausted": True}

    prompt = f"""Sos redactor de un medio de noticias argentino llamado Ahora Noticias, con sede en Santiago del Estero.

INSTRUCCION IMPORTANTE: Primero evalua si el texto fuente tiene suficiente contenido para escribir una nota periodistica completa. Devuelve es_publicable=false (y los otros campos en blanco) si el texto:
1) Esta cortado o termina abruptamente sin punto final
2) Es solo una lista de numeros (sorteos, resultados sin editorial)
3) Tiene indicios de paywall ("suscribite para leer", "contenido exclusivo")
4) Tiene menos de 4 parrafos reales de informacion periodistica
5) Es publicidad, spam o sin valor noticioso
6) Es irrelevante para audiencia argentina (loterias de Mexico, sorteos extranjeros)

NOTA: El texto puede comenzar con metadata de navegacion web (links, menus). Ignoralos y evalua solo el contenido periodistico real.

CRITERIOS DE RELEVANCIA (ig_relevancia):
- NOTICIAS NACIONALES IMPORTANTES (politica nacional, economia, dolar, inflacion, elecciones, escandalo politico, desastres, crimen organizado, deportes de alto impacto como Mundial o Copa America): SIEMPRE 8-10 puntos. NUNCA se deben descartar.
- NOTICIAS DE SANTIAGO DEL ESTERO o LA BANDA (municipio, obras, eventos, cultura local): 5-8 puntos segun impacto.
- NOTICIAS INTERNACIONALES relevantes para Argentina (acuerdos FMI, Trump, vecinos): 6-8 puntos.
- Contenido menor o muy local sin impacto general: 3-5 puntos.

Si SI es publicable, reescribi completamente la noticia de {source_name} con tus propias palabras, en espanol rioplatense, de forma clara y profesional. NO copies frases textuales del original.

Campos a completar si es_publicable=true:
- titulo: titulo nuevo, atractivo y original
- cuerpo_html: cuerpo completo en HTML con parrafos <p>, minimo 4 parrafos
- caption_instagram: caption de Instagram. REGLAS: (1) Primera linea = GOLPE EMOCIONAL antes del "ver mas": dato duro, cifra concreta, nombre propio + hecho. Tiene que generar reaccion visceral — dolor, indignacion, orgullo, sorpresa. Sin rodeos. (2) 2-4 oraciones con los datos mas importantes de la nota, tono directo como habla un santiagueno. (3) Termina SIEMPRE con pregunta al lector: "¿Vos que opinas?", "¿Lo sabias?", "¿Que hace falta para que cambie esto?". (4) Maximo 5 hashtags relevantes al final. (5) NO usar frases como "Te contamos", "Enterate", "La noticia de hoy", "En nuestro portal".
- caption_facebook: caption para Facebook. REGLAS ESTRICTAS: (1) Primera linea OBLIGATORIA = gancho EMOCIONAL puro: usa dato impactante, cifra, nombre propio, verbo fuerte — genera indignacion, tristeza, sorpresa o esperanza. EVITA frases debiles como "Te contamos" o "Enterate". EJEMPLOS buenos: "Tenia 3 años y no llego a tiempo." / "El gobierno le corto la beca a 50.000 jovenes." / "Kicillof le planto cara a Milei en plena Casa Rosada." (2) 2-3 oraciones desarrollando el hecho con dato concreto. (3) Cierra con pregunta que invite a comentar o compartir. (4) Sin hashtags. (5) Maximo 450 caracteres en total.
- texto_whatsapp: texto corto maximo 500 caracteres
- categoria: UNA de estas: Politica, Economia, Salud, Medio Ambiente, Tecnologia, Sociedad, Seguridad, Deportes, Cultura. O nombre del pais si es internacional.
- region: exactamente "Argentina", "Latinoamerica" o "Internacional"
- ig_relevancia: puntaje 1-10 para audiencia argentina. 10=maximo impacto. 7-9=importante. 4-6=moderado. 1-3=irrelevante.
- es_catastrofe: true SOLO si region es "Internacional" o "Latinoamerica" Y el hecho es una catastrofe de impacto excepcional: desastre climatico (terremoto, inundacion masiva, incendio forestal a escala nacional, tsunami, huracan devastador), crisis financiera sistemica (default de un pais, colapso bancario, crash de mercados), crisis humanitaria grave (guerra con miles de desplazados, hambruna, pandemia), o evento con consecuencias directas para Argentina. Para noticias argentinas o internacionales rutinarias, siempre false.

TITULO ORIGINAL: {title}

TEXTO ORIGINAL:
{original_text[:12000]}"""

    if extra_instructions:
        prompt += f"\n\nINSTRUCCIONES EDITORIALES ADICIONALES (aplicar obligatoriamente):\n{extra_instructions}"

    try:
        _record_gemini_call()
        response = _get_client().models.generate_content(
            model=MODEL,
            contents=prompt,
            config=types.GenerateContentConfig(
                response_mime_type="application/json",
                response_schema={
                    "type": "object",
                    "properties": {
                        "es_publicable": {"type": "boolean"},
                        "titulo": {"type": "string"},
                        "cuerpo_html": {"type": "string"},
                        "caption_instagram": {"type": "string"},
                        "caption_facebook": {"type": "string"},
                        "texto_whatsapp": {"type": "string"},
                        "categoria": {"type": "string"},
                        "region": {
                            "type": "string",
                            "enum": ["Argentina", "Latinoamerica", "Internacional"],
                        },
                        "ig_relevancia": {"type": "integer"},
                        "es_catastrofe": {"type": "boolean"},
                    },
                    "required": ["es_publicable"],
                },
                temperature=0.7,
            ),
        )

        data = json.loads(response.text)
        es_publicable = bool(data.get("es_publicable", False))

        if not es_publicable:
            logger.info(f"  [GEMINI] Contenido NO publicable: {title[:70]}")
            return _RESULTADO_NO_PUBLICABLE

        titulo = data.get("titulo", "").strip()
        cuerpo = data.get("cuerpo_html", "").strip()
        if not titulo or not cuerpo:
            logger.warning(f"  [GEMINI] Respuesta incompleta — descartando: {title[:70]}")
            return _RESULTADO_NO_PUBLICABLE

        return {
            "es_publicable": True,
            "title": titulo,
            "body_html": cuerpo,
            "instagram_caption": data.get("caption_instagram", ""),
            "facebook_caption": data.get("caption_facebook", ""),
            "whatsapp_text": data.get("texto_whatsapp", ""),
            "categoria": data.get("categoria", "").strip(),
            "region": data.get("region", "Argentina").strip(),
            "ig_relevancia": int(data.get("ig_relevancia", 5)),
            "es_catastrofe": bool(data.get("es_catastrofe", False)),
        }

    except Exception as e:
        if _is_quota_error(e):
            _set_gemini_cooldown()
            logger.error(f"Rewriter error de cuota para '{title[:60]}': {e}")
            return {**_RESULTADO_NO_PUBLICABLE, "quota_exhausted": True}
        logger.error(f"Rewriter error para '{title[:60]}': {e}")
        return _RESULTADO_NO_PUBLICABLE
