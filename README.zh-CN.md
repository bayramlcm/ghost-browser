# Ghost Browser

🌐 [English](README.md) | [Türkçe](README.tr.md) | [中文](README.zh-CN.md) | [Español](README.es.md) | [Русский](README.ru.md) | [Português](README.pt-BR.md)

基于 Docker 的隐身浏览器服务，具有反机器人检测绕过功能。  
使用 `undetected-chromedriver` 对 Chrome 二进制文件打补丁，通过 HTTP API 提供浏览器自动化服务。

## 功能

- **反机器人绕过** — 通过 `undetected-chromedriver` 对 Chrome 打补丁
- **平台模拟** — 设备指纹伪装（navigator、WebGL、Client Hints）
- **持久化浏览器** — Chrome 保持运行，基于标签页的快速请求（`/fetch`）
- **HTTP API** — FastAPI 端点：`/fetch`、`/navigate`、`/screenshot`、`/health`、`/platforms`
- **空闲标签页清理** — 空闲标签页 60 秒后自动关闭
- **崩溃恢复** — Chrome 崩溃后自动重启
- **定时重启** — 1 小时后自动重启 Chrome（内存管理）
- **Bearer Token 认证** — 简单安全的 API 访问
- **Docker 就绪** — 通过 Docker Compose 轻松部署

## 快速开始

### Docker（推荐）

```bash
docker compose up -d

# 或手动构建
docker build -t ghost-browser .
docker run -p 3000:3000 -e TOKEN=your-secret-token --shm-size=2g ghost-browser
```

### 本地开发

```bash
python -m virtualenv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env

uvicorn app.main:app --host 0.0.0.0 --port 3000
```

## API

### `GET /health`

服务和浏览器状态检查。

### `GET /platforms`

列出所有支持的平台/设备配置。

```bash
curl http://localhost:3000/platforms
```

### `GET /platforms/{id}`

获取指定平台的详细信息。

---

### `POST /fetch` ⚡（推荐）

**持久化浏览器** — Chrome 保持运行，基于标签页。  
比 `/navigate` 快得多，因为 Chrome 无需重启。

```bash
curl -X POST http://localhost:3000/fetch \
  -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://example.com/api", "returnType": "json", "platform": "samsung_s25"}'
```

| 字段 | 类型 | 默认值 | 描述 |
|------|------|--------|------|
| `url` | string | — | 目标 URL（必填）|
| `timeout` | int | `0` | 超时（毫秒），0 = 默认 |
| `returnType` | string | `json` | `json` \| `html` \| `text` \| `screenshot` |
| `platform` | string | `null` | 平台 ID（参见 `/platforms`）|

### `POST /navigate`

每次请求打开新的 Chrome 实例。更慢但隔离。

### `POST /screenshot`

返回 URL 的 PNG 截图。

## 平台

| ID | 名称 | 类别 | 备注 |
|----|------|------|------|
| `desktop_chrome_windows` | Windows 11 — Chrome | 桌面 | Windows 和 Docker 均可用 |
| `desktop_chrome_macos` | macOS Sonoma — Chrome | 桌面 | Windows 和 Docker 均可用 |
| `samsung_s25` | Samsung Galaxy S25 | 移动端 | 仅 Docker 可用 |

> **注意：** 移动平台仅在 Docker（Linux）上可靠运行。

## 环境变量

| 变量 | 默认值 | 描述 |
|------|--------|------|
| `TOKEN` | `""` | API 认证令牌（空 = 无需认证）|
| `MAX_CONCURRENT` | `3` | 最大并发浏览器实例 |
| `HEADLESS` | `true` | Chrome 无头模式 |
| `PORT` | `3000` | API 端口 |
| `CHROME_VERSION` | `auto` | Chrome 主版本号 |
| `TAB_IDLE_TIMEOUT` | `60` | 空闲标签页关闭超时（秒）|
| `BROWSER_MAX_AGE` | `3600` | Chrome 最大生命周期（秒）|

## `/fetch` vs `/navigate`

| | `/fetch` ⚡ | `/navigate` |
|---|---|---|
| Chrome 启动 | 否（保持运行）| 每次新实例 |
| 速度 | ~200-500ms | ~5000-15000ms |
| 内存 | 基于标签页，共享 | 每次隔离 |
| Cookie | 共享（同一会话）| 每次清空 |

## 许可证

MIT
