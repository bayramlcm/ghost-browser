"""
Request / Response şemaları.

Tüm API endpoint'lerinde kullanılan Pydantic modelleri.
"""

from typing import Optional
from pydantic import BaseModel, Field


# ─── Request Models ──────────────────────────────────────────

class BrowseRequest(BaseModel):
    """Tüm browser endpoint'leri için ortak istek modeli."""

    url: str = Field(description="Hedef URL")
    timeout: int = Field(default=0, description="Timeout (ms), 0 = config default")
    returnType: str = Field(default="json", description="json | html | text | screenshot")
    platform: Optional[str] = Field(default=None, description="Cihaz profili ID'si (örn: samsung_s25, desktop_chrome_macos)")


class NavigateRequest(BrowseRequest):
    """Yeni Chrome instance ile navigate — antibot challenge desteği."""

    waitFor: str = Field(default="networkidle", description="networkidle | selector | timeout")
    waitSelector: Optional[str] = Field(default=None, description="CSS selector (waitFor=selector ise)")


class ScreenshotRequest(BaseModel):
    """URL screenshot'ı."""

    url: str = Field(description="Hedef URL")
    fullPage: bool = Field(default=True, description="Tam sayfa screenshot")
    viewport: dict = Field(default={"width": 1920, "height": 1080})
    timeout: int = Field(default=0, description="Timeout (ms), 0 = config default")
    platform: Optional[str] = Field(default=None, description="Cihaz profili ID'si")


# ─── Response Models ─────────────────────────────────────────

class BrowseResponse(BaseModel):
    """Browser işlemi sonucu."""

    success: bool
    url: str
    statusCode: int
    data: object = None
    error: Optional[str] = None
    cookies: list = []
    timing: dict = {}


class HealthResponse(BaseModel):
    """Servis durumu."""

    status: str
    version: str
    max_concurrent: int
    headless: bool
    browser: Optional[dict] = None
    file_descriptors: Optional[dict] = None
