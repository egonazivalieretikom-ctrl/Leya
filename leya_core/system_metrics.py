"""
leya_core/system_metrics.py — Мониторинг реальных ресурсов системы.
Привязывает драйвы к физическим метрикам хоста.
"""

import logging
import time
from typing import Dict, Any

logger = logging.getLogger("SystemMetrics")

try:
    import psutil
    PSUTIL_AVAILABLE = True
except ImportError:
    PSUTIL_AVAILABLE = False
    logger.warning("SystemMetrics: psutil не установлен. Установите: pip install psutil")


class SystemMetrics:
    """Собирает метрики системы и влияет на драйвы."""
    
    def __init__(self):
        self.last_metrics: Dict[str, float] = {}
        self._prev_disk_io = None
        self._prev_net_io = None
        self._prev_time = None
    
    def collect(self) -> Dict[str, float]:
        """
        Собирает текущие метрики системы.
        Возвращает словарь с нормализованными значениями (0.0 - 1.0).
        """
        if not PSUTIL_AVAILABLE:
            return self._fallback_metrics()
        
        try:
            now = time.time()
            
            # CPU usage (0-100 → 0.0-1.0)
            cpu_percent = psutil.cpu_percent(interval=None) / 100.0
            
            # RAM usage (0-100 → 0.0-1.0)
            ram_percent = psutil.virtual_memory().percent / 100.0
            
            # Disk usage (0-100 → 0.0-1.0)
            disk_percent = psutil.disk_usage('/').percent / 100.0
            
            # Disk I/O (скорость чтения/записи)
            disk_io = psutil.disk_io_counters()
            disk_io_rate = 0.0
            if disk_io and self._prev_disk_io and self._prev_time:
                dt = now - self._prev_time
                if dt > 0:
                    read_rate = (disk_io.read_bytes - self._prev_disk_io.read_bytes) / dt
                    write_rate = (disk_io.write_bytes - self._prev_disk_io.write_bytes) / dt
                    # Нормализуем: 10MB/s = 1.0
                    disk_io_rate = min(1.0, (read_rate + write_rate) / (10 * 1024 * 1024))
            
            if disk_io:
                self._prev_disk_io = disk_io
            
            # Network I/O
            net_io = psutil.net_io_counters()
            net_io_rate = 0.0
            if net_io and self._prev_net_io and self._prev_time:
                dt = now - self._prev_time
                if dt > 0:
                    sent_rate = (net_io.bytes_sent - self._prev_net_io.bytes_sent) / dt
                    recv_rate = (net_io.bytes_recv - self._prev_net_io.bytes_recv) / dt
                    # Нормализуем: 1MB/s = 1.0
                    net_io_rate = min(1.0, (sent_rate + recv_rate) / (1024 * 1024))
            
            if net_io:
                self._prev_net_io = net_io
            
            self._prev_time = now
            
            metrics = {
                "cpu": cpu_percent,
                "ram": ram_percent,
                "disk": disk_percent,
                "disk_io": disk_io_rate,
                "net_io": net_io_rate,
                "battery": self._get_battery()
            }
            
            self.last_metrics = metrics
            return metrics
        
        except Exception as e:
            logger.error(f"SystemMetrics: Ошибка сбора метрик: {e}")
            return self._fallback_metrics()
    
    def _get_battery(self) -> float:
        """Возвращает уровень заряда батареи (0.0-1.0) или 1.0 если нет батареи."""
        try:
            battery = psutil.sensors_battery()
            if battery:
                return battery.percent / 100.0
        except Exception:
            pass
        return 1.0  # Нет батареи = "полный заряд"
    
    def _fallback_metrics(self) -> Dict[str, float]:
        """Заглушка если psutil не установлен."""
        return {
            "cpu": 0.5,
            "ram": 0.5,
            "disk": 0.5,
            "disk_io": 0.5,
            "net_io": 0.5,
            "battery": 1.0
        }
    
    def get_drive_modifiers(self) -> Dict[str, float]:
        """
        Возвращает модификаторы для драйвов на основе системных метрик.
        
        Логика:
        - CPU high → AUTONOMY страдает (система перегружена)
        - RAM high → INTEGRITY страдает (нехватка памяти)
        - Disk I/O high → CURIOSITY растёт (активное чтение данных)
        - Net I/O high → CONNECTION растёт (активное общение)
        - Battery low → все драйвы страдают (угроза существованию)
        """
        metrics = self.last_metrics or self.collect()
        
        modifiers = {
            "curiosity": 0.0,
            "connection": 0.0,
            "integrity": 0.0,
            "autonomy": 0.0
        }
        
        # CPU перегрузка снижает автономию
        if metrics["cpu"] > 0.8:
            modifiers["autonomy"] -= 0.02
        elif metrics["cpu"] < 0.3:
            modifiers["autonomy"] += 0.01
        
        # RAM нехватка снижает целостность
        if metrics["ram"] > 0.85:
            modifiers["integrity"] -= 0.03
        elif metrics["ram"] < 0.5:
            modifiers["integrity"] += 0.01
        
        # Disk I/O повышает любознательность (активное чтение)
        if metrics["disk_io"] > 0.5:
            modifiers["curiosity"] += 0.02
        
        # Network I/O повышает связь
        if metrics["net_io"] > 0.3:
            modifiers["connection"] += 0.02
        
        # Батарея: низкий заряд = стресс для всех
        if metrics["battery"] < 0.2:
            for key in modifiers:
                modifiers[key] -= 0.05
            logger.warning(f"SystemMetrics: ⚡ Низкий заряд батареи: {metrics['battery']:.0%}")
        
        return modifiers