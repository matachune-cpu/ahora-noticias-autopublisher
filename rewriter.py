import json
import logging
import requests
from io import BytesIO
from PIL import Image
from dotenv import dotenv_values

from google import genai
from google.genai import types

logger = logging.getLogger(__name__)

_client = None


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
    Retorna True si tiene marca de agua, False si esta limpia.
    """
    try:
        resp = requests.get(image_url, timeout=10)
        resp.raise_for_status()
        img = Image.open(BytesIO(resp.content))

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
        logger.warning(f"No se pudo verificar marca de agua: {e}")
        return False


def rewrite_article(title: str, original_text: str, source_name: str) -> dict:
    """
    Evalua si el articulo es publicable y, de serlo, lo reescribe con Gemini.

    Retorna dict con 'es_publicable' (bool).
    Si es False, no se publica en ningun canal.
    """
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
- caption_instagram: caption con emojis y hashtags al final
- texto_whatsapp: texto corto maximo 500 caracteres
- categoria: UNA de estas: Politica, Economia, Salud, Medio Ambiente, Tecnologia, Sociedad, Seguridad, Deportes, Cultura. O nombre del pais si es internacional.
- region: exactamente "Argentina", "Latinoamerica" o "Internacional"
- ig_relevancia: puntaje 1-10 para audiencia argentina. 10=maximo impacto. 7-9=importante. 4-6=moderado. 1-3=irrelevante.

TITULO ORIGINAL: {title}

TEXTO ORIGINAL:
{original_text[:12000]}"""

    try:
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
                        "texto_whatsapp": {"type": "string"},
                        "categoria": {"type": "string"},
                        "region": {
                            "type": "string",
                            "enum": ["Argentina", "Latinoamerica", "Internacional"],
                        },
                        "ig_relevancia": {"type": "integer"},
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
            "whatsapp_text": data.get("texto_whatsapp", ""),
            "categoria": data.get("categoria", "").strip(),
            "region": data.get("region", "Argentina").strip(),
            "ig_relevancia": int(data.get("ig_relevancia", 5)),
        }

    except Exception as e:
        # Fallback NUNCA publica contenido crudo — siempre descarta.
        logger.error(f"Rewriter error para '{title[:60]}': {e}")
        return _RESULTADO_NO_PUBLICABLE
