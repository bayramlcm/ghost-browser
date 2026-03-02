# Ghost Browser

🌐 [English](README.md) | [Türkçe](README.tr.md) | [中文](README.zh-CN.md) | [Español](README.es.md) | [Русский](README.ru.md) | [Português](README.pt-BR.md)

Antibot bypass yapabilen, browserless mantığında çalışan Docker-based stealth browser servisi.  
`undetected-chromedriver` kullanarak Chrome binary patch'i uygular, HTTP API ile dışarıya browser otomasyonu sunar.

## Özellikler

- **Antibot Bypass** — `undetected-chromedriver` ile Chrome binary patch
- **Platform Emülasyonu** — Cihaz parmak izi taklit (navigator, WebGL, Client Hints)
- **Persistent Browser** — Chrome her zaman açık, tab bazlı hızlı istek (`/fetch`)
- **HTTP API** — FastAPI ile `/fetch`, `/navigate`, `/screenshot`, `/health`, `/platforms`
- **Idle Tab Cleanup** — 60 saniye idle tab otomatik kapanır
- **Crash Recovery** — Chrome çökerse otomatik yeniden başlatır
- **Auto Restart** — 1 saat sonra Chrome otomatik restart (bellek yönetimi)
- **Bearer Token Auth** — Basit ve güvenli API erişimi
- **Docker Ready** — Docker Compose ile kolayca deploy

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

### `GET /platforms`

Desteklenen tüm platform/cihaz profillerini listele.

```bash
curl http://localhost:3000/platforms
```

```json
{
  "total": 3,
  "platforms": [
    { "id": "desktop_chrome_windows", "name": "Windows 11 — Chrome", "category": "desktop" },
    { "id": "desktop_chrome_macos", "name": "macOS Sonoma — Chrome", "category": "desktop" },
    { "id": "samsung_s25", "name": "Samsung Galaxy S25", "category": "mobile" }
  ]
}
```

### `GET /platforms/{id}`

Belirtilen platformun detaylarını döndür.

```bash
curl http://localhost:3000/platforms/samsung_s25
```

---

### `POST /fetch` ⚡ (Önerilen)

**Persistent browser** ile URL'e git — Chrome açık kalır, tab bazlı.  
`/navigate`'den çok daha hızlı çünkü Chrome yeniden başlatılmaz.

```bash
curl -X POST http://localhost:3000/fetch \
  -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/api", "returnType": "json", "platform": "samsung_s25"}'
```

| Alan | Tip | Default | Açıklama |
|------|-----|---------|----------|
| `url` | string | — | Hedef URL (zorunlu) |
| `timeout` | int | `0` | Timeout (ms), 0 = config default |
| `returnType` | string | `json` | `json` \| `html` \| `text` \| `screenshot` |
| `platform` | string | `null` | Platform ID (`/platforms`'dan bakılabilir) |

**Yanıt:**

```json
{
  "success": true,
  "url": "https://example.com/api",
  "statusCode": 200,
  "data": { "result": "..." },
  "cookies": [],
  "timing": { "total": 350, "challenge": 280 }
}
```

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
  -d '{"url": "https://example.com", "returnType": "json", "platform": "desktop_chrome_macos"}'
```

| Alan | Tip | Default | Açıklama |
|------|-----|---------|----------|
| `url` | string | — | Hedef URL (zorunlu) |
| `waitFor` | string | `networkidle` | `networkidle` \| `selector` \| `timeout` |
| `waitSelector` | string | `null` | CSS selector (`waitFor=selector` ise) |
| `timeout` | int | `0` | Timeout (ms), 0 = config default |
| `returnType` | string | `json` | `json` \| `html` \| `text` \| `screenshot` |
| `platform` | string | `null` | Platform ID (`/platforms`'dan bakılabilir) |

---

### `POST /screenshot`

URL'in screenshot'ını PNG olarak döndür.

```bash
curl -X POST http://localhost:3000/screenshot \
  -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com", "platform": "desktop_chrome_macos"}' \
  --output screenshot.png
```

---

### Kimlik Doğrulama

`TOKEN` environment variable'ı set edilmişse tüm endpointler Bearer token gerektirir:

```
Authorization: Bearer <TOKEN>
```

Swagger UI'dan (`/docs`) test ederken 🔒 **Authorize** butonuyla token girebilirsiniz.

## Platformlar

Ghost Browser, antibot parmak izi kontrollerini aşmak için farklı cihazları taklit edebilir. Her platform şunları override eder:

- **User-Agent** — HTTP header ve `navigator.userAgent`
- **Client Hints** — `sec-ch-ua`, `sec-ch-ua-platform`, `sec-ch-ua-model`
- **Navigator** — `navigator.platform`, `appVersion`, `vendor`, `maxTouchPoints`
- **WebGL** — GPU vendor/renderer parmak izi
- **Ekran** — Çözünürlük, oryantasyon, devicePixelRatio
- **Cihaz** — `hardwareConcurrency`, `deviceMemory`

| ID | İsim | Kategori | Not |
|----|------|----------|-----|
| `desktop_chrome_windows` | Windows 11 — Chrome | Desktop | Windows & Docker'da çalışır |
| `desktop_chrome_macos` | macOS Sonoma — Chrome | Desktop | Windows & Docker'da çalışır |
| `samsung_s25` | Samsung Galaxy S25 | Mobile | Sadece Docker'da çalışır |

> **Not:** Mobil platformlar (Samsung vb.) sadece Docker (Linux) üzerinde güvenilir çalışır. Windows host'taki canvas/font parmak izleri mobil cihaz imzalarıyla eşleşmez.

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
    url: "https://example.com/api/data",
    returnType: "json",
    platform: "samsung_s25",
    timeout: 60000
  })
});

const { data, timing } = await response.json();
console.log(data);            // JSON yanıtı
console.log(timing.total);    // ~300ms
```

## Lisans

MIT
