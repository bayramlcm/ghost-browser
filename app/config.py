"""
Ortam değişkenleri ve yapılandırma.
"""

from typing import Optional

from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    """Uygulama yapılandırması — environment variable'lardan okunur."""

    token: str = Field(default="", description="API authentication token (Bearer)")
    max_concurrent: int = Field(default=3, description="Eşzamanlı browser instance sayısı")
    timeout: int = Field(default=60, description="Varsayılan timeout (saniye)")
    headless: bool = Field(default=True, description="Chrome headless mod")
    port: int = Field(default=3000, description="API port")
    chrome_version: Optional[int] = Field(default=None, description="Chrome major version (örn: 145)")
    chrome_binary: Optional[str] = Field(default=None, description="Chrome binary path (Docker: /usr/bin/google-chrome-stable)")
    tab_idle_timeout: int = Field(default=60, description="Idle tab kapatma süresi (saniye)")
    browser_max_age: int = Field(default=3600, description="Chrome max yaşam süresi, restart (saniye)")

    model_config = {"env_file": ".env", "env_file_encoding": "utf-8"}


settings = Settings()
