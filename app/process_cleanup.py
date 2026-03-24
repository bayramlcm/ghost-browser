"""
Process ve file descriptor temizleme yardımcı fonksiyonları.

Chrome subprocess sızıntılarını, zombie prosesleri ve orphan FD'leri temizler.
"""

import os
import signal
import logging
from typing import Optional

logger = logging.getLogger("ghost-browser")


def get_fd_count() -> int:
    """Mevcut prosesin açık file descriptor sayısını döndür (Linux only)."""
    try:
        return len(os.listdir("/proc/self/fd"))
    except (FileNotFoundError, PermissionError):
        return -1


def get_fd_info() -> dict:
    """FD durumu hakkında detaylı bilgi."""
    fd_count = get_fd_count()
    try:
        import resource
        soft, hard = resource.getrlimit(resource.RLIMIT_NOFILE)
    except (ImportError, Exception):
        soft, hard = -1, -1

    return {
        "open_fds": fd_count,
        "soft_limit": soft,
        "hard_limit": hard,
        "usage_percent": int(fd_count / soft * 1000) / 10 if soft > 0 and fd_count > 0 else 0,
    }


def cleanup_zombie_processes():
    """Zombie child process'leri reap et (waitpid ile)."""
    reaped = 0
    try:
        while True:
            pid, status = os.waitpid(-1, os.WNOHANG)
            if pid == 0:
                break
            reaped += 1
            logger.debug(f"Zombie process reaped: PID {pid}, status {status}")
    except ChildProcessError:
        # Bekleyen child process yok
        pass
    except Exception as e:
        logger.debug(f"Zombie reaping hatası (normal): {e}")

    if reaped > 0:
        logger.info(f"Toplam {reaped} zombie process temizlendi")
    return reaped


def kill_chrome_tree(driver) -> bool:
    """
    Chrome driver'a ait tüm proses ağacını zorla sonlandır.

    driver.quit() başarısız olursa bu fonksiyon devreye girer.
    ChromeDriver → Chrome → renderer/gpu/utility proseslerini öldürür.
    """
    killed = False

    # 1. ChromeDriver service process
    try:
        if hasattr(driver, "service") and hasattr(driver.service, "process"):
            proc = driver.service.process
            if proc and proc.poll() is None:
                _kill_process_tree(proc.pid)
                killed = True
                logger.info(f"ChromeDriver prosesi (PID:{proc.pid}) sonlandırıldı")
    except Exception as e:
        logger.debug(f"ChromeDriver kill hatası: {e}")

    # 2. Chrome browser process
    try:
        if hasattr(driver, "browser_pid"):
            pid = driver.browser_pid
            if pid:
                _kill_process_tree(pid)
                killed = True
                logger.info(f"Chrome prosesi (PID:{pid}) sonlandırıldı")
    except Exception as e:
        logger.debug(f"Chrome browser kill hatası: {e}")

    # 3. Zombie reaping
    cleanup_zombie_processes()

    return killed


def _kill_process_tree(pid: int):
    """
    Bir prosesin child'larını ve kendisini SIGKILL ile sonlandır.

    Linux'ta /proc/{pid}/task üzerinden child PID'leri bulur.
    """
    try:
        # Önce child prosesleri bul ve öldür
        children = _get_child_pids(pid)
        for child_pid in children:
            try:
                os.kill(child_pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass

        # Ana prosesi öldür
        os.kill(pid, signal.SIGKILL)

        # Waitpid ile zombie olmasını engelle
        try:
            os.waitpid(pid, os.WNOHANG)
        except ChildProcessError:
            pass

    except ProcessLookupError:
        pass  # Proses zaten ölmüş
    except PermissionError:
        logger.warning(f"PID {pid} kill için yetki yok")
    except Exception as e:
        logger.debug(f"Process tree kill hatası (PID:{pid}): {e}")


def _get_child_pids(parent_pid: int) -> list[int]:
    """Parent PID'e ait child PID'leri bul (Linux /proc)."""
    children = []
    try:
        proc_path = "/proc"
        if not os.path.exists(proc_path):
            return children

        for entry in os.listdir(proc_path):
            if not entry.isdigit():
                continue
            try:
                with open(f"{proc_path}/{entry}/stat", "r") as f:
                    stat = f.read().split()
                    # stat[3] = ppid
                    if len(stat) > 3 and int(stat[3]) == parent_pid:
                        children.append(int(entry))
            except (FileNotFoundError, PermissionError, ValueError, IndexError):
                continue
    except Exception:
        pass
    return children


def force_quit_driver(driver) -> None:
    """
    Driver'ı güvenli şekilde kapat. Başarısız olursa process tree'yi öldür.

    browser.py ve browser_manager.py'de driver cleanup için kullanılır.
    """
    if not driver:
        return

    # 1. Normal quit dene
    try:
        driver.quit()
        logger.debug("Driver.quit() başarılı")
        return
    except Exception as e:
        logger.warning(f"Driver.quit() başarısız: {e} — force kill yapılıyor")

    # 2. quit() başarısız → process tree'yi öldür
    kill_chrome_tree(driver)

    # 3. Son zombie temizliği
    cleanup_zombie_processes()
