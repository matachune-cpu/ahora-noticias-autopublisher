# News Auto-Publisher — Guía de configuración

## Requisitos previos

- Python 3.11+
- Cuenta de Meta Business Suite con app configurada
- WordPress con REST API activada y Application Password
- API Key de Anthropic (Claude)

---

## 1. Instalar dependencias

```bash
cd news-autopublisher
pip install -r requirements.txt
```

---

## 2. Configurar credenciales

Copiá el archivo de ejemplo y completá los valores:

```bash
copy .env.example .env
```

### Variables a completar en `.env`

| Variable | Cómo obtenerla |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com → API Keys |
| `WP_URL` | Tu sitio WordPress, ej: `https://tumedio.com.ar` |
| `WP_USERNAME` | Tu usuario de WordPress admin |
| `WP_APP_PASSWORD` | WP Admin → Usuarios → Tu perfil → Application Passwords |
| `META_ACCESS_TOKEN` | developers.facebook.com → Tu App → Access Token con permisos: `pages_manage_posts`, `instagram_basic`, `instagram_content_publish` |
| `FB_PAGE_ID` | ID numérico de tu Página de Facebook (se ve en Configuración de la Página) |
| `IG_ACCOUNT_ID` | ID de tu cuenta Instagram Business (Meta Business Suite → Configuración) |
| `WA_PHONE_NUMBER_ID` | Meta Business Suite → WhatsApp → Phone Number ID |
| `WA_CHANNEL_ID` | ID del canal de WhatsApp (formato numérico) |
| `WA_API_TOKEN` | Mismo token Meta con permiso `whatsapp_business_messaging` |

---

## 3. Crear plantilla del flyer

```bash
python create_template.py
```

Esto crea `templates/flyer_base.png` con un diseño básico.
**Reemplazala con tu diseño en Canva o Photoshop** (1080×1080 px).

El sistema respeta las bandas superior e inferior de la plantilla y superpone:
- La foto de la noticia como fondo semitransparente
- El título de la noticia en blanco
- El nombre del medio como fuente

---

## 4. Instagram: imagen pública

Meta Graph API requiere que la imagen del flyer esté en una URL pública.
Opciones:

**Opción A (recomendada):** Usar la imagen subida a WordPress como URL pública.
El sistema ya sube el flyer a WordPress — configurar en `publishers/instagram.py`:
```python
# En main.py, obtener la URL de WordPress media y pasarla:
public_image_url = wp_media_url  # URL devuelta por wordpress.upload_image()
```

**Opción B:** Usar imgbb.com (gratuito, 32MB max):
1. Crear cuenta en imgbb.com → obtener API Key
2. Poner la key en `publishers/instagram.py`: `IMGBB_API_KEY = "tu-key"`

---

## 5. Correr el sistema

```bash
python main.py
```

El sistema:
1. Corre inmediatamente al iniciar
2. Repite cada 30 minutos (configurable en `.env` con `CHECK_INTERVAL_MINUTES`)
3. Guarda logs en `autopublisher.log`
4. Evita republicar la misma URL (base de datos `published_articles.db`)

---

## 6. Correr como servicio de Windows (opcional)

Para que corra en segundo plano al iniciar Windows:

```bash
pip install pywin32
python -m win32serviceutil install news_autopublisher
```

O usar **Task Scheduler** de Windows:
- Acción: `python main.py`
- Directorio: ruta del proyecto
- Disparador: Al iniciar el sistema

---

## Notas importantes

- **WhatsApp Channels API:** Los canales de WhatsApp usan el mismo endpoint de Cloud API.
  El `WA_CHANNEL_ID` es el ID del canal (encontrarlo en WhatsApp → Canal → Configuración).
- **Límite de publicaciones en Instagram:** Meta limita a 50 posts/día por cuenta.
- **Dentro de 60 días:** El sistema tiene toda la estructura lista para agregar revisión
  humana. Bastará con cambiar `status: "publish"` a `status: "draft"` en `publishers/wordpress.py`
  y agregar una cola de aprobación.
