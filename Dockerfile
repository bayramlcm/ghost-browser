# ── Stage 1: Build ──────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc g++ python3-dev curl gnupg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir --prefix=/install -r requirements.txt


# ── Stage 2: Runtime ────────────────────────────────────
FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

# Google Chrome official repo + runtime deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl gnupg ca-certificates \
    && curl -fsSL https://dl.google.com/linux/linux_signing_key.pub | gpg --dearmor -o /usr/share/keyrings/google.gpg \
    && echo "deb [arch=amd64 signed-by=/usr/share/keyrings/google.gpg] http://dl.google.com/linux/chrome/deb/ stable main" \
       > /etc/apt/sources.list.d/google.list \
    && apt-get update \
    && apt-get install -y --no-install-recommends \
       google-chrome-stable \
       fonts-liberation \
       xvfb \
       dbus dbus-x11 \
    && rm -rf /var/lib/apt/lists/*

# Python packages
COPY --from=builder /install /usr/local

WORKDIR /srv
COPY app/ /srv/app/

RUN groupadd -r ghost && useradd -r -g ghost -G audio,video ghost \
    && mkdir -p /home/ghost/.cache \
    && chown -R ghost:ghost /home/ghost /srv

USER ghost

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=3000 \
    CHROME_BINARY=/usr/bin/google-chrome \
    DISPLAY=:99

EXPOSE 3000

COPY entrypoint.sh /srv/entrypoint.sh
USER root
RUN chmod +x /srv/entrypoint.sh
USER ghost

ENTRYPOINT ["/srv/entrypoint.sh"]