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

from app.config import settings
from app.browser import navigate, take_screenshot
from app.browser_manager import manager
from app.platforms import get_platform, get_all_platforms
from app.schemas import (
    NavigateRequest,
    BrowseRequest,
    ScreenshotRequest,
    BrowseResponse,
    HealthResponse,
)

# ─── Logging ─────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger("ghost-browser")


# ─── Lifespan ────────────────────────────────────────────────
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup / shutdown hooks."""
    logger.info(f"Ghost Browser başlatıldı — port:{settings.port}, "
                f"max_concurrent:{settings.max_concurrent}, headless:{settings.headless}")
    await manager.start()
    yield
    await manager.shutdown()
    logger.info("Ghost Browser kapatılıyor...")


# ─── App ─────────────────────────────────────────────────────
app = FastAPI(
    title="Ghost Browser",
    description="Stealth browser service with antibot bypass — undetected-chromedriver",
    version="1.0.0",
    lifespan=lifespan,
)


# ─── Auth ────────────────────────────────────────────────────
security = HTTPBearer(auto_error=False)


async def verify_token(credentials: Optional[HTTPAuthorizationCredentials] = Depends(security)):
    """Bearer token doğrulama."""
    if not settings.token:
        return

    if not credentials:
        raise HTTPException(status_code=401, detail="Authorization header gerekli")

    if credentials.credentials != settings.token:
        raise HTTPException(status_code=403, detail="Geçersiz token")


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  HEALTH
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/health", response_model=HealthResponse, tags=["System"])
async def health():
    """Servis durumu kontrolü."""
    return HealthResponse(
        status="ok",
        version="1.0.0",
        max_concurrent=settings.max_concurrent,
        headless=settings.headless,
        browser=manager.get_status(),
    )


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  PLATFORMS
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.get("/platforms", tags=["Platforms"])
async def list_platforms():
    """Tüm desteklenen platform/cihaz profillerini listele."""
    platforms = get_all_platforms()
    return {
        "total": len(platforms),
        "platforms": [p.model_dump() for p in platforms],
    }


@app.get("/platforms/{platform_id}", tags=["Platforms"])
async def get_platform_detail(platform_id: str):
    """Belirtilen platformın detaylarını döndür."""
    platform = get_platform(platform_id)
    if not platform:
        raise HTTPException(status_code=404, detail=f"Platform bulunamadı: {platform_id}")
    return platform.model_dump()


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  BROWSER
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

@app.post("/navigate", response_model=BrowseResponse, tags=["Browser"])
async def navigate_endpoint(req: NavigateRequest, _=Depends(verify_token)):
    """
    Yeni Chrome instance ile URL'e git.

    Her istek için Chrome başlatılır, antibot challenge geçilir,
    sonuç döndürülür ve Chrome kapatılır. Güvenli ama yavaş.
    """
    result = await navigate(
        url=req.url,
        wait_for=req.waitFor,
        wait_selector=req.waitSelector,
        timeout=req.timeout,
        return_type=req.returnType,
        platform_id=req.platform,
    )
    return BrowseResponse(**result)


@app.post("/fetch", response_model=BrowseResponse, tags=["Browser"])
async def fetch_endpoint(req: BrowseRequest, _=Depends(verify_token)):
    """
    Persistent browser ile URL'e git (hızlı).

    Chrome sürekli açık kalır, her istek yeni tab açar.
    /navigate'den ~10x daha hızlı. Antibot cookie'leri korunur.
    """
    result = await manager.fetch(
        url=req.url,
        timeout=req.timeout,
        return_type=req.returnType,
        platform_id=req.platform,
    )
    return BrowseResponse(**result)


@app.post("/screenshot", tags=["Browser"])
async def screenshot_endpoint(req: ScreenshotRequest, _=Depends(verify_token)):
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
            platform_id=req.platform,
        )
        return Response(content=png_bytes, media_type="image/png")
    except Exception as e:
        logger.error(f"Screenshot hatası: {e}")
        raise HTTPException(status_code=500, detail=str(e))


# ─── Entrypoint ──────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "app.main:app",
        host="0.0.0.0",
        port=settings.port,
        reload=False,
    )
