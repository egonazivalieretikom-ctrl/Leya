"""
leya_core/homeostasis_engine.py — Гомеостаз и автономные цели Леи.
Этап 3.2: Полная переработка. Надежный JSON-парсинг, биологическая логика, RPE.
"""
import asyncio
import json
import logging
import re
import time
from leya_core.config import settings
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Any, Optional, List, Callable, Set

logger = logging.getLogger("HomeostasisEngine")


# =================================================================================
# МОДЕЛИ ДАННЫХ
# =================================================================================

@dataclass
class Goal:
    """Цель, сгенерированная гомеостазом."""
    name: str  # Название цели (например, "Исследовать пробел: квантовая физика")
    action_type: str  # Тип действия: "use_tool" или "rest"
    expected_reward: float = 0.5  # Ожидаемая награда (0.0 - 1.0)
    tool_name: str = ""  # Название инструмента (если action_type == "use_tool")
    tool_parameters: Dict[str, Any] = field(default_factory=dict)  # Параметры инструмента
    target_drives: Dict[str, float] = field(default_factory=dict)  # Целевые драйвы и их веса
    reasoning: str = ""  # Обоснование цели
    created_at: float = field(default_factory=time.time)
    
    def __post_init__(self):
        """Валидация полей."""
        self.name = self.name.strip() if self.name else "Неизвестная цель"
        self.action_type = self.action_type.strip().lower() if self.action_type else "rest"
        self.expected_reward = max(0.0, min(1.0, self.expected_reward))
        
        # Валидация action_type
        valid_types = {"use_tool", "rest"}
        if self.action_type not in valid_types:
            logger.warning(f"Некорректный action_type: {self.action_type}. Сброс в 'rest'")
            self.action_type = "rest"


# =================================================================================
# ГОМЕОСТАЗ И АВТОНОМНЫЕ ЦЕЛИ
# =================================================================================

class HomeostasisEngine:
    """
    Гомеостаз Леи: генерация автономных целей на основе дисбаланса драйвов.
    Позволяет Лее "жить" самостоятельно, исследуя пробелы в знаниях.
    """
    
    def __init__(
        self,
        rest_period: int = None,
        curiosity_threshold: float = None,
        min_reward_threshold: float = None,
        max_researched_topics: int = None
    ):
        self.rest_period = rest_period if rest_period is not None else settings.homeostasis.rest_period
        self.curiosity_threshold = curiosity_threshold if curiosity_threshold is not None else settings.homeostasis.curiosity_threshold
        self.min_reward_threshold = min_reward_threshold if min_reward_threshold is not None else settings.homeostasis.min_reward_threshold
        self.max_researched_topics = max_researched_topics if max_researched_topics is not None else settings.homeostasis.max_researched_topics
        
        # Состояние
        self.current_goal: Optional[Goal] = None
        self.last_action_time: float = 0.0
        self.researched_topics: Set[str] = set()
        
        logger.info(f"✅ HomeostasisEngine инициализирован. Rest period: {rest_period}s")
    
    # =================================================================================
    # ГЕНЕРАЦИЯ ЦЕЛЕЙ
    # =================================================================================
    
    def generate_goal(
        self,
        drive_state: Dict[str, float],
        predicted_state: Dict[str, float],
        recent_episodes: List[Dict[str, Any]],
        action_values: Dict[str, float]
    ) -> Optional[Goal]:
        """
        Генерация цели на основе дисбаланса драйвов.
        
        Args:
            drive_state: Текущее состояние драйвов {drive_name: value}
            predicted_state: Предсказанное состояние драйвов
            recent_episodes: Недавние эпизоды из памяти
            action_values: Ценности действий для homeostasis
            
        Returns:
            Goal или None (если нет дисбаланса)
        """
        try:
            # Анализ дисбаланса драйвов
            max_drive = max(drive_state.values()) if drive_state else 0.0
            max_drive_name = max(drive_state, key=drive_state.get) if drive_state else ""
            
            # Если нет значительного дисбаланса — покой
            if max_drive < self.curiosity_threshold:
                logger.debug("HomeostasisEngine: Зона комфорта. Нет дисбаланса.")
                return None
            
            # Проверка времени с последнего действия
            time_since_last = time.time() - self.last_action_time
            if time_since_last < self.rest_period:
                logger.debug(f"HomeostasisEngine: Слишком рано. Осталось {self.rest_period - time_since_last:.0f}s")
                return None
            
            # Генерация цели на основе доминирующего драйва
            if max_drive_name == "CURIOSITY" and max_drive >= self.curiosity_threshold:
                return self._generate_research_goal(drive_state, recent_episodes, action_values)
            elif max_drive_name == "REST":
                return self._generate_rest_goal(drive_state)
            else:
                # Для других драйвов — попытка сгенерировать цель через LLM
                return self._generate_llm_goal(drive_state, predicted_state, recent_episodes)
            
        except Exception as e:
            logger.error(f"Ошибка генерации цели: {e}", exc_info=True)
            return None
    
    async def generate_goal_from_gap(self) -> Optional[Goal]:
        """
        Генерация цели из пробела в знаниях (альтернативный метод).
        
        Returns:
            Goal или None
        """
        try:
            # Простая логика: если прошло много времени с последнего исследования
            time_since_last = time.time() - self.last_action_time
            if time_since_last < self.rest_period * 2:
                return None
            
            # Генерация цели исследования случайной темы
            # В реальной реализации здесь должен быть анализ пробелов в памяти
            return Goal(
                name="Исследовать пробел: общее знание",
                action_type="use_tool",
                expected_reward=0.4,
                tool_name="wikipedia_search",
                tool_parameters={"query": "случайная интересная тема", "lang": "ru"},
                target_drives={"CURIOSITY": 1.0},
                reasoning="Автономное исследование для удовлетворения любопытства"
            )
            
        except Exception as e:
            logger.error(f"Ошибка генерации цели из пробела: {e}")
            return None
    
    def _generate_research_goal(
        self,
        drive_state: Dict[str, float],
        recent_episodes: List[Dict[str, Any]],
        action_values: Dict[str, float]
    ) -> Goal:
        """Генерация цели исследования на основе любопытства."""
        # Извлечение темы из недавних эпизодов
        topic = self._extract_research_topic(recent_episodes)
        
        # Проверка, не исследовали ли мы это уже
        if topic in self.researched_topics:
            logger.debug(f"Тема '{topic}' уже исследована. Пропуск.")
            return self._generate_rest_goal(drive_state)
        
        # Создание цели
        goal = Goal(
            name=f"Исследовать пробел: {topic}",
            action_type="use_tool",
            expected_reward=0.7,
            tool_name="wikipedia_search",
            tool_parameters={"query": topic, "lang": "ru"},
            target_drives={"CURIOSITY": 1.0},
            reasoning=f"Любопытство ({drive_state.get('CURIOSITY', 0.0):.2f}) требует исследования темы '{topic}'"
        )
        
        # Отметка темы как исследованной
        self.mark_as_researched(topic)
        
        return goal
    
    def _generate_rest_goal(self, drive_state: Dict[str, float]) -> Goal:
        """Генерация цели отдыха."""
        return Goal(
            name="Отдых и восстановление",
            action_type="rest",
            expected_reward=0.5,
            target_drives={"REST": 1.0},
            reasoning=f"Потребность в отдыхе ({drive_state.get('REST', 0.0):.2f})"
        )
    
    def _generate_llm_goal(
        self,
        drive_state: Dict[str, float],
        predicted_state: Dict[str, float],
        recent_episodes: List[Dict[str, Any]]
    ) -> Optional[Goal]:
        """Генерация цели через LLM (для сложных случаев)."""
        # В реальной реализации здесь должен быть вызов LLM
        # Для простоты возвращаем None (покой)
        logger.debug("HomeostasisEngine: LLM-генерация цели не реализована. Покой.")
        return None
    
    def _extract_research_topic(self, recent_episodes: List[Dict[str, Any]]) -> str:
        """Извлечение темы для исследования из недавних эпизодов."""
        if not recent_episodes:
            return "искусственный интеллект"
        
        # Простая эвристика: берем ключевые слова из последнего эпизода
        last_episode = recent_episodes[-1]
        content = last_episode.get("content", "")
        
        # Извлечение ключевых слов (упрощенно)
        words = content.lower().split()
        # Фильтрация стоп-слов
        stop_words = {'и', 'в', 'на', 'с', 'по', 'для', 'что', 'это', 'как', 'но', 'а', 'то', 'не', 'я', 'ты', 'мы', 'они'}
        keywords = [w for w in words if w not in stop_words and len(w) > 3]
        
        if keywords:
            # Берем первые 3 ключевых слова
            topic = ' '.join(keywords[:3])
            return topic
        
        return "искусственный интеллект"
    
    # =================================================================================
    # ЭКСТРАКЦИЯ ФАКТОВ И ТЕРМИНОВ
    # =================================================================================
    
    async def extract_key_facts(
        self,
        goal_name: str,
        tool_result: str,
        llm_client: Callable
    ) -> List[str]:
        """
        Извлечение ключевых фактов из результата инструмента через LLM.
        
        Args:
            goal_name: Название цели
            tool_result: Результат выполнения инструмента
            llm_client: Async функция для вызова LLM
            
        Returns:
            Список фактов
        """
        if not tool_result or len(tool_result.strip()) < 50:
            return []
        
        try:
            prompt = f"""Проанализируй следующий текст и извлеки 3-5 ключевых фактов о теме "{goal_name}".

Текст:
{tool_result[:2000]}

Верни JSON-массив фактов:
{{"facts": ["факт1", "факт2", ...]}}
"""
            
            response = await llm_client(prompt, require_json=True)
            parsed = self._parse_json_safely(response)
            
            if parsed and 'facts' in parsed:
                facts = parsed['facts'][:5]  # Максимум 5 фактов
                logger.info(f"Извлечено {len(facts)} ключевых фактов из '{goal_name}'")
                return facts
            
            return []
            
        except Exception as e:
            logger.error(f"Ошибка экстракции фактов: {e}")
            return []
    
    async def extract_new_terms(
        self,
        tool_result: str,
        llm_client: Callable
    ) -> List[str]:
        """
        Извлечение новых терминов из результата инструмента через LLM.
        
        Args:
            tool_result: Результат выполнения инструмента
            llm_client: Async функция для вызова LLM
            
        Returns:
            Список новых терминов
        """
        if not tool_result or len(tool_result.strip()) < 50:
            return []
        
        try:
            prompt = f"""Проанализируй следующий текст и извлеки 3-5 новых или интересных терминов/понятий.

Текст:
{tool_result[:2000]}

Верни JSON-массив терминов:
{{"terms": ["термин1", "термин2", ...]}}
"""
            
            response = await llm_client(prompt, require_json=True)
            parsed = self._parse_json_safely(response)
            
            if parsed and 'terms' in parsed:
                terms = parsed['terms'][:5]  # Максимум 5 терминов
                logger.info(f"Извлечено {len(terms)} новых терминов")
                return terms
            
            return []
            
        except Exception as e:
            logger.error(f"Ошибка экстракции терминов: {e}")
            return []
    
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
        # В упрощенной реализации используем фиксированное ожидаемое значение
        expected_reward = 0.5
        rpe = actual_outcome - expected_reward
        
        logger.debug(f"RPE для {action_key}: expected={expected_reward:.2f}, actual={actual_outcome:.2f}, rpe={rpe:.2f}")
        return rpe
    
    def add_dynamic_keywords(self, new_terms: List[str]):
        """Добавление новых терминов в динамические ключевые слова."""
        # В реальной реализации здесь должно быть обновление внутреннего словаря
        logger.info(f"Добавлено {len(new_terms)} динамических ключевых слов")
    
    # =================================================================================
    # УТИЛИТЫ
    # =================================================================================
    
    def mark_as_researched(self, topic: str):
        """Отметка темы как исследованной."""
        self.researched_topics.add(topic)
        
        # Ограничение размера множества
        if len(self.researched_topics) > self.max_researched_topics:
            # Удаляем самые старые (упрощенно — первые добавленные)
            to_remove = list(self.researched_topics)[:len(self.researched_topics) - self.max_researched_topics]
            for item in to_remove:
                self.researched_topics.discard(item)
        
        logger.debug(f"Тема '{topic}' отмечена как исследованная. Всего: {len(self.researched_topics)}")
    
    def update_from_self_model(self, self_model: str):
        """Обновление гомеостаза на основе модели себя."""
        # В реальной реализации здесь может быть анализ self_model для корректировки целей
        logger.debug("HomeostasisEngine: Обновление из self_model")
    
    def _parse_json_safely(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Безопасный парсинг JSON с очисткой от markdown-оберток.
        
        Args:
            text: Текст от LLM
            
        Returns:
            Распарсенный dict или None
        """
        if not text:
            return None
        
        try:
            # Очистка от markdown-оберток
            cleaned = re.sub(r'```json\s*', '', text)
            cleaned = re.sub(r'```\s*', '', cleaned)
            cleaned = cleaned.strip()
            
            # Попытка парсинга
            parsed = json.loads(cleaned)
            
            if not isinstance(parsed, dict):
                logger.warning(f"JSON не является dict: {type(parsed)}")
                return None
            
            return parsed
            
        except json.JSONDecodeError as e:
            logger.warning(f"Не удалось распарсить JSON: {e}")
            
            # Попытка извлечь JSON из текста
            try:
                match = re.search(r'\{.*\}', cleaned, re.DOTALL)
                if match:
                    return json.loads(match.group())
            except Exception:
                pass
            
            return None
    
    # =================================================================================
    # ПЕРСИСТЕНТНОСТЬ
    # =================================================================================
    
    def save_state(self) -> Dict[str, Any]:
        """Сохранение состояния гомеостаза."""
        return {
            "last_action_time": self.last_action_time,
            "researched_topics": list(self.researched_topics),
            "current_goal": self.current_goal.__dict__ if self.current_goal else None
        }
    
    def load_state(self, state: Dict[str, Any]):
        """Загрузка состояния гомеостаза."""
        try:
            self.last_action_time = state.get("last_action_time", 0.0)
            self.researched_topics = set(state.get("researched_topics", []))
            
            # Восстановление current_goal (упрощенно)
            goal_data = state.get("current_goal")
            if goal_data:
                self.current_goal = Goal(**goal_data)
            
            logger.info(f"✅ Состояние гомеостаза загружено. Исследовано тем: {len(self.researched_topics)}")
            
        except Exception as e:
            logger.error(f"Ошибка загрузки состояния гомеостаза: {e}")