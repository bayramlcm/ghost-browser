# Ghost Browser

🌐 [English](README.md) | [Türkçe](README.tr.md) | [中文](README.zh-CN.md) | [Español](README.es.md) | [Русский](README.ru.md) | [Português](README.pt-BR.md)

Docker-based stealth browser service with antibot bypass.  
Patches Chrome binary using `undetected-chromedriver`, exposes browser automation via HTTP API.

## Features

- **Antibot Bypass** — Chrome binary patch via `undetected-chromedriver`
- **Persistent Browser** — Chrome stays open, tab-based fast requests (`/fetch`)
- **HTTP API** — FastAPI endpoints: `/fetch`, `/navigate`, `/screenshot`, `/health`
- **Idle Tab Cleanup** — Idle tabs auto-close after 60 seconds
- **Crash Recovery** — Chrome auto-restarts on crash
- **Auto Restart** — Chrome restarts after 1 hour (memory management)
- **Bearer Token Auth** — Simple and secure API access
- **Docker Ready** — Easy deploy via Coolify / Docker Compose

## Quick Start

### Docker (Recommended)

```bash
docker compose up -d

# Or manually
docker build -t ghost-browser .
docker run -p 3000:3000 -e TOKEN=your-secret-token --shm-size=2g ghost-browser
```

### Local Development

```bash
python -m virtualenv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env

uvicorn app.main:app --host 0.0.0.0 --port 3000
```

## API

### `GET /health`

Service and browser status check.

```bash
curl http://localhost:3000/health
```

```json
{
  "status": "ok",
  "version": "1.0.0",
  "max_concurrent": 3,
  "headless": true,
  "browser": {
    "alive": true,
    "uptime": 3600,
    "request_count": 42,
    "active_tabs": 0,
    "idle_tabs": 1,
    "total_tabs": 2
  }
}
```

---

### `POST /fetch` ⚡ (Recommended)

**Persistent browser** — Chrome stays open, tab-based.  
Much faster than `/navigate` since Chrome doesn't restart.

```bash
curl -X POST http://localhost:3000/fetch \
  -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://jsonplaceholder.typicode.com/todos/1", "returnType": "json"}'
```

**Request Body:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | string | — | Target URL (required) |
| `timeout` | int | `0` | Timeout (ms), 0 = config default |
| `returnType` | string | `json` | `json` \| `html` \| `text` \| `screenshot` |

**Response:**

```json
{
  "success": true,
  "url": "https://jsonplaceholder.typicode.com/todos/1",
  "statusCode": 200,
  "data": { "userId": 1, "id": 1, "title": "...", "completed": false },
  "cookies": [],
  "timing": { "total": 350, "challenge": 280 }
}
```

**Persistent Browser Behavior:**
- First request: Chrome already open, opens new tab (~300ms)
- Subsequent requests: Reuses idle tab (~200ms)
- Idle tabs auto-close after 60 seconds
- Chrome auto-restarts after 1 hour (memory management)
- Chrome auto-recovers from crashes

---

### `POST /navigate`

Opens a new Chrome instance per request. Slower but isolated.

```bash
curl -X POST http://localhost:3000/navigate \
  -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "returnType": "json"}'
```

**Request Body:**

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `url` | string | — | Target URL (required) |
| `waitFor` | string | `networkidle` | `networkidle` \| `selector` \| `timeout` |
| `waitSelector` | string | `null` | CSS selector (if `waitFor=selector`) |
| `timeout` | int | `0` | Timeout (ms), 0 = config default |
| `returnType` | string | `json` | `json` \| `html` \| `text` \| `screenshot` |

---

### `POST /screenshot`

Returns a PNG screenshot of the URL.

```bash
curl -X POST http://localhost:3000/screenshot \
  -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}' \
  --output screenshot.png
```

---

### Authentication

If the `TOKEN` environment variable is set, all endpoints require a Bearer token:

```
Authorization: Bearer <TOKEN>
```

Use the 🔒 **Authorize** button in Swagger UI (`/docs`) to enter your token.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `TOKEN` | `""` | API auth token (empty = auth disabled) |
| `MAX_CONCURRENT` | `3` | Max concurrent browser instances (`/navigate`) |
| `HEADLESS` | `true` | Chrome headless mode |
| `PORT` | `3000` | API port |
| `TIMEOUT` | `60` | Default timeout (seconds) |
| `CHROME_VERSION` | `auto` | Chrome major version (e.g., `145`) |
| `TAB_IDLE_TIMEOUT` | `60` | Idle tab close timeout (seconds) |
| `BROWSER_MAX_AGE` | `3600` | Chrome max lifetime before restart (seconds) |

## `/fetch` vs `/navigate`

| | `/fetch` ⚡ | `/navigate` |
|---|---|---|
| Chrome startup | No (stays open) | New instance per request |
| Speed | ~200-500ms | ~5000-15000ms |
| Memory | Tab-based, shared | Isolated per request |
| Cookies | Shared (same session) | Clean each time |
| Use case | Frequent requests, same site | Different sites, isolation |

## Usage Example (Node.js)

```javascript
const response = await fetch("http://localhost:3000/fetch", {
  method: "POST",
  headers: {
    "Content-Type": "application/json",
    "Authorization": "Bearer your-secret-token"
  },
  body: JSON.stringify({
    url: "https://jsonplaceholder.typicode.com/todos/1",
    returnType: "json",
    timeout: 60000
  })
});

const { data, timing } = await response.json();
console.log(data);            // JSON response
console.log(timing.total);    // ~300ms
```

## Deploy (Coolify)

1. Connect GitHub repo to Coolify
2. **Build Pack**: Dockerfile
3. **Port**: 3000
4. **Environment Variables**: `TOKEN`, `MAX_CONCURRENT`, `HEADLESS`, `CHROME_VERSION`
5. **Resources**: min 2GB RAM, `shm_size: 2gb`

## License

MIT
