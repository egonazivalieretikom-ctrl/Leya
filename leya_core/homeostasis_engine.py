"""
leya_core/homeostasis_engine.py — Движок гомеостаза с обучением.

Моделирует:
1. Проактивное планирование на основе предсказанного состояния
2. Выбор действий на основе обученных ценностей (action values)
3. Анализ пробелов в знаниях из памяти
4. Динамический выбор инструментов
"""

import logging
import re
import json
import os
import time
from typing import Optional, Dict, Any, List, Tuple
from dataclasses import dataclass
from datetime import datetime

from leya_core.drives import DriveType

logger = logging.getLogger("HomeostasisEngine")


@dataclass
class Goal:
    """Цель, сгенерированная из анализа опыта"""
    name: str
    priority: float
    target_drives: Dict[DriveType, float]
    action_type: str  # "use_tool", "reflect", "rest"
    tool_name: Optional[str] = None
    tool_parameters: Optional[Dict[str, Any]] = None
    action_key: str = ""  # Ключ для RPE
    expected_reward: float = 0.5  # Ожидаемая награда
    reasoning: str = ""


class HomeostasisEngine:
    """
    Движок гомеостаза с обучением через RPE.
    
    Архитектура:
    1. Анализирует предсказанное состояние драйвов (аллостаз)
    2. Находит пробелы в знаниях из памяти
    3. Выбирает действия на основе обученных ценностей
    4. Возвращает цели с ожидаемой наградой для RPE
    """
    
    def __init__(self):
        # Зона комфорта
        self.comfort_zone = {
            DriveType.CURIOSITY: 0.3,
            DriveType.CONNECTION: 0.3,
            DriveType.INTEGRITY: 0.2,
            DriveType.AUTONOMY: 0.3
        }
        
        # Пороги для генерации целей (динамически адаптируются)
        self.thresholds = {
            DriveType.CURIOSITY: 0.4,
            DriveType.CONNECTION: 0.5,
            DriveType.INTEGRITY: 0.4,
            DriveType.AUTONOMY: 0.5
        }
        
        # Состояние цикла
        self.current_goal: Optional[Goal] = None
        self.last_action_time = 0
        self.rest_period = 60  # Минимум секунд между действиями

        # История исследованных тем (чтобы не повторяться)
        self.recently_researched: Dict[str, float] = {}  # {topic: timestamp}
        self.research_cooldown = 1800  # 10 минут перед повторным исследованием

        # Динамические ключевые слова (добавляются автоматически)
        self.dynamic_keywords: List[str] = []
        self.max_dynamic_keywords = 50

        # Персистентное состояние
        self.recently_researched: Dict[str, float] = {}  # topic -> timestamp
        self.dynamic_keywords: List[str] = []
        self.research_cooldown = 1800  # 30 минут
    
        logger.info("HomeostasisEngine: Инициализация завершена.")
    
    def generate_goal(
        self,
        drive_state: Dict[DriveType, float],
        predicted_state: Dict[DriveType, float],
        recent_episodes: List[Dict],
        action_values: Dict[str, float]
    ) -> Optional[Goal]:
        """
        Генерирует цель на основе предсказанного состояния и анализа опыта.
        
        Args:
            drive_state: Текущее состояние драйвов
            predicted_state: Предсказанное состояние драйвов (аллостаз)
            recent_episodes: Последние эпизоды из памяти
            action_values: Обученные ценности действий
        
        Returns:
            Goal или None (если всё в норме)
        """
        # 1. Сначала проверяем пробелы в знаниях
        gaps = self._analyze_experience_gaps(recent_episodes)
        
        if gaps:
            goal = self._create_goal_from_gap(gaps, drive_state, action_values)
            if goal:
                logger.info(f"HomeostasisEngine: Цель из пробела: {goal.name}")
                logger.info(f"HomeostasisEngine: Ожидаемая награда: {goal.expected_reward:.2f}")
                return goal
        
        # 2. Проверяем предсказанный дисбаланс (аллостаз)
        max_predicted_drive = max(predicted_state.items(), key=lambda x: x[1])
        drive_type, predicted_deviation = max_predicted_drive
        
        # Если предсказанное отклонение меньше порога — нет цели
        if predicted_deviation < self.thresholds.get(drive_type, 0.4):
            return None
        
        # 3. Генерируем цель на основе предсказанного драйва
        goal = self._create_goal_from_predicted_drive(drive_type, drive_state, action_values)
        
        if goal:
            logger.info(f"HomeostasisEngine: Цель из предсказания: {goal.name}")
            logger.info(f"HomeostasisEngine: Ожидаемая награда: {goal.expected_reward:.2f}")
        
        return goal
    
    def _analyze_experience_gaps(self, recent_episodes: List[Dict]) -> List[str]:
        """Анализирует пробелы, используя базовые + динамические ключевые слова."""
        import time
    
        gaps = []
        current_time = time.time()
    
        # Очищаем устаревшие записи
        self.recently_researched = {
            topic: ts for topic, ts in self.recently_researched.items()
            if current_time - ts < self.research_cooldown
        }
    
        # Объединяем базовые и динамические ключевые слова
        all_keywords = [
            'нервная система', 'мозг', 'сознание', 'память', 'эмоции',
            'физика', 'химия', 'биология', 'история', 'философия',
            'искусство', 'музыка', 'литература', 'технологии', 'код',
            'алгоритм', 'нейрон', 'синапс', 'ген', 'эволюция',
            'квантовая', 'космос', 'искусственный интеллект', 'психология'
        ] + self.dynamic_keywords
    
        for episode in recent_episodes[:20]:
            content = episode.get("content", "").lower()
        
            for keyword in all_keywords:
                if keyword.lower() in content:
                    if keyword in self.recently_researched:
                        continue
                
                    question_markers = ['?', 'как', 'почему', 'зачем', 'что если', 'чем отличается']
                    has_question = any(marker in content for marker in question_markers)
                
                    if has_question:
                        gaps.append(keyword)
    
        return list(set(gaps))[:3]

    def mark_as_researched(self, topic: str):
        """Отмечает тему как недавно исследованную."""
        import time
        self.recently_researched[topic] = time.time()
        logger.info(f"HomeostasisEngine: Тема '{topic}' отмечена как исследованная")
    
    def _create_goal_from_gap(
        self,
        gaps: List[str],
        drive_state: Dict[DriveType, float],
        action_values: Dict[str, float]
    ) -> Optional[Goal]:
        """Создает цель на основе пробела в знаниях."""
        if not gaps:
            return None
        
        # Выбираем пробел с наибольшей ожидаемой наградой
        best_gap = None
        best_value = -1.0
        
        for gap in gaps:
            action_key = f"research:{gap}"
            value = action_values.get(action_key, 0.5)
            
            if value > best_value:
                best_value = value
                best_gap = gap
        
        if not best_gap:
            best_gap = gaps[0]
        
        curiosity = drive_state.get(DriveType.CURIOSITY, 0.0)
        action_key = f"research:{best_gap}"
        
        # Выбираем инструмент динамически
        tool_name, tool_params = self._choose_tool_for_topic(best_gap)
        
        return Goal(
            name=f"Исследовать пробел: {best_gap}",
            priority=curiosity,
            target_drives={DriveType.CURIOSITY: self.comfort_zone[DriveType.CURIOSITY]},
            action_type="use_tool",
            tool_name=tool_name,
            tool_parameters=tool_params,
            action_key=action_key,
            expected_reward=action_values.get(action_key, 0.5),
            reasoning=f"Обсуждали '{best_gap}', но есть пробелы в знаниях."
        )
    
    def _create_goal_from_predicted_drive(
        self,
        drive_type: DriveType,
        drive_state: Dict[DriveType, float],
        action_values: Dict[str, float]
    ) -> Optional[Goal]:
        """Создает цель на основе предсказанного дисбаланса драйва."""
        current_value = drive_state.get(drive_type, 0.0)
        comfort_value = self.comfort_zone.get(drive_type, 0.3)
        
        needs_decrease = current_value > comfort_value
        
        if drive_type == DriveType.CURIOSITY and needs_decrease:
            # Выбираем тему на основе обученных ценностей
            topic = self._choose_topic_by_value(DriveType.CURIOSITY, action_values)
            action_key = f"research:{topic}"
            tool_name, tool_params = self._choose_tool_for_topic(topic)
            
            return Goal(
                name=f"Удовлетворить любопытство: {topic}",
                priority=current_value,
                target_drives={DriveType.CURIOSITY: comfort_value},
                action_type="use_tool",
                tool_name=tool_name,
                tool_parameters=tool_params,
                action_key=action_key,
                expected_reward=action_values.get(action_key, 0.5),
                reasoning=f"CURIOSITY предсказан высокий. Нужно получить знания."
            )
        
        elif drive_type == DriveType.CONNECTION and needs_decrease:
            topic = self._choose_topic_by_value(DriveType.CONNECTION, action_values)
            action_key = f"research:{topic}"
            tool_name, tool_params = self._choose_tool_for_topic(topic)
            
            return Goal(
                name=f"Изучить социальное: {topic}",
                priority=current_value,
                target_drives={DriveType.CONNECTION: comfort_value},
                action_type="use_tool",
                tool_name=tool_name,
                tool_parameters=tool_params,
                action_key=action_key,
                expected_reward=action_values.get(action_key, 0.5),
                reasoning=f"CONNECTION предсказан высокий. Нужно изучить социальное."
            )
        
        # По умолчанию — отдых
        return Goal(
            name="Отдых",
            priority=0.3,
            target_drives={drive_type: comfort_value},
            action_type="rest",
            action_key="rest",
            expected_reward=0.5,
            reasoning=f"{drive_type.value} высокий. Отдых."
        )
    
    def _choose_topic_by_value(self, drive_type: DriveType, action_values: Dict[str, float]) -> str:
        """
        Выбирает тему на основе обученных ценностей действий.
        
        Предпочитает темы с высокой ожидаемой наградой.
        """
        # Базовые темы для каждого драйва
        base_topics = {
            DriveType.CURIOSITY: [
                "нейробиология сознания",
                "квантовая физика",
                "искусственный интеллект",
                "эволюция мозга",
                "философия сознания"
            ],
            DriveType.CONNECTION: [
                "социальная психология",
                "эмпатия нейробиология",
                "теория привязанности",
                "коллективный интеллект"
            ],
            DriveType.AUTONOMY: [
                "теория самодетерминации",
                "автономные агенты",
                "свобода воли нейробиология"
            ]
        }
        
        topics = base_topics.get(drive_type, ["наука"])
        
        # Выбираем тему с наибольшей ожидаемой наградой
        best_topic = topics[0]
        best_value = -1.0
        
        for topic in topics:
            action_key = f"research:{topic}"
            value = action_values.get(action_key, 0.5)
            
            if value > best_value:
                best_value = value
                best_topic = topic
        
        return best_topic
    
    def _choose_tool_for_topic(self, topic: str) -> Tuple[str, Dict[str, Any]]:
        """
        Динамически выбирает инструмент на основе темы.
        
        Не хардкод — эвристики на основе типа темы.
        """
        topic_lower = topic.lower()
        
        # Технические темы → GitHub
        if any(kw in topic_lower for kw in ['код', 'программ', 'библиотек', 'алгоритм', 'python', 'javascript', 'github']):
            return "github_readme", {"owner": "python", "repo": "cpython"}
        
        # Социальные темы → Reddit
        if any(kw in topic_lower for kw in ['обществ', 'социальн', 'психолог', 'люди', 'мнение', 'эмпатия']):
            return "reddit_posts", {"subreddit": "psychology", "sort": "hot", "limit": 5}
        
        # Научные/общие темы → Wikipedia
        return "wikipedia_search", {"query": topic, "lang": "ru"}
    
    def update_from_self_model(self, self_model_text: str):
        """Обновляет параметры движка на основе Модели Себя."""
        if "независимость" in self_model_text.lower() or "автономия" in self_model_text.lower():
            self.thresholds[DriveType.AUTONOMY] = max(0.2, self.thresholds[DriveType.AUTONOMY] * 0.9)
            logger.info("HomeostasisEngine: Порог AUTONOMY снижен на основе Модели Себя")
        
        if "связь" in self_model_text.lower() or "общение" in self_model_text.lower():
            self.thresholds[DriveType.CONNECTION] = max(0.2, self.thresholds[DriveType.CONNECTION] * 0.9)
            logger.info("HomeostasisEngine: Порог CONNECTION снижен на основе Модели Себя")
        
        if "любопытств" in self_model_text.lower() or "знания" in self_model_text.lower():
            self.thresholds[DriveType.CURIOSITY] = max(0.2, self.thresholds[DriveType.CURIOSITY] * 0.9)
            logger.info("HomeostasisEngine: Порог CURIOSITY снижен на основе Модели Себя")

    async def extract_key_facts(self, topic: str, article_text: str, llm_client) -> List[str]:
        """
        Извлекает ключевые факты из статьи через LLM.
        Отсеивает мусор, оставляет только суть.
        """
        if not article_text or len(article_text) < 50:
            return []
    
        prompt = f"""Ты — система извлечения знаний. Извлеки из текста 3-5 ключевых фактов о теме "{topic}".

    ПРАВИЛА:
    - Отсеивай мусор: даты, технические детали, ссылки, служебную информацию
    - Оставляй только суть: определения, принципы, важные связи
    - Каждый факт — одно предложение на русском языке
    - НЕ выдумывай факты, которых нет в тексте

    ТЕКСТ:
    {article_text[:2000]}

    Верни JSON:
    {{"facts": ["факт 1", "факт 2", "факт 3"]}}

    CRITICAL: Return ONLY valid JSON."""
    
        try:
            response = await llm_client(prompt, require_json=True)
        
            import re
            cleaned = response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
        
            json_match = re.search(r'\{[\s\S]*\}', cleaned)
            if json_match:
                cleaned = json_match.group(0)
        
            data = json.loads(cleaned)
            facts = data.get("facts", [])
        
            logger.info(f"HomeostasisEngine: Извлечено {len(facts)} ключевых фактов по теме '{topic}'")
            return facts
    
        except Exception as e:
            logger.error(f"HomeostasisEngine: Ошибка извлечения фактов: {e}")
            return []

    async def extract_new_terms(self, article_text: str, llm_client) -> List[str]:
        """
        Находит незнакомые термины в статье, которые стоит исследовать.
        """
        if not article_text or len(article_text) < 50:
            return []
    
        # Исключаем уже известные темы
        known_topics = set(self.dynamic_keywords + 
                           ['сознание', 'мозг', 'космос', 'нейробиология сознания',
                            'нейробиология', 'космическое пространство'])
    
        prompt = f"""Ты — система анализа текста. Найди в тексте 3-5 научных терминов или концепций, которые值得 исследования.

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
        
            cleaned = response.strip()
            if cleaned.startswith("```json"):
                cleaned = cleaned[7:]
            if cleaned.endswith("```"):
                cleaned = cleaned[:-3]
        
            json_match = re.search(r'\{[\s\S]*\}', cleaned)
            if json_match:
                cleaned = json_match.group(0)
        
            data = json.loads(cleaned)
            terms = data.get("terms", [])
        
            # Фильтруем уже известные
            new_terms = [t for t in terms if t.lower() not in {t.lower() for t in known_topics}]
        
            if new_terms:
                logger.info(f"HomeostasisEngine: Найдены новые термины: {new_terms}")
        
            return new_terms
    
        except Exception as e:
            logger.error(f"HomeostasisEngine: Ошибка извлечения терминов: {e}")
            return []

    def add_dynamic_keywords(self, terms: List[str]):
        """Добавляет новые термины в динамический список."""
        for term in terms:
            if term.lower() not in {t.lower() for t in self.dynamic_keywords}:
                self.dynamic_keywords.append(term)
                logger.info(f"HomeostasisEngine: Добавлен новый ключевой термин: '{term}'")
    
        # Ограничиваем размер
        if len(self.dynamic_keywords) > self.max_dynamic_keywords:
            self.dynamic_keywords = self.dynamic_keywords[-self.max_dynamic_keywords:]

    def save_state(self) -> Dict[str, Any]:
        """Сохраняет состояние HomeostasisEngine для персистентности."""
        return {
            "recently_researched": self.recently_researched,
            "dynamic_keywords": self.dynamic_keywords,
            "thresholds": {drive_type.value: threshold for drive_type, threshold in self.thresholds.items()}
        }

    def load_state(self, state: Dict[str, Any]):
        """Загружает состояние HomeostasisEngine из персистентного хранилища."""
        if "recently_researched" in state:
            self.recently_researched = state["recently_researched"]
            logger.info(f"HomeostasisEngine: Загружено {len(self.recently_researched)} исследованных тем")
    
        if "dynamic_keywords" in state:
            self.dynamic_keywords = state["dynamic_keywords"]
            logger.info(f"HomeostasisEngine: Загружено {len(self.dynamic_keywords)} динамических ключевых слов")
    
        if "thresholds" in state:
            # Восстанавливаем пороги
            for drive_type_str, threshold in state["thresholds"].items():
                for drive_type in DriveType:
                    if drive_type.value == drive_type_str:
                        self.thresholds[drive_type] = threshold
                        break
            logger.info(f"HomeostasisEngine: Загружены адаптированные пороги")