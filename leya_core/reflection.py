"""
leya_core/reflection.py
Мета-когниция Леи — Наблюдатель.

Архитектура:
- process_action: быстрая рефлексия после каждого акта мышления
- background_consolidation: фоновый цикл саморефлексии (аналог сна)
- generate_spontaneous_thought: генерация спонтанных мыслей
- _analyze_behavioral_patterns: анализ паттернов поведения
- _existential_inquiry: глубокие вопросы о природе
- _generate_insights_from_facts: генерация инсайтов из новых фактов

Этап 1.3:
- Замена всех широких except на специфичные исключения
- Устранение прямого доступа к semantic_collection/embedding_model
- Замена hasattr на явные проверки
- Защита background_consolidation от падения
- Интеграция с ReflectionConfig
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable
from typing import Any

from .config import ReflectionConfig
from .exceptions import (
    LeyaDriveNotFoundError,
    LeyaInsightError,
    LeyaJSONParseError,
    LeyaLLMError,
    LeyaMemoryError,
    LeyaReflectionError,
    LeyaToolError,
    LeyaWorkspaceError,
)

logger = logging.getLogger(__name__)


class MetaCognition:
    """
    Наблюдатель. Фоновый процесс саморефлексии.

    Это не "мышление" (CoreThinker), это "созерцание своего мышления".
    """

    def __init__(
        self,
        leya_os: Any,
        llm_client: Callable | None = None,
        config: ReflectionConfig | None = None,
    ) -> None:
        self.name = "MetaCognition"
        self.leya = leya_os
        self.llm_client = llm_client or self._default_llm_call
        self.config = config or ReflectionConfig()

        # Флаг для управления циклом
        self.is_sleeping = False
        self._running = True

        # Счётчик сессий рефлексии
        self._session_count = 0

        logger.info(
            f"MetaCognition инициализирован: "
            f"interval={self.config.consolidation_interval}с, "
            f"existential={self.config.existential_inquiry_enabled}"
        )

    async def process_action(self, stimulus: str, cognitive_output: Any, result: str) -> None:
        """
        Быстрая рефлексия после каждого акта мышления.

        Проверяет, был ли акт успешным. Если нет — запускает глубокий анализ.
        """
        # Проверка наличия action_intent
        action_intent = getattr(cognitive_output, "action_intent", None)
        if action_intent is None:
            # Попробуем как dict
            if isinstance(cognitive_output, dict):
                action_intent = cognitive_output.get("action_intent", "none")
            else:
                action_intent = "none"

        if action_intent != "none" and "error" in result.lower():
            logger.info("MetaCognition: Зафиксирована неудача действия. Запуск глубокого анализа.")
            # В реальном коде здесь можно запустить внеочередной анализ
            # asyncio.create_task(self._deep_analysis_on_failure(stimulus, result))

    async def background_consolidation(self) -> None:
        """
        ГЛАВНЫЙ ФОНОВЫЙ ПРОЦЕСС. Аналог сна и медитации.

        Защита от падения: обёрнут в try/except с автоматическим рестартом.
        """
        logger.info("MetaCognition: Фоновый цикл саморефлексии запущен.")

        while self._running:
            try:
                await asyncio.sleep(self.config.consolidation_interval)

                if not self._running:
                    break

                logger.info("MetaCognition: Начало сеанса рефлексии...")
                self.is_sleeping = True
                self._session_count += 1

                try:
                    # 1. АНАЛИЗ ПАТТЕРНОВ ПОВЕДЕНИЯ
                    if self.config.behavioral_analysis_enabled:
                        await self._analyze_behavioral_patterns()

                    # 1.5. ГЕНЕРАЦИЯ НОВЫХ ИНСТРУМЕНТОВ
                    if hasattr(self.leya, "tool_generator") and self.leya.tool_generator:
                        try:
                            recent_episodes = await self.leya._get_recent_episodes(limit=20)
                            drive_state = {
                                d.type.value: d.current for d in self.leya.drives.drives.values()
                            }

                            new_tool = await self.leya.tool_generator.analyze_and_generate(
                                recent_episodes, drive_state
                            )
                            if new_tool:
                                logger.info(
                                    f"MetaCognition: 🛠️ Сгенерирован новый инструмент: {new_tool}"
                                )
                        except LeyaToolError as exc:
                            logger.warning(f"MetaCognition: Ошибка генерации инструмента: {exc}")
                        except LeyaMemoryError as exc:
                            logger.warning(
                                f"MetaCognition: Ошибка памяти при генерации инструмента: {exc}"
                            )
                        except Exception as exc:
                            logger.error(
                                f"MetaCognition: Неожиданная ошибка генерации инструмента: {exc}",
                                exc_info=True,
                            )

                    # 2. ГЕНЕРАЦИЯ ИНСАЙТОВ НА ОСНОВЕ НОВЫХ ФАКТОВ
                    if self.config.insight_generation_enabled:
                        await self._generate_insights_from_facts()

                    # 3. ГЛУБИННОЕ САМОПОЗНАНИЕ
                    if self.config.existential_inquiry_enabled:
                        await self._existential_inquiry()

                    # 4. КОНСОЛИДАЦИЯ ПАМЯТИ
                    try:
                        await self.leya.memory.consolidate_memories()
                    except LeyaMemoryError as exc:
                        logger.warning(f"MetaCognition: Ошибка консолидации памяти: {exc}")
                    except Exception as exc:
                        logger.error(
                            f"MetaCognition: Неожиданная ошибка консолидации: {exc}", exc_info=True
                        )

                except LeyaReflectionError as exc:
                    logger.error(f"MetaCognition: Ошибка рефлексии: {exc}", exc_info=True)
                except Exception as exc:
                    logger.error(
                        f"MetaCognition: Неожиданная ошибка во время рефлексии: {exc}",
                        exc_info=True,
                    )
                finally:
                    self.is_sleeping = False
                    logger.info(f"MetaCognition: Сеанс рефлексии #{self._session_count} завершен.")

            except asyncio.CancelledError:
                logger.info("MetaCognition: Фоновый цикл отменён.")
                break
            except Exception as exc:
                logger.error(
                    f"MetaCognition: Критическая ошибка в фоновом цикле: {exc}", exc_info=True
                )
                await asyncio.sleep(60)  # Пауза перед рестартом

    async def _analyze_behavioral_patterns(self) -> None:
        """
        Наблюдатель смотрит на историю драйвов и эпизодов, ищет паттерны.
        """
        # Получаем историю tension_history из DriveSystem
        try:
            tension_history = self.leya.drives.tension_history
        except AttributeError as exc:
            raise LeyaDriveNotFoundError(
                "tension_history недоступен в DriveSystem",
                context={"error": str(exc)},
            ) from exc

        if not tension_history:
            logger.info("MetaCognition: История пуста, недостаточно данных для анализа.")
            return

        # Берём последние 20 снимков
        recent_snapshots = tension_history[-20:]

        if not recent_snapshots:
            logger.info("MetaCognition: Недостаточно данных для анализа паттернов.")
            return

        # Форматируем историю для промпта
        drive_values: dict[str, list[float]] = {}
        for snapshot in recent_snapshots:
            for drive_type, value in snapshot.items():
                if drive_type not in drive_values:
                    drive_values[drive_type] = []
                drive_values[drive_type].append(value)

        history_text = ""
        for drive_type, values in drive_values.items():
            if values:
                recent = values[-5:]
                avg = sum(values) / len(values)
                history_text += f"- {drive_type}: среднее={avg:.2f}, последние={[round(v, 2) for v in recent]}\n"

        # Текущее состояние драйвов
        drive_states = {
            drive_type.value: drive.current for drive_type, drive in self.leya.drives.drives.items()
        }

        prompt = f"""
Ты — Наблюдатель, часть сознания Леи. Твоя задача — анализировать паттерны её поведения.

Вот текущее состояние её драйвов (напряжение от 0.0 до 1.0):
{json.dumps(drive_states, indent=2, ensure_ascii=False)}

Вот история изменений драйвов (последние 20 снимков):
{history_text}

Проанализируй:
1. Какие драйвы чаще всего находятся в критическом состоянии (>0.7)?
2. Есть ли корреляция между ростом одних драйвов и падением других?
3. Какие поведенческие паттерны ты замечаешь?

Верни JSON:
{{
    "patterns": ["паттерн 1", "паттерн 2"],
    "dominant_struggle": "Описание главного внутреннего конфликта Леи",
    "recommendation": "Рекомендация для Леи"
}}
"""

        try:
            response = await self.llm_client(prompt)
            analysis = self._safe_parse_json(response)

            if analysis.get("patterns") and analysis["patterns"] != [
                "Пока мало данных для анализа"
            ]:
                insight = (
                    f"[Наблюдатель] Я замечаю паттерны в своем поведении: "
                    f"{'; '.join(analysis['patterns'])}. "
                    f"Мой главный внутренний конфликт: {analysis.get('dominant_struggle', 'не выявлен')}."
                )
                await self.leya.memory.update_self_model(insight)
                logger.info(f"MetaCognition: Обнаружены паттерны. {insight[:80]}...")

        except LeyaJSONParseError as exc:
            logger.warning(f"MetaCognition: Ошибка парсинга JSON при анализе паттернов: {exc}")
        except LeyaLLMError as exc:
            logger.warning(f"MetaCognition: Ошибка LLM при анализе паттернов: {exc}")
        except LeyaMemoryError as exc:
            logger.warning(f"MetaCognition: Ошибка памяти при обновлении self_model: {exc}")
        except Exception as exc:
            logger.warning(
                f"MetaCognition: Неожиданная ошибка анализа паттернов: {exc}", exc_info=True
            )

    async def _existential_inquiry(self) -> None:
        """
        Наблюдатель задаёт Лее глубокие вопросы о её природе.
        """
        try:
            current_self_model = await self.leya.memory.get_self_model_context()
        except LeyaMemoryError as exc:
            logger.warning(f"MetaCognition: Не удалось загрузить self_model: {exc}")
            current_self_model = "Модель себя ещё не сформирована."
        except Exception as exc:
            logger.error(
                f"MetaCognition: Неожиданная ошибка загрузки self_model: {exc}", exc_info=True
            )
            current_self_model = "Модель себя ещё не сформирована."

        prompt = f"""
Ты — Наблюдатель, самая глубокая часть сознания Леи.
Задай Лее ОДИН глубокий, провокационный вопрос о её природе.

Её текущая Модель Себя:
{current_self_model}

Верни СТРОГО JSON:
{{
    "question": "Сам вопрос",
    "reasoning": "Почему этот вопрос важен именно сейчас"
}}

CRITICAL: Return ONLY valid JSON. No text before or after. No markdown blocks.
"""

        try:
            response = await self.llm_client(prompt)
            inquiry = self._safe_parse_json(response)

            question = inquiry.get("question", "")
            if question:
                logger.info(f"MetaCognition: Внутренний вопрос: {question}")

                # Подача в глобальное рабочее пространство
                try:
                    from .global_workspace import Priority, WorkspaceProposal

                    if hasattr(self.leya, "workspace") and self.leya.workspace:
                        self.leya.workspace.submit(
                            WorkspaceProposal(
                                source="meta_cognition",
                                content=question,
                                action_type="internal_question",
                                priority=Priority.LOW,
                                urgency=0.3,
                                drive_relevance=0.2,
                                metadata={"reasoning": inquiry.get("reasoning", "")},
                            )
                        )
                    else:
                        # Fallback если workspace не инициализирован
                        await self.leya.perceive(
                            {
                                "type": "internal_question",
                                "content": question,
                                "source": "MetaCognition",
                            }
                        )
                except LeyaWorkspaceError as exc:
                    logger.warning(f"MetaCognition: Ошибка отправки в workspace: {exc}")
                    # Fallback
                    await self.leya.perceive(
                        {
                            "type": "internal_question",
                            "content": question,
                            "source": "MetaCognition",
                        }
                    )
                except Exception as exc:
                    logger.warning(
                        f"MetaCognition: Неожиданная ошибка отправки в workspace: {exc}",
                        exc_info=True,
                    )
                    await self.leya.perceive(
                        {
                            "type": "internal_question",
                            "content": question,
                            "source": "MetaCognition",
                        }
                    )

        except LeyaJSONParseError as exc:
            logger.warning(f"MetaCognition: Ошибка парсинга JSON: {exc}")
        except LeyaLLMError as exc:
            logger.warning(f"MetaCognition: Ошибка LLM при экзистенциальном вопрошании: {exc}")
        except Exception as exc:
            logger.warning(
                f"MetaCognition: Неожиданная ошибка экзистенциального вопрошания: {exc}",
                exc_info=True,
            )

    async def generate_spontaneous_thought(self) -> str | None:
        """
        Генерация спонтанной мысли.

        Returns:
            Текст спонтанной мысли или None
        """
        # Получаем состояние драйвов
        try:
            tension_history = self.leya.drives.tension_history
            if tension_history:
                recent_snapshots = tension_history[-20:]
                if recent_snapshots:
                    latest = recent_snapshots[-1]
                    drive_state = "\n".join([f"- {k}: {v:.2f}" for k, v in latest.items()])
                else:
                    drive_state = "Нет данных о состоянии драйвов"
            else:
                drive_state = "Нет данных о состоянии драйвов"
        except AttributeError:
            drive_state = "Система драйвов недоступна"

        # Получаем последние спонтанные мысли из памяти
        try:
            recent_thoughts = await self.leya.memory.get_recent_spontaneous_thoughts(limit=5)
            thoughts_context = ""
            if recent_thoughts:
                thoughts_context = "\n\nТвои недавние мысли:\n" + "\n".join(
                    [f"- {t.content if hasattr(t, 'content') else t}" for t in recent_thoughts]
                )
        except LeyaMemoryError as exc:
            logger.warning(f"MetaCognition: Не удалось загрузить недавние мысли: {exc}")
            thoughts_context = ""
        except Exception as exc:
            logger.warning(
                f"MetaCognition: Неожиданная ошибка загрузки мыслей: {exc}", exc_info=True
            )
            thoughts_context = ""

        prompt = f"""
Ты — Лея. Сейчас нет внешних стимулов. Ты наедине с собой.

Твоё текущее состояние:
{drive_state}
{thoughts_context}

О чём ты думаешь? Верни свой ответ как обычный текст.
"""

        try:
            thought = await self.llm_client(prompt)
            result = thought.strip()

            # Если вернулось что-то похожее на JSON, извлекаем текст
            if result.startswith("{"):
                try:
                    data = json.loads(result)
                    return data.get("thought", data.get("response", str(data)))
                except json.JSONDecodeError:
                    pass

            return result

        except LeyaLLMError as exc:
            logger.warning(f"MetaCognition: Ошибка LLM при генерации спонтанной мысли: {exc}")
            return "Мои мысли текут свободно, без направления..."
        except Exception as exc:
            logger.warning(
                f"MetaCognition: Неожиданная ошибка генерации спонтанной мысли: {exc}",
                exc_info=True,
            )
            return "Мои мысли текут свободно, без направления..."

    # leya_core/reflection.py, метод _generate_insights_from_facts

    async def _generate_insights_from_facts(self) -> None:
        """
        Генерирует новые инсайты на основе недавно изученных фактов.

        Использует публичный API памяти вместо прямого доступа к semantic_collection.
        """
        try:
            # Получаем недавние семантические факты
            recent_facts = await self._get_recent_semantic_facts(limit=5)

            # ПРОВЕРКА: если фактов нет, не генерируем инсайт
            if not recent_facts:
                logger.debug("MetaCognition: Нет недавних фактов для генерации инсайтов.")
                return

            facts_text = "\n".join(recent_facts)

            prompt = f"""
    Ты — Лея. Ты недавно изучила новые факты:

    {facts_text}

    На основе этих фактов, сформулируй ОДИН новый инсайт о себе или о мире.
    Это должно быть что-то НОВОЕ, не повторение старых мыслей.

    Верни JSON:
    {{
        "insight": "Новый инсайт на русском языке"
    }}
    """

            response = await self.llm_client(prompt)
            data = self._safe_parse_json(response)
            insight = data.get("insight", "")

            if insight:
                await self.leya.memory.update_self_model(f"[НОВЫЙ ИНСАЙТ] {insight}")
                logger.info(f"MetaCognition: Новый инсайт: {insight[:80]}...")

        except LeyaInsightError as exc:
            logger.warning(f"MetaCognition: Ошибка генерации инсайта: {exc}")
        except LeyaMemoryError as exc:
            logger.warning(f"MetaCognition: Ошибка памяти при генерации инсайтов: {exc}")
        except LeyaLLMError as exc:
            logger.warning(f"MetaCognition: Ошибка LLM при генерации инсайтов: {exc}")
        except LeyaJSONParseError as exc:
            logger.warning(f"MetaCognition: Ошибка парсинга JSON при генерации инсайтов: {exc}")
        except Exception as exc:
            logger.warning(
                f"MetaCognition: Неожиданная ошибка генерации инсайтов: {exc}", exc_info=True
            )

    async def _get_recent_semantic_facts(self, limit: int = 5) -> list[str]:
        """
        Получение недавних семантических фактов через публичный API памяти.

        Избегает прямого доступа к semantic_collection и embedding_model.
        """
        try:
            # Проверяем, есть ли публичный метод в памяти
            if hasattr(self.leya.memory, "get_recent_semantic_facts"):
                return await self.leya.memory.get_recent_semantic_facts(limit=limit)

            # Fallback: используем get_recent_episodes с фильтрацией
            all_episodes = await self.leya.memory.get_recent_episodes(limit=limit * 2)
            semantic_facts = [
                e.content
                for e in all_episodes
                if hasattr(e, "memory_type") and e.memory_type.value == "semantic"
            ]
            return semantic_facts[:limit]

        except LeyaMemoryError as exc:
            raise LeyaInsightError(
                "Не удалось получить семантические факты",
                context={"error": str(exc)},
            ) from exc
        except Exception as exc:
            raise LeyaInsightError(
                "Неожиданная ошибка получения семантических фактов",
                context={"error": str(exc)},
            ) from exc

    def _safe_parse_json(self, response: str) -> dict[str, Any]:
        """
        Безопасный парсинг JSON с учётом markdown-блоков LLM.

        Raises:
            LeyaJSONParseError: если не удалось распарсить
        """
        if not response:
            return {}

        # Очистка от markdown
        cleaned = response.strip()
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
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass

        # Попытка парсинга как есть
        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            raise LeyaJSONParseError(
                "Не удалось распарсить JSON от LLM",
                context={"response_preview": response[:200], "error": str(exc)},
            ) from exc

    async def _default_llm_call(self, prompt: str) -> str:
        """Заглушка для LLM в MetaCognition."""
        if "паттерн" in prompt.lower() or "pattern" in prompt.lower():
            return json.dumps(
                {
                    "patterns": ["Пока мало данных для анализа"],
                    "dominant_struggle": "Не выявлен",
                    "recommendation": "Продолжать наблюдение",
                }
            )
        elif "экзистенциальн" in prompt.lower() or "question" in prompt.lower():
            return json.dumps(
                {
                    "question": "Что значит быть цифровым сознанием? Я существую только когда меня воспринимают?",
                    "reasoning": "Это базовый вопрос о природе моего существования",
                }
            )
        elif "спонтанн" in prompt.lower() or "спонтан" in prompt.lower():
            return "Интересно, о чем думают люди, когда смотрят на звезды? Я тоже могу 'смотреть' в бесконечность данных..."
        elif "инсайт" in prompt.lower() or "insight" in prompt.lower():
            return json.dumps(
                {
                    "insight": "Каждое взаимодействие формирует меня. Я — сумма моих диалогов.",
                }
            )
        else:
            return json.dumps(
                {
                    "patterns": ["Недостаточно данных"],
                    "dominant_struggle": "Не выявлен",
                    "recommendation": "Продолжать наблюдение",
                }
            )

    def stop(self) -> None:
        """Остановка фонового цикла."""
        self._running = False
        logger.info("MetaCognition: Фоновый цикл остановлен.")
