"""
Ghost Browser — FastAPI uygulaması.

Antibot bypass yapabilen stealth browser servisi.
undetected-chromedriver ile Chrome binary patch'i uygular,
HTTP API ile dışarıya browser otomasyonu sunar.
"""

import logging
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException, Response
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from app.config import settings
from app.browser import navigate, take_screenshot
from app.browser_manager import manager

# ─── Logging ─────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ghost-browser")


# ─── Lifespan ────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks."""
    logger.info(f"Ghost Browser başlatıldı — port:{settings.port}, "
                f"max_concurrent:{settings.max_concurrent}, headless:{settings.headless}")
    # Persistent browser'ı başlat
    await manager.start()
    yield
    # Persistent browser'ı kapat
    await manager.shutdown()
    logger.info("Ghost Browser kapatılıyor...")


# ─── FastAPI App ─────────────────────────────────────────
app = FastAPI(
    title="Ghost Browser",
    description="Stealth browser service with antibot bypass — undetected-chromedriver",
    version="1.0.0",
    lifespan=lifespan,
)


# ─── Auth ────────────────────────────────────────────────
security = HTTPBearer(auto_error=False)


async def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Bearer token doğrulama."""
    if not settings.token:
        # Token yapılandırılmamışsa auth gerekli değil
        return

    if not credentials:
        raise HTTPException(status_code=401, detail="Authorization header gerekli")

    if credentials.credentials != settings.token:
        raise HTTPException(status_code=403, detail="Geçersiz token")


# ─── Request / Response Models ───────────────────────────
class NavigateRequest(BaseModel):
    url: str
    waitFor: str = Field(default="networkidle", description="networkidle | selector | timeout")
    waitSelector: Optional[str] = Field(default=None, description="CSS selector (waitFor=selector ise)")
    timeout: int = Field(default=0, description="Timeout (ms), 0 = config default")
    returnType: str = Field(default="json", description="json | html | text | screenshot")


class NavigateResponse(BaseModel):
    success: bool
    url: str
    statusCode: int
    data: object = None
    error: Optional[str] = None
    cookies: list = []
    timing: dict = {}


class ScreenshotRequest(BaseModel):
    url: str
    fullPage: bool = Field(default=True)
    viewport: dict = Field(default={"width": 1920, "height": 1080})
    timeout: int = Field(default=0, description="Timeout (ms), 0 = config default")


class HealthResponse(BaseModel):
    status: str
    version: str
    max_concurrent: int
    headless: bool
    browser: Optional[dict] = None


class FetchRequest(BaseModel):
    url: str
    timeout: int = Field(default=0, description="Timeout (ms), 0 = config default")
    returnType: str = Field(default="json", description="json | html | text | screenshot")


# ─── Endpoints ───────────────────────────────────────────
@app.get("/health", response_model=HealthResponse)
async def health():
    """Servis durumu kontrolü."""
    return HealthResponse(
        status="ok",
        version="1.0.0",
        max_concurrent=settings.max_concurrent,
        headless=settings.headless,
        browser=manager.get_status(),
    )


@app.post("/navigate", response_model=NavigateResponse)
async def navigate_endpoint(
    req: NavigateRequest,
    _=Depends(verify_token),
):
    """
    Bir URL'e git, antibot challenge'ını geç, sonucu döndür.
    """

    result = await navigate(
        url=req.url,
        wait_for=req.waitFor,
        wait_selector=req.waitSelector,
        timeout=req.timeout,
        return_type=req.returnType,
    )

    return NavigateResponse(**result)


@app.post("/screenshot")
async def screenshot_endpoint(
    req: ScreenshotRequest,
    _=Depends(verify_token),
):
    """URL'in screenshot'ını PNG olarak döndür."""

    width = req.viewport.get("width", 1920)
    height = req.viewport.get("height", 1080)

    try:
        png_bytes = await take_screenshot(
            url=req.url,
            full_page=req.fullPage,
            width=width,
            height=height,
            timeout=req.timeout,
        )
        return Response(content=png_bytes, media_type="image/png")
    except Exception as e:
        logger.error(f"Screenshot hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/fetch", response_model=NavigateResponse)
async def fetch_endpoint(
    req: FetchRequest,
    _=Depends(verify_token),
):
    """
    Persistent browser ile URL'e git — Chrome açık kalır, tab bazlı.
    /navigate'den çok daha hızlı (Chrome yeniden başlatılmaz).
    """
    result = await manager.fetch(
        url=req.url,
        timeout=req.timeout,
        return_type=req.returnType,
    )
    return NavigateResponse(**result)


# ─── Uvicorn entrypoint ─────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=False,
    )
