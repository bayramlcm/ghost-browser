"""
BrowserManager — Persistent Chrome instance with tab pooling.

Tek bir Chrome instance'ını sürekli açık tutar, her istek için yeni tab açar.
Idle tab'ları otomatik kapatır, crash durumunda yeniden başlatır.
"""

import asyncio
import json
import time
import logging
from typing import Optional

import undetected_chromedriver as uc

from app.config import settings

logger = logging.getLogger("ghost-browser")


class BrowserManager:
    """
    Singleton browser yöneticisi.

    - Chrome her zaman açık kalır (about:blank'te bekler)
    - Her istek yeni tab açar → işi bitince idle'a alır
    - 1 dakika idle tab → otomatik kapanır
    - Chrome crash → otomatik restart
    """

    def __init__(self):
        self._driver: Optional[uc.Chrome] = None
        self._lock = asyncio.Lock()
        self._tab_last_active: dict[str, float] = {}  # tab_handle → timestamp
        self._active_tabs: set[str] = set()  # şu an iş yapan tab'lar
        self._idle_tabs: list[str] = []  # yeniden kullanılabilir idle tab'lar
        self._cleanup_task: Optional[asyncio.Task] = None
        self._started = False
        self._start_time: float = 0
        self._request_count: int = 0

    # ─── Lifecycle ───────────────────────────────────────

    async def start(self):
        """Chrome'u başlat ve cleanup task'ı kur."""
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, self._create_driver)
        self._started = True
        self._start_time = time.time()
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())
        logger.info("BrowserManager başlatıldı — Chrome açık ve hazır")

    async def shutdown(self):
        """Chrome'u kapat ve cleanup task'ı durdur."""
        self._started = False
        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        if self._driver:
            try:
                self._driver.quit()
            except Exception:
                pass
            self._driver = None

        logger.info("BrowserManager kapatıldı")

    def _create_driver(self):
        """UC Chrome instance oluştur."""
        options = uc.ChromeOptions()
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--lang=ru-RU")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")

        self._driver = uc.Chrome(
            options=options,
            headless=settings.headless,
            use_subprocess=True,
            version_main=settings.chrome_version,
        )
        self._start_time = time.time()
        self._tab_last_active.clear()
        self._active_tabs.clear()
        logger.info("Chrome instance oluşturuldu")

    # ─── Health ──────────────────────────────────────────

    def _is_alive(self) -> bool:
        """Chrome hâlâ çalışıyor mu?"""
        if not self._driver:
            return False
        try:
            _ = self._driver.current_url
            return True
        except Exception:
            return False

    async def _ensure_alive(self):
        """Chrome ölmüşse yeniden başlat."""
        loop = asyncio.get_event_loop()
        alive = await loop.run_in_executor(None, self._is_alive)

        if not alive:
            logger.warning("Chrome ölmüş — yeniden başlatılıyor...")
            if self._driver:
                try:
                    self._driver.quit()
                except Exception:
                    pass
            await loop.run_in_executor(None, self._create_driver)

    async def _check_max_age(self):
        """Chrome max yaşını aştıysa yeniden başlat."""
        if settings.browser_max_age <= 0:
            return

        age = time.time() - self._start_time
        if age > settings.browser_max_age:
            logger.info(f"Chrome max yaşı aştı ({int(age)}s) — yeniden başlatılıyor...")
            loop = asyncio.get_event_loop()

            # Aktif tab yoksa restart
            if not self._active_tabs:
                if self._driver:
                    try:
                        self._driver.quit()
                    except Exception:
                        pass
                await loop.run_in_executor(None, self._create_driver)

    # ─── Fetch ───────────────────────────────────────────

    async def fetch(self, url: str, timeout: int = 0,
                    return_type: str = "json") -> dict:
        """
        Persistent browser ile URL'e git ve sonucu döndür.

        1. Yeni tab aç
        2. URL'e navigate et
        3. Challenge bekle
        4. Sonucu topla
        5. Tab'ı idle'a al (about:blank)
        """
        timeout_s = (timeout / 1000) if timeout > 0 else settings.timeout

        async with self._lock:
            await self._ensure_alive()

        self._request_count += 1

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._fetch_sync, url, timeout_s, return_type
        )

    def _get_or_create_tab(self, driver) -> str:
        """Idle tab varsa yeniden kullan, yoksa yeni aç."""
        # Idle tab havuzundan al
        while self._idle_tabs:
            handle = self._idle_tabs.pop()
            try:
                if handle in driver.window_handles:
                    driver.switch_to.window(handle)
                    self._tab_last_active.pop(handle, None)
                    return handle
            except Exception:
                continue

        # Yeni tab aç
        driver.execute_script("window.open('about:blank', '_blank');")
        handles = driver.window_handles
        new_handle = handles[-1]
        driver.switch_to.window(new_handle)
        return new_handle

    def _fetch_sync(self, url: str, timeout_s: float, return_type: str) -> dict:
        """Senkron fetch işlemi — tab bazlı, idle tab reuse."""
        start_time = time.time()
        tab_handle = None

        try:
            driver = self._driver

            # Tab al (idle varsa reuse, yoksa yeni)
            tab_handle = self._get_or_create_tab(driver)
            self._active_tabs.add(tab_handle)

            logger.info(f"Tab ({tab_handle[:8]}...) → {url}")

            # URL'e git
            driver.get(url)
            challenge_start = time.time()

            # İçerik bekle (hızlı polling)
            self._wait_for_content(driver, timeout_s)

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
                result["data"] = self._extract_json(driver)
            elif return_type == "html":
                result["data"] = driver.page_source
            elif return_type == "text":
                result["data"] = driver.execute_script(
                    "return document.body ? document.body.innerText : ''"
                )
            elif return_type == "screenshot":
                result["data"] = driver.get_screenshot_as_base64()

            # Tab'ı idle havuzuna geri koy (about:blank'e gitmeye gerek yok)
            self._active_tabs.discard(tab_handle)
            self._tab_last_active[tab_handle] = time.time()
            self._idle_tabs.append(tab_handle)

            logger.info(f"Tab ({tab_handle[:8]}...) tamamlandı — {total_time}ms")
            return result

        except Exception as e:
            total_time = int((time.time() - start_time) * 1000)
            logger.error(f"Fetch hatası: {e}")

            # Hatalı tab'ı temizle
            if tab_handle:
                self._active_tabs.discard(tab_handle)
                try:
                    self._close_tab(tab_handle)
                except Exception:
                    pass

            return {
                "success": False,
                "error": str(e),
                "url": url,
                "statusCode": 0,
                "timing": {"total": total_time, "challenge": 0},
            }

    # ─── Tab Cleanup ─────────────────────────────────────

    async def _cleanup_loop(self):
        """Background task — idle tab'ları periyodik temizle."""
        while self._started:
            try:
                await asyncio.sleep(10)
                await self._cleanup_idle_tabs()
                await self._check_max_age()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Cleanup hatası: {e}")

    async def _cleanup_idle_tabs(self):
        """Idle timeout'u geçmiş tab'ları kapat."""
        if not self._driver or not self._tab_last_active:
            return

        now = time.time()
        tabs_to_close = []

        for handle, last_active in list(self._tab_last_active.items()):
            if handle in self._active_tabs:
                continue
            if now - last_active > settings.tab_idle_timeout:
                tabs_to_close.append(handle)

        if tabs_to_close:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._close_tabs, tabs_to_close)

    def _close_tabs(self, handles: list[str]):
        """Tab'ları kapat (senkron)."""
        for handle in handles:
            try:
                self._close_tab(handle)
                logger.info(f"Idle tab kapatıldı ({handle[:8]}...)")
            except Exception:
                pass

    def _close_tab(self, handle: str):
        """Tek bir tab'ı kapat."""
        self._tab_last_active.pop(handle, None)
        self._active_tabs.discard(handle)
        if handle in self._idle_tabs:
            self._idle_tabs.remove(handle)

        try:
            current_handles = self._driver.window_handles
            if handle in current_handles:
                self._driver.switch_to.window(handle)
                self._driver.close()

                # Kalan tab'a geç
                remaining = self._driver.window_handles
                if remaining:
                    self._driver.switch_to.window(remaining[0])
        except Exception:
            pass

    # ─── Wait Logic ──────────────────────────────────────

    # Tek bir JS çağrısı ile tüm kontrolleri yap (round-trip minimizasyonu)
    _CHECK_CONTENT_JS = """
        var result = {ready: false, hasJson: false, body: null, hasChallenge: false};
        result.ready = (document.readyState === 'complete');
        result.hasChallenge = !!(document.querySelector('#challenge-running') ||
                                 document.querySelector('.challenge-form') ||
                                 document.querySelector('[data-challenge]'));
        var pre = document.querySelector('pre');
        if (pre) {
            result.body = pre.textContent;
        } else {
            var bodyText = document.body ? document.body.innerText : '';
            if (bodyText.length > 0 && (bodyText[0] === '{' || bodyText[0] === '[')) {
                result.body = bodyText;
            }
        }
        if (result.body) {
            try { JSON.parse(result.body); result.hasJson = true; } catch(e) {}
        }
        return result;
    """

    def _wait_for_content(self, driver, timeout_s: float):
        """
        Sayfa içeriği hazır olana kadar bekle.
        İlk kontrol hemen yapılır (sleep yok), sonra 0.2s aralıkla polling.
        """
        start = time.time()
        first_check = True

        while time.time() - start < timeout_s:
            # İlk kontrol hemen, sonraki kontroller 0.2s sonra
            if not first_check:
                time.sleep(0.2)
            first_check = False

            try:
                result = driver.execute_script(self._CHECK_CONTENT_JS)

                # JSON bulundu → hemen dön
                if result.get("hasJson"):
                    elapsed = int((time.time() - start) * 1000)
                    logger.info(f"İçerik bulundu — {elapsed}ms")
                    return

                # Sayfa yüklendi, challenge yok, içerik var → hazır
                if result.get("ready") and not result.get("hasChallenge"):
                    body = result.get("body")
                    if body and len(body) > 10:
                        elapsed = int((time.time() - start) * 1000)
                        logger.info(f"Sayfa hazır — {elapsed}ms")
                        return

            except Exception:
                continue

        logger.warning(f"Content wait timeout ({timeout_s}s)")

    def _extract_json(self, driver) -> dict | str | None:
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

        try:
            return driver.execute_script(
                "return document.body ? document.body.innerText : ''"
            )
        except Exception:
            return None

    # ─── Status ──────────────────────────────────────────

    def get_status(self) -> dict:
        """BrowserManager durumu."""
        alive = self._is_alive()
        age = int(time.time() - self._start_time) if self._start_time else 0
        return {
            "alive": alive,
            "uptime": age,
            "request_count": self._request_count,
            "active_tabs": len(self._active_tabs),
            "idle_tabs": len(self._tab_last_active) - len(self._active_tabs),
            "total_tabs": len(self._driver.window_handles) if alive and self._driver else 0,
        }


# Singleton instance
manager = BrowserManager()
