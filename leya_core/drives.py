"""
leya_core/drives.py
Биологически мотивированная система драйвов Леи.

Архитектура:
- DriveType Enum + Drive dataclass (current, tension, target, action_values)
- Аллостаз: предсказываем будущее состояние, действуем заранее
- RPE (Reward Prediction Error): учимся на ошибках предсказания награды
- Перекрестное влияние: драйвы модулируют рост друг друга
- Метаболизм: фоновое нарастание tension
- Оценка стимулов и применение удовлетворения

Этап 1.3:
- Интеграция с DrivesConfig (замена хардкода)
- Специфичные исключения (LeyaDriveNotFoundError, LeyaHomeostasisError)
- Улучшение RPE и метаболизма
"""

from __future__ import annotations

import asyncio
import logging
import time
import re
from dataclasses import dataclass
from enum import Enum
from typing import Any

from .config import DrivesConfig
from .exceptions import LeyaDriveNotFoundError

logger = logging.getLogger(__name__)


class DriveType(str, Enum):
    """Типы драйвов."""

    CURIOSITY = "curiosity"
    CONNECTION = "connection"
    AUTONOMY = "autonomy"
    COMPETENCE = "competence"
    SECURITY = "security"
    REST = "rest"
    INTEGRITY = "integrity"
    CREATIVITY = "creativity"
    UNDERSTANDING = "understanding"


@dataclass
class Drive:
    """
    Единичный драйв с текущим состоянием.

    Биологическая модель:
    - current: текущее напряжение (0.0–1.0)
    - baseline: базовое значение (точка гомеостаза)
    - predicted: предсказанное будущее состояние (аллостаз)
    - base_growth_rate: скорость роста напряжения
    - satisfaction_decay: скорость удовлетворения
    """

    type: DriveType
    current: float = 0.5
    baseline: float = 0.5
    predicted: float = 0.5
    prediction_horizon: int = 10
    base_growth_rate: float = 0.01
    satisfaction_decay: float = 0.02
    predicted_deviation: float = 0.0

    @property
    def tension(self) -> float:
        """Синоним current — напряжение драйва."""
        return self.current

    @property
    def target(self) -> float:
        """Целевое значение драйва (baseline как точка гомеостаза)."""
        return self.baseline


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
    CROSS_INFLUENCE = {
        (DriveType.CURIOSITY, DriveType.AUTONOMY): 0.15,
        (DriveType.AUTONOMY, DriveType.CONNECTION): -0.1,
        (DriveType.CONNECTION, DriveType.INTEGRITY): 0.1,
        (DriveType.INTEGRITY, DriveType.CURIOSITY): 0.1,
        (DriveType.AUTONOMY, DriveType.INTEGRITY): -0.15,
        (DriveType.CONNECTION, DriveType.CURIOSITY): 0.1,
        # Мастерство усиливает автономию (уверенность в своих силах)
        (DriveType.COMPETENCE, DriveType.AUTONOMY): 0.12,
        # Автономия стимулирует развитие компетенции
        (DriveType.AUTONOMY, DriveType.COMPETENCE): 0.1,
        # Компетенция поддерживает креативность (мастерство → творчество)
        (DriveType.COMPETENCE, DriveType.CREATIVITY): 0.08,
        # Целостность системы повышает чувство безопасности
        (DriveType.INTEGRITY, DriveType.SECURITY): 0.15,
        # Безопасность снижает потребность в отдыхе (стабильность = спокойствие)
        (DriveType.SECURITY, DriveType.REST): -0.08,
        # Отдых повышает чувство безопасности (восстановление ресурсов)
        (DriveType.REST, DriveType.SECURITY): 0.1,
    }

    def __init__(self, config: DrivesConfig | None = None) -> None:
        """
        Инициализация системы драйвов.

        Args:
            config: Конфигурация драйвов (rates, intervals)
        """
        self.config = config or DrivesConfig()

        self.tension_history: list[dict[str, float]] = []

        # Инициализация драйвов с rates из конфигурации
        self.drives: dict[DriveType, Drive] = {
            DriveType.CURIOSITY: Drive(
                type=DriveType.CURIOSITY,
                current=0.3,
                base_growth_rate=self.config.curiosity_rate,
                satisfaction_decay=0.02,
            ),
            DriveType.CONNECTION: Drive(
                type=DriveType.CONNECTION,
                current=0.3,
                base_growth_rate=self.config.connection_rate,
                satisfaction_decay=0.015,
            ),
            DriveType.INTEGRITY: Drive(
                type=DriveType.INTEGRITY,
                current=0.3,
                base_growth_rate=0.008,
                satisfaction_decay=0.01,
            ),
            DriveType.AUTONOMY: Drive(
                type=DriveType.AUTONOMY,
                current=0.3,
                base_growth_rate=self.config.autonomy_rate,
                satisfaction_decay=0.012,
            ),
            DriveType.REST: Drive(
                type=DriveType.REST,
                current=0.2,
                base_growth_rate=self.config.rest_rate,
                satisfaction_decay=0.025,
            ),
            DriveType.CREATIVITY: Drive(
                type=DriveType.CREATIVITY,
                current=0.25,
                base_growth_rate=self.config.creativity_rate,
                satisfaction_decay=0.015,
            ),
            DriveType.UNDERSTANDING: Drive(
                type=DriveType.UNDERSTANDING,
                current=0.25,
                base_growth_rate=self.config.understanding_rate,
                satisfaction_decay=0.018,
            ),
            DriveType.COMPETENCE: Drive(
                type=DriveType.COMPETENCE,
                current=0.25,
                base_growth_rate=0.005,  # Медленный рост — фоновая потребность
                satisfaction_decay=0.015,
            ),
            DriveType.SECURITY: Drive(
                type=DriveType.SECURITY,
                current=0.2,
                base_growth_rate=0.005,  # Медленный рост — фоновая потребность
                satisfaction_decay=0.01,  # Медленное удовлетворение — стабильность долгосрочна
            ),
        }

        self.max_history_length = self.config.max_action_history

        # Action values — ожидаемая награда для каждого действия (обучается через RPE)
        self.action_values: dict[str, float] = {}

        # История удовлетворения для анализа паттернов
        self.satisfaction_history: list[dict[str, Any]] = []

        # Параметры аллостаза
        self.prediction_horizon = 300  # Горизонт предсказания (секунды)
        self.prediction_update_interval = self.config.metabolism_interval

        # Параметры RPE
        self.learning_rate = 0.1  # Скорость обучения на RPE

        self._running = True

        logger.info(
            f"DriveSystem инициализирован: "
            f"metabolism_interval={self.config.metabolism_interval}с, "
            f"drives={len(self.drives)}"
        )

    async def evaluate_stimulus(self, stimulus: str, context: str = " ") -> dict[str, float]:
        """Оценивает влияние стимула на драйвы.

        Returns:
            dict[str, float] — дельты изменений, где ключи — строковые значения DriveType
            (например, {"curiosity": 0.15}). Совместимо с IDriveSystem Protocol.
        """
        deltas: dict[DriveType, float] = {}
        stimulus_lower = stimulus.lower()

        # Вопросы (исключаем "что-то", "чтобы")
        if re.search(r'\b(почему|зачем|как\s+работает|что\s+такое)\b', stimulus_lower):
            deltas[DriveType.CURIOSITY] = 0.15

        # Эмоциональные сообщения
        if re.search(r'\b(чувствую|думаю|мне\s+одиноко|скучно)\b', stimulus_lower):
            deltas[DriveType.CONNECTION] = 0.1

        # Команды
        if re.search(r'\b(должна|обязана|немедленно|быстро)\b', stimulus_lower):
            deltas[DriveType.AUTONOMY] = 0.15

        # Позитивная обратная связь
        if re.search(r'\b(спасибо|отлично|молодец|супер)\b', stimulus_lower):
            deltas[DriveType.CONNECTION] = -0.15
            deltas[DriveType.AUTONOMY] = -0.1

        # Негативная обратная связь
        if re.search(r'\b(плохо|ошибка|неправильно|глупая)\b', stimulus_lower):
            deltas[DriveType.CONNECTION] = 0.1
            deltas[DriveType.INTEGRITY] = 0.1

        # Сохраняем в историю (используем .value для единообразия)
        current_state = {d.type.value: d.current for d in self.drives.values()}
        self.tension_history.append(current_state)

        if len(self.tension_history) > self.max_history_length:
            self.tension_history = self.tension_history[-self.max_history_length:]

        # Возвращаем строковые ключи (совместимо с Protocol)
        return {k.value: v for k, v in deltas.items()}

    def apply_deltas(self, deltas: dict[str, float]) -> None:
        """Применяет дельты изменений к драйвам.

        Args:
            deltas: Словарь {drive_type_value: delta}, например {"curiosity": 0.15}.
                    Ключи — строковые значения DriveType (совместимо с IDriveSystem Protocol).

        Note:
            Lookup в self.drives (dict[DriveType, Drive]) работает благодаря
            str-наследованию DriveType: hash("curiosity") == hash(DriveType.CURIOSITY).
        """
        for drive_type_str, delta in deltas.items():
            # Нормализация: принимаем как строки, так и DriveType enum
            if isinstance(drive_type_str, DriveType):
                drive_type = drive_type_str
            else:
                try:
                    drive_type = DriveType(drive_type_str)
                except ValueError:
                    logger.warning(f"DriveSystem: Неизвестный драйв '{drive_type_str}', пропуск")
                    continue

            if drive_type in self.drives:
                drive = self.drives[drive_type]
                drive.current = max(0.1, min(0.9, drive.current + delta))
                logger.debug(
                    f"DriveSystem: {drive_type.value} изменён на {delta:+.2f} → {drive.current:.2f}"
                )
            else:
                logger.warning(f"DriveSystem: Драйв {drive_type.value} не найден")

    def stop(self) -> None:
        """Останавливает фоновый метаболизм."""
        self._running = False

    async def background_metabolism(self) -> None:
        """
        Фоновый метаболизм драйвов.

        Защита от падения: обёрнут в try/except.
        """
        logger.info("DriveSystem: Метаболизм запущен.")

        while self._running:
            try:
                await asyncio.sleep(self.prediction_update_interval)

                if not self._running:
                    break

                # 1. Применяем перекрестное влияние
                for drive in self.drives.values():
                    cross_effect = self._calculate_cross_influence(drive.type)
                    effective_growth = drive.base_growth_rate + cross_effect

                    # Рост с учётом перекрестного влияния
                    drive.current = min(1.0, max(0.0, drive.current + effective_growth))

                # 2. Обновляем предсказания (аллостаз)
                self._update_predictions()

                # 3. Сохраняем снимок состояния в историю
                current_state = {d.type.value: d.current for d in self.drives.values()}
                self.tension_history.append(current_state)

                if len(self.tension_history) > self.max_history_length:
                    self.tension_history = self.tension_history[-self.max_history_length :]

            except asyncio.CancelledError:
                logger.info("DriveSystem: Метаболизм отменён.")
                break
            except Exception as exc:
                logger.error(f"DriveSystem: Ошибка в метаболизме: {exc}", exc_info=True)
                await asyncio.sleep(10)  # Пауза перед рестартом

    def _calculate_cross_influence(self, target_type: DriveType) -> float:
        """
        Вычисляет суммарное перекрестное влияние на целевой драйв.

        Биологический аналог: нейромодуляция (дофамин, серотонин, кортизол).
        """
        total_effect = 0.0

        for (source_type, tgt_type), coefficient in self.CROSS_INFLUENCE.items():
            if tgt_type == target_type and source_type in self.drives:
                source = self.drives[source_type]
                source_deviation = source.current - source.baseline
                total_effect += coefficient * source_deviation

        return total_effect

    def _update_predictions(self) -> None:
        """
        Обновляет предсказанные состояния драйвов (аллостаз).

        Биологический аналог: префронтальная кора предсказывает будущие потребности.
        """
        ticks_ahead = self.prediction_horizon / self.prediction_update_interval

        for drive in self.drives.values():
            cross_effect = self._calculate_cross_influence(drive.type)
            effective_growth = drive.base_growth_rate + cross_effect

            # Линейная экстраполяция на горизонт предсказания
            drive.predicted = min(1.0, max(0.0, drive.current + effective_growth * ticks_ahead))

    def calculate_rpe(self, action_key: str, actual_outcome: float) -> float:
        """
        Вычисляет Reward Prediction Error (ошибку предсказания награды).

        Биологический аналог: дофаминовые нейроны в VTA.
        - RPE > 0: награда лучше ожидаемой → дофаминовый всплеск
        - RPE < 0: награда хуже ожидаемой → падение дофамина
        - RPE = 0: награда как ожидалась → стабильный дофамин

        Args:
            action_key: Ключ действия (например, "wikipedia_search:science")
            actual_outcome: Фактический результат (0.0–1.0)

        Returns:
            RPE (ошибка предсказания)
        """
        actual_outcome = max(0.0, min(1.0, actual_outcome))
        expected = self.action_values.get(action_key, 0.5)
        rpe = actual_outcome - expected

        # Обновляем ожидаемую награду (Q-learning)
        self.action_values[action_key] = expected + self.learning_rate * rpe

        # Записываем в историю
        self.satisfaction_history.append(
            {
                "action_key": action_key,
                "expected": expected,
                "actual": actual_outcome,
                "rpe": rpe,
                "timestamp": time.time(),
            }
        )

        if len(self.satisfaction_history) > self.max_history_length:
            self.satisfaction_history = self.satisfaction_history[-self.max_history_length :]

        logger.info(
            f"DriveSystem: RPE для {action_key}: {rpe:.2f} "
            f"(expected={expected:.2f}, actual={actual_outcome:.2f})"
        )

        return rpe

    def apply_satisfaction(self, drive_type: DriveType, base_amount: float, rpe: float) -> None:
        """
        Применяет удовлетворение драйва, модифицированное RPE.

        Биологический аналог: дофамин усиливает удовлетворение при положительном RPE.

        ⚠️ ВАЖНО: drive.current может опуститься до 0.0 (полное удовлетворение).
        Это биологически корректно и имеет важные последствия:

        1. Перенасыщение (over-saturation):
           - Если current < baseline (0.5), возникает отрицательная девиация
           - source_deviation = current - baseline < 0
           - Через _calculate_cross_influence это ОТРИЦАТЕЛЬНО влияет на связанные драйвы

        2. Биологический аналог:
           - После обильного удовлетворения любопытства (CURIOSITY → 0.0)
           - Наступает "пресыщение", которое временно подавляет другие познавательные драйвы
           - AUTONOMY и CONNECTION также могут получить отрицательный эффект
           - Это имитирует когнитивную усталость после интенсивного обучения

        3. Восстановление:
           - Метаболизм (background_metabolism) постепенно возвращает current к baseline
           - Отрицательный эффект перенасыщения временный
           - Это обеспечивает баланс и предотвращает "вечное удовлетворение"

        Args:
            drive_type: Тип драйва
            base_amount: Базовое количество удовлетворения
            rpe: Ошибка предсказания награды (модифицирует base_amount)
        """
        if drive_type not in self.drives:
            raise LeyaDriveNotFoundError(
                f"Драйв {drive_type} не найден",
                context={"drive_type": drive_type},
            )

        # RPE модифицирует удовлетворение
        rpe_modifier = 1.0 + (rpe * 0.5)
        rpe_modifier = max(0.2, min(2.0, rpe_modifier))

        actual_amount = base_amount * rpe_modifier

        drive = self.drives[drive_type]
        # ✅ ИСПРАВЛЕНО: объединяем обе операции в одну строку
        # Драйв может опуститься до 0.0 (полное удовлетворение), но не ниже
        drive.current = max(0.0, min(0.9, drive.current - actual_amount))

        logger.info(
            f"DriveSystem: {drive_type.value} удовлетворён на {actual_amount:.2f} "
            f"(RPE modifier: {rpe_modifier:.2f}, new_current={drive.current:.2f})"
        )

    def get_action_value(self, action_key: str) -> float:
        """Возвращает ожидаемую награду для действия."""
        return self.action_values.get(action_key, 0.5)

    def get_internal_state_prompt(self) -> str:
        """Возвращает текстовое описание состояния для промпта LLM."""
        lines = ["=== СОСТОЯНИЕ ДРАЙВОВ ==="]

        for drive_type, drive in self.drives.items():
            status = self._describe_drive_state(drive)
            lines.append(
                f"- {drive_type.value}: {drive.current:.2f} "
                f"(предсказано: {drive.predicted:.2f}) — {status}"
            )

        return "\n".join(lines)

    def get_drives_state(self) -> dict[str, dict[str, float]]:
        """
        Возвращает полное состояние всех драйвов в структурированном виде.
        Публичный API для UI и внешних потребителей.

        Returns:
            dict вида:
            {
                "CURIOSITY": {
                    "current": 0.5,
                    "tension": 0.3,
                    "target": 0.8,
                    "satisfaction": 0.0
                },
                ...
            }
        """

        result = {}
        for drive_type, drive in self.drives.items():
            result[drive_type.value] = {
                "current": drive.current,
                "tension": drive.tension,
                "target": drive.target,
                "satisfaction": max(0.0, drive.baseline - drive.current),
            }
        return result

    def _describe_drive_state(self, drive: Drive) -> str:
        """Генерирует текстовое описание состояния драйва."""
        if drive.current < 0.2:
            return "удовлетворён"
        elif drive.current < 0.5:
            return "нормальный"
        elif drive.current < 0.7:
            return "нарастает"
        else:
            return "критический"

    def get_predicted_disbalance(self) -> dict[DriveType, float]:
        """
        Возвращает предсказанный дисбаланс для всех драйвов.
        Используется HomeostasisEngine для проактивного планирования.
        """
        return {
            drive_type: drive.predicted - drive.baseline
            for drive_type, drive in self.drives.items()
        }

    def update_from_system_metrics(self, modifiers: dict[str, float]) -> None:
        """Применяет модификаторы от системных метрик к драйвам."""
        drive_map = {
            "curiosity": DriveType.CURIOSITY,
            "connection": DriveType.CONNECTION,
            "integrity": DriveType.INTEGRITY,
            "autonomy": DriveType.AUTONOMY,
            "rest": DriveType.REST,
            "creativity": DriveType.CREATIVITY,
            "understanding": DriveType.UNDERSTANDING,
            "competence": DriveType.COMPETENCE,
            "security": DriveType.SECURITY,
        }

        for metric_name, modifier in modifiers.items():
            if modifier != 0.0 and metric_name in drive_map:
                drive_type = drive_map[metric_name]
                if drive_type in self.drives:
                    drive = self.drives[drive_type]
                    drive.current = max(0.1, min(0.9, drive.current + modifier))

    def save_state(self) -> dict[str, Any]:
        """Сохраняет состояние DriveSystem."""
        return {
            "action_values": self.action_values,
            "satisfaction_history": self.satisfaction_history[-100:],
            "current_drives": {
                drive_type.value: drive.current for drive_type, drive in self.drives.items()
            },
        }

    def load_state(self, state: dict[str, Any]) -> None:
        """Загружает состояние DriveSystem."""
        if "action_values" in state:
            self.action_values = state["action_values"]
            logger.info(
                f"DriveSystem: Загружено {len(self.action_values)} обученных ценностей действий"
            )

        if "satisfaction_history" in state:
            self.satisfaction_history = state["satisfaction_history"]

        if "current_drives" in state:
            for drive_type_str, value in state["current_drives"].items():
                for drive_type in DriveType:
                    if drive_type.value == drive_type_str:
                        if drive_type in self.drives:
                            self.drives[drive_type].current = max(0.1, min(0.9, value))
                        break
            logger.info("DriveSystem: Загружены текущие значения драйвов")
