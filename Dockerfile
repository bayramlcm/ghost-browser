FROM python:3.11-slim

# Chrome bağımlılıkları + Chrome kurulumu
RUN apt-get update && apt-get install -y \
    wget gnupg2 unzip \
    # Chrome'un ihtiyaç duyduğu sistem kütüphaneleri
    fonts-liberation libasound2 libatk-bridge2.0-0 libatk1.0-0 \
    libcups2 libdbus-1-3 libdrm2 libgbm1 libgtk-3-0 libnspr4 \
    libnss3 libxcomposite1 libxdamage1 libxrandr2 xdg-utils \
    && wget -q -O - https://dl.google.com/linux/linux_signing_key.pub | apt-key add - \
    && echo "deb http://dl.google.com/linux/chrome/deb/ stable main" >> /etc/apt/sources.list.d/google.list \
    && apt-get update && apt-get install -y google-chrome-stable \
    && apt-get clean && rm -rf /var/lib/apt/lists/*

# Python bağımlılıkları
WORKDIR /srv
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Uygulama dosyaları
COPY app/ /srv/app/

# Ortam değişkenleri
ENV PORT=3000
ENV HEADLESS=true
ENV MAX_CONCURRENT=3
ENV PYTHONUNBUFFERED=1

EXPOSE 3000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "3000"]
