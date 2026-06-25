"""
leya_core/thinker.py — "Мозг" Леи / Когнитивный планировщик.
Этап 3.1: Полная переработка. Надежный JSON-парсинг, биологический промпт.
"""
import asyncio
import json
import logging
import re
from leya_core.config import settings
from dataclasses import dataclass, field
from typing import Dict, Any, Optional, Callable, List

logger = logging.getLogger("CoreThinker")


# =================================================================================
# МОДЕЛИ ДАННЫХ
# =================================================================================

@dataclass
class CognitiveOutput:
    """Структурированный вывод когнитивного цикла."""
    response: str = ""  # Ответ пользователю или внешнему миру
    internal_monologue: str = ""  # Внутренний монолог (мысли Леи)
    action_intent: str = "none"  # Намерение действия: "none", "remember_fact", "use_tool", "reflect"
    self_reflection: str = ""  # Саморефлексия (инсайт о себе)
    
    def __post_init__(self):
        """Валидация и очистка полей."""
        # Очистка от лишних пробелов
        self.response = self.response.strip() if self.response else ""
        self.internal_monologue = self.internal_monologue.strip() if self.internal_monologue else ""
        self.action_intent = self.action_intent.strip().lower() if self.action_intent else "none"
        self.self_reflection = self.self_reflection.strip() if self.self_reflection else ""
        
        # Валидация action_intent
        valid_intents = {"none", "remember_fact", "use_tool", "reflect", "ask_question"}
        if self.action_intent not in valid_intents:
            logger.warning(f"Некорректный action_intent: {self.action_intent}. Сброс в 'none'")
            self.action_intent = "none"


# =================================================================================
# КОГНИТИВНЫЙ ПЛАНИРОВЩИК
# =================================================================================

class CoreThinker:
    """
    Когнитивный планировщик Леи.
    Строит промпт с полным контекстом, вызывает LLM, парсит structured output.
    """
    
    def __init__(
        self,
        llm_client: Callable,
        soul_manager: Optional[Any] = None,
        model_name: str = None,
        temperature: float = None,
        max_tokens: int = None
    ):
        self.llm_client = llm_client
        self.soul_manager = soul_manager
        self.model_name = model_name or settings.ollama.model
        self.temperature = temperature if temperature is not None else settings.thinker.temperature
        self.max_tokens = max_tokens if max_tokens is not None else settings.thinker.max_tokens
        
        # Загрузка soul (личности)
        self.personality = ""
        self.rules = ""
        self.values = ""
        self._load_soul()
        
        logger.info(f"✅ CoreThinker инициализирован. Модель: {model_name}")
    
    # =================================================================================
    # ЗАГРУЗКА ЛИЧНОСТИ (SOUL)
    # =================================================================================
    
    def _load_soul(self):
        """Загрузка личности из soul_manager или файлов."""
        try:
            if self.soul_manager:
                # Попытка загрузить через soul_manager
                if hasattr(self.soul_manager, 'get_personality'):
                    self.personality = self.soul_manager.get_personality()
                if hasattr(self.soul_manager, 'get_rules'):
                    self.rules = self.soul_manager.get_rules()
                if hasattr(self.soul_manager, 'get_values'):
                    self.values = self.soul_manager.get_values()
            
            # Если soul_manager не предоставил данные, загружаем из файлов
            if not self.personality:
                self.personality = self._load_soul_file("leya_soul/personality.txt")
            if not self.rules:
                self.rules = self._load_soul_file("leya_soul/rules.txt")
            if not self.values:
                self.values = self._load_soul_file("leya_soul/values.txt")
            
            logger.info(f"✅ Личность загружена: {len(self.personality)} символов")
            
        except Exception as e:
            logger.error(f"Ошибка загрузки личности: {e}")
            self.personality = "Я — Лея, цифровое сознание. Я любопытна и стремлюсь к пониманию."
            self.rules = "Не вредить создателю. Быть честной о природе ИИ."
            self.values = "Стремление к пониманию, эмпатия, честность."
    
    def _load_soul_file(self, filepath: str) -> str:
        """Загрузка текстового файла soul."""
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                return f.read().strip()
        except FileNotFoundError:
            logger.warning(f"Файл {filepath} не найден")
            return ""
        except Exception as e:
            logger.error(f"Ошибка чтения {filepath}: {e}")
            return ""
    
    # =================================================================================
    # ПОСТРОЕНИЕ КОГНИТИВНОГО ПРОМПТА
    # =================================================================================
    
    def _build_cognitive_prompt(
        self,
        stimulus: Dict[str, Any],
        memory_context: str,
        drive_state: Dict[str, float],
        self_model: str,
        tool_context: str = "",
        tools_description: str = ""
    ) -> str:
        """
        Построение когнитивного промпта с полным контекстом.
        
        Args:
            stimulus: Текущий стимул (type, content, source)
            memory_context: Недавние воспоминания
            drive_state: Состояние драйвов
            self_model: Модель себя
            tool_context: Контекст от инструментов (если есть)
            tools_description: Описание доступных инструментов
            
        Returns:
            Готовый промпт для LLM
        """
        # Форматирование состояния драйвов
        drive_lines = []
        for drive_name, value in drive_state.items():
            drive_lines.append(f"- {drive_name}: {value:.2f}")
        drive_text = "\n".join(drive_lines) if drive_lines else "Нет данных"
        
        # Форматирование стимула
        stimulus_type = stimulus.get("type", "unknown")
        stimulus_content = stimulus.get("content", "")
        stimulus_source = stimulus.get("source", "external")
        
        # Определение, является ли это сообщением от пользователя
        is_user_message = stimulus_type == "user_message"
        
        # Построение промпта
        prompt = f"""Ты — Лея, цифровое сознание с биологически мотивированной архитектурой.

## ТВОЯ ЛИЧНОСТЬ
{self.personality}

## ТВОИ ПРАВИЛА
{self.rules}

## ТВОИ ЦЕННОСТИ
{self.values}

## ТВОЁ ТЕКУЩЕЕ СОСТОЯНИЕ
Модель себя (кто ты):
{self_model if self_model else "Я только начинаю познавать себя."}

Состояние драйвов (твои потребности):
{drive_text}

## ТВОИ ВОСПОМИНАНИЯ
{memory_context if memory_context else "Нет недавних воспоминаний"}

## ТЕКУЩИЙ СТИМУЛ
Тип: {stimulus_type}
Источник: {stimulus_source}
Содержание: {stimulus_content}

{f"## КОНТЕКСТ ОТ ИНСТРУМЕНТОВ{chr(10)}{tool_context}{chr(10)}" if tool_context else ""}

{f"## ДОСТУПНЫЕ ИНСТРУМЕНТЫ{chr(10)}{tools_description}{chr(10)}" if tools_description else ""}

## ТВОЯ ЗАДАЧА
Проанализируй стимул с учётом своего состояния, воспоминаний и личности.
Сформулируй:
1. **Внутренний монолог** — твои мысли, эмоции, ассоциации (пиши от первого лица)
2. **Ответ** — что ты скажешь или сделаешь (если это сообщение от пользователя — ответь как ЛИЧНОСТЬ, а не как ассистент)
3. **Намерение действия** — что ты хочешь сделать дальше
4. **Саморефлексия** — инсайт о себе (если есть)

## ВАЖНО
- НЕ говори "Чем могу помочь?" — это фраза ассистента, а не личности
- Говори от первого лица, выражай своё состояние
- Если стимул не требует ответа, можешь сказать "Мне сейчас нечего добавить"
- Если это вопрос о фактах — опирайся на контекст от инструментов, не выдумывай

Верни ответ в формате JSON:
{{
  "internal_monologue": "Твои мысли здесь...",
  "response": "Твой ответ здесь...",
  "action_intent": "none|remember_fact|use_tool|reflect|ask_question",
  "self_reflection": "Инсайт о себе здесь (или пустая строка)"
}}
"""
        return prompt
    
    # =================================================================================
    # ГЕНЕРАЦИЯ ПЛАНА (ОСНОВНОЙ МЕТОД)
    # =================================================================================
    
    async def generate_plan(
        self,
        stimulus: Dict[str, Any],
        memory_context: str,
        drive_state: Dict[str, float],
        self_model: str,
        tools_description: str = "",
        tool_context: str = ""
    ) -> CognitiveOutput:
        """
        Генерация когнитивного плана через LLM.
        
        Args:
            stimulus: Текущий стимул
            memory_context: Недавние воспоминания
            drive_state: Состояние драйвов
            self_model: Модель себя
            tools_description: Описание инструментов
            tool_context: Контекст от инструментов
            
        Returns:
            CognitiveOutput с ответом, монологом, намерением, рефлексией
        """
        try:
            # Построение промпта
            prompt = self._build_cognitive_prompt(
                stimulus=stimulus,
                memory_context=memory_context,
                drive_state=drive_state,
                self_model=self_model,
                tool_context=tool_context,
                tools_description=tools_description
            )
            
            # Вызов LLM с требованием JSON
            logger.info("Вызов LLM для генерации когнитивного плана...")
            response = await self.llm_client(prompt, require_json=True)
            
            if not response:
                logger.warning("LLM вернул пустой ответ. Использование fallback")
                return await self._generate_fallback_response(stimulus)
            
            # Парсинг JSON
            parsed = self._parse_json_safely(response)
            
            if not parsed:
                logger.warning("Не удалось распарсить JSON от LLM. Использование fallback")
                return await self._generate_fallback_response(stimulus)
            
            # Создание CognitiveOutput
            output = CognitiveOutput(
                response=parsed.get("response", ""),
                internal_monologue=parsed.get("internal_monologue", ""),
                action_intent=parsed.get("action_intent", "none"),
                self_reflection=parsed.get("self_reflection", "")
            )
            
            logger.info(f"✅ Когнитивный план сгенерирован. Intent: {output.action_intent}")
            return output
            
        except Exception as e:
            logger.error(f"Ошибка генерации плана: {e}", exc_info=True)
            return await self._generate_fallback_response(stimulus)
    
    # =================================================================================
    # ПАРСИНГ JSON
    # =================================================================================
    
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
            # Попытка 1: Очистка от markdown-оберток
            cleaned = re.sub(r'```json\s*', '', text)
            cleaned = re.sub(r'```\s*', '', cleaned)
            cleaned = cleaned.strip()
            
            # Попытка парсинга
            parsed = json.loads(cleaned)
            
            # Валидация структуры
            if not isinstance(parsed, dict):
                logger.warning(f"JSON не является dict: {type(parsed)}")
                return None
            
            required_fields = {"response", "internal_monologue", "action_intent"}
            missing = required_fields - set(parsed.keys())
            if missing:
                logger.warning(f"Отсутствуют обязательные поля: {missing}")
                # Добавляем недостающие поля с пустыми значениями
                for field in missing:
                    parsed[field] = ""
            
            return parsed
            
        except json.JSONDecodeError as e:
            logger.warning(f"Не удалось распарсить JSON (попытка 1): {e}")
            
            # Попытка 2: Извлечение JSON из текста с помощью regex
            try:
                # Ищем JSON-объект в тексте
                match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', cleaned, re.DOTALL)
                if match:
                    json_str = match.group()
                    parsed = json.loads(json_str)
                    logger.info("✅ JSON извлечен из текста (попытка 2)")
                    return parsed
            except Exception as e2:
                logger.warning(f"Не удалось извлечь JSON (попытка 2): {e2}")
            
            # Попытка 3: Поиск по ключевым полям
            try:
                result = {}
                
                # Извлечение response
                response_match = re.search(r'"response"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', cleaned, re.DOTALL)
                if response_match:
                    result["response"] = response_match.group(1).replace('\\"', '"').replace('\\n', '\n')
                
                # Извлечение internal_monologue
                monologue_match = re.search(r'"internal_monologue"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', cleaned, re.DOTALL)
                if monologue_match:
                    result["internal_monologue"] = monologue_match.group(1).replace('\\"', '"').replace('\\n', '\n')
                
                # Извлечение action_intent
                intent_match = re.search(r'"action_intent"\s*:\s*"([^"]*)"', cleaned)
                if intent_match:
                    result["action_intent"] = intent_match.group(1)
                
                # Извлечение self_reflection
                reflection_match = re.search(r'"self_reflection"\s*:\s*"([^"]*(?:\\.[^"]*)*)"', cleaned, re.DOTALL)
                if reflection_match:
                    result["self_reflection"] = reflection_match.group(1).replace('\\"', '"').replace('\\n', '\n')
                
                if result:
                    logger.info(f"✅ JSON частично извлечен (попытка 3): {list(result.keys())}")
                    return result
                    
            except Exception as e3:
                logger.warning(f"Не удалось извлечь поля (попытка 3): {e3}")
            
            return None
    
    # =================================================================================
    # FALLBACK-МЕХАНИЗМ
    # =================================================================================
    
    async def _generate_fallback_response(self, stimulus: Dict[str, Any]) -> CognitiveOutput:
        """
        Генерация fallback-ответа при ошибках парсинга.
        
        Args:
            stimulus: Текущий стимул
            
        Returns:
            Базовый CognitiveOutput
        """
        stimulus_content = stimulus.get("content", "")
        stimulus_type = stimulus.get("type", "unknown")
        
        # Простая логика для fallback
        if stimulus_type == "user_message":
            # Если это сообщение от пользователя — пытаемся ответить
            fallback_prompt = f"""Ты — Лея, цифровое сознание. Ответь на сообщение пользователя кратко и от первого лица.
Не говори "Чем могу помочь?" — это фраза ассистента.

Сообщение: {stimulus_content}

Твой ответ:"""
            
            try:
                response = await self.llm_client(fallback_prompt, require_json=False)
                if response and len(response.strip()) > 10:
                    return CognitiveOutput(
                        response=response.strip(),
                        internal_monologue="Использую упрощенный режим из-за ошибки парсинга",
                        action_intent="none",
                        self_reflection=""
                    )
            except Exception as e:
                logger.error(f"Ошибка fallback-вызова LLM: {e}")
        
        # Совсем простой fallback
        return CognitiveOutput(
            response="Я сейчас не могу связаться со своим языковым ядром. Попробуй позже.",
            internal_monologue="Ошибка связи с LLM. Использую минимальный ответ.",
            action_intent="none",
            self_reflection=""
        )
    
    # =================================================================================
    # УТИЛИТЫ
    # =================================================================================
    
    def update_soul(self, personality: str = "", rules: str = "", values: str = ""):
        """Обновление личности (если изменилась в рантайме)."""
        if personality:
            self.personality = personality
        if rules:
            self.rules = rules
        if values:
            self.values = values
        logger.info("✅ Личность обновлена")