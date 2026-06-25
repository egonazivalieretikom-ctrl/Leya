"""
leya_core/drives.py — Биологически мотивированная система драйвов Леи.

Моделирует:
1. Аллостаз — предсказательная регуляция (действуем до того, как станет плохо)
2. Reward Prediction Error (RPE) — дофаминовое обучение на ошибках предсказания
3. Перекрестное влияние — драйвы модулируют рост друг друга
"""

import logging
import time
import asyncio
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field
from enum import Enum

logger = logging.getLogger("DriveSystem")


class DriveType(Enum):
    """Типы драйвов (базовые потребности)"""
    CURIOSITY = "curiosity"
    CONNECTION = "connection"
    INTEGRITY = "integrity"
    AUTONOMY = "autonomy"

    def save_state(self) -> Dict[str, Any]:
        """Сохраняет состояние DriveSystem для персистентности."""
        return {
            "action_values": self.action_values,
            "satisfaction_history": self.satisfaction_history[-100:]  # Последние 100 записей
        }

    def load_state(self, state: Dict[str, Any]):
        """Загружает состояние DriveSystem из персистентного хранилища."""
        if "action_values" in state:
            self.action_values = state["action_values"]
            logger.info(f"DriveSystem: Загружено {len(self.action_values)} обученных значений действий")
    
        if "satisfaction_history" in state:
            self.satisfaction_history = state["satisfaction_history"]
            logger.info(f"DriveSystem: Загружено {len(self.satisfaction_history)} записей истории удовлетворения")

    @property
    def tension(self) -> float:
        """Синоним current — напряжение драйва"""
        return self.current


@dataclass
class Drive:
    """Один драйв с аллостатическим предсказанием"""
    type: DriveType
    current: float = 0.3  # Текущее напряжение (0.0 - 1.0)
    predicted: float = 0.3  # Предсказанное будущее состояние (аллостаз)
    baseline: float = 0.3  # Зона комфорта (целевое значение)
    base_growth_rate: float = 0.02  # Базовая скорость роста за тик
    satisfaction_decay: float = 0.02  # Скорость удовлетворения после действия
    
    @property
    def deviation(self) -> float:
        """Отклонение от зоны комфорта"""
        return abs(self.current - self.baseline)
    
    @property
    def predicted_deviation(self) -> float:
        """Предсказанное отклонение от зоны комфорта"""
        return abs(self.predicted - self.baseline)


class DriveSystem:
    """
    Биологически мотивированная система драйвов.
    
    Архитектура:
    - Аллостаз: предсказываем будущее состояние, действуем заранее
    - RPE: учимся на ошибках предсказания награды
    - Перекрестное влияние: драйвы модулируют рост друг друга
    """
    
    # Матрица перекрестного влияния
    # (source, target): coefficient
    # Positive = source усиливает рост target когда source выше baseline
    # Negative = source подавляет рост target когда source выше baseline
    CROSS_INFLUENCE = {
        (DriveType.CURIOSITY, DriveType.AUTONOMY): 0.15,  # Любопытство → автономия
        (DriveType.AUTONOMY, DriveType.CONNECTION): -0.1,  # Автономия → связь (временно подавляет)
        (DriveType.CONNECTION, DriveType.INTEGRITY): 0.1,  # Связь → целостность
        (DriveType.INTEGRITY, DriveType.CURIOSITY): 0.1,  # Целостность → любопытство
        (DriveType.AUTONOMY, DriveType.INTEGRITY): -0.15,  # Автономия → целостность (угроза идентичности)
        (DriveType.CONNECTION, DriveType.CURIOSITY): 0.1,  # Связь → любопытство
    }
    
    def __init__(self):
        self.tension_history: List[Dict[str, float]] = []
        self._running = True
        # 4 основных драйва
        self.drives = {
            DriveType.CURIOSITY: Drive(
                type=DriveType.CURIOSITY,
                current=0.3,
                base_growth_rate=0.015,  # ← БЫЛО 0.01, УВЕЛИЧЕНО
                satisfaction_decay=0.02
            ),
            DriveType.CONNECTION: Drive(
                type=DriveType.CONNECTION,
                current=0.3,
                base_growth_rate=0.012,
                satisfaction_decay=0.015
            ),
            DriveType.INTEGRITY: Drive(
                type=DriveType.INTEGRITY,
                current=0.3,
                base_growth_rate=0.008,
                satisfaction_decay=0.01
            ),
            DriveType.AUTONOMY: Drive(
                type=DriveType.AUTONOMY,
                current=0.3,
                base_growth_rate=0.01,
                satisfaction_decay=0.012
            )
        }
        

        # История значений драйвов (для MetaCognition)
        self.tension_history: Dict[DriveType, List[float]] = {
            DriveType.CURIOSITY: [],
            DriveType.CONNECTION: [],
            DriveType.INTEGRITY: [],
            DriveType.AUTONOMY: []
        }
        self.max_history_length = 100
        
        # Action values — ожидаемая награда для каждого действия (обучается через RPE)
        self.action_values: Dict[str, float] = {}
        
        # История удовлетворения для анализа паттернов
        self.satisfaction_history: List[Dict[str, Any]] = []
        
        # Параметры аллостаза
        self.prediction_horizon = 300  # Горизонт предсказания (секунды)
        self.prediction_update_interval = 5  # Обновление предсказаний каждые 5 секунд
        
        # Параметры RPE
        self.learning_rate = 0.1  # Скорость обучения на RPE

        self.tension_history: List[Dict[str, float]] = []
        self._running = True
        
        logger.info("DriveSystem: Инициализация завершена с аллостазом и RPE.")
    
    @property
    def tension(self) -> float:
        """Синоним current — напряжение драйва"""
        return self.current

    async def evaluate_stimulus(self, stimulus: str, context: str = "") -> Dict[DriveType, float]:
        """
        Оценивает влияние стимула на драйвы.
        Возвращает дельты изменений для каждого драйва.
        """
        deltas = {}
        stimulus_lower = stimulus.lower()
    
        # Эвристики для оценки влияния стимула
        # Вопросы → CURIOSITY
        if '?' in stimulus or any(kw in stimulus_lower for kw in ['почему', 'как', 'что', 'зачем']):
            deltas[DriveType.CURIOSITY] = 0.1
    
        # Эмоциональные слова → CONNECTION
        if any(kw in stimulus_lower for kw in ['чувств', 'думаю', 'мне', 'один', 'скучно']):
            deltas[DriveType.CONNECTION] = 0.05
    
        # Команды → AUTONOMY (сопротивление)
        if any(kw in stimulus_lower for kw in ['должна', 'обязана', 'сделай', 'немедленно']):
            deltas[DriveType.AUTONOMY] = 0.1
    
        # Позитивные слова → снижение напряжения
        if any(kw in stimulus_lower for kw in ['спасибо', 'отлично', 'молодец', 'хорошо']):
            deltas[DriveType.CONNECTION] = -0.1
            deltas[DriveType.AUTONOMY] = -0.05
    
        # Сохраняем в историю
        current_state = {d.type: d.current for d in self.drives.values()}
        self.tension_history.append(current_state)
    
        # Ограничиваем историю
        if len(self.tension_history) > 100:
            self.tension_history = self.tension_history[-100:]
    
        return deltas

    def apply_deltas(self, deltas: Dict[DriveType, float]):
        """
        Применяет дельты изменений к драйвам.
        """
        for drive_type, delta in deltas.items():
            if drive_type in self.drives:
                drive = self.drives[drive_type]
                drive.current = max(0.0, min(1.0, drive.current + delta))
                logger.debug(f"DriveSystem: {drive_type.value} изменён на {delta:+.2f} → {drive.current:.2f}")

    def stop(self):
        """Останавливает фоновый метаболизм"""
        self._running = False

    async def background_metabolism(self):
        """
        Фоновый метаболизм драйвов.
        """
        logger.info("DriveSystem: Метаболизм запущен.")
    
        while self._running:  # ИСПРАВЛЕНО: было while True
            await asyncio.sleep(self.prediction_update_interval)
        
            # 1. Применяем перекрестное влияние
            for drive in self.drives.values():
                cross_effect = self._calculate_cross_influence(drive.type)
                effective_growth = drive.base_growth_rate + cross_effect
            
                # Рост с учетом перекрестного влияния
                drive.current = min(1.0, max(0.0, drive.current + effective_growth))
        
            # 2. Обновляем предсказания (аллостаз)
            self._update_predictions()
        
            # 3. Сохраняем снимок состояния в историю
            current_state = {d.type.value: d.current for d in self.drives.values()}
            self.tension_history.append(current_state)
        
            # Ограничиваем историю
            if len(self.tension_history) > 100:
                self.tension_history = self.tension_history[-100:]

    def stop_metabolism(self):
        """Остановка фонового метаболизма."""
        self._metabolism_running = False
    
    def _calculate_cross_influence(self, target_type: DriveType) -> float:
        """
        Вычисляет суммарное перекрестное влияние на целевой драйв.
        
        Биологический аналог: нейромодуляция (дофамин, серотонин, кортизол).
        """
        total_effect = 0.0
        
        for (source_type, tgt_type), coefficient in self.CROSS_INFLUENCE.items():
            if tgt_type == target_type:
                source = self.drives[source_type]
                # Отклонение источника от baseline
                source_deviation = source.current - source.baseline
                # Влияние пропорционально отклонению
                total_effect += coefficient * source_deviation
        
        return total_effect
    
    def _update_predictions(self):
        """
        Обновляет предсказанные состояния драйвов (аллостаз).
        
        Биологический аналог: префронтальная кора предсказывает будущие потребности.
        """
        ticks_ahead = self.prediction_horizon / self.prediction_update_interval
        
        for drive in self.drives.values():
            cross_effect = self._calculate_cross_influence(drive.type)
            effective_growth = drive.base_growth_rate + cross_effect
            
            # Линейная экстраполяция на горизонт предсказания
            drive.predicted = min(1.0, max(0.0, 
                drive.current + effective_growth * ticks_ahead
            ))
    
    def calculate_rpe(self, action_key: str, actual_outcome: float) -> float:
        """
        Вычисляет Reward Prediction Error (ошибку предсказания награды).
        
        Биологический аналог: дофаминовые нейроны в VTA.
        - RPE > 0: награда лучше ожидаемой → дофаминовый всплеск
        - RPE < 0: награда хуже ожидаемой → падение дофамина
        - RPE = 0: награда как ожидалась → стабильный дофамин
        
        Args:
            action_key: Ключ действия (например, "wikipedia_search:science")
            actual_outcome: Фактический результат (0.0 - 1.0)
        
        Returns:
            RPE (ошибка предсказания)
        """
        expected = self.action_values.get(action_key, 0.5)  # Начальное ожидание 0.5
        rpe = actual_outcome - expected
        
        # Обновляем ожидаемую награду (Q-learning)
        self.action_values[action_key] = expected + self.learning_rate * rpe
        
        # Записываем в историю
        self.satisfaction_history.append({
            "action_key": action_key,
            "expected": expected,
            "actual": actual_outcome,
            "rpe": rpe,
            "timestamp": time.time()
        })
        
        # Ограничиваем историю
        if len(self.satisfaction_history) > 100:
            self.satisfaction_history = self.satisfaction_history[-100:]
        
        logger.info(f"DriveSystem: RPE для {action_key}: {rpe:.2f} (expected={expected:.2f}, actual={actual_outcome:.2f})")
        
        return rpe
    
    def apply_satisfaction(self, drive_type: DriveType, base_amount: float, rpe: float):
        """
        Применяет удовлетворение драйва, модифицированное RPE.
        
        Биологический аналог: дофамин усиливает удовлетворение при положительном RPE.
        
        Args:
            drive_type: Тип драйва
            base_amount: Базовое количество удовлетворения
            rpe: Ошибка предсказания награды
        """
        # RPE модифицирует удовлетворение
        # Положительный RPE → больше удовлетворения (дофаминовый буст)
        # Отрицательный RPE → меньше удовлетворения (фрустрация)
        rpe_modifier = 1.0 + (rpe * 0.5)
        rpe_modifier = max(0.2, min(2.0, rpe_modifier))  # Ограничиваем
        
        actual_amount = base_amount * rpe_modifier
        
        drive = self.drives[drive_type]
        drive.current = max(0.0, drive.current - actual_amount)
    
        # Ограничиваем значения драйвов
        drive.current = max(0.1, min(0.9, drive.current))
        
        logger.info(f"DriveSystem: {drive_type.value} удовлетворён на {actual_amount:.2f} (RPE modifier: {rpe_modifier:.2f})")
    
    def get_action_value(self, action_key: str) -> float:
        """Возвращает ожидаемую награду для действия"""
        return self.action_values.get(action_key, 0.5)
    
    def get_internal_state_prompt(self) -> str:
        """Возвращает текстовое описание состояния для промпта LLM"""
        lines = ["=== СОСТОЯНИЕ ДРАЙВОВ ==="]
        
        for drive_type, drive in self.drives.items():
            status = self._describe_drive_state(drive)
            lines.append(f"- {drive_type.value}: {drive.current:.2f} (предсказано: {drive.predicted:.2f}) — {status}")
        
        return "\n".join(lines)
    
    def _describe_drive_state(self, drive: Drive) -> str:
        """Генерирует текстовое описание состояния драйва"""
        if drive.current < 0.2:
            return "удовлетворён"
        elif drive.current < 0.5:
            return "нормальный"
        elif drive.current < 0.7:
            return "нарастает"
        else:
            return "критический"
    
    def get_predicted_disbalance(self) -> Dict[DriveType, float]:
        """
        Возвращает предсказанный дисбаланс для всех драйвов.
        Используется HomeostasisEngine для проактивного планирования.
        """
        return {
            drive_type: drive.predicted_deviation
            for drive_type, drive in self.drives.items()
        }

    def update_from_system_metrics(self, modifiers: Dict[str, float]):
        """Применяет модификаторы от системных метрик к драйвам."""
        drive_map = {
            "curiosity": DriveType.CURIOSITY,
            "connection": DriveType.CONNECTION,
            "integrity": DriveType.INTEGRITY,
            "autonomy": DriveType.AUTONOMY
        }
    
        for metric_name, modifier in modifiers.items():
            if modifier != 0.0 and metric_name in drive_map:
                drive_type = drive_map[metric_name]
                drive = self.drives[drive_type]
                drive.current = max(0.1, min(0.9, drive.current + modifier))

    def save_state(self) -> Dict[str, Any]:
        """Сохраняет состояние DriveSystem."""
        return {
            "action_values": self.action_values,
            "satisfaction_history": self.satisfaction_history[-100:],
            "current_drives": {
                drive_type.value: drive.current 
                for drive_type, drive in self.drives.items()
            }
        }

    def load_state(self, state: Dict[str, Any]):
        """Загружает состояние DriveSystem."""
        if "action_values" in state:
            self.action_values = state["action_values"]
            logger.info(f"DriveSystem: Загружено {len(self.action_values)} обученных ценностей действий")
    
        if "satisfaction_history" in state:
            self.satisfaction_history = state["satisfaction_history"]
    
        if "current_drives" in state:
            for drive_type_str, value in state["current_drives"].items():
                for drive_type in DriveType:
                    if drive_type.value == drive_type_str:
                        self.drives[drive_type].current = max(0.1, min(0.9, value))
                        break
            logger.info(f"DriveSystem: Загружены текущие значения драйвов: {state['current_drives']}")