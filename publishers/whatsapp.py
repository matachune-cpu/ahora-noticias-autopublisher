"""
Envía mensajes al Canal de WhatsApp usando la WhatsApp Business Cloud API.
Los canales de WhatsApp se administran como un "newsletter" — se envía
con el endpoint /messages usando el channel_id como recipient.
"""
import requests
import logging
import config

logger = logging.getLogger(__name__)

WA_API_URL = f"https://graph.facebook.com/v19.0/{config.WA_PHONE_NUMBER_ID}/messages"


def send_to_channel(text: str, wp_post_url: str = None) -> bool:
    """
    Envía una noticia al canal de WhatsApp.
    Retorna True si tuvo éxito.
    """
    try:
        # Agregar enlace al final si hay URL de WordPress
        full_text = text
        if wp_post_url:
            full_text += f"\n\n🔗 {wp_post_url}"

        headers = {
            "Authorization": f"Bearer {config.WA_API_TOKEN}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": config.WA_CHANNEL_ID,
            "type": "text",
            "text": {"preview_url": True, "body": full_text},
        }
        resp = requests.post(WA_API_URL, json=payload, headers=headers, timeout=20)
        resp.raise_for_status()
        logger.info(f"WhatsApp: mensaje enviado al canal")
        return True
    except Exception as e:
        logger.error(f"WhatsApp send error: {e}")
        return False
