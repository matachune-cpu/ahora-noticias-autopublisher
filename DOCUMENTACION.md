# 📰 Ahora Noticias — Autopublicador Inteligente
### Documentación técnica del sistema de publicación automática de noticias

> **Versión:** 1.0 · **Medio:** [ahoranoticias.com.ar](https://ahoranoticias.com.ar) · **Operativo desde:** Mayo 2026

---

## ¿Qué hace este sistema?

El **Autopublicador de Ahora Noticias** es un sistema de software que:

1. **Monitorea** los principales diarios argentinos cada 30 minutos, las 24 horas del día, los 7 días de la semana
2. **Reescribe** cada noticia con Inteligencia Artificial en español rioplatense, con identidad propia del medio
3. **Publica automáticamente** en WordPress (sitio web), Facebook y genera flyers para Instagram
4. **Filtra** las noticias más relevantes para la audiencia argentina y las **distribuye estratégicamente** en Instagram a lo largo del día
5. **Funciona sin supervisión humana** y sin necesidad de tener la computadora encendida, corriendo en servidores en la nube

---

## 🗺️ Arquitectura general del sistema

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                        AHORA NOTICIAS — AUTOPUBLICADOR                      │
│                                                                             │
│   FUENTES                  PROCESAMIENTO                  DESTINOS          │
│   ───────                  ─────────────                  ────────          │
│                                                                             │
│  ┌──────────┐             ┌─────────────┐            ┌──────────────┐      │
│  │ Infobae  │──RSS──────▶│             │───────────▶│  WordPress   │      │
│  └──────────┘            │   Scraper   │            │  (sitio web) │      │
│  ┌──────────┐            │             │            └──────────────┘      │
│  │ Página12 │──scraping─▶│  Extractor  │                                   │
│  └──────────┘            │  de texto   │            ┌──────────────┐      │
│  ┌──────────┐            │  e imágenes │───────────▶│   Facebook   │      │
│  │ElLiberal │──scraping─▶│             │            │  (link post) │      │
│  └──────────┘            └──────┬──────┘            └──────────────┘      │
│  ┌──────────┐                   │                                          │
│  │ Cadena 3 │──scraping─────────┘            ┌──────────────┐             │
│  └──────────┘                                │  Instagram   │             │
│                            ┌──────────────┐  │  (flyer con  │             │
│                            │    Claude    │  │   diseño)    │             │
│                            │  (IA Anthr.)│─▶└──────────────┘             │
│                            │             │                                 │
│                            │ • Reescribe │  ┌──────────────┐             │
│                            │ • Clasifica │  │  Base de     │             │
│                            │ • Puntúa    │─▶│  datos SQLite│             │
│                            └─────────────┘  └──────────────┘             │
│                                                                             │
│   INFRAESTRUCTURA: GitHub Actions (Ubuntu) · cron-job.org (disparador)     │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## 🔄 Flujo completo paso a paso

```
┌────────────────────────────────────────────────────────────────────────────┐
│  cron-job.org dispara cada 30 min → GitHub Actions se activa               │
└───────────────────────────────┬────────────────────────────────────────────┘
                                │
                    ┌───────────▼───────────┐
                    │  Para cada fuente de  │
                    │  noticias configurada │
                    └───────────┬───────────┘
                                │
              ┌─────────────────▼──────────────────┐
              │  1. OBTENER NOTICIAS                │
              │  • RSS (Infobae)                    │
              │  • Scraping de portada (el resto)   │
              │  → Lista de URLs nuevas             │
              └─────────────────┬──────────────────┘
                                │
              ┌─────────────────▼──────────────────┐
              │  2. FILTRAR YA PUBLICADAS           │
              │  • Consulta SQLite por URL exacta   │
              │  • Si ya existe → saltar            │
              └─────────────────┬──────────────────┘
                                │
              ┌─────────────────▼──────────────────┐
              │  3. EXTRAER CONTENIDO               │
              │  • Descarga HTML del artículo       │
              │  • Extrae texto (article, main, p)  │
              │  • Extrae imagen (og:image primero) │
              └─────────────────┬──────────────────┘
                                │
              ┌─────────────────▼──────────────────┐
              │  3b. DEDUPLICACIÓN SEMÁNTICA        │
              │  Compara el título reescrito con    │
              │  los últimas 12h de publicaciones   │
              │  usando similitud Jaccard sobre     │
              │  palabras clave (umbral: 38%)       │
              │  • Mismo tema → marcar URL "vista"  │
              │    y saltar (no publica nada)       │
              │  • Funciona ENTRE fuentes: si       │
              │    Infobae cubrió el tema, Página   │
              │    12 no lo repite en el mismo ciclo│
              └─────────────────┬──────────────────┘
              ┌─────────────────▼──────────────────┐
              │  4. INTELIGENCIA ARTIFICIAL         │
              │  Claude reescribe completamente:    │
              │  • Título atractivo y original      │
              │  • Cuerpo en español rioplatense    │
              │  • Caption para Instagram           │
              │  • Texto para WhatsApp              │
              │  • Categoría temática               │
              │  • Región geográfica                │
              │  • Score de relevancia IG (1-10)   │
              └─────────────────┬──────────────────┘
                                │
              ┌─────────────────▼──────────────────┐
              │  5. DETECCIÓN DE MARCA DE AGUA      │
              │  Claude Vision analiza la imagen    │
              │  • ¿Tiene watermark? → descartar    │
              │  • Sin watermark → usar             │
              └─────────────────┬──────────────────┘
                                │
                    ┌───────────▼──────────┐
                    │  Ordenar por región  │
                    │  Argentina primero   │
                    │  Latinoamérica seg.  │
                    │  Internacional últ.  │
                    └───────────┬──────────┘
                                │
          ┌─────────────────────┼──────────────────────┐
          │                     │                      │
┌─────────▼──────┐   ┌──────────▼────────┐   ┌────────▼────────┐
│  WORDPRESS     │   │  FACEBOOK         │   │  INSTAGRAM COLA │
│                │   │                   │   │                 │
│ • Sube foto    │   │ • Post con link   │   │ ¿Score >= 7?    │
│   original     │   │   al artículo WP  │   │                 │
│ • Crea post    │   │ • Imagen tomada   │   │ SÍ → generar    │
│   con imagen   │   │   de Open Graph   │   │ flyer diseñado  │
│   destacada    │   │   de WP           │   │ + subir a WP    │
│                │   │                   │   │ + guardar en    │
│ Resultado:     │   │ Resultado:        │   │ ig_queue DB     │
│ URL del post   │   │ Post ID FB        │   │                 │
└────────────────┘   └───────────────────┘   │ NO → omitir IG  │
                                             └─────────────────┘
                                                      │
                                          ┌───────────▼──────────────┐
                                          │  ¿Estamos en ventana     │
                                          │  horaria activa?         │
                                          │                          │
                                          │  6:00–9:00   ✓          │
                                          │  12:00–15:00 ✓          │
                                          │  21:00–00:00 ✓          │
                                          │                          │
                                          │  Otro horario → esperar  │
                                          └───────────┬──────────────┘
                                                      │ (si es ventana activa)
                                          ┌───────────▼──────────────┐
                                          │  Publicar hasta 2 posts  │
                                          │  de la cola (más         │
                                          │  relevantes primero)     │
                                          │  Máx. 50 posts/día       │
                                          └──────────────────────────┘
```

---

## 🧩 Módulos del sistema

### `scraper.py` — Obtención de noticias

Responsable de obtener las noticias de cada fuente. Usa dos estrategias:

| Estrategia | Fuente | Cómo funciona |
|-----------|--------|---------------|
| **RSS** | Infobae | Lee el feed XML directamente → obtiene títulos, resúmenes y URLs |
| **Web scraping** | Página 12, El Liberal, Cadena 3 | Descarga la portada del diario y extrae los links de artículos según un selector CSS específico de cada sitio |

Una vez obtenidas las URLs, para **cada artículo** el módulo:
- Descarga el HTML completo de la nota
- Elimina publicidades, menús, pies de página
- Extrae el texto de los párrafos del cuerpo de la nota
- Busca la imagen principal (prioriza la etiqueta `og:image`)

---

### `rewriter.py` — Inteligencia Artificial con Claude

El cerebro del sistema. Usa la API de **Claude Sonnet** de Anthropic con la función **Tool Use** para garantizar que la respuesta sea siempre estructurada (sin errores de formato).

**Entrada:** título original + texto completo de la nota + nombre del medio

**Salida garantizada en formato estructurado:**

```
┌─────────────────────────────────────────────────────────────────┐
│  CAMPOS QUE DEVUELVE CLAUDE PARA CADA NOTICIA                   │
├──────────────────────┬──────────────────────────────────────────┤
│  titulo              │ Título nuevo, atractivo y original       │
│  cuerpo_html         │ Artículo reescrito en HTML con <p>       │
│  caption_instagram   │ Texto para IG con emojis y hashtags      │
│  texto_whatsapp      │ Versión corta ≤ 500 caracteres           │
│  categoria           │ Política / Economía / Salud / etc.       │
│                      │ o nombre de país / provincia             │
│  region              │ Argentina / Latinoamerica / Internacional│
│  ig_relevancia       │ Puntaje 1 a 10 para filtro Instagram     │
└──────────────────────┴──────────────────────────────────────────┘
```

El módulo también incluye **detección de marcas de agua** usando **Claude Haiku con visión**: descarga la imagen, la convierte a base64 y le pregunta al modelo si tiene watermark visible. Si la respuesta es "SÍ", la imagen se descarta y el artículo se publica sin foto.

---

### `flyer_generator.py` — Diseño de flyers para Instagram

Genera imágenes de **1080 × 1350 px** (formato portrait de Instagram) con Pillow (Python Imaging Library).

```
┌─────────────────────────────────────┐  ▲
│                                     │  │
│         FOTO DEL ARTÍCULO           │  │ 770 px
│         (recortada y centrada)      │  │ (57% del alto)
│  ┌─────────────┐                    │  │
│  │  CATEGORÍA  │ ← etiqueta roja    │  │
│  └─────────────┘   pill redondeada  │  │
│                                     │  ▼
├─────────────────────────────────────┤  ← Línea roja 12px
│                                     │  ▲
│                                     │  │
│   TÍTULO DE LA NOTICIA              │  │ Zona de texto
│   EN MAYÚSCULAS                     │  │ Open Sans Bold
│   CENTRADO Y BALANCEADO             │  │ 48px
│                                     │  │
│                                     │  ▼
├─────────────────────────────────────┤
│         🔴 Ahora Noticias           │  Logo centrado
└─────────────────────────────────────┘  180px de zona
  ←──────── 1080 px ────────────────→
```

**Características del diseño:**
- La foto se escala y recorta automáticamente para llenar exactamente el área sin deformarse
- La etiqueta de categoría usa una píldora roja con bordes redondeados y texto perfectamente centrado (corrigiendo el offset de baseline de PIL)
- El título se parte en líneas respetando el ancho disponible y se redistribuye si la última línea queda muy corta
- Si no hay imagen disponible, se usa un fondo gris neutro

---

### `database.py` — Persistencia con SQLite

Dos tablas principales:

**`articles`** — registro de todo lo publicado (y temas vistos/descartados)
```
url_hash │ title │ source │ wp_post_id │ fb_post_id │ ig_post_id │ wa_sent │ published_at
```
> Los artículos descartados por deduplicación también quedan aquí (sin IDs de post), para no reprocesarlos en ciclos futuros.

**`ig_queue`** — cola de publicación para Instagram
```
url_hash │ title │ ig_caption │ flyer_public_url │ relevance_score │ queued_at │ posted_at │ ig_post_id
```

La DB es un archivo `published_articles.db` que viaja dentro del repositorio de GitHub, y se actualiza en cada ejecución de GitHub Actions mediante un commit automático.

---

### `publishers/` — Conectores con plataformas

#### WordPress (`wordpress.py`)
- Usa la **WordPress REST API** con autenticación por **Application Password**
- Sube la foto original como imagen destacada del post
- Crea el post con el HTML generado por Claude

#### Facebook (`facebook.py`)
- Usa la **Meta Graph API v19.0**
- Publica un **link post** apuntando al artículo de WordPress
- Facebook obtiene automáticamente la imagen de la etiqueta `og:image` del sitio

#### Instagram (`instagram.py`)
- Usa la **Meta Graph API Content Publishing**
- Proceso en 3 pasos: crear container → verificar estado → publicar
- La imagen debe estar en una URL pública: se usa WordPress como CDN

---

## 📅 Sistema de cola inteligente para Instagram

Este es el módulo más sofisticado del sistema. A diferencia de WordPress y Facebook (donde todo se publica de inmediato), Instagram tiene un proceso de dos etapas.

### Etapa 1: Filtrado por relevancia

Cuando Claude analiza una noticia, le asigna un **score de relevancia de 1 a 10** específico para Instagram:

```
SCORE  TIPO DE NOTICIA                          ¿VA A IG?
─────  ─────────────────────────────────────   ─────────
 10    Noticia de máximo impacto nacional         ✅ Sí
        (crisis económica, política mayor,
         escándalo, catástrofe, mundial)

  9    Noticia importante del día                 ✅ Sí
        (declaraciones relevantes, deporte
         de alto perfil, salud pública)

  8    Noticia con amplio interés general         ✅ Sí
        (economía cotidiana, seguridad,
         cultura popular)

  7    Noticia de interés medio-alto              ✅ Sí
        (política provincial, tecnología,
         medio ambiente relevante)

  6    Interés moderado                           ❌ No
  5    Interés normal                             ❌ No
  4    Nicho específico                           ❌ No
  3    Interés local menor                        ❌ No
  2    Técnica o especializada                    ❌ No
  1    Muy poco interés masivo                    ❌ No
```

**Umbral mínimo: 7 puntos.** Solo las noticias con score ≥ 7 generan flyer y entran a la cola.

### Etapa 2: Publicación en ventanas horarias

Los artículos en cola no se publican de inmediato. El sistema espera a estar dentro de una **ventana horaria de alto engagement**:

```
HORARIO ARGENTINA        VENTANA        AUDIENCIA OBJETIVO
────────────────────     ───────        ──────────────────
  6:00 → 9:00 AM     🌅 Mañana        Usuarios despertando,
                                        revisando noticias
                                        del día

 12:00 → 15:00 PM    ☀️ Mediodía      Pausa del almuerzo,
                                        pico de uso móvil

 21:00 → 00:00       🌙 Noche         Prime time de redes,
                                        mayor tiempo libre
```

**Por cada ciclo de 30 minutos dentro de una ventana**, el sistema publica hasta **2 posts**, comenzando siempre por los de mayor puntaje de relevancia.

### Límites de la API de Meta

```
Límite oficial Meta Graph API:     50 posts/día
Máximo real del sistema:           36 posts/día
(3 ventanas × 6 ciclos × 2 posts)

                  Margen de seguridad: 28%
```

---

## ☁️ Infraestructura y automatización

El sistema corre completamente en la nube, sin necesidad de servidor propio ni computadora encendida.

```
┌────────────────────────────────────────────────────────────────────┐
│                    CADENA DE AUTOMATIZACIÓN                        │
│                                                                    │
│  ┌─────────────┐     HTTP POST      ┌────────────────────────┐    │
│  │ cron-job.org│ ─────────────────▶ │    GitHub Actions API  │    │
│  │             │  cada 30 minutos   │  /dispatches endpoint  │    │
│  │ (servicio   │  las 24 horas      └──────────┬─────────────┘    │
│  │  gratuito)  │                               │                  │
│  └─────────────┘                    ┌──────────▼─────────────┐    │
│                                     │   Workflow de GitHub   │    │
│                                     │   Actions (Ubuntu)     │    │
│                                     │                        │    │
│                                     │  1. Clonar repositorio │    │
│                                     │  2. Instalar Python    │    │
│                                     │  3. Crear .env desde   │    │
│                                     │     GitHub Secrets     │    │
│                                     │  4. Ejecutar ciclo     │    │
│                                     │  5. Commitear DB       │    │
│                                     │  6. Push al repo       │    │
│                                     │                        │    │
│                                     │  Timeout: 12 minutos   │    │
│                                     └────────────────────────┘    │
└────────────────────────────────────────────────────────────────────┘
```

### ¿Por qué cron-job.org en lugar del schedule nativo de GitHub?

GitHub pausa automáticamente los workflows programados en repositorios con poca actividad. **cron-job.org** es un servicio externo gratuito que dispara el workflow vía la API de GitHub cada 30 minutos, garantizando la ejecución continua.

### Persistencia de la base de datos

Cada vez que GitHub Actions termina un ciclo, hace un **commit automático** de la base de datos SQLite al repositorio:

```
git add published_articles.db
git commit -m "DB actualizada [skip ci]"
git push
```

El tag `[skip ci]` evita que este commit dispare un nuevo workflow, previniendo un loop infinito.

---

## 🔐 Credenciales y configuración

Todas las claves sensibles se almacenan como **GitHub Secrets** (nunca en el código fuente):

| Secret | Servicio | Para qué se usa |
|--------|---------|-----------------|
| `ANTHROPIC_API_KEY` | Anthropic / Claude | Reescritura de artículos + detección de watermarks |
| `WP_URL` | WordPress | URL base del sitio (`https://ahoranoticias.com.ar`) |
| `WP_USERNAME` | WordPress | Usuario del panel de administración |
| `WP_APP_PASSWORD` | WordPress | Contraseña de aplicación (diferente a la contraseña normal) |
| `META_ACCESS_TOKEN` | Meta / Facebook | Token de página para publicar en FB e IG |
| `FB_PAGE_ID` | Facebook | ID de la página de Ahora Noticias |
| `IG_ACCOUNT_ID` | Instagram | ID de la cuenta business de Instagram |

En cada ejecución, GitHub Actions reconstruye el archivo `.env` desde estos secrets antes de ejecutar el script.

---

## 🛠️ Stack tecnológico

```
CAPA                    TECNOLOGÍA              VERSIÓN / SERVICIO
────────────────────    ─────────────────────   ──────────────────
Lenguaje                Python                  3.11
IA / LLM                Claude Sonnet           claude-sonnet-4-6
IA Vision               Claude Haiku            claude-haiku-4-5
Scraping web            BeautifulSoup + lxml    —
Feeds RSS               feedparser              —
Imágenes                Pillow (PIL)            —
HTTP                    requests                —
Programación tareas     schedule                —
Base de datos           SQLite 3                —
CMS / Web               WordPress REST API      —
Redes sociales          Meta Graph API          v19.0
Fuente tipográfica      Open Sans Bold          Google Fonts
CI/CD                   GitHub Actions          Ubuntu latest
Disparador externo      cron-job.org            Gratuito
```

---

## 📁 Estructura del repositorio

```
ahora-noticias-autopublisher/
│
├── main.py                    # Orquestador principal
├── config.py                  # Configuración y fuentes de noticias
├── database.py                # Manejo de SQLite (artículos + cola IG)
├── scraper.py                 # Obtención y extracción de noticias
├── rewriter.py                # Reescritura con Claude IA
├── flyer_generator.py         # Generación de imágenes para Instagram
├── run_once.py                # Punto de entrada para GitHub Actions
│
├── publishers/
│   ├── wordpress.py           # Publicador en WordPress
│   ├── facebook.py            # Publicador en Facebook
│   ├── instagram.py           # Publicador en Instagram
│   └── whatsapp.py            # Generador de texto para WhatsApp
│
├── templates/
│   └── fonts/
│       └── OpenSans-Bold.ttf  # Fuente para los flyers
│
├── .github/
│   └── workflows/
│       └── autopublish.yml    # Workflow de GitHub Actions
│
├── published_articles.db      # Base de datos SQLite (versionada en git)
├── requirements.txt           # Dependencias Python
└── DOCUMENTACION.md           # Este documento
```

---

## 📊 Métricas operativas del sistema

| Métrica | Valor |
|---------|-------|
| Frecuencia de chequeo | Cada 30 minutos |
| Artículos revisados por ciclo | Hasta 25 (entre todas las fuentes) |
| Tiempo promedio por ciclo | 4-8 minutos |
| Timeout máximo por ciclo | 12 minutos |
| Posts WordPress/Facebook | Inmediatos, sin límite artificial |
| Umbral de relevancia para IG | Score ≥ 7/10 |
| Posts Instagram por ventana activa | Hasta 2 cada 30 min |
| Ventanas horarias IG | 3 por día (mañana, mediodía, noche) |
| Límite diario Instagram | 50 (API Meta) · ~36 real del sistema |
| Costo de infraestructura | $0 (GitHub Actions en repo público) |

---

## 🔍 Decisiones de diseño destacadas

### ¿Cómo funciona la deduplicación semántica?

El sistema no puede detectar duplicados solo por URL (diferentes diarios tienen URLs diferentes para la misma noticia). Por eso usa **similitud de Jaccard** sobre palabras clave:

1. Al inicio de cada ciclo, carga todos los títulos publicados en las **últimas 12 horas**
2. Por cada artículo nuevo, extrae sus **palabras clave** (sin artículos, preposiciones ni palabras cortas)
3. Calcula qué porcentaje de palabras comparten el título nuevo y cada título reciente
4. Si la superposición supera el **38%** → lo considera el mismo tema y lo descarta

```
Ejemplo:
  Infobae publica: "Milei anunció nueva rebaja en retenciones al agro"
  Palabras clave: {milei, anuncio, nueva, rebaja, retenciones, agro}

  Página 12 cubre: "El gobierno eliminó retenciones para el sector agrario"
  Palabras clave: {gobierno, elimino, retenciones, sector, agrario}

  Intersección: {retenciones} → 1 palabra
  Unión: 10 palabras → Jaccard = 0.10 → NO detectado (diferente enfoque)

  Cadena 3 cubre: "Milei bajó retenciones agropecuarias tras presión del campo"
  Palabras clave: {milei, bajo, retenciones, agropecuarias, presion, campo}

  Intersección con Infobae: {milei, retenciones} → 2 palabras
  Unión: 10 → Jaccard = 0.20 → NO detectado (límite borderline)

  → El umbral de 0.38 está calibrado para evitar falsos positivos.
    Para forzar una detección se necesitan 3+ palabras clave comunes.
```

La lista se actualiza **en tiempo real dentro del ciclo**: si Infobae publica primero el tema A, cuando se procesa Página 12 ese mismo tema ya está en la lista de comparación.

### ¿Por qué no publicar todo en Instagram inmediatamente?

Tres razones:
1. **Calidad sobre cantidad**: No toda noticia merece presencia en IG. La IA filtra para que solo llegue contenido con alto potencial de engagement.
2. **Algoritmo de Instagram**: Publicar en horarios de alta audiencia maximiza el alcance orgánico.
3. **Límite de la API**: Meta permite 50 posts/día. Al distribuir en ventanas, el sistema nunca llega al límite.

### ¿Por qué WordPress como CDN para Instagram?

La API de Instagram requiere que las imágenes estén en una **URL pública y accesible**. En lugar de pagar un servicio de hosting de imágenes externo, el sistema usa la biblioteca de medios de WordPress (que ya está pago) para alojar temporalmente los flyers y obtener su URL pública.

### ¿Por qué SQLite en lugar de una base de datos en la nube?

Simplicidad y costo cero. SQLite es un archivo único que se incluye directamente en el repositorio de GitHub. Cada ejecución lo lee, lo modifica y lo vuelve a subir. Para el volumen de este sistema (cientos de artículos, no millones) es más que suficiente.

### ¿Por qué reescribir las noticias en lugar de copiarlas?

- **Legal**: copiar textualmente sin licencia viola derechos de autor
- **SEO**: Google penaliza el contenido duplicado
- **Identidad editorial**: el medio desarrolla su propia voz y estilo
- **Valor agregado**: Claude adapta el tono, la estructura y el enfoque

---

## 📡 Fuentes de noticias configuradas

| Medio | Método | Prioridad | Notas por ciclo | Observaciones |
|-------|--------|-----------|-----------------|---------------|
| **Infobae** | RSS | 🔴 Alta | Hasta 8 | Feed RSS nativo disponible |
| **Página 12** | Scraping | 🔴 Alta | Hasta 8 | Selector: links del año actual |
| **El Liberal** | Scraping | 🟡 Fija | Hasta 5 | Cobertura Santiago del Estero — siempre incluido |
| **Cadena 3** | Scraping | 🟢 Complementaria | Hasta 4 | Cobertura nacional desde Córdoba |

**Prioridad geográfica de publicación:** dentro de cada ciclo, los artículos se ordenan así:

```
1° 🇦🇷 Argentina
2° 🌎 Latinoamérica
3° 🌍 Internacional
```

---

*Documento generado en Mayo 2026 · Sistema desarrollado para Ahora Noticias · ahoranoticias.com.ar*
