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
from app.platforms import get_platform, Platform, NavigatorOverride
from app.process_cleanup import force_quit_driver, cleanup_zombie_processes, get_fd_info, kill_chrome_tree

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
        self._max_requests_before_restart: int = 500  # Her 500 istekte Chrome restart

    # ─── Lifecycle ───────────────────────────────────────

    async def start(self):
        """Chrome'u başlat ve cleanup task'ı kur."""
        loop = asyncio.get_event_loop()
        try:
            await asyncio.wait_for(
                loop.run_in_executor(None, self._create_driver),
                timeout=120  # 2 dakika timeout
            )
        except asyncio.TimeoutError:
            logger.error("Chrome başlatma TIMEOUT (120s) — ChromeDriver indirme veya Chrome başlatma takıldı!")
            raise RuntimeError("Chrome startup timeout — sunucuda Chrome başlatılamadı")
        except Exception as e:
            logger.error(f"Chrome başlatma HATASI: {e}", exc_info=True)
            raise
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
            force_quit_driver(self._driver)
            self._driver = None

        # Son zombie temizliği
        cleanup_zombie_processes()
        logger.info("BrowserManager kapatıldı")

    def _create_driver(self, platform_id: Optional[str] = None):
        """UC Chrome instance oluştur. Eski driver varsa process tree'sini öldür."""
        # Eski driver'ı temizle (restart senaryosu)
        if self._driver:
            logger.info("Eski Chrome instance temizleniyor...")
            force_quit_driver(self._driver)
            self._driver = None
            cleanup_zombie_processes()

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
        options.add_argument("--disable-software-rasterizer")
        options.add_argument("--disable-extensions")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-default-apps")
        options.add_argument("--remote-debugging-port=0")

        # Docker'da Chrome binary path'ini açıkça belirt
        if settings.chrome_binary:
            options.binary_location = settings.chrome_binary

        logger.info(f"ChromeDriver oluşturuluyor... (headless={settings.headless}, "
                     f"version={settings.chrome_version}, binary={settings.chrome_binary})")

        self._driver = uc.Chrome(
            options=options,
            headless=settings.headless,
            use_subprocess=True,
            version_main=settings.chrome_version,
            browser_executable_path=settings.chrome_binary,
        )

        logger.info("ChromeDriver oluşturuldu, emülasyon uygulanıyor...")

        # Mobil emülasyon — CDP komutu ile
        if platform and platform.isMobile:
            self._apply_mobile_emulation(platform)

        # Navigator fingerprint override — antibot bypass
        if platform and platform.navigatorOverride:
            from app.browser import _apply_navigator_override
            _apply_navigator_override(self._driver, platform)

        self._start_time = time.time()
        self._tab_last_active.clear()
        self._active_tabs.clear()
        self._idle_tabs.clear()
        logger.info(f"Chrome instance oluşturuldu{' — ' + platform.name if platform else ''}")

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
                force_quit_driver(self._driver)
                self._driver = None
            cleanup_zombie_processes()
            await loop.run_in_executor(None, self._create_driver)

    async def _check_max_age(self):
        """Chrome max yaşını veya istek limitini aştıysa yeniden başlat."""
        should_restart = False
        reason = ""

        # Yaş kontrolü
        if settings.browser_max_age > 0:
            age = time.time() - self._start_time
            if age > settings.browser_max_age:
                should_restart = True
                reason = f"max yaş aşıldı ({int(age)}s)"

        # İstek sayısı kontrolü (FD sızıntısını sınırlamak için)
        if self._request_count >= self._max_requests_before_restart:
            should_restart = True
            reason = f"istek limiti aşıldı ({self._request_count})"

        if should_restart and not self._active_tabs:
            logger.info(f"Chrome yeniden başlatılıyor — {reason}")
            loop = asyncio.get_event_loop()
            if self._driver:
                force_quit_driver(self._driver)
                self._driver = None
            cleanup_zombie_processes()
            await loop.run_in_executor(None, self._create_driver)
            self._request_count = 0

    # ─── Fetch ───────────────────────────────────────────

    def _apply_mobile_emulation(self, platform: Platform):
        """CDP komutu ile mobil cihaz emülasyonu uygula."""
        try:
            self._driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
                "width": platform.viewport["width"],
                "height": platform.viewport["height"],
                "deviceScaleFactor": platform.deviceScaleFactor,
                "mobile": platform.isMobile,
            })
            self._driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {
                "enabled": platform.hasTouch,
            })
            logger.info(f"Mobil emülasyon uygulandı: {platform.name}")
        except Exception as e:
            logger.warning(f"Mobil emülasyon hatası: {e}")

    def _apply_platform_to_tab(self, platform: Platform):
        """Tab bazlı CDP ile user-agent, viewport ve navigator override uygula."""
        try:
            # 1. User-Agent + Client Hints — tam navigator override
            nav = platform.navigatorOverride
            if nav:
                ua_override = {
                    "userAgent": platform.userAgent,
                    "platform": nav.platform,
                }
                if nav.brands:
                    ua_override["userAgentMetadata"] = {
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
                self._driver.execute_cdp_cmd("Network.setUserAgentOverride", ua_override)
            else:
                self._driver.execute_cdp_cmd("Network.setUserAgentOverride", {
                    "userAgent": platform.userAgent,
                })

            # 2. Viewport / Device metrics
            self._driver.execute_cdp_cmd("Emulation.setDeviceMetricsOverride", {
                "width": platform.viewport["width"],
                "height": platform.viewport["height"],
                "deviceScaleFactor": platform.deviceScaleFactor,
                "mobile": platform.isMobile,
            })

            # 3. Touch emulation
            if platform.hasTouch:
                self._driver.execute_cdp_cmd("Emulation.setTouchEmulationEnabled", {
                    "enabled": True,
                })

            # 4. JS injection — navigator properties override
            if nav:
                from app.browser import _build_navigator_override_js
                override_js = _build_navigator_override_js(platform)
                self._driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                    "source": override_js,
                })

            logger.info(f"Tab platform override: {platform.name} → {nav.platform if nav else 'default'}")
        except Exception as e:
            logger.warning(f"Tab platform override hatası: {e}")

    async def fetch(self, url: str, timeout: int = 0,
                    return_type: str = "json",
                    platform_id: Optional[str] = None) -> dict:
        """
        Persistent browser ile URL'e git ve sonucu döndür.

        1. Yeni tab aç
        2. Platform override uygula (CDP)
        3. URL'e navigate et
        4. Challenge bekle
        5. Sonucu topla
        6. Tab'ı idle'a al
        """
        timeout_s = (timeout / 1000) if timeout > 0 else settings.timeout

        async with self._lock:
            await self._ensure_alive()

        self._request_count += 1

        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(
            None, self._fetch_sync, url, timeout_s, return_type, platform_id
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

    def _fetch_sync(self, url: str, timeout_s: float, return_type: str,
                    platform_id: Optional[str] = None) -> dict:
        """Senkron fetch işlemi — tab bazlı, idle tab reuse."""
        start_time = time.time()
        tab_handle = None

        try:
            driver = self._driver

            # Tab al (idle varsa reuse, yoksa yeni)
            tab_handle = self._get_or_create_tab(driver)
            self._active_tabs.add(tab_handle)

            # Platform override uygula (tab bazlı CDP)
            platform = get_platform(platform_id) if platform_id else None
            if platform:
                self._apply_platform_to_tab(platform)

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
        """Background task — idle tab'ları periyodik temizle, zombie reap, FD izle."""
        while self._started:
            try:
                await asyncio.sleep(10)
                await self._cleanup_idle_tabs()
                await self._check_max_age()

                # Zombie process temizliği
                cleanup_zombie_processes()

                # FD monitoring — uyarı logu
                fd_info = get_fd_info()
                if fd_info["usage_percent"] > 75:
                    logger.warning(
                        f"⚠️ FD kullanımı yüksek: {fd_info['open_fds']}/{fd_info['soft_limit']} "
                        f"(%{fd_info['usage_percent']})"
                    )
                elif fd_info["open_fds"] > 0 and fd_info["open_fds"] % 100 == 0:
                    logger.info(f"FD durumu: {fd_info['open_fds']}/{fd_info['soft_limit']}")

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
