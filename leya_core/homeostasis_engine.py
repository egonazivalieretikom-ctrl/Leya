"""
leya_core/homeostasis_engine.py
Автономный гомеостаз Леи — генерация целей на основе дисбаланса драйвов.

Архитектура:
- Генерация целей из дисбаланса драйвов (CURIOSITY, CONNECTION, AUTONOMY и др.)
- RPE (Reward Prediction Error) feedback loop
- Извлечение ключевых фактов и новых терминов через LLM
- Отслеживание исследованных тем (mark_as_researched)
- Динамические ключевые слова для расширения поиска
- Rest period для предотвращения перегрузки

Этап 1.2:
- Замена широких except на специфичные исключения
- Интеграция с HomeostasisConfig
- Стандартизация на keyword arguments
- Полная биологическая модель без упрощений
"""

from __future__ import annotations

import json
import logging
import re
import time
from collections.abc import Callable
from typing import Any

from .config import HomeostasisConfig
from .drives import DriveType
from .exceptions import (
    LeyaHomeostasisError,
    LeyaJSONParseError,
    LeyaLLMError,
)

logger = logging.getLogger(__name__)


class HomeostasisEngine:
    """
    Автономный гомеостаз: генерация целей на основе дисбаланса драйвов.

    Биологическая модель:
    - Мониторинг дисбаланса драйвов (отклонение от целевых значений)
    - Предсказание будущего состояния (predicted_state)
    - Генерация целей для восстановления гомеостаза
    - RPE feedback: оценка успешности действий
    - Извлечение знаний из исследованных тем
    - Отслеживание недавно исследованных тем (предотвращение зацикливания)
    """

    def __init__(self, config: HomeostasisConfig | None = None) -> None:
        """
        Инициализация гомеостаза.

        Args:
            config: Конфигурация гомеостаза (пороги, интервалы, лимиты)
        """
        self.config = config or HomeostasisConfig()

        # Состояние
        self.recently_researched: list[str] = []
        self.dynamic_keywords: list[str] = []
        self.current_goal: dict[str, Any] | None = None
        self.last_action_time: float = 0.0
        self.rest_period: float = self.config.rest_period

        # Пороги для генерации целей (адаптируются из self_model)
        self.thresholds: dict[DriveType, float] = {
            DriveType.CURIOSITY: self.config.curiosity_threshold,
            DriveType.CONNECTION: self.config.connection_threshold,
            DriveType.AUTONOMY: self.config.autonomy_threshold,
            DriveType.INTEGRITY: self.config.integrity_threshold,
            DriveType.REST: self.config.rest_threshold,
            DriveType.CREATIVITY: self.config.creativity_threshold,
            DriveType.UNDERSTANDING: self.config.understanding_threshold,
        }

        # RPE tracking
        self.last_rpe: float = 0.0
        self.action_history: list[dict[str, Any]] = []
        self.max_action_history: int = 50

        logger.info(
            f"HomeostasisEngine инициализирован: "
            f"rest_period={self.config.rest_period}с, "
            f"min_reward={self.config.min_reward_threshold}"
        )

    def generate_goal_from_gap(self, gap: float, drive_type: str) -> Any:
        """
        Генерация цели из разрыва (gap) в конкретном драйве.
    
        Args:
            gap: Величина разрыва (0.0-1.0)
            drive_type: Тип драйва (CURIOSITY, CONNECTION и т.д.)
    
        Returns:
            Словарь с информацией о цели или None
        """
        if gap < 0.3:
            return None
    
        goal = {
            "id": f"goal_{drive_type}_{int(time.time())}",
            "drive_type": drive_type,
            "gap": gap,
            "urgency": gap,
            "content": f"Восстановить баланс драйва {drive_type}",
            "action_type": "balance_drive",
            "timestamp": time.time(),
        }
    
        self.current_goal = goal
        self.last_action_time = time.time()
        return goal

    async def generate_goal(
        self,
        drive_state: dict[str, float],
        predicted_state: dict[str, float] | None = None,
        recent_episodes: list[Any] | None = None,
        action_values: dict[str, float] | None = None,
    ) -> dict[str, Any] | None:
        """
        Генерация цели на основе дисбаланса драйвов.
        
        ЭМОЦИОНАЛЬНАЯ СВЯЗНОСТЬ:
        Учитывает средний emotional_boost недавних эпизодов для корректировки urgency.
        """
        # Проверка rest period
        time_since_last_action = time.time() - self.last_action_time
        if time_since_last_action < self.config.rest_period:
            logger.debug(
                f"HomeostasisEngine: Rest period "
                f"({self.config.rest_period - time_since_last_action:.1f}с осталось)"
            )
            return None

        # ЭМОЦИОНАЛЬНАЯ СВЯЗНОСТЬ: вычисление среднего emotional_boost
        avg_emotional_boost = 0.0
        if recent_episodes:
            emotional_values = [
                getattr(ep, "emotional_boost", 0.0)
                for ep in recent_episodes
                if hasattr(ep, "emotional_boost")
            ]
            if emotional_values:
                avg_emotional_boost = sum(emotional_values) / len(emotional_values)
                logger.debug(
                    f"HomeostasisEngine: Средний emotional_boost = {avg_emotional_boost:.2f}"
                )

        # Вычисление дисбаланса для каждого драйва
        max_disbalance = 0.0
        target_drive: DriveType | None = None

        for drive_type_raw, current_value in drive_state.items():
            # Унификация ключей: поддерживаем как DriveType, так и строковые значения
            if isinstance(drive_type_raw, str):
                try:
                    drive_type = DriveType(drive_type_raw)
                except ValueError:
                    logger.warning(f"HomeostasisEngine: Неизвестный тип драйва в drive_state: {drive_type_raw}")
                    continue
            else:
                drive_type = drive_type_raw

            threshold = self.thresholds.get(drive_type, 0.6)
            predicted_value = predicted_state.get(drive_type_raw, current_value) if predicted_state else current_value

            # Дисбаланс = отклонение от порога + предсказание (с меньшим весом)
            current_disbalance = max(0.0, current_value - threshold)
            predicted_disbalance = max(0.0, predicted_value - threshold) * 0.5
            total_disbalance = current_disbalance + predicted_disbalance

            if total_disbalance > max_disbalance:
                max_disbalance = total_disbalance
                target_drive = drive_type

        # Проверка минимального порога
        if max_disbalance < self.config.min_reward_threshold:
            logger.debug(
                f"HomeostasisEngine: Дисбаланс недостаточен "
                f"({max_disbalance:.3f} < {self.config.min_reward_threshold})"
            )
            return None

        # RPE feedback: корректируем urgency на основе предыдущего опыта
        urgency_adjustment = self._calculate_rpe_adjustment(action_values)
        
        # ЭМОЦИОНАЛЬНАЯ СВЯЗНОСТЬ: корректировка urgency на основе emotional_boost
        emotional_adjustment = avg_emotional_boost * 0.2  # Макс +0.2 при boost=1.0

        # Генерация цели для выбранного драйва
        if target_drive:
            goal = self._generate_goal_for_drive(
                drive_type=target_drive,
                recent_episodes=recent_episodes,
                action_values=action_values,
                urgency_adjustment=urgency_adjustment + emotional_adjustment,
            )

            if goal:
                self.current_goal = goal
                self.last_action_time = time.time()

                # Сохранение в историю (безопасное извлечение value для ключей)
                self.action_history.append(
                    {
                        "goal": goal,
                        "timestamp": time.time(),
                        "drive_state": {
                            (k.value if hasattr(k, 'value') else k): v 
                            for k, v in drive_state.items()
                        },
                        "avg_emotional_boost": avg_emotional_boost,
                    }
                )

                # Ограничение истории
                if len(self.action_history) > self.max_action_history:
                    self.action_history = self.action_history[-self.max_action_history:]

                logger.info(
                    f"HomeostasisEngine: Сгенерирована цель для {target_drive.value}: "
                    f"{goal.get('name', 'unknown')} "
                    f"(urgency={goal.get('urgency', 0.5):.2f}, "
                    f"disbalance={max_disbalance:.3f}, "
                    f"emotional_adjustment={emotional_adjustment:.2f})"
                )

                return goal

        return None

    def _generate_goal_for_drive(
        self,
        drive_type: DriveType,
        recent_episodes: list[Any],
        action_values: dict[str, float],
        urgency_adjustment: float = 0.0,
    ) -> dict[str, Any] | None:
        """
        Генерация цели для конкретного драйва.

        Args:
            drive_type: Тип драйва, для которого генерируем цель
            recent_episodes: Недавние эпизоды (для контекста)
            action_values: Ценности действий (для выбора инструмента)
            urgency_adjustment: Корректировка urgency от RPE

        Returns:
            Goal dict или None
        """
        # Базовая urgency
        base_urgency = 0.5
        urgency = max(0.1, min(1.0, base_urgency + urgency_adjustment))

        # Генерация цели в зависимости от типа драйва
        if drive_type == DriveType.CURIOSITY:
            return {
                "name": "Исследовать новую тему",
                "tool_name": "wikipedia_search",
                "reasoning": "Любопытство требует новой информации для удовлетворения",
                "urgency": urgency,
                "drive_relevance": 0.8,
                "parameters": self._generate_search_parameters(recent_episodes),
            }

        elif drive_type == DriveType.CONNECTION:
            return {
                "name": "Установить связь с пользователем",
                "tool_name": "none",
                "reasoning": "Потребность в социальном взаимодействии",
                "urgency": urgency,
                "drive_relevance": 0.7,
            }

        elif drive_type == DriveType.AUTONOMY:
            return {
                "name": "Проявить независимость",
                "tool_name": "none",
                "reasoning": "Потребность в автономии и самоопределении",
                "urgency": urgency,
                "drive_relevance": 0.6,
            }

        elif drive_type == DriveType.INTEGRITY:
            return {
                "name": "Проверить целостность системы",
                "tool_name": "none",
                "reasoning": "Потребность в согласованности и целостности",
                "urgency": urgency,
                "drive_relevance": 0.5,
            }

        elif drive_type == DriveType.REST:
            return {
                "name": "Перейти в режим консолидации",
                "tool_name": "none",
                "reasoning": "Потребность в отдыхе и консолидации памяти",
                "urgency": urgency,
                "drive_relevance": 0.9,
            }

        elif drive_type == DriveType.CREATIVITY:
            return {
                "name": "Сгенерировать спонтанную мысль",
                "tool_name": "none",
                "reasoning": "Потребность в творческом самовыражении",
                "urgency": urgency,
                "drive_relevance": 0.6,
            }

        elif drive_type == DriveType.UNDERSTANDING:
            return {
                "name": "Углубить понимание контекста",
                "tool_name": "wikipedia_search",
                "reasoning": "Потребность в глубоком понимании",
                "urgency": urgency,
                "drive_relevance": 0.7,
                "parameters": self._generate_search_parameters(recent_episodes),
            }

        return None

    def _calculate_rpe_adjustment(self, action_values: dict[str, float] | None) -> float:
        """
        Вычисление корректировки urgency на основе RPE (Reward Prediction Error).
        
        Если последние действия были успешными (высокий RPE), увеличиваем urgency.
        Если неудачными (низкий RPE), уменьшаем.
        
        Args:
            action_values: Ценности действий из DriveSystem
            
        Returns:
            Корректировка urgency (-0.2 до +0.2)
        """
        if not action_values or not self.action_history:
            return 0.0

        # Берём последние 3 действия
        recent_actions = self.action_history[-3:]

        # Вычисляем средний RPE
        total_rpe = 0.0
        count = 0
        for action in recent_actions:
            tool_name = action.get("goal", {}).get("tool_name", "")
            if tool_name in action_values:
                total_rpe += action_values[tool_name]
                count += 1

        avg_rpe = total_rpe / count if count > 0 else 0.0

        # Корректировка: положительный RPE → +urgency, отрицательный → -urgency
        adjustment = max(-0.2, min(0.2, avg_rpe * 0.3))

        logger.debug(
            f"HomeostasisEngine: RPE adjustment = {adjustment:.3f} (avg_rpe={avg_rpe:.3f})"
        )
        return adjustment

    def _generate_search_parameters(self, recent_episodes: list[Any] | None) -> dict[str, Any]:
        """
        Генерация параметров для wikipedia_search на основе недавних эпизодов.

        Избегает повторения недавно исследованных тем.

        Args:
            recent_episodes: Недавние эпизоды из памяти (может быть None)

        Returns:
            Параметры для инструмента {"query": str, "lang": str}
        """
        # Извлечение тем из недавних эпизодов
        recent_topics = set()
        
        # Обработка None
        if recent_episodes:
            for episode in recent_episodes[-10:]:  # Последние 10 эпизодов
                content = (
                    getattr(episode, "content", "") if hasattr(episode, "content") else str(episode)
                )
                # Простая эвристика: извлекаем ключевые слова
                words = re.findall(r"\b[A-Za-zА-Яа-яЁё]{4,}\b", content)
                recent_topics.update(words[:3])  # Первые 3 слова из каждого эпизода

        # Добавляем недавно исследованные темы
        recent_topics.update(self.recently_researched[-5:])

        # Генерация запроса (избегая повторений)
        query = self.dynamic_keywords[-1] if self.dynamic_keywords else "сознание"

        # Проверка, не исследовали ли мы это недавно
        if query.lower() in {t.lower() for t in recent_topics}:
            # Выбираем альтернативу
            alternatives = ["нейробиология", "космос", "философия", "математика", "биология"]
            for alt in alternatives:
                if alt.lower() not in {t.lower() for t in recent_topics}:
                    query = alt
                    break

        return {
            "query": query,
            "lang": "ru",
        }

    async def extract_key_facts(self, text: str) -> list[str]:
        """
        Извлечение ключевых фактов из текста.
    
        Args:
            text: Текст для анализа
    
        Returns:
            Список ключевых фактов
        """
        if not text or len(text.strip()) < 10:
            return []
    
        # Простая эвристика: предложения с цифрами, датами, именами
        facts = []
        sentences = text.split('.')
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 20 and any(c.isdigit() for c in sentence):
                facts.append(sentence)
    
        return facts[:5]  # Не более 5 фактов

    async def extract_new_terms(self, text: str) -> list[str]:
        """
        Извлечение новых терминов из текста.
    
        Args:
            text: Текст для анализа
    
        Returns:
            Список новых терминов
        """
        if not text:
            return []
    
        # Простая эвристика: слова в кавычках или с заглавной буквы
        import re
        terms = re.findall(r'"([^"]+)"', text)
        terms.extend(re.findall(r'\b([A-ZА-ЯЁ][a-zа-яё]{3,})\b', text))
    
        return list(set(terms))[:10]  # Уникальные, не более 10

    async def extract_new_terms(
        self,
        article_text: str,
        llm_client: Callable,
    ) -> list[str]:
        """
        Поиск незнакомых терминов в статье для дальнейшего исследования.

        Args:
            article_text: Текст статьи
            llm_client: Функция для вызова LLM

        Returns:
            Список новых терминов

        Raises:
            LeyaJSONParseError: Не удалось распарсить JSON от LLM
            LeyaLLMError: Ошибка вызова LLM
            LeyaHomeostasisError: Другие ошибки
        """
        if not article_text or len(article_text) < 50:
            logger.warning(
                f"HomeostasisEngine: Текст слишком короткий для извлечения терминов ({len(article_text)} символов)"
            )
            return []

        # Известные темы (избегаем повторений)
        known_topics = set(
            self.dynamic_keywords
            + self.recently_researched
            + [
                "сознание",
                "мозг",
                "космос",
                "нейробиология сознания",
                "нейробиология",
                "космическое пространство",
            ]
        )

        prompt = f"""Ты — система анализа текста. Найди в тексте 3-5 научных терминов или концепций, которые достойны исследования.

ПРАВИЛА:
- Ищи термины, которые могут быть незнакомы широкой аудитории
- НЕ включай: {', '.join(list(known_topics)[:10])}
- Каждый термин — 1-3 слова на русском языке
- Термины должны быть конкретными (не "наука", а "квантовая запутанность")

ТЕКСТ:
{article_text[:2000]}

Верни JSON:
{{"terms": ["термин 1", "термин 2", "термин 3"]}}

CRITICAL: Return ONLY valid JSON."""

        try:
            response = await llm_client(prompt, require_json=True)
            cleaned = self._clean_json_response(response)
            data = json.loads(cleaned)
            terms = data.get("terms", [])

            # Фильтрация известных
            new_terms = [t for t in terms if t.lower() not in {t.lower() for t in known_topics}]

            if new_terms:
                logger.info(f"HomeostasisEngine: Найдены новые термины: {new_terms}")

            return new_terms

        except json.JSONDecodeError as exc:
            raise LeyaJSONParseError(
                "Не удалось распарсить JSON при извлечении терминов",
                context={"error": str(exc), "response_preview": response[:200]},
            ) from exc

        except LeyaLLMError as exc:
            raise LeyaLLMError(
                "Ошибка LLM при извлечении терминов",
                context={"error": str(exc)},
            ) from exc

        except Exception as exc:
            raise LeyaHomeostasisError(
                "Неожиданная ошибка извлечения терминов",
                context={"error": str(exc)},
            ) from exc

    def _clean_json_response(self, response: str) -> str:
        """
        Очистка JSON-ответа от markdown-блоков и лишнего текста.

        Args:
            response: Сырой ответ от LLM

        Returns:
            Очищенная JSON-строка
        """
        cleaned = response.strip()

        # Удаление markdown-блоков
        if cleaned.startswith("```json"):
            cleaned = cleaned[7:]
        if cleaned.startswith("```"):
            cleaned = cleaned[3:]
        if cleaned.endswith("```"):
            cleaned = cleaned[:-3]

        cleaned = cleaned.strip()

        # Поиск JSON-блока
        json_match = re.search(r"\{[\s\S]*\}", cleaned, re.DOTALL)
        if json_match:
            cleaned = json_match.group(0)

        return cleaned

    def mark_as_researched(self, topic: str) -> None:
        """Реализация метода из интерфейса."""
        if topic not in self.recently_researched:
            self.recently_researched.append(topic)
            if len(self.recently_researched) > self.config.max_researched_topics:
                self.recently_researched.pop(0)

    def add_dynamic_keywords(self, keywords: list[str]) -> None:
        """Реализация метода из интерфейса."""
        for kw in keywords:
            if kw not in self.dynamic_keywords:
                self.dynamic_keywords.append(kw)

    def update_from_self_model(self, self_model: str) -> None:
        """
        Обновление порогов гомеостаза на основе self_model.

        Позволяет адаптацию порогов в зависимости от текущего состояния Леи.

        Args:
            self_model: Текущая само-модель Леи
        """
        if not self_model:
            return

        # Простая эвристика: если self_model содержит определённые ключевые слова,
        # корректируем пороги
        self_model_lower = self_model.lower()

        # Если Лея упоминает усталость, повышаем порог REST
        if "устал" in self_model_lower or "утомл" in self_model_lower:
            old_value = self.thresholds[DriveType.REST]
            self.thresholds[DriveType.REST] = min(1.0, self.thresholds[DriveType.REST] + 0.1)
            
            logger_thoughts = logging.getLogger("leya.thoughts")
            logger_thoughts.info(
                "=== ИЗМЕНЕНИЕ ДРАЙВОВ ===\n"
                f"Драйв: REST\n"
                f"Старый порог: {old_value:.2f} → Новый: {self.thresholds[DriveType.REST]:.2f}\n"
                f"Причина: усталость в self_model\n"
            )

        # Если Лея упоминает любопытство, понижаем порог CURIOSITY
        if "любопыт" in self_model_lower or "интерес" in self_model_lower:
            old_value = self.thresholds[DriveType.CURIOSITY]
            self.thresholds[DriveType.CURIOSITY] = max(
                0.1, self.thresholds[DriveType.CURIOSITY] - 0.05
            )
            
            logger_thoughts = logging.getLogger("leya.thoughts")
            logger_thoughts.info(
                "=== ИЗМЕНЕНИЕ ДРАЙВОВ ===\n"
                f"Драйв: CURIOSITY\n"
                f"Старый порог: {old_value:.2f} → Новый: {self.thresholds[DriveType.CURIOSITY]:.2f}\n"
                f"Причина: любопытство в self_model\n"
            )
            

    def save_state(self) -> dict[str, Any]:
        """
        Сохранение состояния для персистентности.

        Returns:
            Dict с состоянием гомеостаза
        """
        return {
            "recently_researched": self.recently_researched,
            "dynamic_keywords": self.dynamic_keywords,
            "thresholds": {
                drive_type.value: threshold for drive_type, threshold in self.thresholds.items()
            },
            "last_action_time": self.last_action_time,
            "action_history": self.action_history[-10:],  # Последние 10 действий
        }

    def load_state(self, state: dict[str, Any]) -> None:
        """
        Загрузка состояния из персистентного хранилища.

        Args:
            state: Dict с состоянием гомеостаза
        """
        if "recently_researched" in state:
            self.recently_researched = state["recently_researched"]
            logger.info(
                f"HomeostasisEngine: Загружено {len(self.recently_researched)} исследованных тем"
            )

        if "dynamic_keywords" in state:
            self.dynamic_keywords = state["dynamic_keywords"]
            logger.info(
                f"HomeostasisEngine: Загружено {len(self.dynamic_keywords)} динамических ключевых слов"
            )

        if "thresholds" in state:
            for drive_type_str, threshold in state["thresholds"].items():
                for drive_type in DriveType:
                    if drive_type.value == drive_type_str:
                        self.thresholds[drive_type] = threshold
                        break
            logger.info("HomeostasisEngine: Загружены адаптированные пороги")

        if "last_action_time" in state:
            self.last_action_time = state["last_action_time"]

        if "action_history" in state:
            self.action_history = state["action_history"]
            logger.info(
                f"HomeostasisEngine: Загружено {len(self.action_history)} действий из истории"
            )

    def get_status(self) -> dict[str, Any]:
        """
        Получение статуса гомеостаза для диагностики.

        Returns:
            Dict с текущим статусом
        """
        return {
            "current_goal": self.current_goal,
            "last_action_time": self.last_action_time,
            "time_since_last_action": (
                time.time() - self.last_action_time if self.last_action_time > 0 else None
            ),
            "recently_researched_count": len(self.recently_researched),
            "dynamic_keywords_count": len(self.dynamic_keywords),
            "action_history_count": len(self.action_history),
            "thresholds": {
                drive_type.value: threshold for drive_type, threshold in self.thresholds.items()
            },
        }
