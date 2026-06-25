"""
leya_core/drives.py — Система драйвов (мотиваций) Леи.
Этап 3.3: Полная переработка. Биологическая модель, RPE, метаболизм.
"""
import asyncio
import logging
import time
from leya_core.config import settings
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any, Tuple

logger = logging.getLogger("DriveSystem")


# =================================================================================
# МОДЕЛИ ДАННЫХ
# =================================================================================

class DriveType(Enum):
    """Типы драйвов (биологических потребностей)."""
    CURIOSITY = "CURIOSITY"  # Любопытство, стремление к знанию
    CONNECTION = "CONNECTION"  # Потребность в связи с другими
    REST = "REST"  # Потребность в отдыхе
    CREATIVITY = "CREATIVITY"  # Потребность в самовыражении
    UNDERSTANDING = "UNDERSTANDING"  # Стремление к пониманию
    AUTONOMY = "AUTONOMY"  # Потребность в независимости


@dataclass
class Drive:
    """Биологический драйв с текущим состоянием."""
    type: DriveType
    current: float = 0.5  # Текущее значение (0.0 - 1.0)
    tension: float = 0.0  # Напряжение (накопленная неудовлетворенность)
    target: float = 0.5  # Целевое значение (гомеостатический баланс)
    metabolism_rate: float = 0.01  # Скорость метаболизма (нарастание tension)
    last_update: float = field(default_factory=time.time)
    
    def __post_init__(self):
        """Валидация полей."""
        self.current = max(0.0, min(1.0, self.current))
        self.tension = max(0.0, min(1.0, self.tension))
        self.target = max(0.0, min(1.0, self.target))
        self.metabolism_rate = max(0.0, min(0.1, self.metabolism_rate))
    
    def update_tension(self, current_time: float):
        """Обновление напряжения на основе метаболизма."""
        time_passed = current_time - self.last_update
        hours_passed = time_passed / 3600.0
        
        # Напряжение нарастает со временем (биологический метаболизм)
        tension_increase = self.metabolism_rate * hours_passed
        
        # Если текущее значение ниже целевого — напряжение растет быстрее
        if self.current < self.target:
            deficit = self.target - self.current
            tension_increase += deficit * 0.1 * hours_passed
        
        self.tension = max(0.0, min(1.0, self.tension + tension_increase))
        self.last_update = current_time
    
    def apply_delta(self, delta: float):
        """Применение дельты к текущему значению."""
        self.current = max(0.0, min(1.0, self.current + delta))
        
        # Если значение приблизилось к целевому — напряжение снижается
        if abs(self.current - self.target) < 0.1:
            self.tension = max(0.0, self.tension - 0.05)


@dataclass
class ActionRecord:
    """Запись о действии для расчета RPE."""
    action_key: str
    expected_reward: float
    actual_reward: float
    timestamp: float = field(default_factory=time.time)
    rpe: float = 0.0
    
    def __post_init__(self):
        """Расчет RPE."""
        self.rpe = self.actual_reward - self.expected_reward


# =================================================================================
# СИСТЕМА ДРАЙВОВ
# =================================================================================

class DriveSystem:
    """
    Биологически правдоподобная система драйвов.
    Управляет мотивациями, метаболизмом, RPE и предсказанием дисбаланса.
    """
    
    def __init__(
        self,
        metabolism_interval: int = None,
        max_action_history: int = None
    ):
        self.metabolism_interval = metabolism_interval or settings.drives.metabolism_interval
        self.max_action_history = max_action_history or settings.drives.max_action_history
    
        # Инициализация драйвов
        self.drives: Dict[DriveType, Drive] = {
            DriveType.CURIOSITY: Drive(
                type=DriveType.CURIOSITY,
                current=0.5,
                target=0.6,
                metabolism_rate=settings.drives.curiosity_rate
            ),
            DriveType.CONNECTION: Drive(
                type=DriveType.CONNECTION,
                current=0.5,
                target=0.5,
                metabolism_rate=settings.drives.connection_rate
            ),
            DriveType.REST: Drive(
                type=DriveType.REST,
                current=0.5,
                target=0.4,
                metabolism_rate=settings.drives.rest_rate
            ),
            DriveType.CREATIVITY: Drive(
                type=DriveType.CREATIVITY,
                current=0.5,
                target=0.5,
                metabolism_rate=settings.drives.creativity_rate
            ),
            DriveType.UNDERSTANDING: Drive(
                type=DriveType.UNDERSTANDING,
                current=0.5,
                target=0.6,
                metabolism_rate=settings.drives.understanding_rate
            ),
            DriveType.AUTONOMY: Drive(
                type=DriveType.AUTONOMY,
                current=0.5,
                target=0.5,
                metabolism_rate=settings.drives.autonomy_rate
            ),
        }
        
        # История действий для RPE
        self.action_history: List[ActionRecord] = []
        
        # Ценности действий для гомеостаза
        self.action_values: Dict[str, float] = {
            "wikipedia_search": 0.7,
            "reddit_search": 0.5,
            "code_execution": 0.6,
            "rest": 0.4
        }
        
        # Флаг остановки фонового метаболизма
        self._running = False
        self._metabolism_task: Optional[asyncio.Task] = None
        
        logger.info(f"✅ DriveSystem инициализирована. Драйвов: {len(self.drives)}")
    
    # =================================================================================
    # ОЦЕНКА СТИМУЛОВ
    # =================================================================================
    
    async def evaluate_stimulus(
        self,
        stimulus: str,
        context: str = ""
    ) -> Dict[DriveType, float]:
        """
        Оценка того, как стимул влияет на драйвы.
        
        Args:
            stimulus: Текст стимула
            context: Дополнительный контекст
            
        Returns:
            Dict[DriveType, float] — дельты для каждого драйва
        """
        try:
            deltas: Dict[DriveType, float] = {}
            stimulus_lower = stimulus.lower()
            
            # Эвристики для оценки стимула
            # Сообщение от пользователя → удовлетворение CONNECTION
            if any(word in stimulus_lower for word in ['привет', 'здравствуй', 'здравствуйте']):
                deltas[DriveType.CONNECTION] = 0.15
            
            # Вопрос → удовлетворение CURIOSITY (если ответим)
            if '?' in stimulus:
                deltas[DriveType.CURIOSITY] = 0.05
            
            # Длинное сообщение → больше вовлеченности
            if len(stimulus) > 200:
                deltas[DriveType.CONNECTION] = 0.1
            
            # Креативный запрос
            if any(word in stimulus_lower for word in ['придумай', 'создай', 'напиши', 'творчество']):
                deltas[DriveType.CREATIVITY] = 0.1
            
            # Если нет явных признаков — минимальное влияние
            if not deltas:
                deltas[DriveType.CONNECTION] = 0.02
            
            logger.debug(f"Оценка стимула: {deltas}")
            return deltas
            
        except Exception as e:
            logger.error(f"Ошибка оценки стимула: {e}", exc_info=True)
            return {DriveType.CONNECTION: 0.0}
    
    # =================================================================================
    # ПРИМЕНЕНИЕ ДЕЛЬТ И УДОВЛЕТВОРЕНИЕ
    # =================================================================================
    
    def apply_deltas(self, deltas: Dict[DriveType, float]):
        """
        Применение дельт к драйвам.
        
        Args:
            deltas: Dict[DriveType, float] — изменения для каждого драйва
        """
        try:
            for drive_type, delta in deltas.items():
                if drive_type in self.drives:
                    self.drives[drive_type].apply_delta(delta)
                    logger.debug(f"Применена дельта {delta:+.3f} к {drive_type.value}")
        except Exception as e:
            logger.error(f"Ошибка применения дельт: {e}", exc_info=True)
    
    def apply_satisfaction(self, drive_type: DriveType, satisfaction: float, rpe: float = 0.0):
        """
        Применение удовлетворения к драйву с учетом RPE.
        
        Args:
            drive_type: Тип драйва
            satisfaction: Базовое удовлетворение (0.0 - 1.0)
            rpe: Reward Prediction Error (корректировка)
        """
        try:
            if drive_type not in self.drives:
                logger.warning(f"Драйв {drive_type} не найден")
                return
            
            # Удовлетворение с учетом RPE
            # Положительный RPE → больше удовлетворения
            # Отрицательный RPE → меньше удовлетворения
            adjusted_satisfaction = satisfaction + rpe * 0.2
            adjusted_satisfaction = max(-0.5, min(0.5, adjusted_satisfaction))
            
            self.drives[drive_type].apply_delta(adjusted_satisfaction)
            
            logger.info(f"Удовлетворение {drive_type.value}: {satisfaction:.2f} + RPE {rpe:.2f} = {adjusted_satisfaction:.2f}")
            
        except Exception as e:
            logger.error(f"Ошибка применения удовлетворения: {e}", exc_info=True)
    
    # =================================================================================
    # RPE (REWARD PREDICTION ERROR)
    # =================================================================================
    
    def calculate_rpe(self, action_key: str, actual_outcome: float) -> float:
        """
        Расчет Reward Prediction Error (RPE).
        
        Args:
            action_key: Ключ действия (например, "research:wikipedia_search")
            actual_outcome: Фактический результат (0.0 - 1.0)
            
        Returns:
            RPE (разница между ожидаемым и фактическим)
        """
        try:
            # Получение ожидаемой награды из истории или action_values
            expected_reward = self._get_expected_reward(action_key)
            
            # Расчет RPE
            rpe = actual_outcome - expected_reward
            
            # Запись в историю
            record = ActionRecord(
                action_key=action_key,
                expected_reward=expected_reward,
                actual_reward=actual_outcome,
                rpe=rpe
            )
            self.action_history.append(record)
            
            # Ограничение размера истории
            if len(self.action_history) > self.max_action_history:
                self.action_history = self.action_history[-self.max_action_history:]
            
            logger.debug(f"RPE для {action_key}: expected={expected_reward:.2f}, actual={actual_outcome:.2f}, rpe={rpe:.2f}")
            return rpe
            
        except Exception as e:
            logger.error(f"Ошибка расчета RPE: {e}", exc_info=True)
            return 0.0
    
    def _get_expected_reward(self, action_key: str) -> float:
        """Получение ожидаемой награды для действия."""
        try:
            # Поиск в истории действий
            similar_actions = [
                record for record in self.action_history
                if record.action_key == action_key
            ]
            
            if similar_actions:
                # Среднее ожидаемое значение из истории
                return sum(r.expected_reward for r in similar_actions) / len(similar_actions)
            
            # Если нет истории — используем action_values
            for key, value in self.action_values.items():
                if key in action_key:
                    return value
            
            # По умолчанию
            return 0.5
            
        except Exception as e:
            logger.error(f"Ошибка получения ожидаемой награды: {e}")
            return 0.5
    
    # =================================================================================
    # ПРЕДСКАЗАНИЕ ДИСБАЛАНСА
    # =================================================================================
    
    def get_predicted_disbalance(self) -> Dict[str, float]:
        """
        Предсказание дисбаланса драйвов на основе tension.
        
        Returns:
            Dict[str, float] — предсказанное состояние драйвов
        """
        try:
            predicted = {}
            current_time = time.time()
            
            for drive_type, drive in self.drives.items():
                # Обновление tension
                drive.update_tension(current_time)
                
                # Предсказание: если tension высокое — драйв будет расти
                # Если tension низкое — драйв останется стабильным
                predicted_value = drive.current + drive.tension * 0.2
                predicted[drive_type.value] = max(0.0, min(1.0, predicted_value))
            
            return predicted
            
        except Exception as e:
            logger.error(f"Ошибка предсказания дисбаланса: {e}", exc_info=True)
            return {drive_type.value: drive.current for drive_type, drive in self.drives.items()}
    
    # =================================================================================
    # ВНУТРЕННЕЕ СОСТОЯНИЕ
    # =================================================================================
    
    def get_internal_state_prompt(self) -> str:
        """
        Генерация текстового описания внутреннего состояния для промпта.
        
        Returns:
            Строка с описанием состояния драйвов
        """
        try:
            lines = []
            for drive_type, drive in self.drives.items():
                status = "норма"
                if drive.current < 0.3:
                    status = "низкое"
                elif drive.current > 0.7:
                    status = "высокое"
                
                tension_status = ""
                if drive.tension > 0.6:
                    tension_status = " (высокое напряжение!)"
                elif drive.tension > 0.3:
                    tension_status = " (умеренное напряжение)"
                
                lines.append(f"- {drive_type.value}: {drive.current:.2f} [{status}]{tension_status}")
            
            return "\n".join(lines)
            
        except Exception as e:
            logger.error(f"Ошибка генерации внутреннего состояния: {e}")
            return "Состояние драйвов недоступно"
    
    # =================================================================================
    # ФОНОВЫЙ МЕТАБОЛИЗМ
    # =================================================================================
    
    async def background_metabolism(self):
        """Фоновый цикл метаболизма (постепенное нарастание tension)."""
        self._running = True
        logger.info("Фоновый метаболизм драйвов запущен")
        
        try:
            while self._running:
                await asyncio.sleep(self.metabolism_interval)
                
                try:
                    current_time = time.time()
                    for drive_type, drive in self.drives.items():
                        drive.update_tension(current_time)
                    
                    logger.debug("Метаболизм: tension обновлен")
                    
                except Exception as e:
                    logger.error(f"Ошибка в цикле метаболизма: {e}", exc_info=True)
                    await asyncio.sleep(10)
                    
        except asyncio.CancelledError:
            logger.info("Фоновый метаболизм остановлен")
    
    def stop(self):
        """Остановка фонового метаболизма."""
        self._running = False
        if self._metabolism_task and not self._metabolism_task.done():
            self._metabolism_task.cancel()
        logger.info("DriveSystem остановлена")
    
    # =================================================================================
    # ОБНОВЛЕНИЕ ИЗ СИСТЕМНЫХ МЕТРИК
    # =================================================================================
    
    def update_from_system_metrics(self, modifiers: Dict[str, float]):
        """
        Обновление драйвов на основе системных метрик (CPU, memory).
        
        Args:
            modifiers: Dict[str, float] — модификаторы для драйвов
        """
        try:
            for drive_name, modifier in modifiers.items():
                # Поиск драйва по имени
                for drive_type in DriveType:
                    if drive_type.value == drive_name:
                        self.drives[drive_type].apply_delta(modifier)
                        logger.debug(f"Системная метрика: {drive_name} {modifier:+.3f}")
                        break
        except Exception as e:
            logger.error(f"Ошибка обновления из системных метрик: {e}", exc_info=True)
    
    # =================================================================================
    # ПЕРСИСТЕНТНОСТЬ
    # =================================================================================
    
    def save_state(self) -> Dict[str, Any]:
        """Сохранение состояния драйвов."""
        try:
            state = {}
            for drive_type, drive in self.drives.items():
                state[drive_type.value] = {
                    "current": drive.current,
                    "tension": drive.tension,
                    "target": drive.target,
                    "metabolism_rate": drive.metabolism_rate,
                    "last_update": drive.last_update
                }
            
            # Сохранение истории действий
            state["action_history"] = [
                {
                    "action_key": record.action_key,
                    "expected_reward": record.expected_reward,
                    "actual_reward": record.actual_reward,
                    "timestamp": record.timestamp,
                    "rpe": record.rpe
                }
                for record in self.action_history[-50:]  # Последние 50 записей
            ]
            
            return state
            
        except Exception as e:
            logger.error(f"Ошибка сохранения состояния драйвов: {e}", exc_info=True)
            return {}
    
    def load_state(self, state: Dict[str, Any]):
        """Загрузка состояния драйвов."""
        try:
            for drive_type in DriveType:
                if drive_type.value in state:
                    drive_data = state[drive_type.value]
                    drive = self.drives[drive_type]
                    drive.current = drive_data.get("current", 0.5)
                    drive.tension = drive_data.get("tension", 0.0)
                    drive.target = drive_data.get("target", 0.5)
                    drive.metabolism_rate = drive_data.get("metabolism_rate", 0.01)
                    drive.last_update = drive_data.get("last_update", time.time())
            
            # Загрузка истории действий
            if "action_history" in state:
                self.action_history = [
                    ActionRecord(
                        action_key=record["action_key"],
                        expected_reward=record["expected_reward"],
                        actual_reward=record["actual_reward"],
                        timestamp=record["timestamp"],
                        rpe=record["rpe"]
                    )
                    for record in state["action_history"]
                ]
            
            logger.info(f"✅ Состояние драйвов загружено. История действий: {len(self.action_history)} записей")
            
        except Exception as e:
            logger.error(f"Ошибка загрузки состояния драйвов: {e}", exc_info=True)