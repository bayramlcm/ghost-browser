#!/bin/bash
set -e

# Xvfb sanal ekranı başlat (headless=false ise Chrome GUI gerektirir)
if [ "$HEADLESS" = "false" ] || [ "$HEADLESS" = "False" ]; then
    # Eski lock dosyalarını temizle (container restart sonrası kalabilir)
    rm -f /tmp/.X99-lock /tmp/.X11-unix/X99 2>/dev/null || true

    echo "Starting Xvfb on display :99..."
    Xvfb :99 -screen 0 1920x1080x24 -nolisten tcp &
    sleep 1
    echo "Xvfb started"
fi

# Uvicorn'u başlat
exec uvicorn app.main:app --host 0.0.0.0 --port 3000
