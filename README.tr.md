# Ghost Browser

🌐 [English](README.md) | [Türkçe](README.tr.md) | [中文](README.zh-CN.md) | [Español](README.es.md) | [Русский](README.ru.md) | [Português](README.pt-BR.md)

Antibot bypass yapabilen, browserless mantığında çalışan Docker-based stealth browser servisi.  
`undetected-chromedriver` kullanarak Chrome binary patch'i uygular, HTTP API ile dışarıya browser otomasyonu sunar.

## Özellikler

- **Antibot Bypass** — `undetected-chromedriver` ile Chrome binary patch
- **Persistent Browser** — Chrome her zaman açık, tab bazlı hızlı istek (`/fetch`)
- **HTTP API** — FastAPI ile `/fetch`, `/navigate`, `/screenshot`, `/health` endpointleri
- **Idle Tab Cleanup** — 60 saniye idle tab otomatik kapanır
- **Crash Recovery** — Chrome çökerse otomatik yeniden başlatır
- **Auto Restart** — 1 saat sonra Chrome otomatik restart (bellek yönetimi)
- **Bearer Token Auth** — Basit ve güvenli API erişimi
- **Docker Ready** — Coolify / Docker Compose ile kolayca deploy

## Hızlı Başlangıç

### Docker (Önerilen)

```bash
docker compose up -d

# Veya tek komutla
docker build -t ghost-browser .
docker run -p 3000:3000 -e TOKEN=your-secret-token --shm-size=2g ghost-browser
```

### Lokal Geliştirme

```bash
python -m virtualenv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env

uvicorn app.main:app --host 0.0.0.0 --port 3000
```

## API

### `GET /health`

Servis ve browser durumu kontrolü.

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

### `POST /fetch` ⚡ (Önerilen)

**Persistent browser** ile URL'e git — Chrome açık kalır, tab bazlı.  
`/navigate`'den çok daha hızlı çünkü Chrome yeniden başlatılmaz.

```bash
curl -X POST http://localhost:3000/fetch \
  -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://jsonplaceholder.typicode.com/todos/1", "returnType": "json"}'
```

| Alan | Tip | Default | Açıklama |
|------|-----|---------|----------|
| `url` | string | — | Hedef URL (zorunlu) |
| `timeout` | int | `0` | Timeout (ms), 0 = config default |
| `returnType` | string | `json` | `json` \| `html` \| `text` \| `screenshot` |

**Persistent Browser Davranışı:**
- İlk istek: Chrome zaten açık, yeni tab açar (~300ms)
- Sonraki istekler: Idle tab yeniden kullanılır (~200ms)
- 60 saniye istek gelmezse idle tab otomatik kapanır
- 1 saat sonra Chrome otomatik restart edilir (bellek yönetimi)
- Chrome çökerse otomatik yeniden başlatılır

---

### `POST /navigate`

Her istekte yeni Chrome instance açar. Daha yavaş ama izole.

```bash
curl -X POST http://localhost:3000/navigate \
  -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "returnType": "json"}'
```

| Alan | Tip | Default | Açıklama |
|------|-----|---------|----------|
| `url` | string | — | Hedef URL (zorunlu) |
| `waitFor` | string | `networkidle` | `networkidle` \| `selector` \| `timeout` |
| `waitSelector` | string | `null` | CSS selector (`waitFor=selector` ise) |
| `timeout` | int | `0` | Timeout (ms), 0 = config default |
| `returnType` | string | `json` | `json` \| `html` \| `text` \| `screenshot` |

---

### `POST /screenshot`

URL'in screenshot'ını PNG olarak döndür.

```bash
curl -X POST http://localhost:3000/screenshot \
  -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com"}' \
  --output screenshot.png
```

---

### Kimlik Doğrulama

`TOKEN` environment variable'ı set edilmişse tüm endpointler Bearer token gerektirir:

```
Authorization: Bearer <TOKEN>
```

Swagger UI'dan (`/docs`) test ederken 🔒 **Authorize** butonuyla token girebilirsiniz.

## Ortam Değişkenleri

| Değişken | Default | Açıklama |
|----------|---------|----------|
| `TOKEN` | `""` | API auth token (boş = auth kapalı) |
| `MAX_CONCURRENT` | `3` | Eşzamanlı browser instance sayısı (`/navigate` için) |
| `HEADLESS` | `true` | Chrome headless modu |
| `PORT` | `3000` | API portu |
| `TIMEOUT` | `60` | Varsayılan timeout (saniye) |
| `CHROME_VERSION` | `auto` | Chrome major version (örn: `145`) |
| `TAB_IDLE_TIMEOUT` | `60` | Idle tab kapatma süresi (saniye) |
| `BROWSER_MAX_AGE` | `3600` | Chrome max yaşam süresi, restart (saniye) |

## `/fetch` vs `/navigate`

| | `/fetch` ⚡ | `/navigate` |
|---|---|---|
| Chrome başlatma | Hayır (açık kalır) | Her istekte yeni |
| Hız | ~200-500ms | ~5000-15000ms |
| Bellek | Tab bazlı, paylaşımlı | Her istek izole |
| Cookie | Paylaşımlı (aynı session) | Her seferinde temiz |
| Kullanım | Sık istek, aynı site | Farklı siteler, izolasyon |

## Kullanım Örneği (Node.js)

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
console.log(data);            // JSON yanıtı
console.log(timing.total);    // ~300ms
```

## Coolify Deploy

1. GitHub repo'yu Coolify'a bağla
2. **Build Pack**: Dockerfile
3. **Port**: 3000
4. **Environment Variables**: `TOKEN`, `MAX_CONCURRENT`, `HEADLESS`, `CHROME_VERSION`
5. **Resources**: min 2GB RAM, `shm_size: 2gb`

## Lisans

MIT
