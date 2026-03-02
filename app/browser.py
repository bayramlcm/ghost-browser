"""
UC Browser lifecycle yönetimi.

undetected-chromedriver kullanarak Chrome binary'sindeki cdc_ markerlarını patch'ler,
antibot scriptlerinin otomasyon tespitini engeller.
"""

import asyncio
import json
import time
import logging
import base64
from typing import Optional

import undetected_chromedriver as uc

from app.config import settings
from app.platforms import get_platform, Platform, NavigatorOverride

logger = logging.getLogger("ghost-browser")

# Eşzamanlı browser erişimini sınırlayan semaphore
_semaphore: Optional[asyncio.Semaphore] = None


def get_semaphore() -> asyncio.Semaphore:
    """Lazy-init semaphore (event loop hazır olduğunda)."""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.max_concurrent)
    return _semaphore


def create_driver(platform_id: Optional[str] = None) -> uc.Chrome:
    """
    Yeni undetected-chromedriver Chrome instance oluştur.

    - Binary patch uygular (cdc_ marker temizliği)
    - Antibot-friendly ayarlar
    - Platform seçilmişse user-agent, viewport, mobil emülasyon uygular
    """
    platform = get_platform(platform_id) if platform_id else None

    options = uc.ChromeOptions()

    # Viewport — platformdan veya default
    vp_w = platform.viewport["width"] if platform else 1920
    vp_h = platform.viewport["height"] if platform else 1080
    options.add_argument(f"--window-size={vp_w},{vp_h}")

    # Dil — platformdan veya default
    lang = platform.lang if platform else "en-US"
    options.add_argument(f"--lang={lang}")

    # User-Agent
    if platform:
        options.add_argument(f"--user-agent={platform.userAgent}")

    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--disable-gpu")

    # Docker'da Chrome binary path'ini açıkça belirt
    if settings.chrome_binary:
        options.binary_location = settings.chrome_binary

    driver = uc.Chrome(
        options=options,
        headless=settings.headless,
        use_subprocess=True,
        version_main=settings.chrome_version,
        browser_executable_path=settings.chrome_binary,
    )

    # Mobil emülasyon — CDP komutu ile
    if platform and platform.isMobile:
        _apply_mobile_emulation(driver, platform)

    # Navigator fingerprint override — antibot bypass
    if platform and platform.navigatorOverride:
        _apply_navigator_override(driver, platform)

    return driver


def _apply_mobile_emulation(driver, platform: Platform):
    """CDP komutu ile mobil cihaz emülasyonu uygula."""
    try:
        driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
            "width": platform.viewport["width"],
            "height": platform.viewport["height"],
            "deviceScaleFactor": platform.deviceScaleFactor,
            "mobile": platform.isMobile,
        })
        driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {
            "enabled": platform.hasTouch,
        })
        logger.info(f"Mobil emülasyon uygulandı: {platform.name}")
    except Exception as e:
        logger.warning(f"Mobil emülasyon hatası: {e}")


def _apply_navigator_override(driver, platform: Platform):
    """
    CDP + JS injection ile navigator özelliklerini platform'a uygun hale getir.

    Antibot scriptleri şunları kontrol eder:
    - navigator.platform ("Win32", "MacIntel", "Linux armv81", "iPhone")
    - navigator.appVersion
    - navigator.userAgentData (Client Hints API)
    - navigator.oscpu (Firefox)
    - navigator.vendor

    Bu fonksiyon tüm bu değerleri tutarlı şekilde override eder.
    """
    nav = platform.navigatorOverride
    if not nav:
        return

    try:
        # 1. CDP: Network.setUserAgentOverride — HTTP header + JS navigator.userAgent
        ua_override = {
            "userAgent": platform.userAgent,
            "platform": nav.platform,
        }

        # Client Hints metadata (Chrome/Chromium tabanlı browserlar)
        if nav.brands:
            ua_metadata = {
                "brands": [{"brand": b["brand"], "version": b["version"]} for b in nav.brands],
                "fullVersionList": [{"brand": b["brand"], "version": nav.uaFullVersion} for b in nav.brands],
                "platform": nav.uaPlatform,
                "platformVersion": nav.uaPlatformVersion,
                "architecture": "arm" if "arm" in nav.platform.lower() else "x86",
                "model": nav.uaModel,
                "mobile": nav.uaMobile,
                "bitness": "64",
                "wow64": False,
            }
            ua_override["userAgentMetadata"] = ua_metadata

        driver.execute_cdp_cmd("Network.setUserAgentOverride", ua_override)

        # 2. JS injection: navigator properties override (sayfa yüklenmeden önce)
        override_js = _build_navigator_override_js(platform)
        driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
            "source": override_js,
        })

        logger.info(f"Navigator override uygulandı: {platform.name} → platform={nav.platform}")

    except Exception as e:
        logger.warning(f"Navigator override hatası: {e}")


def _build_navigator_override_js(platform: Platform) -> str:
    """
    Sayfa yüklenmeden önce çalışacak JS kodu oluştur.
    navigator.platform, appVersion, vendor, userAgentData vb. override eder.
    """
    nav = platform.navigatorOverride
    if not nav:
        return ""

    # Vendor ayarla — Safari ve Chrome farklı vendor kullanır
    if "Safari" in platform.userAgent and "Chrome" not in platform.userAgent:
        vendor = "Apple Computer, Inc."
    elif "Firefox" in platform.userAgent:
        vendor = ""  # Firefox vendor boş döner
    else:
        vendor = "Google Inc."

    # maxTouchPoints — mobil cihazlarda dokunmatik ekran
    max_touch = 5 if platform.hasTouch else 0

    # Mobil cihaz için ek ayarlar
    is_mobile = platform.isMobile
    vp_w = platform.viewport["width"]
    vp_h = platform.viewport["height"]
    dpr = platform.deviceScaleFactor
    hw_concurrency = 8 if is_mobile else 12  # Mobil için düşük
    device_memory = 8 if is_mobile else 16   # Mobil için 8GB

    # Brands JSON string
    import json
    brands_json = json.dumps(nav.brands) if nav.brands else "[]"
    full_version_list_json = json.dumps(
        [{"brand": b["brand"], "version": nav.uaFullVersion} for b in nav.brands]
    ) if nav.brands else "[]"

    oscpu_line = ""
    if nav.oscpu:
        oscpu_line = f"Object.defineProperty(navigator, 'oscpu', {{get: () => '{nav.oscpu}'}});"

    js = f"""
    (() => {{
        // navigator.platform
        Object.defineProperty(navigator, 'platform', {{
            get: () => '{nav.platform}'
        }});

        // navigator.appVersion
        Object.defineProperty(navigator, 'appVersion', {{
            get: () => '{nav.appVersion}'
        }});

        // navigator.vendor
        Object.defineProperty(navigator, 'vendor', {{
            get: () => '{vendor}'
        }});

        // navigator.maxTouchPoints
        Object.defineProperty(navigator, 'maxTouchPoints', {{
            get: () => {max_touch}
        }});

        // navigator.hardwareConcurrency
        Object.defineProperty(navigator, 'hardwareConcurrency', {{
            get: () => {hw_concurrency}
        }});

        // navigator.deviceMemory
        Object.defineProperty(navigator, 'deviceMemory', {{
            get: () => {device_memory}
        }});

        // navigator.oscpu (Firefox)
        {oscpu_line}

        // Screen / Window boyutları override (mobil emülasyon için)
        if ({str(is_mobile).lower()}) {{
            const vpW = {vp_w};
            const vpH = {vp_h};
            const dpr = {dpr};

            // screen dimensions
            Object.defineProperty(screen, 'width', {{ get: () => vpW }});
            Object.defineProperty(screen, 'height', {{ get: () => vpH }});
            Object.defineProperty(screen, 'availWidth', {{ get: () => vpW }});
            Object.defineProperty(screen, 'availHeight', {{ get: () => vpH }});

            // window dimensions
            Object.defineProperty(window, 'outerWidth', {{ get: () => vpW }});
            Object.defineProperty(window, 'outerHeight', {{ get: () => vpH }});
            Object.defineProperty(window, 'innerWidth', {{ get: () => vpW }});
            Object.defineProperty(window, 'innerHeight', {{ get: () => vpH }});
            Object.defineProperty(window, 'devicePixelRatio', {{ get: () => dpr }});

            // orientation -> portrait for mobile
            if (screen.orientation) {{
                Object.defineProperty(screen.orientation, 'type', {{ get: () => 'portrait-primary' }});
                Object.defineProperty(screen.orientation, 'angle', {{ get: () => 0 }});
            }}
        }}

        // navigator.userAgentData (Client Hints API)
        if (navigator.userAgentData || {str(bool(nav.brands)).lower()}) {{
            const brands = {brands_json};
            const fullVersionList = {full_version_list_json};
            const mobile = {'true' if nav.uaMobile else 'false'};
            const platformStr = '{nav.uaPlatform}';

            const uaData = {{
                brands: brands.map(b => ({{brand: b.brand, version: b.version}})),
                mobile: mobile,
                platform: platformStr,
                getHighEntropyValues: function(hints) {{
                    return Promise.resolve({{
                        brands: brands.map(b => ({{brand: b.brand, version: b.version}})),
                        fullVersionList: fullVersionList.map(b => ({{brand: b.brand, version: b.version}})),
                        mobile: mobile,
                        model: '{nav.uaModel}',
                        platform: platformStr,
                        platformVersion: '{nav.uaPlatformVersion}',
                        architecture: '{'arm' if 'arm' in nav.platform.lower() else 'x86'}',
                        bitness: '64',
                        uaFullVersion: '{nav.uaFullVersion}',
                        wow64: false
                    }});
                }},
                toJSON: function() {{
                    return {{
                        brands: this.brands,
                        mobile: this.mobile,
                        platform: this.platform
                    }};
                }}
            }};

            Object.defineProperty(navigator, 'userAgentData', {{
                get: () => uaData,
                configurable: true
            }});
        }}

        // WebGL Renderer / Vendor override
        const webglVendor = '{nav.webglVendor}';
        const webglRenderer = '{nav.webglRenderer}';

        const hookGetParameter = (proto) => {{
            const original = proto.getParameter;
            proto.getParameter = function(param) {{
                // UNMASKED_VENDOR_WEBGL (0x9245) veya VENDOR (0x1F00)
                if (param === 0x9245 || param === 37445) return webglVendor;
                // UNMASKED_RENDERER_WEBGL (0x9246) veya RENDERER (0x1F01)
                if (param === 0x9246 || param === 37446) return webglRenderer;
                return original.call(this, param);
            }};
        }};

        if (typeof WebGLRenderingContext !== 'undefined') {{
            hookGetParameter(WebGLRenderingContext.prototype);
        }}
        if (typeof WebGL2RenderingContext !== 'undefined') {{
            hookGetParameter(WebGL2RenderingContext.prototype);
        }}
    }})();
    """

    return js


async def navigate(url: str, wait_for: str = "networkidle",
                   wait_selector: Optional[str] = None,
                   timeout: int = 0, return_type: str = "json",
                   platform_id: Optional[str] = None) -> dict:
    """
    URL'e git, antibot challenge'ını geç, sonucu döndür.

    Args:
        url: Hedef URL
        wait_for: Bekleme stratejisi — "networkidle" | "selector" | "timeout"
        wait_selector: CSS selector (wait_for="selector" ise)
        timeout: Maksimum bekleme süresi (ms), 0 ise config default
        return_type: Dönüş tipi — "json" | "html" | "text" | "screenshot"
        platform_id: Cihaz profili ID'si (opsiyonel)

    Returns:
        dict — success, url, statusCode, data, cookies, timing
    """
    timeout_s = (timeout / 1000) if timeout > 0 else settings.timeout
    sem = get_semaphore()

    async with sem:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, _navigate_sync, url, wait_for, wait_selector, timeout_s, return_type, platform_id
        )


def _navigate_sync(url: str, wait_for: str, wait_selector: Optional[str],
                    timeout_s: float, return_type: str,
                    platform_id: Optional[str] = None) -> dict:
    """Senkron navigate işlemi (thread pool'da çalışır)."""
    driver = None
    start_time = time.time()
    challenge_start = start_time

    try:
        driver = create_driver(platform_id=platform_id)
        logger.info(f"Chrome başlatıldı — navigating to {url}")

        driver.get(url)
        challenge_start = time.time()

        # Bekleme stratejisi
        if wait_for == "selector" and wait_selector:
            _wait_for_selector(driver, wait_selector, timeout_s)
        elif wait_for == "networkidle":
            _wait_for_network_idle(driver, timeout_s)
        else:
            # timeout — sadece bekle
            time.sleep(min(timeout_s, 5))

        challenge_time = int((time.time() - challenge_start) * 1000)
        total_time = int((time.time() - start_time) * 1000)

        # Sonuç topla
        result = {
            "success": True,
            "url": driver.current_url,
            "statusCode": 200,
            "cookies": driver.get_cookies(),
            "timing": {
                "total": total_time,
                "challenge": challenge_time,
            },
        }

        # Dönüş tipi
        if return_type == "json":
            result["data"] = _extract_json(driver)
        elif return_type == "html":
            result["data"] = driver.page_source
        elif return_type == "text":
            result["data"] = driver.execute_script(
                "return document.body ? document.body.innerText : ''"
            )
        elif return_type == "screenshot":
            screenshot_b64 = driver.get_screenshot_as_base64()
            result["data"] = screenshot_b64

        return result

    except Exception as e:
        total_time = int((time.time() - start_time) * 1000)
        logger.error(f"Navigate hatası: {e}")
        return {
            "success": False,
            "error": str(e),
            "url": url,
            "statusCode": 0,
            "timing": {"total": total_time, "challenge": 0},
        }
    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass


def _wait_for_network_idle(driver, timeout_s: float):
    """
    Sayfa yüklenene ve antibot challenge geçene kadar bekle.
    Body'de JSON veya anlamlı içerik aranır.
    """
    start = time.time()
    while time.time() - start < timeout_s:
        time.sleep(2)

        try:
            # JSON yanıt kontrolü
            body_text = driver.execute_script("""
                var pre = document.querySelector('pre');
                if (pre) return pre.textContent;
                var body = document.body ? document.body.innerText : '';
                if (body.startsWith('{') || body.startsWith('[')) return body;
                return null;
            """)

            if body_text:
                try:
                    json.loads(body_text)
                    logger.info("API yanıtı body'den alındı")
                    return
                except json.JSONDecodeError:
                    pass

            # URL değişikliği kontrolü — antibot redirect sonrası
            current_url = driver.current_url
            if "__rr=1" not in current_url:
                body = driver.execute_script(
                    "return document.body ? document.body.innerText : ''"
                )
                if body and (body.startswith("{") or body.startswith("[")):
                    try:
                        json.loads(body)
                        logger.info("Redirect sonrası API yanıtı alındı")
                        return
                    except json.JSONDecodeError:
                        pass

            # Sayfa tam yüklendi mi kontrolü
            ready_state = driver.execute_script("return document.readyState")
            if ready_state == "complete":
                # Body boş değilse ve challenge elementi yoksa hazır
                has_challenge = driver.execute_script("""
                    return !!(document.querySelector('#challenge-running') ||
                              document.querySelector('.challenge-form') ||
                              document.querySelector('[data-challenge]'));
                """)
                if not has_challenge:
                    inner = driver.execute_script(
                        "return document.body ? document.body.innerText.length : 0"
                    )
                    if inner > 10:
                        return

        except Exception:
            continue

    logger.warning(f"Network idle timeout ({timeout_s}s)")


def _wait_for_selector(driver, selector: str, timeout_s: float):
    """CSS selector belirene kadar bekle."""
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC

    WebDriverWait(driver, timeout_s).until(
        EC.presence_of_element_located((By.CSS_SELECTOR, selector))
    )


def _extract_json(driver) -> dict | str | None:
    """Sayfadaki JSON verisini çıkar."""
    try:
        body_text = driver.execute_script("""
            var pre = document.querySelector('pre');
            if (pre) return pre.textContent;
            var body = document.body ? document.body.innerText : '';
            return body;
        """)

        if body_text:
            return json.loads(body_text)
    except (json.JSONDecodeError, Exception):
        pass

    # JSON bulunamadıysa raw text döndür
    try:
        return driver.execute_script(
            "return document.body ? document.body.innerText : ''"
        )
    except Exception:
        return None


async def take_screenshot(url: str, full_page: bool = True,
                          width: int = 1920, height: int = 1080,
                          timeout: int = 0,
                          platform_id: Optional[str] = None) -> bytes:
    """
    URL'in screenshot'ını al ve PNG bytes olarak döndür.
    """
    timeout_s = (timeout / 1000) if timeout > 0 else settings.timeout
    sem = get_semaphore()

    async with sem:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, _screenshot_sync, url, full_page, width, height, timeout_s, platform_id
        )


def _screenshot_sync(url: str, full_page: bool, width: int, height: int,
                      timeout_s: float, platform_id: Optional[str] = None) -> bytes:
    """Senkron screenshot işlemi."""
    driver = None
    try:
        driver = create_driver(platform_id=platform_id)

        # Viewport ayarla
        driver.set_window_size(width, height)

        driver.get(url)
        _wait_for_network_idle(driver, timeout_s)

        if full_page:
            # Tam sayfa height hesapla
            total_height = driver.execute_script(
                "return Math.max(document.body.scrollHeight, document.documentElement.scrollHeight)"
            )
            driver.set_window_size(width, total_height)
            time.sleep(0.5)

        return driver.get_screenshot_as_png()

    finally:
        if driver:
            try:
                driver.quit()
            except Exception:
                pass
