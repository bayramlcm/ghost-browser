# Ghost Browser

🌐 [English](README.md) | [Türkçe](README.tr.md) | [中文](README.zh-CN.md) | [Español](README.es.md) | [Русский](README.ru.md) | [Português](README.pt-BR.md)

Serviço de navegador stealth baseado em Docker com bypass de antibot.  
Aplica patch no binário do Chrome usando `undetected-chromedriver`, expõe automação do navegador via HTTP API.

## Recursos

- **Bypass Antibot** — Patch do binário do Chrome via `undetected-chromedriver`
- **Navegador Persistente** — Chrome permanece aberto, requisições rápidas por abas (`/fetch`)
- **HTTP API** — Endpoints FastAPI: `/fetch`, `/navigate`, `/screenshot`, `/health`
- **Limpeza de Abas** — Abas ociosas fecham automaticamente após 60 segundos
- **Recuperação de Falhas** — Chrome reinicia automaticamente em caso de crash
- **Reinício Automático** — Chrome reinicia após 1 hora (gerenciamento de memória)
- **Autenticação Bearer Token** — Acesso API simples e seguro
- **Pronto para Docker** — Deploy fácil via Coolify / Docker Compose

## Início Rápido

### Docker (Recomendado)

```bash
docker compose up -d

# Ou manualmente
docker build -t ghost-browser .
docker run -p 3000:3000 -e TOKEN=your-secret-token --shm-size=2g ghost-browser
```

### Desenvolvimento Local

```bash
python -m virtualenv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

pip install -r requirements.txt
cp .env.example .env

uvicorn app.main:app --host 0.0.0.0 --port 3000
```

## API

### `POST /fetch` ⚡ (Recomendado)

**Navegador persistente** — Chrome permanece aberto, baseado em abas.  
Muito mais rápido que `/navigate` pois o Chrome não reinicia.

```bash
curl -X POST http://localhost:3000/fetch \
  -H "Authorization: Bearer your-secret-token" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://jsonplaceholder.typicode.com/todos/1", "returnType": "json"}'
```

| Campo | Tipo | Padrão | Descrição |
|-------|------|--------|-----------|
| `url` | string | — | URL alvo (obrigatório) |
| `timeout` | int | `0` | Timeout (ms), 0 = padrão |
| `returnType` | string | `json` | `json` \| `html` \| `text` \| `screenshot` |

### `POST /navigate`

Abre nova instância do Chrome por requisição. Mais lento, porém isolado.

### `POST /screenshot`

Retorna screenshot PNG da URL.

### `GET /health`

Verificação de status do serviço e navegador.

## Variáveis de Ambiente

| Variável | Padrão | Descrição |
|----------|--------|-----------|
| `TOKEN` | `""` | Token de autenticação (vazio = sem auth) |
| `MAX_CONCURRENT` | `3` | Máximo de instâncias simultâneas |
| `HEADLESS` | `true` | Modo headless do Chrome |
| `PORT` | `3000` | Porta da API |
| `CHROME_VERSION` | `auto` | Versão principal do Chrome |
| `TAB_IDLE_TIMEOUT` | `60` | Timeout de aba ociosa (segundos) |
| `BROWSER_MAX_AGE` | `3600` | Tempo máximo de vida do Chrome (segundos) |

## `/fetch` vs `/navigate`

| | `/fetch` ⚡ | `/navigate` |
|---|---|---|
| Inicialização do Chrome | Não (permanece aberto) | Nova instância |
| Velocidade | ~200-500ms | ~5000-15000ms |
| Memória | Baseada em abas | Isolada por requisição |
| Cookies | Compartilhados | Limpos a cada vez |

## Licença

MIT
