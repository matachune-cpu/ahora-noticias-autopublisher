import anthropic
import logging
import base64
import requests
from dotenv import dotenv_values

logger = logging.getLogger(__name__)

_client = None


def _get_client():
    global _client
    if _client is None:
        import os
        key = os.getenv("ANTHROPIC_API_KEY") or dotenv_values(".env").get("ANTHROPIC_API_KEY")
        _client = anthropic.Anthropic(api_key=key)
    return _client


def check_watermark(image_url: str) -> bool:
    """
    Usa Claude Vision para detectar si una imagen tiene marca de agua.
    Retorna True si tiene marca de agua, False si está limpia.
    """
    try:
        resp = requests.get(image_url, timeout=10)
        resp.raise_for_status()
        img_b64 = base64.standard_b64encode(resp.content).decode("utf-8")
        ct = resp.headers.get("Content-Type", "image/jpeg").split(";")[0].strip()

        message = _get_client().messages.create(
            model="claude-haiku-4-5",
            max_tokens=10,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64", "media_type": ct, "data": img_b64},
                    },
                    {
                        "type": "text",
                        "text": "¿Esta imagen tiene marca de agua (watermark) visible de algún medio o agencia? Respondé solo SI o NO.",
                    },
                ],
            }],
        )
        answer = message.content[0].text.strip().upper()
        has_watermark = answer.startswith("SI") or answer.startswith("SÍ")
        if has_watermark:
            logger.info(f"Marca de agua detectada en: {image_url}")
        return has_watermark
    except Exception as e:
        logger.warning(f"No se pudo verificar marca de agua: {e}")
        return False


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


def rewrite_article(title: str, original_text: str, source_name: str) -> dict:
    """
    Evalúa si el artículo es publicable y, de serlo, lo reescribe.

    Retorna un dict que SIEMPRE incluye 'es_publicable' (bool).
    Si es False, el resto de los campos están vacíos y NO se debe publicar.
    Si es True, incluye: title, body_html, instagram_caption, whatsapp_text,
                         categoria, region, ig_relevancia.
    """
    try:
        message = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            tools=[{
                "name": "publicar_noticia",
                "description": "Evalúa el contenido fuente y, si es publicable, lo reescribe para todos los canales.",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "es_publicable": {
                            "type": "boolean",
                            "description": (
                                "Evaluá esto PRIMERO antes de escribir cualquier otra cosa. "
                                "Poné FALSE (y no escribas nada más en los otros campos) si el texto fuente: "
                                "1) está cortado o termina abruptamente sin punto final, "
                                "2) es una lista de números de sorteo/lotería/resultados deportivos sin editorial, "
                                "3) tiene indicios de paywall ('suscribite para leer', 'contenido exclusivo', etc.), "
                                "4) tiene menos de 4 párrafos reales de información periodística, "
                                "5) es publicidad, spam o contenido sin valor noticioso, "
                                "6) el tema es irrelevante para una audiencia argentina (loterías de México, resultados de sorteos extranjeros). "
                                "Poné TRUE solo si el texto tiene suficiente información para escribir una nota completa y coherente."
                            ),
                        },
                        "titulo": {
                            "type": "string",
                            "description": "Título nuevo, atractivo y original. Solo requerido si es_publicable=true."
                        },
                        "cuerpo_html": {
                            "type": "string",
                            "description": "Cuerpo completo del artículo en HTML con párrafos <p>. Mínimo 4 párrafos. Solo requerido si es_publicable=true."
                        },
                        "caption_instagram": {
                            "type": "string",
                            "description": "Caption para Instagram con emojis y hashtags al final. Solo requerido si es_publicable=true."
                        },
                        "texto_whatsapp": {
                            "type": "string",
                            "description": "Texto corto para WhatsApp, máximo 500 caracteres. Solo requerido si es_publicable=true."
                        },
                        "categoria": {
                            "type": "string",
                            "description": (
                                "Categoría principal: Política, Economía, Salud, Medio Ambiente, "
                                "Tecnología, Sociedad, Seguridad, Deportes, Cultura. "
                                "O el nombre del país si es internacional (Brasil, Chile, EEUU). "
                                "Solo requerido si es_publicable=true."
                            )
                        },
                        "region": {
                            "type": "string",
                            "description": (
                                "'Argentina' si el tema ocurre en Argentina, "
                                "'Latinoamerica' si ocurre en otro país de América Latina, "
                                "'Internacional' si ocurre fuera de América Latina. "
                                "Solo requerido si es_publicable=true."
                            ),
                            "enum": ["Argentina", "Latinoamerica", "Internacional"]
                        },
                        "ig_relevancia": {
                            "type": "integer",
                            "description": (
                                "Puntaje 1-10 de relevancia para audiencia argentina en Instagram. "
                                "10=máximo impacto (política, economía, escándalo, tragedia). "
                                "7-9=noticia importante del día. "
                                "4-6=interés moderado. "
                                "1-3=irrelevante o muy específico. "
                                "Solo requerido si es_publicable=true."
                            ),
                            "minimum": 1,
                            "maximum": 10
                        },
                    },
                    "required": ["es_publicable"],
                },
            }],
            tool_choice={"type": "tool", "name": "publicar_noticia"},
            messages=[{
                "role": "user",
                "content": (
                    f"Sos redactor de un medio de noticias argentino llamado Ahora Noticias.\n\n"
                    f"INSTRUCCIÓN IMPORTANTE: Primero evaluá si el texto fuente tiene suficiente "
                    f"contenido para escribir una nota periodística completa. Si no lo tiene, "
                    f"devolvé es_publicable=false y no escribas nada más.\n\n"
                    f"Si sí es publicable, reescribí completamente la noticia de {source_name} "
                    f"con tus propias palabras, en español rioplatense, de forma clara y profesional. "
                    f"NO copies frases textuales del original.\n\n"
                    f"TÍTULO ORIGINAL: {title}\n\n"
                    f"TEXTO ORIGINAL:\n{original_text[:4000]}"
                )
            }],
        )

        for block in message.content:
            if block.type == "tool_use":
                data = block.input
                es_publicable = bool(data.get("es_publicable", False))

                if not es_publicable:
                    logger.info(
                        f"  [REWRITER] Claude marcó el contenido como NO publicable: {title[:70]}"
                    )
                    return _RESULTADO_NO_PUBLICABLE

                categoria = data.get("categoria", "").strip()
                region = data.get("region", "Argentina").strip()
                ig_relevancia = int(data.get("ig_relevancia", 5))

                return {
                    "es_publicable": True,
                    "title": data.get("titulo", title),
                    "body_html": data.get("cuerpo_html", ""),
                    "instagram_caption": data.get("caption_instagram", ""),
                    "whatsapp_text": data.get("texto_whatsapp", ""),
                    "categoria": categoria,
                    "region": region,
                    "ig_relevancia": ig_relevancia,
                }

        raise ValueError("No se recibió respuesta del tool")

    except Exception as e:
        # CRÍTICO: el fallback nunca publica contenido directamente.
        # Si Claude falla, el artículo se descarta (es_publicable=False).
        # Antes el fallback publicaba original_text[:1000] sin filtros —
        # esa era la causa principal de artículos incompletos en WordPress.
        logger.error(f"Rewriter error para '{title[:60]}': {e}")
        return _RESULTADO_NO_PUBLICABLE
