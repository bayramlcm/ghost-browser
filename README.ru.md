# Ghost Browser

🌐 [English](README.md) | [Türkçe](README.tr.md) | [中文](README.zh-CN.md) | [Español](README.es.md) | [Русский](README.ru.md) | [Português](README.pt-BR.md)

Стелс-браузерный сервис на базе Docker с обходом антибот-защиты.  
Патчит бинарный файл Chrome с помощью `undetected-chromedriver`, предоставляет автоматизацию браузера через HTTP API.

## Возможности

- **Обход антибота** — Патч бинарного файла Chrome через `undetected-chromedriver`
- **Эмуляция платформы** — Подмена отпечатка устройства (navigator, WebGL, Client Hints)
- **Постоянный браузер** — Chrome остаётся открытым, быстрые запросы через вкладки (`/fetch`)
- **HTTP API** — Эндпоинты FastAPI: `/fetch`, `/navigate`, `/screenshot`, `/health`, `/platforms`
- **Очистка вкладок** — Неактивные вкладки автоматически закрываются через 60 секунд
- **Восстановление после сбоев** — Chrome автоматически перезапускается при падении
- **Автоперезапуск** — Chrome перезапускается через 1 час (управление памятью)
- **Bearer Token аутентификация** — Простой и безопасный доступ к API
- **Готов для Docker** — Лёгкий деплой через Docker Compose

## Быстрый старт

### Docker (Рекомендуется)

```bash
docker compose up -d

# Или вручную
docker build -t ghost-browser .
docker run -p 3000:3000 -e TOKEN=your-secret-token --shm-size=2g ghost-browser
```

### Локальная разработка

```bash
python -m virtualenv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env

uvicorn app.main:app --host 0.0.0.0 --port 3000
```

## API

### `GET /health`

Проверка состояния сервиса и браузера.

### `GET /platforms`

Список всех поддерживаемых профилей платформ/устройств.

```bash
curl http://localhost:3000/platforms
```

### `GET /platforms/{id}`

Получить детали конкретной платформы.

---

### `POST /fetch` ⚡ (Рекомендуется)

**Постоянный браузер** — Chrome остаётся открытым, работа через вкладки.  
Намного быстрее `/navigate`, так как Chrome не перезапускается.

```bash
curl -X POST http://localhost:3000/fetch \
  -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/api", "returnType": "json", "platform": "samsung_s25"}'
```

| Поле | Тип | По умолчанию | Описание |
|------|-----|--------------|----------|
| `url` | string | — | Целевой URL (обязательно) |
| `timeout` | int | `0` | Таймаут (мс), 0 = по умолчанию |
| `returnType` | string | `json` | `json` \| `html` \| `text` \| `screenshot` |
| `platform` | string | `null` | ID платформы (см. `/platforms`) |

### `POST /navigate`

Открывает новый экземпляр Chrome для каждого запроса. Медленнее, но изолированно.

### `POST /screenshot`

Возвращает PNG-скриншот URL.

## Платформы

| ID | Название | Категория | Примечание |
|----|----------|-----------|------------|
| `desktop_chrome_windows` | Windows 11 — Chrome | Десктоп | Работает на Windows и Docker |
| `desktop_chrome_macos` | macOS Sonoma — Chrome | Десктоп | Работает на Windows и Docker |
| `samsung_s25` | Samsung Galaxy S25 | Мобильный | Только Docker |

> **Примечание:** Мобильные платформы надёжно работают только в Docker (Linux).

## Переменные окружения

| Переменная | По умолчанию | Описание |
|------------|--------------|----------|
| `TOKEN` | `""` | Токен аутентификации (пусто = без аутентификации) |
| `MAX_CONCURRENT` | `3` | Максимум одновременных экземпляров |
| `HEADLESS` | `true` | Безголовый режим Chrome |
| `PORT` | `3000` | Порт API |
| `CHROME_VERSION` | `auto` | Мажорная версия Chrome |
| `TAB_IDLE_TIMEOUT` | `60` | Таймаут неактивной вкладки (секунды) |
| `BROWSER_MAX_AGE` | `3600` | Максимальное время жизни Chrome (секунды) |

## `/fetch` vs `/navigate`

| | `/fetch` ⚡ | `/navigate` |
|---|---|---|
| Запуск Chrome | Нет (остаётся открытым) | Новый экземпляр |
| Скорость | ~200-500мс | ~5000-15000мс |
| Память | На основе вкладок | Изолированно |
| Cookies | Общие (одна сессия) | Чистые каждый раз |

## Лицензия

MIT
