# Ghost Browser

🌐 [English](README.md) | [Türkçe](README.tr.md) | [中文](README.zh-CN.md) | [Español](README.es.md) | [Русский](README.ru.md) | [Português](README.pt-BR.md)

Servicio de navegador sigiloso basado en Docker con evasión de antibot.  
Parchea el binario de Chrome usando `undetected-chromedriver`, expone automatización del navegador vía HTTP API.

## Características

- **Evasión Antibot** — Parche del binario de Chrome vía `undetected-chromedriver`
- **Emulación de Plataforma** — Suplantación de huella digital del dispositivo (navigator, WebGL, Client Hints)
- **Navegador Persistente** — Chrome permanece abierto, solicitudes rápidas por pestañas (`/fetch`)
- **HTTP API** — Endpoints FastAPI: `/fetch`, `/navigate`, `/screenshot`, `/health`, `/platforms`
- **Limpieza de Pestañas** — Las pestañas inactivas se cierran automáticamente después de 60 segundos
- **Recuperación de Fallos** — Chrome se reinicia automáticamente si falla
- **Reinicio Automático** — Chrome se reinicia después de 1 hora (gestión de memoria)
- **Autenticación Bearer Token** — Acceso API simple y seguro
- **Listo para Docker** — Despliegue fácil con Docker Compose

## Inicio Rápido

### Docker (Recomendado)

```bash
docker compose up -d

# O manualmente
docker build -t ghost-browser .
docker run -p 3000:3000 -e TOKEN=your-secret-token --shm-size=2g ghost-browser
```

### Desarrollo Local

```bash
python -m virtualenv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env

uvicorn app.main:app --host 0.0.0.0 --port 3000
```

## API

### `GET /health`

Verificación de estado del servicio y navegador.

### `GET /platforms`

Listar todos los perfiles de plataforma/dispositivo soportados.

```bash
curl http://localhost:3000/platforms
```

### `GET /platforms/{id}`

Obtener detalles de una plataforma específica.

---

### `POST /fetch` ⚡ (Recomendado)

**Navegador persistente** — Chrome permanece abierto, basado en pestañas.  
Mucho más rápido que `/navigate` ya que Chrome no se reinicia.

```bash
curl -X POST http://localhost:3000/fetch \
  -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/api", "returnType": "json", "platform": "samsung_s25"}'
```

| Campo | Tipo | Defecto | Descripción |
|-------|------|---------|-------------|
| `url` | string | — | URL objetivo (obligatorio) |
| `timeout` | int | `0` | Timeout (ms), 0 = por defecto |
| `returnType` | string | `json` | `json` \| `html` \| `text` \| `screenshot` |
| `platform` | string | `null` | ID de plataforma (ver `/platforms`) |

### `POST /navigate`

Abre una nueva instancia de Chrome por solicitud. Más lento pero aislado.

### `POST /screenshot`

Devuelve una captura PNG de la URL.

## Plataformas

| ID | Nombre | Categoría | Notas |
|----|--------|-----------|-------|
| `desktop_chrome_windows` | Windows 11 — Chrome | Escritorio | Funciona en Windows y Docker |
| `desktop_chrome_macos` | macOS Sonoma — Chrome | Escritorio | Funciona en Windows y Docker |
| `samsung_s25` | Samsung Galaxy S25 | Móvil | Solo funciona en Docker |

> **Nota:** Las plataformas móviles solo funcionan de forma confiable en Docker (Linux).

## Variables de Entorno

| Variable | Defecto | Descripción |
|----------|---------|-------------|
| `TOKEN` | `""` | Token de autenticación (vacío = sin auth) |
| `MAX_CONCURRENT` | `3` | Instancias concurrentes máximas |
| `HEADLESS` | `true` | Modo headless de Chrome |
| `PORT` | `3000` | Puerto API |
| `CHROME_VERSION` | `auto` | Versión mayor de Chrome |
| `TAB_IDLE_TIMEOUT` | `60` | Timeout de pestaña inactiva (segundos) |
| `BROWSER_MAX_AGE` | `3600` | Vida máxima de Chrome (segundos) |

## `/fetch` vs `/navigate`

| | `/fetch` ⚡ | `/navigate` |
|---|---|---|
| Inicio de Chrome | No (permanece abierto) | Nueva instancia |
| Velocidad | ~200-500ms | ~5000-15000ms |
| Memoria | Basada en pestañas | Aislada por solicitud |
| Cookies | Compartidas | Limpias cada vez |

## Licencia

MIT
