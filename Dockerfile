# ── Stage 1: Build ──────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Build tools for C extensions (uvloop, httptools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ python3-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── Stage 2: Runtime ────────────────────────────────────
FROM python:3.11-slim

# System dependencies for Chrome
RUN apt-get update && apt-get install -y --no-install-recommends \
    wget ca-certificates \
    fonts-liberation libasound2 libatk-bridge2.0-0 libatk1.0-0 \
    libcups2 libdbus-1-3 libdrm2 libgbm1 libgtk-3-0 libnspr4 \
    libnss3 libxcomposite1 libxdamage1 libxrandr2 xdg-utils \
    && rm -rf /var/lib/apt/lists/*

# Download and install Chrome separately (so errors are visible)
RUN wget -q -O /tmp/chrome.deb https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb \
    && dpkg -i /tmp/chrome.deb || true \
    && apt-get update && apt-get install -f -y --no-install-recommends \
    && rm /tmp/chrome.deb \
    && rm -rf /var/lib/apt/lists/*

# Verify
RUN which google-chrome-stable && google-chrome-stable --version

# Copy Python packages from builder
COPY --from=builder /install /usr/local

# App
WORKDIR /srv
COPY app/ /srv/app/

# Non-root user
RUN groupadd -r ghost && useradd -r -g ghost -G audio,video ghost \
    && mkdir -p /home/ghost/.local/share/undetected_chromedriver \
    && chown -R ghost:ghost /home/ghost /srv

USER ghost

# Environment
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=3000 \
    HEADLESS=true \
    MAX_CONCURRENT=3 \
    CHROME_BINARY=/usr/bin/google-chrome-stable

EXPOSE 3000

HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:3000/health')" || exit 1

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000", "--workers", "1"]
