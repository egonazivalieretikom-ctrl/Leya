import psutil
import pygetwindow as gw
from Core.logger import log

class SystemMonitor:
    def __init__(self):
        log.info("🖥️ System Monitor (Proprioception) initialized")
        
    def get_active_window(self) -> str:
        try:
            window = gw.getActiveWindow()
            if window and window.title:
                return window.title.strip()
        except Exception as e:
            log.debug("Could not get active window", error=str(e))
        return "Unknown"

    def get_system_stats(self) -> dict:
        try:
            # Быстрый снимок нагрузки
            cpu = psutil.cpu_percent(interval=0.1)
            ram = psutil.virtual_memory().percent
            return {"cpu": cpu, "ram": ram}
        except Exception as e:
            return {"cpu": 0.0, "ram": 0.0}