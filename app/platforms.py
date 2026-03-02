"""
Platform / Cihaz tanımları.

Her platform, Chrome'un user-agent, viewport ve mobil emülasyon
ayarlarını belirler. Antibot sistemlerine karşı gerçekçi cihaz
parmak izi oluşturmak için kullanılır.

navigatorOverride alanları, JavaScript navigator API'larının
gerçek OS bilgisi yerine platform'a uygun değerler döndürmesini sağlar.
"""

from typing import Optional
from pydantic import BaseModel


class NavigatorOverride(BaseModel):
    """JavaScript navigator nesnesinde override edilecek değerler."""

    platform: str  # navigator.platform — "Win32", "MacIntel", "Linux armv81", vb.
    appVersion: str  # navigator.appVersion
    oscpu: Optional[str] = None  # navigator.oscpu (Firefox only)
    # Chrome sec-ch-ua / userAgentData için
    uaFullVersion: str = "131.0.0.0"
    uaPlatform: str = "Windows"
    uaPlatformVersion: str = "15.0.0"
    uaMobile: bool = False
    uaModel: str = ""
    # Chrome Client Hints brands
    brands: list[dict] = []
    # WebGL fingerprint
    webglVendor: str = "Google Inc. (NVIDIA)"
    webglRenderer: str = "ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)"


class Platform(BaseModel):
    """Tek bir cihaz/platform profili."""

    id: str
    name: str
    category: str  # desktop | mobile
    userAgent: str
    viewport: dict  # {"width": int, "height": int}
    deviceScaleFactor: float = 1.0
    isMobile: bool = False
    hasTouch: bool = False
    lang: str = "en-US"
    navigatorOverride: Optional[NavigatorOverride] = None


# ─── Platform Kataloğu ──────────────────────────────────────

PLATFORMS: dict[str, Platform] = {}


def _register(p: Platform):
    PLATFORMS[p.id] = p


# ─── Ortak Client Hints Brands ──────────────────────────────

_CHROME_131_BRANDS = [
    {"brand": "Google Chrome", "version": "131"},
    {"brand": "Chromium", "version": "131"},
    {"brand": "Not_A Brand", "version": "24"},
]


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  DESKTOP
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_register(Platform(
    id="desktop_chrome_windows",
    name="Windows 11 — Chrome",
    category="desktop",
    userAgent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    viewport={"width": 1920, "height": 1080},
    lang="en-US",
    navigatorOverride=NavigatorOverride(
        platform="Win32",
        appVersion="5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        uaPlatform="Windows",
        uaPlatformVersion="15.0.0",
        brands=_CHROME_131_BRANDS,
        webglVendor="Google Inc. (NVIDIA)",
        webglRenderer="ANGLE (NVIDIA, NVIDIA GeForce RTX 3060 Direct3D11 vs_5_0 ps_5_0, D3D11)",
    ),
))

_register(Platform(
    id="desktop_chrome_macos",
    name="macOS Sonoma — Chrome",
    category="desktop",
    userAgent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
    viewport={"width": 1920, "height": 1080},
    lang="en-US",
    navigatorOverride=NavigatorOverride(
        platform="MacIntel",
        appVersion="5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        uaPlatform="macOS",
        uaPlatformVersion="14.5.0",
        brands=_CHROME_131_BRANDS,
        webglVendor="Google Inc. (Apple)",
        webglRenderer="ANGLE (Apple, ANGLE Metal Renderer: Apple M2 Pro, Unspecified Version)",
    ),
))

# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
#  MOBILE
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

_register(Platform(
    id="samsung_s25",
    name="Samsung Galaxy S25",
    category="mobile",
    userAgent="Mozilla/5.0 (Linux; Android 15; SM-S931B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
    viewport={"width": 360, "height": 780},
    deviceScaleFactor=3.0,
    isMobile=True,
    hasTouch=True,
    lang="en-US",
    navigatorOverride=NavigatorOverride(
        platform="Linux armv81",
        appVersion="5.0 (Linux; Android 15; SM-S931B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Mobile Safari/537.36",
        uaPlatform="Android",
        uaPlatformVersion="15",
        uaMobile=True,
        uaModel="SM-S931B",
        brands=_CHROME_131_BRANDS,
        webglVendor="Qualcomm",
        webglRenderer="Adreno (TM) 830",
    ),
))


# ─── Yardımcı fonksiyonlar ───────────────────────────────────

def get_platform(platform_id: str) -> Optional[Platform]:
    """Belirtilen ID'ye ait platformu döndür, yoksa None."""
    return PLATFORMS.get(platform_id)


def get_all_platforms() -> list[Platform]:
    """Tüm platformları liste olarak döndür."""
    return list(PLATFORMS.values())
