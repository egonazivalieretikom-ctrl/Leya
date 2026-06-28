# leya_core/request_classifier.py — Классификатор пользовательских запросов.
# Этап 2.1: Трёхуровневая классификация (эвристика → cache → LLM) с
# confidence-based routing и graceful degradation.

import asyncio
import json
import logging
import re
from dataclasses import dataclass
from enum import Enum
from typing import Optional, Any

from pydantic import BaseModel, Field

from .exceptions import LeyaLLMError, LeyaJSONParseError, LeyaLLMUnavailableError

logger = logging.getLogger("LeyaRequestClassifier")


# =================================================================================
# PYDANTIC MODELS
# =================================================================================

class UserIntent(str, Enum):
    """Намерение пользователя."""
    GREETING = "GREETING"
    FAREWELL = "FAREWELL"
    QUESTION = "QUESTION"
    SEARCH = "SEARCH"
    REMEMBER = "REMEMBER"
    FORGET = "FORGET"
    STATUS = "STATUS"
    HELP = "HELP"
    TOOL_REQUEST = "TOOL_REQUEST"
    PERSONAL = "PERSONAL"
    UNKNOWN = "UNKNOWN"


class IntentClassification(BaseModel):
    """Результат классификации запроса."""
    intent: UserIntent = Field(..., description="Намерение пользователя")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Уверенность классификации")
    topic: Optional[str] = Field(None, description="Извлечённая тема (если есть)")
    source: str = Field(..., description="Источник классификации: heuristic|cache|llm|fallback")
    raw_input: str = Field(..., description="Исходный запрос")

    class Config:
        use_enum_values = True


# =================================================================================
# HEURISTIC PATTERNS (синонимы и regex)
# =================================================================================

# Словарь паттернов для каждого intent с весами
HEURISTIC_PATTERNS: dict[UserIntent, list[tuple[str, float]]] = {
    UserIntent.GREETING: [
        (r"\b(привет|здравствуй|добрый\s+(день|вечер|утро)|hello|hi|хеллоу|приветствую)\b", 0.95),
        (r"^(прив|здрав|хай)$", 0.9),
    ],
    UserIntent.FAREWELL: [
        (r"\b(пока|до\s+(свидания|встречи)|увидимся|прощай|всего\s+доброго|bye)\b", 0.95),
        (r"^(поки|чао)$", 0.9),
    ],
    UserIntent.QUESTION: [
        (r"\b(что\s+такое|кто\s+такой|как\s+(работает|устроен)|почему|зачем|объясни|расскажи\s+про)\b", 0.85),
        (r"\?$", 0.7),  # вопросительный знак в конце
    ],
    UserIntent.SEARCH: [
        (r"\b(поищи|найди|загугли|поиск|ищу\s+информацию|погугли)\b", 0.9),
        (r"\b(в\s+интернете|в\s+сети|онлайн)\b", 0.8),
    ],
    UserIntent.REMEMBER: [
        (r"\b(запомни|сохрани|запиши|помни|запиши\s+что)\b", 0.9),
    ],
    UserIntent.FORGET: [
        (r"\b(забудь|удали|стереть|не\s+помни)\b", 0.9),
    ],
    UserIntent.STATUS: [
        (r"\b(как\s+ты|как\s+себя\s+чувствуешь|какое\s+состояние|что\s+делаешь|как\s+дела)\b", 0.85),
    ],
    UserIntent.HELP: [
        (r"\b(помоги|помощь|help|что\s+ты\s+умеешь|как\s+тобой\s+управлять)\b", 0.9),
    ],
    UserIntent.TOOL_REQUEST: [
        (r"\b(используй|запусти|выполни|открой|браузер|калькулятор)\b", 0.8),
    ],
    UserIntent.PERSONAL: [
        (r"\b(ты\s+кто|расскажи\s+о\s+себе|твоё\s+имя|сколько\s+тебе\s+лет|ты\s+живая)\b", 0.85),
    ],
}


# =================================================================================
# REQUEST CLASSIFIER
# =================================================================================

class RequestClassifier:
    """Трёхуровневый классификатор пользовательских запросов.

    Этап 2.1: defence-in-depth подход.
    1. Быстрая эвристика (regex + синонимы) — мгновенно
    2. Semantic cache через memory — если похожий запрос уже был
    3. LLM-assisted extraction — только если нужно

    Confidence-based routing: если эвристика уверена (≥ threshold),
    LLM не вызывается. Graceful degradation: если LLM недоступен,
    fallback на эвристику.
    """

    def __init__(
        self,
        llm_client,
        memory,
        use_llm_threshold: float = 0.7,
        cache_similarity_threshold: float = 0.85,
    ):
        """
        Args:
            llm_client: LLM клиент для level 3
            memory: Memory system для semantic cache
            use_llm_threshold: Порог confidence для вызова LLM
            cache_similarity_threshold: Порог similarity для cache hit
        """
        self.llm_client = llm_client
        self.memory = memory
        self.use_llm_threshold = use_llm_threshold
        self.cache_similarity_threshold = cache_similarity_threshold
        
        # Компилируем regex паттерны
        self._compiled_patterns = {}
        for intent, patterns in HEURISTIC_PATTERNS.items():
            self._compiled_patterns[intent] = [
                (re.compile(pattern, re.IGNORECASE | re.UNICODE), weight)
                for pattern, weight in patterns
            ]
        
        logger.info(
            f"✅ RequestClassifier инициализирован "
            f"(llm_threshold={use_llm_threshold}, cache_threshold={cache_similarity_threshold})"
        )

    async def classify(self, user_input: str) -> IntentClassification:
        """Классификация пользовательского запроса.

        Трёхуровневая стратегия:
        1. Быстрая эвристика
        2. Semantic cache
        3. LLM-assisted extraction
        4. Fallback

        Args:
            user_input: Текст запроса пользователя

        Returns:
            IntentClassification с intent, confidence, topic, source
        """
        if not user_input or not user_input.strip():
            return IntentClassification(
                intent=UserIntent.UNKNOWN,
                confidence=0.0,
                topic=None,
                source="fallback",
                raw_input=user_input or "",
            )

        user_input = user_input.strip()

        # Уровень 1: Проверка кэша (самый быстрый путь)
        cache_result = await self._cache_lookup(user_input)
        if cache_result:
            logger.debug(f"Найдено в кэше: {cache_result.intent}")
            return cache_result

        # Уровень 2: Быстрая эвристика
        heuristic_result = self._heuristic_classify(user_input)
        if heuristic_result.confidence >= self.use_llm_threshold:
            logger.debug(
                f"Эвристика уверена: {heuristic_result.intent} "
                f"(confidence={heuristic_result.confidence:.2f})"
            )
            return heuristic_result

        # Уровень 3: LLM (с graceful degradation)
        try:
            llm_result = await self._llm_classify(user_input)
            return llm_result
        except (LeyaLLMError, LeyaLLMUnavailableError, Exception) as exc:
            logger.warning(f"Ошибка LLM классификации, fallback на эвристику: {exc}")
            # Fallback: возвращаем результат эвристики с пониженной уверенностью
            return IntentClassification(
                intent=heuristic_result.intent,
                confidence=min(heuristic_result.confidence, 0.6),  # Понижаем уверенность
                source="fallback",
                topic=heuristic_result.topic,
                raw_input=heuristic_result.raw_input,
            )

        # Уровень 4: Fallback — используем лучшую эвристику
        logger.debug("Fallback на эвристику")
        return heuristic_result

    def _heuristic_classify(self, text: str) -> IntentClassification:
        """
        Быстрая эвристическая классификация без LLM.
    
        Args:
            text: Текст запроса пользователя
    
        Returns:
            IntentClassification с результатом классификации
        """
        text_lower = text.lower().strip()
    
        # STATUS эвристики (высокий приоритет)
        status_patterns = [
            r"как(?:ое|ая|ую|ие)\s+(?:у\s+тебя\s+)?состояни",
            r"как\s+ты\s+себя\s+чувству",
            r"что\s+ты\s+(?:сейчас\s+)?делаешь",
            r"как\s+твои\s+дела",
            r"как\s+поживаешь",
            r"что\s+нового",
        ]
    
        for pattern in status_patterns:
            if re.search(pattern, text_lower):
                return IntentClassification(
                    intent=UserIntent.STATUS,
                    confidence=0.85,
                    source="heuristic",  # ← ДОБАВЬТЕ
                    topic=None,
                    raw_input=text_lower,
                )
    
        # QUESTION эвристики
        question_patterns = [
            r"^(?:что|кто|как|где|когда|почему|зачем)\s+",
            r"\?$",
        ]
    
        for pattern in question_patterns:
            if re.search(pattern, text_lower):
                # Извлекаем тему из вопроса
                topic = self._extract_topic_heuristic(text_lower, UserIntent.QUESTION)
                return IntentClassification(
                    intent=UserIntent.QUESTION,
                    confidence=0.75,
                    source="heuristic",
                    topic=topic,  # ← ИСПРАВЛЕНО
                    raw_input=text_lower,
                )
    
        # Основной цикл по скомпилированным паттернам
        scores: dict[UserIntent, float] = {}
    
        for intent, patterns in self._compiled_patterns.items():
            total_weight = 0.0
            for pattern, weight in patterns:
                if pattern.search(text_lower):  # ✅ ИСПРАВЛЕНО: было user_input
                    total_weight += weight
        
            if total_weight > 0:
                normalized = min(1.0, total_weight / max(1, len(patterns) * 0.5))
                scores[intent] = normalized
    
        if not scores:
            return IntentClassification(
                intent=UserIntent.UNKNOWN,
                confidence=0.0,
                source="heuristic",  # ← ДОБАВЬТЕ
                topic=None,
                raw_input=text_lower,
            )
    
        best_intent = max(scores, key=scores.get)
        confidence = scores[best_intent]
    
        topic = self._extract_topic_heuristic(text_lower, best_intent)
    
        return IntentClassification(
            intent=best_intent,
            confidence=confidence,
            source="heuristic",  # ← ДОБАВЬТЕ
            topic=topic,
            raw_input=text_lower,
        )

    def _extract_topic_heuristic(self, user_input: str, intent: UserIntent) -> Optional[str]:
        """Простая эвристика извлечения темы.

        Для QUESTION/SEARCH — пытаемся извлечь ключевые слова.
        """
        if intent not in (UserIntent.QUESTION, UserIntent.SEARCH):
            return None

        # Удаляем стоп-слова
        stop_words = {
            "что", "как", "кто", "почему", "зачем", "где", "когда",
            "расскажи", "объясни", "поищи", "найди", "мне", "хочу",
            "узнать", "интересно", "это", "такое", "такой", "работае",
        }
        
        # Токенизация (простая)
        words = re.findall(r"\b\w+\b", user_input.lower())
        topic_words = [w for w in words if w not in stop_words and len(w) > 2]
        
        if topic_words:
            # Берём первые 3-5 значимых слов
            topic = " ".join(topic_words[:5])
            return topic
        
        return None

    async def _cache_lookup(self, user_input: str) -> Optional[IntentClassification]:
        """Уровень 2: Semantic cache через memory.

        Ищет похожие запросы в памяти. Если similarity ≥ threshold —
        возвращает кэшированный результат.
        """
        if not self.memory:
            return None

        try:
            # Ищем похожие запросы в памяти
            similar = await self.memory.retrieve_context(
                query=user_input,
                top_k=3,
                memory_type="EPISODIC",
                filters={"type": "user_request"},
            )

            if not similar:
                return None

            # Проверяем similarity
            for item in similar:
                similarity = item.get("similarity", 0.0)
                if similarity >= self.cache_similarity_threshold:
                    metadata = item.get("metadata", {})
                    cached_intent = metadata.get("intent")
                    cached_confidence = metadata.get("confidence", 0.0)
                    cached_topic = metadata.get("topic")

                    if cached_intent and cached_confidence > 0:
                        return IntentClassification(
                            intent=UserIntent(cached_intent),
                            confidence=cached_confidence,
                            topic=cached_topic,
                            source="cache",
                            raw_input=user_input,
                        )

        except Exception as e:
            logger.warning(f"Ошибка cache lookup: {e}", exc_info=True)

        return None

    async def _llm_classify(self, user_input: str) -> IntentClassification:
        """Уровень 3: LLM-assisted extraction.

        Отправляет маленький промпт с require_json=True.
        """
        prompt = f"""Проанализируй запрос пользователя и определи намерение.

Запрос: "{user_input}"

Верни СТРОГО JSON в формате:
{{
    "intent": "Одно из: GREETING, FAREWELL, QUESTION, SEARCH, REMEMBER, FORGET, STATUS, HELP, TOOL_REQUEST, PERSONAL, UNKNOWN",
    "confidence": 0.0-1.0,
    "topic": "Извлечённая тема (если есть, иначе null)"
}}

ВАЖНО:
- Ответ ДОЛЖЕН быть валидным JSON
- intent — одно из перечисленных значений
- confidence — число от 0.0 до 1.0
- topic — строка или null
"""

        try:
            raw_response = await self.llm_client.chat(
                prompt=prompt,
                system="Ты — классификатор намерений. Отвечай СТРОГО в формате JSON.",
                require_json=True,
                timeout=10.0,  # короткий timeout для классификации
            )

            # Проверка типа ответа (защита от некорректных mock'ов)
            if not isinstance(raw_response, (str, bytes, bytearray)):
                raise LeyaLLMError(
                    f"LLM вернул некорректный тип ответа: {type(raw_response).__name__}"
                )

            try:
                data = json.loads(raw_response)
            except (json.JSONDecodeError, TypeError) as exc:
                raise LeyaJSONParseError(
                    f"Не удалось распарсить JSON от LLM: {exc}",
                    context={"raw_response": str(raw_response)[:200]},
                ) from exc

            intent_str = data.get("intent", "UNKNOWN")
            confidence = float(data.get("confidence", 0.5))
            topic = data.get("topic")

            # Валидируем intent
            try:
                intent = UserIntent(intent_str)
            except ValueError:
                logger.warning(f"LLM вернул невалидный intent: {intent_str}")
                intent = UserIntent.UNKNOWN

            return IntentClassification(
                intent=intent,
                confidence=confidence,
                topic=topic,
                source="llm",
                raw_input=user_input,
            )

        except Exception as e:
            logger.warning(f"Ошибка LLM классификации: {e}", exc_info=True)
            raise
    

    async def save_to_cache(self, classification: IntentClassification) -> None:
        """Сохранение результата классификации в memory для будущего cache.

        Вызывается после успешной обработки запроса, чтобы следующие
        похожие запросы могли использовать cache.
        """
        if not self.memory:
            return

        try:
            await self.memory.store_perception(
                content=classification.raw_input,
                memory_type="EPISODIC",
                metadata={
                    "type": "user_request",
                    "intent": classification.intent,
                    "confidence": classification.confidence,
                    "topic": classification.topic,
                    "source": classification.source,
                },
            )
            logger.debug(f"Классификация сохранена в cache: {classification.intent}")
        except Exception as e:
            logger.warning(f"Ошибка сохранения в cache: {e}", exc_info=True)