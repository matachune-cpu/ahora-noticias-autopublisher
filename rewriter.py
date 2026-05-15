import anthropic
import logging
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


def rewrite_article(title: str, original_text: str, source_name: str) -> dict:
    """
    Returns dict with keys: title, body_html, instagram_caption, whatsapp_text
    """
    try:
        import json

        # Pedimos cada campo por separado usando tool use para evitar errores de JSON
        message = _get_client().messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            tools=[{
                "name": "publicar_noticia",
                "description": "Publica la noticia reescrita en todos los canales",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "titulo": {"type": "string", "description": "Título nuevo, atractivo y original"},
                        "cuerpo_html": {"type": "string", "description": "Cuerpo del artículo en HTML con párrafos <p>"},
                        "caption_instagram": {"type": "string", "description": "Caption para Instagram con emojis y hashtags al final"},
                        "texto_whatsapp": {"type": "string", "description": "Texto corto para WhatsApp, máximo 500 caracteres"},
                    },
                    "required": ["titulo", "cuerpo_html", "caption_instagram", "texto_whatsapp"],
                },
            }],
            tool_choice={"type": "tool", "name": "publicar_noticia"},
            messages=[{"role": "user", "content": f"""Sos redactor de un medio de noticias argentino. Reescribí completamente la siguiente noticia de {source_name} con tus propias palabras. NO copies frases textuales. Redactá de forma clara, profesional y en español rioplatense.

TÍTULO ORIGINAL: {title}

TEXTO ORIGINAL:
{original_text[:4000]}"""}],
        )

        # Extraer resultado del tool use
        for block in message.content:
            if block.type == "tool_use":
                data = block.input
                return {
                    "title": data.get("titulo", title),
                    "body_html": data.get("cuerpo_html", f"<p>{original_text[:500]}</p>"),
                    "instagram_caption": data.get("caption_instagram", ""),
                    "whatsapp_text": data.get("texto_whatsapp", ""),
                }

        raise ValueError("No se recibió respuesta del tool")

    except Exception as e:
        logger.error(f"Rewriter error: {e}")
        return {
            "title": title,
            "body_html": f"<p>{original_text[:1000]}</p>",
            "instagram_caption": f"{title}\n\n#noticias #argentina",
            "whatsapp_text": f"{title[:400]}",
        }
