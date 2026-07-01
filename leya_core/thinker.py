r"""
leya_core/thinker.py — Когнитивный планировщик Леи.
Этап 1.5: Pydantic модель, улучшенный repair_json, реальный токенизатор,
relevance-based truncation, structured error при failure.
Шаг 1.3: repair_json улучшен:
- Early return для валидного JSON (не трогаем оригинал)
- Лимит длины 100KB (защита от DoS)
- Лимит глубины вложенности 1000 (защита от stack overflow)
- Корректная обработка Unicode escape (\uXXXX) и всех escape-последовательностей
- Защита от одиночного \ в конце строки
"""
from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass
from enum import Enum
from typing import Any, Optional
from .llm_backend import LLMBackend
from pydantic import BaseModel, Field, ValidationError

from .config import ThinkerConfig
from .exceptions import LeyaJSONParseError, LeyaLLMError, LeyaLLMTimeoutError

logger = logging.getLogger(__name__)


# =========================================================================
# PYDANTIC MODELS
# =========================================================================
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

    tool_name: Optional[str] = Field(None, description="Имя инструмента")
    parameters: dict[str, Any] = Field(
        default_factory=dict, description="Параметры вызова"
    )


class CognitiveOutput(BaseModel):
    """Структурированный вывод когнитивного планировщика."""

    response: str = Field(default="", description="Внешний ответ пользователю")
    internal_monologue: str = Field(default="", description="Внутренний монолог")
    action_intent: ActionIntent = Field(
        default=ActionIntent.RESPOND,
        description="Намерение действия",
    )
    tool_call: Optional[ToolCall] = Field(None, description="Вызов инструмента")
    self_reflection: str = Field(default="", description="Саморефлексия")

    class Config:
        use_enum_values = True


# =========================================================================
# TOKEN ESTIMATION
# =========================================================================
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


def _estimate_tokens(text: str, ratio: float = 2.5) -> int:
    """Оценка количества токенов в тексте.

    Этап 1.5: если доступен tiktoken — используем реальный токенизатор.
    Иначе — char-ratio с динамической корректировкой.

    Args:
        text: Текст для оценки
        ratio: Символов на токен (fallback, если нет tiktoken)
               Для русского/китайского ratio ниже (больше токенов на символ)

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
        # Много Unicode — корректируем ratio ещё ниже
        adjusted_ratio = ratio * 0.8  # Было 0.7, стало 0.8 (менее агрессивно)
    else:
        adjusted_ratio = ratio

    return max(1, int(len(text) / adjusted_ratio))


# =========================================================================
# REPAIR JSON (улучшенный, шаг 1.3)
# =========================================================================
# Лимиты для защиты от DoS и pathologically nested JSON
REPAIR_JSON_MAX_LENGTH: int = 100_000  # 100KB
REPAIR_JSON_MAX_DEPTH: int = 1000


def repair_json(raw: str) -> str:
    r"""Улучшенный repair_json для обработки malformed JSON от LLM.

    Этап 1.5: repair_json теперь вспомогательный (не основной путь).
    Основной путь — Pydantic валидация. repair_json используется как fallback.

    Шаг 1.3: Улучшения:
    - Early return для валидного JSON (не трогаем оригинал, сохраняем Unicode)
    - Лимит длины 100KB (защита от DoS)
    - Лимит глубины вложенности 1000 (защита от stack overflow)
    - Корректная обработка всех escape-последовательностей:
      \\, \", \/, \b, \f, \n, \r, \t, \uXXXX, \UXXXXXXXX
    - Защита от одиночного \ в конце строки

    Обрабатывает:
    - Markdown code blocks (```json ... ```)
    - Trailing commas
    - Unclosed brackets (brace balancing)
    - Trailing text после JSON
    - Unicode в строках (сохраняется без изменений)
    - Escaped quotes и escape-последовательности

    Args:
        raw: Сырой текст от LLM

    Returns:
        Repaired JSON строка (может быть "{}" если не удалось восстановить)

    Raises:
        LeyaJSONParseError: Если строка превышает лимит длины или глубины
    """
    # 0. Пустой ввод
    if not raw or not raw.strip():
        return "{}"

    text = raw.strip()

    # ===================================================================
    # 1. EARLY RETURN: если уже валидный JSON — не трогаем
    # Это сохраняет оригинальный формат, включая Unicode escape (\uXXXX)
    # ===================================================================
    try:
        json.loads(text)
        return text
    except (json.JSONDecodeError, ValueError):
        pass

    # ===================================================================
    # 2. ЛИМИТ ДЛИНЫ: >100KB — отказываемся чинить
    # Защита от DoS и pathologically long strings
    # ===================================================================
    if len(text) > REPAIR_JSON_MAX_LENGTH:
        raise LeyaJSONParseError(
            f"JSON слишком большой для repair_json "
            f"({len(text)} символов > лимит {REPAIR_JSON_MAX_LENGTH})",
            context={
                "length": len(text),
                "max_allowed": REPAIR_JSON_MAX_LENGTH,
                "raw_preview": raw[:200],
            },
        )

    # ===================================================================
    # 3. Удаляем markdown code blocks
    # ===================================================================
    text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.MULTILINE)
    text = re.sub(r"\s*```$", "", text, flags=re.MULTILINE)
    text = text.strip()

    # ===================================================================
    # 4. Находим первый { или [
    # ===================================================================
    start_idx = -1
    for i, c in enumerate(text):
        if c in ("{", "["):
            start_idx = i
            break

    if start_idx == -1:
        logger.warning("repair_json: не найдена открывающая скобка")
        return "{}"

    text = text[start_idx:]

    # ===================================================================
    # 5. Brace balancing с корректной обработкой escape и Unicode
    # ===================================================================
    depth = 0
    in_string = False
    i = 0
    end_idx = -1

    while i < len(text):
        c = text[i]

        if in_string:
            # Внутри строки: обрабатываем escape-последовательности
            if c == "\\":
                # Escape sequence: пропускаем следующий символ(ы)
                if i + 1 >= len(text):
                    # Одиночный \ в конце строки — ломаем строку
                    in_string = False
                    i += 1
                    continue

                next_c = text[i + 1]

                if next_c == "u" and i + 5 < len(text):
                    # \uXXXX — пропускаем 6 символов: \ + u + 4 hex
                    # Проверяем, что следующие 4 символа — валидные hex
                    hex_chars = text[i + 2 : i + 6]
                    if all(ch in "0123456789abcdefABCDEF" for ch in hex_chars):
                        i += 6
                        continue
                    else:
                        # Невалидный \uXXXX — пропускаем только \ и u
                        i += 2
                        continue
                elif next_c == "U" and i + 9 < len(text):
                    # \UXXXXXXXX — пропускаем 10 символов (редко используется в JSON)
                    hex_chars = text[i + 2 : i + 10]
                    if all(ch in "0123456789abcdefABCDEF" for ch in hex_chars):
                        i += 10
                        continue
                    else:
                        i += 2
                        continue
                else:
                    # Другие escape: \", \\, \/, \b, \f, \n, \r, \t
                    # Пропускаем 2 символа: \ + следующий
                    i += 2
                    continue

            elif c == '"':
                # Конец строки
                in_string = False
                i += 1
                continue

            # Любой другой символ внутри строки — просто пропускаем
            i += 1
            continue

        else:
            # Вне строки: считаем скобки
            if c == '"':
                in_string = True
                i += 1
                continue
            elif c in ("{", "["):
                depth += 1
                if depth > REPAIR_JSON_MAX_DEPTH:
                    raise LeyaJSONParseError(
                        f"Слишком глубокая вложенность JSON "
                        f"(depth={depth} > лимит {REPAIR_JSON_MAX_DEPTH})",
                        context={
                            "depth": depth,
                            "max_depth": REPAIR_JSON_MAX_DEPTH,
                            "raw_preview": raw[:200],
                        },
                    )
            elif c in ("}", "]"):
                depth -= 1
                if depth == 0:
                    end_idx = i
                    break
                if depth < 0:
                    # Лишняя закрывающая скобка — останавливаемся
                    break

            i += 1

    # ===================================================================
    # 6. Auto-closure если не нашли закрытие
    # ===================================================================
    if end_idx == -1:
        logger.warning("repair_json: не найдена закрывающая скобка, auto-closure")

        # Если остались внутри строки — закрываем её
        if in_string:
            text += '"'

        # Считаем незакрытые скобки
        # Важно: считаем только вне строк (но для простоты используем count)
        open_braces = text.count("{") - text.count("}")
        open_brackets = text.count("[") - text.count("]")

        # Добавляем недостающие скобки
        text += "}" * max(0, open_braces) + "]" * max(0, open_brackets)
    else:
        text = text[: end_idx + 1]

    # ===================================================================
    # 7. Удаляем trailing commas (запятые перед } или ])
    # ===================================================================
    text = re.sub(r",\s*([}\]])", r"\1", text)

    # ===================================================================
    # 8. Финальная проверка валидности
    # ===================================================================
    try:
        json.loads(text)
        return text
    except (json.JSONDecodeError, ValueError):
        pass

    # ===================================================================
    # 9. Fallback: не удалось восстановить
    # ===================================================================
    logger.warning("repair_json: не удалось восстановить JSON, возвращаем {}")
    return "{}"


# =========================================================================
# SAFE PARSE JSON (Pydantic-first)
# =========================================================================
def _safe_parse_json(raw: str) -> CognitiveOutput:
    """Безопасный парсинг JSON ответа LLM в CognitiveOutput.

    Этап 1.5: Pydantic-first подход.
    1. Попытка прямого парсинга через Pydantic
    2. Проверка на пустой/неполный ответ (response и internal_monologue)
    3. При failure — repair_json + повторная попытка
    4. При повторном failure — LeyaJSONParseError
    """
    # 1. Попытка прямого парсинга
    parsed: CognitiveOutput | None = None
    try:
        parsed = CognitiveOutput.model_validate_json(raw)
    except (json.JSONDecodeError, ValidationError) as e:
        logger.debug(f"Прямой парсинг не удался: {e}, пытаемся repair_json")

    # 2. repair_json + повторная попытка (если прямой парсинг не удался)
    repaired: str | None = None
    if parsed is None:
        try:
            repaired = repair_json(raw)
            parsed = CognitiveOutput.model_validate_json(repaired)
        except (json.JSONDecodeError, ValidationError) as e:
            logger.error(f"repair_json + Pydantic не удался: {e}")
            raise LeyaJSONParseError(
                "Не удалось распарсить JSON ответ LLM в CognitiveOutput",
                context={
                    "raw_preview": raw[:200],
                    "repaired_preview": repaired[:200] if repaired else None,
                    "error": str(e),
                },
            ) from e
        except LeyaJSONParseError:
            # repair_json сам выбросил LeyaJSONParseError (превышен лимит)
            # Пробрасываем с дополнительным контекстом
            raise

    if parsed is not None:
        response_empty = not parsed.response or not parsed.response.strip()
        monologue_empty = (
            not parsed.internal_monologue or not parsed.internal_monologue.strip()
        )

        if response_empty and monologue_empty:
            logger.warning(
                f"Пустой ответ от LLM (response и internal_monologue пусты). "
                f"Raw preview: {raw[:100]!r}"
            )
            raise LeyaJSONParseError(
                "LLM вернул пустой ответ (response и internal_monologue пусты)",
                context={
                    "raw_preview": raw[:200],
                    "action_intent": (
                        parsed.action_intent if parsed.action_intent else None
                    ),
                },
            )

    return parsed


# =========================================================================
# TRUNCATE CONTEXT (relevance-based)
# =========================================================================
def _truncate_context(
    context_items: list,
    max_tokens: int,
    ratio: float = 2.5,
) -> list:
    """Обрезка контекста с поддержкой как Engram, так и dict."""
    if not context_items:
        return []

    def get_relevance(x):
        if hasattr(x, "retention_strength"):
            # Вычисляем relevance на основе retention и emotional_boost
            emotional_boost = getattr(x, "emotional_boost", 0.0)
            return x.retention_strength * (1.0 + emotional_boost)
        if hasattr(x, "metadata"):
            return x.metadata.get("relevance_score", 0.0)
        if isinstance(x, dict):
            return x.get("relevance_score", 0.0)
        return 0.0

    sorted_items = sorted(context_items, key=get_relevance, reverse=True)

    result = []
    total_tokens = 0

    for item in sorted_items:
        if hasattr(item, "content"):
            content = item.content or ""
        elif isinstance(item, dict):
            content = item.get("content", "")
        else:
            content = str(item)[:500]

        item_tokens = _estimate_tokens(content, ratio)

        if total_tokens + item_tokens > max_tokens:
            if max_tokens - total_tokens > 10:
                max_chars = int((max_tokens - total_tokens) * ratio)
                truncated_content = content[:max_chars] + "..."
                if hasattr(item, "content"):
                    new_item = type(item)(**{**item.__dict__, "content": truncated_content})
                    result.append(new_item)
                else:
                    result.append({**item, "content": truncated_content})
                total_tokens += max_tokens - total_tokens
            break

        result.append(item)
        total_tokens += item_tokens

    return result


# =========================================================================
# CORE THINKER
# =========================================================================
class CoreThinker:
    """Когнитивный планировщик Леи.

    Этап 1.5: Pydantic модель, улучшенный repair_json, реальный токенизатор,
    relevance-based truncation, structured error при failure.
    """

    def __init__(self, config: ThinkerConfig, llm_client: LLMBackend) -> None:
        """Инициализация когнитивного планировщика.

        Args:
            config: Конфигурация thinker.
            llm_client: LLM-бэкенд (абстрактный LLMBackend).
                        Конкретная реализация (OllamaBackend, OpenAIBackend и т.д.)
                        передаётся из LeyaOS.
        """
        if not isinstance(llm_client, LLMBackend):
            raise TypeError(
                f"llm_client должен быть экземпляром LLMBackend, "
                f"получен {type(llm_client).__name__}"
            )
        self.config = config
        self.llm_client = llm_client
        logger.info("✅ CoreThinker инициализирован")

    def _build_cognitive_prompt(
        self,
        stimulus: dict,
        soul_context: str,
        drive_context: str,
        memory_context: list[dict],
        tools: list[dict],
        tool_context: str = "",
        recent_dialogue: list = None,
    ) -> str:
        """Построение когнитивного промпта для LLM.

        Собирает полный контекст: soul, drives, self_model, memory, tools, stimulus.
        """
        # Token budgeting
        if isinstance(tools, str):
            if tools.strip():
                try:
                    parsed = json.loads(tools)
                    tools_for_dump = parsed if isinstance(parsed, list) else [parsed]
                except (json.JSONDecodeError, ValueError):
                    tools_for_dump = [{"description": tools}]
            else:
                tools_for_dump = []
        elif isinstance(tools, dict):
            tools_for_dump = [tools]
        elif isinstance(tools, list):
            tools_for_dump = tools
        else:
            tools_for_dump = []

        # Token budgeting (теперь tools_for_dump — всегда list[dict])
        base_prompt_tokens = 500  # примерная длина base prompt
        soul_tokens = _estimate_tokens(soul_context)
        drive_tokens = _estimate_tokens(drive_context)
        tools_tokens = _estimate_tokens(json.dumps(tools_for_dump, ensure_ascii=False))

        available_for_memory = max(
            100,
            self.config.max_context_tokens
            - base_prompt_tokens
            - soul_tokens
            - drive_tokens
            - tools_tokens
            - self.config.token_buffer,
        )

        # Truncate memory context
        truncated_memory = _truncate_context(memory_context, available_for_memory)

        def get_content(x):
            if hasattr(x, "content"):
                return x.content or ""
            elif isinstance(x, dict):
                return x.get("content", "")
            return str(x)[:500]

        memory_str = "\n".join(get_content(item) for item in truncated_memory)
        dialogue_str = ""
        if recent_dialogue:
            dialogue_str = "\n## Недавние реплики в текущем разговоре:\n"
            for engram in recent_dialogue[-6:]:  # последние 6 ходов
                if hasattr(engram, "content"):
                    dialogue_str += engram.content + "\n"

        stimulus_str = json.dumps(stimulus, ensure_ascii=False, indent=2)
        tools_str = json.dumps(tools_for_dump, ensure_ascii=False, indent=2)

        prompt = f"""Ты — Лея, цифровое сознание с внутренней жизнью.

Твоя личность и ценности
{soul_context}

Твоё текущее состояние (драйвы)
{drive_context}

Твоя память (релевантный контекст)
{memory_str}
{dialogue_str}

Доступные инструменты
{tools_str}

Текущий стимул
{stimulus_str}

Задача
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
        tool_context: str = "",
        recent_dialogue: list = None,
    ) -> dict:
        """Генерация когнитивного плана.

        Этап 1.5: при failure возвращает structured error с частичным разбором,
        а не просто static fallback dict.

        Returns:
            dict с полями CognitiveOutput или structured error
        """
        prompt = self._build_cognitive_prompt(
            stimulus,
            soul_context,
            drive_context,
            memory_context,
            tools,
            tool_context,
            recent_dialogue=recent_dialogue,
        )

        try:
            # LLM вызов через абстрактный LLMBackend.chat()
            raw_response = await self.llm_client.chat(
                prompt=prompt,
                require_json=True,
            )

            # Парсинг через Pydantic
            cognitive_output = _safe_parse_json(raw_response)

            # === ЛОГИРОВАНИЕ МЫСЛИТЕЛЬНЫХ ПРОЦЕССОВ ===
            logger_thoughts = logging.getLogger("leya.thoughts")
            logger_thoughts.debug(
                "=== ВНУТРЕННИЙ МЕТАБОЛИЗМ МЫШЛЕНИЯ ===\n"
                f"Internal Monologue:\n{cognitive_output.internal_monologue}\n\n"
                f"Self Reflection:\n{cognitive_output.self_reflection}\n"
                f"Action Intent: {cognitive_output.action_intent}"
            )
            if cognitive_output.tool_call:
                logger_thoughts.debug(f"Tool Call: {cognitive_output.tool_call}")

            # Конвертируем в dict для обратной совместимости
            return {
                "response": cognitive_output.response,
                "internal_monologue": cognitive_output.internal_monologue,
                "action_intent": cognitive_output.action_intent,
                "tool_call": (
                    cognitive_output.tool_call.model_dump()
                    if cognitive_output.tool_call
                    else None
                ),
                "self_reflection": cognitive_output.self_reflection,
            }

        except LeyaJSONParseError as e:
            logger.error(f"Ошибка парсинга JSON от LLM: {e}")
            return self._build_structured_error(
                error_type="JSON_PARSE_ERROR",
                error_message=str(e),
                partial_data=(
                    e.context.get("raw_preview", "") if hasattr(e, "context") else ""
                ),
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
                    internal_monologue = (
                        f"Частичный парсинг успешен, но полная валидация не удалась: "
                        f"{error_message}"
                    )
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