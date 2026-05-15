import anthropic
import logging
import base64
import requests
from dotenv import dotenv_values

logger = logging.getLogger(__name__)

_client = None

CATEGORIAS_VALIDAS = [
    "Política", "Economía", "Salud", "Medio Ambiente", "Tecnología",
    "Sociedad", "Seguridad", "Deportes", "Cultura", "Internacional",
]

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
        return False  # si falla la verificación, usar la imagen igual


def rewrite_article(title: str, original_text: str, source_name: str) -> dict:
    """
    Reescribe el artículo y determina su categoría.
    Retorna dict con: title, body_html, instagram_caption, whatsapp_text, categoria, etiqueta
    """
    try:
        message = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            tools=[{
                "name": "publicar_noticia",
                "description": "Publica la noticia reescrita en todos los canales",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "titulo": {
                            "type": "string",
                            "description": "Título nuevo, atractivo y original"
                        },
                        "cuerpo_html": {
                            "type": "string",
                            "description": "Cuerpo del artículo en HTML con párrafos <p>"
                        },
                        "caption_instagram": {
                            "type": "string",
                            "description": "Caption para Instagram con emojis y hashtags al final"
                        },
                        "texto_whatsapp": {
                            "type": "string",
                            "description": "Texto corto para WhatsApp, máximo 500 caracteres"
                        },
                        "categoria": {
                            "type": "string",
                            "description": (
                                "Categoría principal de la noticia. Elegí UNA sola opción: "
                                "Política, Economía, Salud, Medio Ambiente, Tecnología, Sociedad, "
                                "Seguridad, Deportes, Cultura. "
                                "Si la noticia es de otro país (no Argentina) poné el nombre del país en español (ej: Brasil, Chile, EEUU). "
                                "Si es de una provincia argentina específica, poné el nombre de la provincia (ej: Córdoba, Tucumán, Santiago del Estero)."
                            )
                        },
                        "region": {
                            "type": "string",
                            "description": (
                                "Región geográfica principal de la noticia. Elegí UNA sola opción: "
                                "'Argentina' si el tema principal ocurre en Argentina, "
                                "'Latinoamerica' si ocurre en otro país de América Latina o el Caribe, "
                                "'Internacional' si ocurre fuera de América Latina."
                            ),
                            "enum": ["Argentina", "Latinoamerica", "Internacional"]
                        },
                        "ig_relevancia": {
                            "type": "integer",
                            "description": (
                                "Puntaje de 1 a 10 que indica qué tan relevante e interesante es esta noticia "
                                "para publicar en Instagram para una audiencia argentina. "
                                "10 = noticia de máximo impacto, viral, que genera debate (política nacional, economía, escándalo, tragedia, deporte de alto perfil). "
                                "7-9 = noticia importante del día, amplio interés general. "
                                "4-6 = noticia de interés moderado, nicho o local menor. "
                                "1-3 = noticia irrelevante, muy específica, técnica o de poco interés masivo. "
                                "Solo las notas con puntaje 7 o más se publicarán en Instagram."
                            ),
                            "minimum": 1,
                            "maximum": 10
                        },
                    },
                    "required": ["titulo", "cuerpo_html", "caption_instagram", "texto_whatsapp", "categoria", "region", "ig_relevancia"],
                },
            }],
            tool_choice={"type": "tool", "name": "publicar_noticia"},
            messages=[{"role": "user", "content": f"""Sos redactor de un medio de noticias argentino. Reescribí completamente la siguiente noticia de {source_name} con tus propias palabras. NO copies frases textuales. Redactá de forma clara, profesional y en español rioplatense.

TÍTULO ORIGINAL: {title}

TEXTO ORIGINAL:
{original_text[:4000]}"""}],
        )

        for block in message.content:
            if block.type == "tool_use":
                data = block.input
                categoria = data.get("categoria", "").strip()
                region = data.get("region", "Argentina").strip()
                ig_relevancia = int(data.get("ig_relevancia", 5))
                return {
                    "title": data.get("titulo", title),
                    "body_html": data.get("cuerpo_html", f"<p>{original_text[:500]}</p>"),
                    "instagram_caption": data.get("caption_instagram", ""),
                    "whatsapp_text": data.get("texto_whatsapp", ""),
                    "categoria": categoria,
                    "region": region,
                    "ig_relevancia": ig_relevancia,
                }

        raise ValueError("No se recibió respuesta del tool")

    except Exception as e:
        logger.error(f"Rewriter error: {e}")
        return {
            "title": title,
            "body_html": f"<p>{original_text[:1000]}</p>",
            "instagram_caption": f"{title}\n\n#noticias #argentina",
            "whatsapp_text": f"{title[:400]}",
            "categoria": "",
            "region": "Argentina",
            "ig_relevancia": 5,
        }
