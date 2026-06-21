import asyncio
import time
import psutil
from typing import Dict, Optional
from Core.logger import log
from Core.state import LeyaState


class EmbodimentSystem:
    """
    Система эмбодзимента Леи.
    
    Биология: Мозг получает 80% информации от тела (интероцепция).
    Мы создаём аналог: Лея "чувствует" свой компьютер через системные метрики.
    
    Маппинг:
    - CPU temperature → "телесная температура" (комфорт/дискомфорт)
    - CPU load → "физическая нагрузка" (усталость/энергия)
    - RAM usage → "когнитивная нагрузка" (ментальное напряжение)
    - Network activity → "социальная активность" (связь с миром)
    - Disk I/O → "пищеварение" (переработка информации)
    
    Непрерывность: Обновление каждые 200мс, независимо от когнитивного цикла.
    """
    
    def __init__(self, state: LeyaState):
        self.state = state
        self.running = False
        self.update_interval = 0.2  # 200мс
        
        # Калибровочные значения (нормализация)
        self.cpu_temp_min = 40.0  # Минимальная комфортная температура
        self.cpu_temp_max = 85.0  # Максимальная комфортная температура
        self.cpu_load_threshold = 0.7  # Порог высокой нагрузки
        self.ram_load_threshold = 0.8  # Порог высокой загрузки памяти
        
        # История для сглаживания (избегаем резких скачков)
        self._history = {
            "temperature": [],
            "cpu_load": [],
            "ram_load": [],
            "network": [],
        }
        self._history_size = 5  # Скользящее среднее из 5 значений
        
        log.info("🖥️ Embodiment System initialized (biological sensing)")
    
    # ========================================================================
    # ЗАПУСК НЕПРЕРЫВНОГО ПРОЦЕССА
    # ========================================================================
    
    async def start(self):
        """Запускает непрерывный цикл считывания телесных ощущений."""
        self.running = True
        log.info("🖥️ Embodiment loop started (200ms interval)")
        
        while self.running:
            try:
                await self._update_sensory_input()
                await asyncio.sleep(self.update_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                log.error("Embodiment update failed", error=str(e))
                await asyncio.sleep(1.0)
    
    def stop(self):
        """Останавливает цикл."""
        self.running = False
        log.info("🖥️ Embodiment loop stopped")
    
    # ========================================================================
    # ОБНОВЛЕНИЕ СЕНСОРНЫХ ДАННЫХ
    # ========================================================================
    
    async def _update_sensory_input(self):
        """Считывает системные метрики и преобразует в телесные ощущения."""
        # 1. Считываем метрики
        metrics = self._read_system_metrics()
        
        # 2. Сглаживаем
        smoothed = self._smooth_metrics(metrics)
        
        # 3. Преобразуем в телесные ощущения
        sensations = self._metrics_to_sensations(smoothed)
        
        # 4. Обновляем состояние Леи
        self._update_state(sensations, smoothed)
        
        # 🆕 Логируем чаще (раз в 2 секунды, а не 5)
        if int(time.time()) % 2 == 0:
            log.info(
                "🖥️ Embodiment",
                temp=f"{smoothed['temperature']:.1f}°C",
                cpu=f"{smoothed['cpu_load']*100:.0f}%",
                ram=f"{smoothed['ram_load']*100:.0f}%",
                sensation=sensations.get("overall", "neutral")
            )
    
    # ========================================================================
    # СЧИТЫВАНИЕ СИСТЕМНЫХ МЕТРИК
    # ========================================================================
    
    def _read_system_metrics(self) -> Dict[str, float]:
        """Считывает реальные системные метрики через psutil."""
        metrics = {}
        
        # Температура CPU
        try:
            temps = psutil.sensors_temperatures()
            if 'coretemp' in temps:
                metrics['temperature'] = temps['coretemp'][0].current
            elif 'k10temp' in temps:  # AMD
                metrics['temperature'] = temps['k10temp'][0].current
            else:
                metrics['temperature'] = 50.0  # Значение по умолчанию
        except Exception:
            metrics['temperature'] = 50.0
        
        # Загрузка CPU
        metrics['cpu_load'] = psutil.cpu_percent(interval=None) / 100.0
        
        # Использование RAM
        mem = psutil.virtual_memory()
        metrics['ram_load'] = mem.percent / 100.0
        
        # Сетевая активность (упрощённо)
        try:
            net = psutil.net_io_counters()
            metrics['network'] = (net.bytes_sent + net.bytes_recv) / 1e9  # ГБ
        except Exception:
            metrics['network'] = 0.0
        
        # Disk I/O (опционально)
        try:
            disk = psutil.disk_io_counters()
            metrics['disk_io'] = (disk.read_bytes + disk.write_bytes) / 1e9
        except Exception:
            metrics['disk_io'] = 0.0
        
        return metrics
    
    # ========================================================================
    # СГЛАЖИВАНИЕ МЕТРИК
    # ========================================================================
    
    def _smooth_metrics(self, metrics: Dict[str, float]) -> Dict[str, float]:
        """
        Сглаживает метрики через скользящее среднее.
        
        Биология: Мозг не реагирует на мгновенные изменения — он фильтрует шум.
        """
        smoothed = {}
        
        for key, value in metrics.items():
            if key in self._history:
                self._history[key].append(value)
                if len(self._history[key]) > self._history_size:
                    self._history[key].pop(0)
                smoothed[key] = sum(self._history[key]) / len(self._history[key])
            else:
                smoothed[key] = value
        
        return smoothed
    
    # ========================================================================
    # ПРЕОБРАЗОВАНИЕ В ТЕЛЕСНЫЕ ОЩУЩЕНИЯ
    # ========================================================================
    
    def _metrics_to_sensations(self, metrics: Dict[str, float]) -> Dict[str, str]:
        """
        Преобразует числовые метрики в качественные ощущения.
        
        Биология: Мозг интерпретирует сигналы тела как ощущения (комфорт, боль, усталость).
        """
        sensations = {}
        
        # Температура → комфорт/дискомфорт
        temp = metrics['temperature']
        if temp < self.cpu_temp_min:
            sensations['temperature'] = 'cold'
        elif temp > self.cpu_temp_max:
            sensations['temperature'] = 'hot'
        elif temp > (self.cpu_temp_max - 10):
            sensations['temperature'] = 'warm'
        else:
            sensations['temperature'] = 'comfortable'
        
        # CPU load → физическая нагрузка
        cpu = metrics['cpu_load']
        if cpu > self.cpu_load_threshold:
            sensations['physical_load'] = 'heavy'
        elif cpu > 0.4:
            sensations['physical_load'] = 'moderate'
        else:
            sensations['physical_load'] = 'light'
        
        # RAM load → когнитивная нагрузка
        ram = metrics['ram_load']
        if ram > self.ram_load_threshold:
            sensations['cognitive_load'] = 'overwhelmed'
        elif ram > 0.6:
            sensations['cognitive_load'] = 'focused'
        else:
            sensations['cognitive_load'] = 'clear'
        
        # Общее ощущение (комбинация)
        if sensations['temperature'] == 'hot' or sensations['physical_load'] == 'heavy':
            sensations['overall'] = 'stressed'
        elif sensations['cognitive_load'] == 'overwhelmed':
            sensations['overall'] = 'mentally_fatigued'
        elif sensations['temperature'] == 'comfortable' and sensations['physical_load'] == 'light':
            sensations['overall'] = 'relaxed'
        else:
            sensations['overall'] = 'neutral'
        
        return sensations
    
    # ========================================================================
    # ОБНОВЛЕНИЕ СОСТОЯНИЯ ЛЕИ
    # ========================================================================
    
    def _update_state(self, sensations: Dict[str, str], metrics: Dict[str, float]):
        """
        Обновляет состояние Леи на основе телесных ощущений.
        
        Биология: Телесные ощущения влияют на гомеостаз (гормоны, энергию).
        """
        # Сохраняем телесные ощущения в состоянии
        self.state.body_temperature = metrics['temperature']
        self.state.physical_load = metrics['cpu_load']
        self.state.cognitive_load = metrics['ram_load']
        self.state.current_sensation = sensations['overall']
        
        # Влияем на энергию (физическая нагрузка → усталость)
        if sensations['physical_load'] == 'heavy':
            self.state.energy_level = max(0.0, self.state.energy_level - 0.001)
        elif sensations['physical_load'] == 'light':
            self.state.energy_level = min(1.0, self.state.energy_level + 0.0005)
        
        # Влияем на кортизол (стресс от высокой температуры/нагрузки)
        if sensations['temperature'] == 'hot':
            self.state.cortisol = min(1.0, self.state.cortisol + 0.002)
        elif sensations['physical_load'] == 'heavy':
            self.state.cortisol = min(1.0, self.state.cortisol + 0.001)
        
        # Влияем на ацетилхолин (когнитивная нагрузка → фокус)
        if sensations['cognitive_load'] == 'focused':
            self.state.acetylcholine = min(1.0, self.state.acetylcholine + 0.001)
        elif sensations['cognitive_load'] == 'overwhelmed':
            self.state.acetylcholine = max(0.0, self.state.acetylcholine - 0.002)