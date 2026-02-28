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

logger = logging.getLogger("ghost-browser")

# Eşzamanlı browser erişimini sınırlayan semaphore
_semaphore: Optional[asyncio.Semaphore] = None


def get_semaphore() -> asyncio.Semaphore:
    """Lazy-init semaphore (event loop hazır olduğunda)."""
    global _semaphore
    if _semaphore is None:
        _semaphore = asyncio.Semaphore(settings.max_concurrent)
    return _semaphore


def create_driver() -> uc.Chrome:
    """
    Yeni undetected-chromedriver Chrome instance oluştur.

    - Binary patch uygular (cdc_ marker temizliği)
    - Antibot-friendly ayarlar
    """
    options = uc.ChromeOptions()
    options.add_argument("--window-size=1920,1080")
    options.add_argument("--lang=ru-RU")
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
    return driver


async def navigate(url: str, wait_for: str = "networkidle",
                   wait_selector: Optional[str] = None,
                   timeout: int = 0, return_type: str = "json") -> dict:
    """
    URL'e git, antibot challenge'ını geç, sonucu döndür.

    Args:
        url: Hedef URL
        wait_for: Bekleme stratejisi — "networkidle" | "selector" | "timeout"
        wait_selector: CSS selector (wait_for="selector" ise)
        timeout: Maksimum bekleme süresi (ms), 0 ise config default
        return_type: Dönüş tipi — "json" | "html" | "text" | "screenshot"

    Returns:
        dict — success, url, statusCode, data, cookies, timing
    """
    timeout_s = (timeout / 1000) if timeout > 0 else settings.timeout
    sem = get_semaphore()

    async with sem:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, _navigate_sync, url, wait_for, wait_selector, timeout_s, return_type
        )


def _navigate_sync(url: str, wait_for: str, wait_selector: Optional[str],
                    timeout_s: float, return_type: str) -> dict:
    """Senkron navigate işlemi (thread pool'da çalışır)."""
    driver = None
    start_time = time.time()
    challenge_start = start_time

    try:
        driver = create_driver()
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
                          timeout: int = 0) -> bytes:
    """
    URL'in screenshot'ını al ve PNG bytes olarak döndür.
    """
    timeout_s = (timeout / 1000) if timeout > 0 else settings.timeout
    sem = get_semaphore()

    async with sem:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, _screenshot_sync, url, full_page, width, height, timeout_s
        )


def _screenshot_sync(url: str, full_page: bool, width: int, height: int,
                      timeout_s: float) -> bytes:
    """Senkron screenshot işlemi."""
    driver = None
    try:
        driver = create_driver()

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
