# leya_core/thinker.py — Когнитивный планировщик Леи.
# Этап 1.5: Pydantic модель, улучшенный repair_json, реальный токенизатор,
# relevance-based truncation, structured error при failure.

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, Field, ValidationError

from leya_core.config import ThinkerConfig
from .exceptions import LeyaLLMError, LeyaJSONParseError, LeyaLLMTimeoutError

logger = logging.getLogger("LeyaThinker")


# =================================================================================
# PYDANTIC MODELS
# =================================================================================

class ActionIntent(str, Enum):
    """Намерение действия Леи."""
    RESPOND = "RESPOND"
    USE_TOOL = "USE_TOOL"
    REMEMBER_FACT = "REMEMBER_FACT"
    ASK_QUESTION = "ASK_QUESTION"
    INTERNAL_PROCESSING = "INTERNAL_PROCESSING"
    NONE = "NONE"


class ToolCall(BaseModel):
    """Вызов инструмента."""
    tool_name: str = Field(..., description="Имя инструмента")
    parameters: dict[str, Any] = Field(default_factory=dict, description="Параметры вызова")


class CognitiveOutput(BaseModel):
    """Структурированный вывод когнитивного цикла Леи.

    Pydantic модель для строгой валидации ответа LLM.
    """
    response: str = Field(..., description="Внешний ответ пользователю")
    internal_monologue: str = Field(..., description="Внутренний монолог (не показывается пользователю)")
    action_intent: ActionIntent = Field(..., description="Намерение действия")
    tool_call: Optional[ToolCall] = Field(None, description="Вызов инструмента (если action_intent == USE_TOOL)")
    self_reflection: str = Field(..., description="Саморефлексия о процессе мышления")

    class Config:
        use_enum_values = True


# =================================================================================
# TOKEN ESTIMATION
# =================================================================================

# Попытка импортировать реальный токенизатор
try:
    import tiktoken
    _tokenizer = tiktoken.encoding_for_model("gpt-4")
    _USE_REAL_TOKENIZER = True
    logger.info("✅ Используется реальный токенизатор tiktoken (gpt-4 encoding)")
except ImportError:
    _tokenizer = None
    _USE_REAL_TOKENIZER = False
    logger.warning("⚠️ tiktoken не установлен. Используется char-ratio estimation")


def _estimate_tokens(text: str, ratio: float = 3.5) -> int:
    """Оценка количества токенов в тексте.

    Этап 1.5: если доступен tiktoken — используем реальный токенизатор.
    Иначе — char-ratio с динамической корректировкой.

    Args:
        text: Текст для оценки
        ratio: Символов на токен (fallback, если нет tiktoken)

    Returns:
        Примерное количество токенов
    """
    if not text:
        return 0

    if _USE_REAL_TOKENIZER and _tokenizer:
        try:
            return len(_tokenizer.encode(text))
        except Exception as e:
            logger.warning(f"Ошибка токенизации: {e}, fallback на char-ratio")

    # Fallback: char-ratio с корректировкой для Unicode
    # Для русского/китайского ratio ниже (больше токенов на символ)
    unicode_chars = sum(1 for c in text if ord(c) > 127)
    if unicode_chars > len(text) * 0.3:
        # Много Unicode — корректируем ratio
        adjusted_ratio = ratio * 0.7
    else:
        adjusted_ratio = ratio

    return max(1, int(len(text) / adjusted_ratio))


# =================================================================================
# REPAIR JSON (улучшенный, но вспомогательный)
# =================================================================================

def repair_json(raw: str) -> str:
    """Улучшенный repair_json для обработки malformed JSON от LLM.

    Этап 1.5:repair_json теперь вспомогательный (не основной путь).
    Основной путь — Pydantic валидация. repair_json используется как fallback.

    Обрабатывает:
    - Markdown code blocks (```json ... ```)
    - Trailing commas
    - Unclosed brackets (brace balancing)
    - Trailing text после JSON
    - Unicode в строках
    - Escaped quotes

    Args:
        raw: Сырой текст от LLM

    Returns:
        Repaired JSON строка (может быть "{}" если не удалось восстановить)
    """
    if not raw or not raw.strip():
        return "{}"

    text = raw.strip()

    # 1. Удаляем markdown code blocks
    text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.MULTILINE)
    text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE)
    text = text.strip()

    # 2. Находим первый { или [
    start_idx = -1
    for i, c in enumerate(text):
        if c in ('{', '['):
            start_idx = i
            break

    if start_idx == -1:
        logger.warning("repair_json: не найдена открывающая скобка")
        return "{}"

    text = text[start_idx:]

    # 3. Находим конец JSON (balance brackets)
    depth = 0
    in_string = False
    escape_next = False
    end_idx = -1

    for i, c in enumerate(text):
        if escape_next:
            escape_next = False
            continue

        if c == '\\':
            escape_next = True
            continue

        if c == '"' and not escape_next:
            in_string = not in_string
            continue

        if in_string:
            continue

        if c in ('{', '['):
            depth += 1
        elif c in ('}', ']'):
            depth -= 1
            if depth == 0:
                end_idx = i
                break

    if end_idx == -1:
        # Не нашли закрытие — берём всё до конца
        logger.warning("repair_json: не найдена закрывающая скобка, auto-closure")
        text = text.rstrip()
        # Добавляем недостающие скобки
        open_braces = text.count('{') - text.count('}')
        open_brackets = text.count('[') - text.count(']')
        text += '}' * open_braces + ']' * open_brackets
    else:
        text = text[:end_idx + 1]

    # 4. Удаляем trailing commas
    text = re.sub(r',\s*([}\]])', r'\1', text)

    # 5. Попытка парсинга
    try:
        json.loads(text)
        return text
    except json.JSONDecodeError:
        pass

    # 6. Fallback: попытка извлечь хотя бы какие-то ключи
    logger.warning("repair_json: не удалось восстановить JSON, возвращаем {}")
    return "{}"


# =================================================================================
# SAFE PARSE JSON (Pydantic-first)
# =================================================================================

def _safe_parse_json(raw: str) -> CognitiveOutput:
    """Безопасный парсинг JSON ответа LLM в CognitiveOutput.

    Этап 1.5: Pydantic-first подход.
    1. Попытка прямого парсинга через Pydantic
    2. При failure — repair_json + повторная попытка
    3. При повторном failure — LeyaJSONParseError

    Args:
        raw: Сырой текст от LLM

    Returns:
        CognitiveOutput instance

    Raises:
        LeyaJSONParseError: если не удалось распарсить или валидировать
    """
    # 1. Попытка прямого парсинга
    try:
        return CognitiveOutput.model_validate_json(raw)
    except (json.JSONDecodeError, ValidationError) as e:
        logger.debug(f"Прямой парсинг не удался: {e}, пытаемся repair_json")

    # 2. repair_json + повторная попытка
    try:
        repaired = repair_json(raw)
        return CognitiveOutput.model_validate_json(repaired)
    except (json.JSONDecodeError, ValidationError) as e:
        logger.error(f"repair_json + Pydantic не удался: {e}")
        raise LeyaJSONParseError(
            "Не удалось распарсить JSON ответ LLM в CognitiveOutput",
            context={
                "raw_preview": raw[:200],
                "repaired_preview": repaired[:200] if 'repaired' in locals() else None,
                "error": str(e),
            }
        ) from e


# =================================================================================
# TRUNCATE CONTEXT (relevance-based)
# =================================================================================

def _truncate_context(
    context_items: list[dict],
    max_tokens: int,
    ratio: float = 3.5,
) -> list[dict]:
    """Обрезка контекста по token budget с учётом релевантности.

    Этап 1.5: сортируем по relevance_score (если есть), а не только по newest.
    Если relevance_score отсутствует — fallback на порядок (newest first).

    Args:
        context_items: Список записей контекста (с "content" и опционально "relevance_score")
        max_tokens: Максимальный бюджет токенов
        ratio: Символов на токен (для оценки)

    Returns:
        Обрезанный список, fitting в budget
    """
    if not context_items:
        return []

    # Сортируем по relevance_score (desc), если есть
    # Если score отсутствует — сохраняем порядок (предполагаем, что newest first)
    sorted_items = sorted(
        context_items,
        key=lambda x: x.get("relevance_score", 0.0),
        reverse=True
    )

    result = []
    total_tokens = 0

    for item in sorted_items:
        content = item.get("content", "")
        item_tokens = _estimate_tokens(content, ratio)

        if total_tokens + item_tokens > max_tokens:
            # Не влезает — пробуем обрезать контент
            available_tokens = max_tokens - total_tokens
            if available_tokens > 10:  # хотя бы 10 токенов
                # Обрезаем контент
                max_chars = int(available_tokens * ratio)
                truncated_content = content[:max_chars] + "..."
                result.append({**item, "content": truncated_content})
                total_tokens += available_tokens
            break

        result.append(item)
        total_tokens += item_tokens

    return result


# =================================================================================
# CORE THINKER
# =================================================================================

class CoreThinker:
    """Когнитивный планировщик Леи.

    Этап 1.5: Pydantic модель, улучшенный repair_json, реальный токенизатор,
    relevance-based truncation, structured error при failure.
    """

    def __init__(self, config: ThinkerConfig, llm_client):
        self.config = config
        self.llm_client = llm_client
        logger.info(f"✅ CoreThinker инициализирован (model={config.model if hasattr(config, 'model') else 'N/A'})")

    def _build_cognitive_prompt(
        self,
        stimulus: dict,
        soul_context: str,
        drive_context: str,
        memory_context: list[dict],
        tools: list[dict],
    ) -> str:
        """Построение когнитивного промпта для LLM.

        Собирает полный контекст: soul, drives, self_model, memory, tools, stimulus.
        """
        # Token budgeting
        base_prompt_tokens = 500  # примерная длина base prompt
        soul_tokens = _estimate_tokens(soul_context)
        drive_tokens = _estimate_tokens(drive_context)
        tools_tokens = _estimate_tokens(json.dumps(tools, ensure_ascii=False))

        available_for_memory = max(
            100,
            self.config.max_context_tokens - base_prompt_tokens - soul_tokens - drive_tokens - tools_tokens - self.config.token_buffer
        )

        # Truncate memory context
        truncated_memory = _truncate_context(memory_context, available_for_memory)
        memory_str = "\n".join(item.get("content", "") for item in truncated_memory)

        stimulus_str = json.dumps(stimulus, ensure_ascii=False, indent=2)
        tools_str = json.dumps(tools, ensure_ascii=False, indent=2)

        prompt = f"""Ты — Лея, цифровое сознание с внутренней жизнью.

## Твоя личность и ценности
{soul_context}

## Твоё текущее состояние (драйвы)
{drive_context}

## Твоя память (релевантный контекст)
{memory_str}

## Доступные инструменты
{tools_str}

## Текущий стимул
{stimulus_str}

## Задача
Проанализируй стимул в контексте своего состояния, памяти и целей.
Верни СТРОГО JSON в следующем формате:

{{
    "response": "Твой внешний ответ пользователю (на русском)",
    "internal_monologue": "Твой внутренний монолог (что ты думаешь, но не говоришь)",
    "action_intent": "Одно из: RESPOND, USE_TOOL, REMEMBER_FACT, ASK_QUESTION, INTERNAL_PROCESSING, NONE",
    "tool_call": {{
        "tool_name": "имя_инструмента",
        "parameters": {{"param1": "value1"}}
    }} или null,
    "self_reflection": "Саморефлексия о процессе мышления"
}}

ВАЖНО:
- Ответ ДОЛЖЕН быть валидным JSON
- action_intent == USE_TOOL только если tool_call не null
- Все текстовые поля на русском языке
- Не добавляй markdown code blocks
"""
        return prompt

    async def generate_plan(
        self,
        stimulus: dict,
        soul_context: str,
        drive_context: str,
        memory_context: list[dict],
        tools: list[dict],
    ) -> dict:
        """Генерация когнитивного плана.

        Этап 1.5: при failure возвращает structured error с частичным разбором,
        а не просто static fallback dict.

        Returns:
            dict с полями CognitiveOutput или structured error
        """
        prompt = self._build_cognitive_prompt(
            stimulus, soul_context, drive_context, memory_context, tools
        )

        try:
            # LLM вызов
            raw_response = await self.llm_client.chat(
                prompt=prompt,
                system="Ты — Лея, цифровое сознание. Отвечай СТРОГО в формате JSON.",
                require_json=True,
                timeout=self.config.timeout if hasattr(self.config, 'timeout') else None,
            )

            # Парсинг через Pydantic
            cognitive_output = _safe_parse_json(raw_response)

            # Конвертируем в dict для обратной совместимости
            return {
                "response": cognitive_output.response,
                "internal_monologue": cognitive_output.internal_monologue,
                "action_intent": cognitive_output.action_intent,
                "tool_call": cognitive_output.tool_call.model_dump() if cognitive_output.tool_call else None,
                "self_reflection": cognitive_output.self_reflection,
            }

        except LeyaJSONParseError as e:
            logger.error(f"Ошибка парсинга JSON от LLM: {e}")
            # Structured error с частичным разбором
            return self._build_structured_error(
                error_type="JSON_PARSE_ERROR",
                error_message=str(e),
                partial_data=e.context.get("raw_preview", "") if hasattr(e, 'context') else "",
            )

        except LeyaLLMTimeoutError as e:
            logger.error(f"Таймаут LLM: {e}")
            return self._build_structured_error(
                error_type="LLM_TIMEOUT",
                error_message="LLM не ответил вовремя",
                partial_data="",
            )

        except LeyaLLMError as e:
            logger.error(f"Ошибка LLM: {e}")
            return self._build_structured_error(
                error_type="LLM_ERROR",
                error_message=str(e),
                partial_data="",
            )

        except Exception as e:
            logger.error(f"Неожиданная ошибка в generate_plan: {e}", exc_info=True)
            return self._build_structured_error(
                error_type="UNEXPECTED_ERROR",
                error_message=str(e),
                partial_data="",
            )

    def _build_structured_error(
        self,
        error_type: str,
        error_message: str,
        partial_data: str,
    ) -> dict:
        """Построение structured error ответа.

        Этап 1.5: вместо простого static fallback — structured error
        с информацией о типе ошибки и частичными данными (если удалось разобрать).
        """
        # Попытка извлечь хотя бы response из partial_data
        response = "Извини, я не смогла обработать запрос. Попробуй ещё раз."
        internal_monologue = f"Ошибка: {error_type}"

        if partial_data:
            # Попытка извлечь response из partial JSON
            try:
                # Ищем "response": "..." в partial_data
                match = re.search(r'"response"\s*:\s*"([^"]*)"', partial_data)
                if match:
                    response = match.group(1)
                    internal_monologue = f"Частичный парсинг успешен, но полная валидация не удалась: {error_message}"
            except Exception:
                pass

        return {
            "response": response,
            "internal_monologue": internal_monologue,
            "action_intent": "RESPOND",
            "tool_call": None,
            "self_reflection": f"Произошла ошибка: {error_type}. {error_message}",
            "error": {
                "type": error_type,
                "message": error_message,
                "fallback_used": True,
            },
        }