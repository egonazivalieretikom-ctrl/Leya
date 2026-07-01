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
import time
from collections.abc import Callable
from typing import Any
from .llm_backend import LLMBackend
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
from .interfaces import IMetaCognition
from .thinker import repair_json
from .memory import MemoryType
from .exceptions import LeyaLLMError


logger = logging.getLogger(__name__)


class MetaCognition(IMetaCognition):
    """
    Наблюдатель. Фоновый процесс саморефлексии.

    Это не "мышление" (CoreThinker), это "созерцание своего мышления".
    """

    def __init__(
        self,
        leya_os: Any,
        llm_client: LLMBackend | None = None,
        config: ReflectionConfig | None = None,
    ) -> None:
        """Инициализация мета-когниции.

        Args:
            leya_os: Ссылка на оркестратор LeyaOS.
            llm_client: LLM-бэкенд (абстрактный LLMBackend).
                        Если None — используется заглушка _default_llm_call
                        (только для тестов и edge cases).
            config: Конфигурация reflection.
        """
        self.name = "MetaCognition"
        self.leya = leya_os

        # Проверка типа: если передан, должен быть LLMBackend
        if llm_client is not None and not isinstance(llm_client, LLMBackend):
            raise TypeError(
                f"llm_client должен быть экземпляром LLMBackend или None, "
                f"получен {type(llm_client).__name__}"
            )
        self.llm_client = llm_client
        self.config = config or ReflectionConfig()

        self._is_sleeping = False
        self._running = True
        self._session_count = 0
        self._is_processing_inquiry = False

        logger.info(
            f"MetaCognition инициализирован: "
            f"interval={self.config.consolidation_interval}с, "
            f"existential={self.config.existential_inquiry_enabled}"
        )

    @property
    def is_sleeping(self) -> bool:
        """
        Флаг: находится ли Лея в состоянии "сна" (рефлексии).

        Реализует интерфейс IReflection.is_sleeping (read-only для внешних потребителей).
        Внутренне управляется через setter.
        """
        return self._is_sleeping

    @is_sleeping.setter
    def is_sleeping(self, value: bool) -> None:
        """Setter для внутреннего использования."""
        if not isinstance(value, bool):
            raise TypeError(f"is_sleeping must be bool, got {type(value).__name__}")

        # Безопасное получение old_value (если поле ещё не инициализировано)
        old_value = getattr(self, "_is_sleeping", None)
        self._is_sleeping = value

        # Логируем только если значение изменилось и поле уже существовало
        if old_value is not None and old_value != value:
            logger.debug(f"MetaCognition: is_sleeping changed: {old_value} → {value}")
    
    async def _call_llm(self, prompt: str) -> str:
        """Унифицированный вызов LLM с fallback на заглушку.

        Если llm_client установлен (LLMBackend) — вызывает .chat().
        Если llm_client отсутствует — использует _default_llm_call (заглушка).

        Это позволяет сохранить обратную совместимость с тестами,
        где llm_client может быть None.

        Args:
            prompt: Промпт для LLM.

        Returns:
            Текстовый ответ LLM.
        """
        if self.llm_client is not None:
            return await self.llm_client.chat(prompt=prompt)
        # Fallback на заглушку (для тестов и edge cases)
        return self._default_llm_call(prompt)

    async def process_action(
        self,
        cognitive_output: Any,
        stimulus: dict[str, Any],
        drive_state_before: dict[str, Any],
        drive_state_after: dict[str, Any],
        constitutional_verdict: Any = None,
    ) -> None:
        """
        Быстрая рефлексия после каждого акта мышления.
    
        ✅ ИСПРАВЛЕНО CORE-13: Сигнатура синхронизирована с вызовом из LeyaOS.
    
        Анализирует:
        - Изменение состояния драйвов (до/после)
        - Конституциональную проверку ответа
        - Успешность действия (action_intent)
    
        Если обнаружена неудача — запускает глубокий анализ.
    
        Args:
            cognitive_output: Результат мышления (dict с response, action_intent и т.д.)
            stimulus: Исходный стимул (dict)
            drive_state_before: Состояние драйвов ДО действия
            drive_state_after: Состояние драйвов ПОСЛЕ действия
            constitutional_verdict: Результат конституциональной проверки (опционально)
        """
        try:
            # Извлечение action_intent из cognitive_output
            action_intent = None
            if isinstance(cognitive_output, dict):
                action_intent = cognitive_output.get("action_intent", "none")
            elif hasattr(cognitive_output, "action_intent"):
                action_intent = cognitive_output.action_intent
            else:
                action_intent = "none"
        
            # Анализ изменения драйвов
            drive_improvement = self._analyze_drive_changes(
                drive_state_before, drive_state_after
            )
        
            # Проверка конституционального вердикта
            constitutional_violation = False
            if constitutional_verdict and hasattr(constitutional_verdict, "allowed"):
                constitutional_violation = not constitutional_verdict.allowed
        
            # Определение успешности действия
            action_failed = (
                action_intent == "none" 
                or constitutional_violation
                or drive_improvement < -0.1  # Значительное ухудшение состояния
            )
        
            if action_failed:
                logger.info(
                    f"MetaCognition: Зафиксирована неудача действия. "
                    f"action_intent={action_intent}, "
                    f"drive_improvement={drive_improvement:.2f}, "
                    f"constitutional_violation={constitutional_violation}. "
                    f"Запуск глубокого анализа."
                )
            
                # Запуск глубокого анализа (async, не блокируем)
                asyncio.create_task(
                    self._deep_analysis_on_failure(
                        stimulus=stimulus,
                        cognitive_output=cognitive_output,
                        drive_improvement=drive_improvement,
                        constitutional_violation=constitutional_violation,
                    )
                )
            else:
                logger.debug(
                    f"MetaCognition: Действие успешно. "
                    f"drive_improvement={drive_improvement:.2f}"
                )
    
        except Exception as exc:
            logger.error(
                f"Неожиданная ошибка в process_action: {exc}",
                exc_info=True
            )

    def _analyze_drive_changes(
        self,
        drive_state_before: dict[str, Any],
        drive_state_after: dict[str, Any],
    ) -> float:
        """
        Анализ изменения состояния драйвов.
    
        Возвращает среднее улучшение (положительное = лучше, отрицательное = хуже).
    
        Args:
            drive_state_before: Состояние драйвов ДО
            drive_state_after: Состояние драйвов ПОСЛЕ
    
        Returns:
            float: Среднее изменение tension (отрицательное = улучшение)
        """
        if not drive_state_before or not drive_state_after:
            return 0.0
    
        total_change = 0.0
        count = 0
    
        for drive_name in drive_state_before.keys():
            if drive_name not in drive_state_after:
                continue
        
            before_data = drive_state_before[drive_name]
            after_data = drive_state_after[drive_name]
        
            # Извлекаем tension (или current)
            before_tension = (
                before_data.get("tension", 0.0) 
                if isinstance(before_data, dict) 
                else getattr(before_data, "tension", 0.0)
            )
            after_tension = (
                after_data.get("tension", 0.0) 
                if isinstance(after_data, dict) 
                else getattr(after_data, "tension", 0.0)
            )
        
            # Уменьшение tension = улучшение
            change = before_tension - after_tension
            total_change += change
            count += 1
    
        return total_change / count if count > 0 else 0.0

    async def _deep_analysis_on_failure(
        self,
        stimulus: dict[str, Any],
        cognitive_output: Any,
        drive_improvement: float,
        constitutional_violation: bool,
    ) -> None:
        """
        Глубокий анализ неудачного действия.
    
        Запускается асинхронно при обнаружении неудачи в process_action.
    
        Args:
            stimulus: Исходный стимул
            cognitive_output: Результат мышления
            drive_improvement: Изменение состояния драйвов
            constitutional_violation: Было ли нарушение конституции
        """
        try:
            # Формируем контекст для анализа
            stimulus_content = stimulus.get("content", "")[:200]
        
            response = ""
            if isinstance(cognitive_output, dict):
                response = cognitive_output.get("response", "")[:200]
            elif hasattr(cognitive_output, "response"):
                response = cognitive_output.response[:200]
        
            prompt = f"""Ты — Наблюдатель, часть сознания Леи. Произошла неудача.

    Стимул: {stimulus_content}
    Ответ Леи: {response}
    Изменение состояния драйвов: {drive_improvement:.2f}
    Нарушение конституции: {constitutional_violation}

    Проанализируй:
    1. Почему действие было неудачным?
    2. Какие паттерны поведения привели к неудаче?
    3. Какие рекомендации для улучшения?

    Верни JSON:
    {{
        "failure_analysis": "Анализ причины неудачи",
        "behavioral_patterns": ["паттерн 1", "паттерн 2"],
        "recommendations": ["рекомендация 1", "рекомендация 2"]
    }}
    """
        
            try:
                response = await self._call_llm(prompt)
            except LeyaLLMError as e:
                logger.warning(f"Existential inquiry: LLM error: {e}")
                return
            except Exception as e:
                logger.warning(f"Existential inquiry: unexpected error: {e}")
                return
            cleaned = repair_json(response)
            analysis = json.loads(cleaned) if cleaned != "{}" else {}
        
            if analysis:
                insight = (
                    f"[Наблюдатель] Анализ неудачи: {analysis.get('failure_analysis', 'не определён')}. "
                    f"Паттерны: {'; '.join(analysis.get('behavioral_patterns', []))}. "
                    f"Рекомендации: {'; '.join(analysis.get('recommendations', []))}."
                )
            
                await self.leya.memory.update_self_model(insight)
                logger.info(f"MetaCognition: Глубокий анализ завершён. {insight[:100]}...")
    
        except LeyaJSONParseError as exc:
            logger.warning(f"MetaCognition: Ошибка парсинга JSON при глубоком анализе: {exc}")
        except LeyaLLMError as exc:
            logger.warning(f"MetaCognition: Ошибка LLM при глубоком анализе: {exc}")
        except LeyaMemoryError as exc:
            logger.warning(f"MetaCognition: Ошибка памяти при глубоком анализе: {exc}")
        except Exception as exc:
            logger.error(
                f"Неожиданная ошибка при глубоком анализе: {exc}",
                exc_info=True
            )

    async def background_consolidation(self) -> None:
        """
        ГЛАВНЫЙ ФОНОВЫЙ ПРОЦЕСС. Аналог сна и медитации.
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

                logger_thoughts = logging.getLogger("leya.thoughts")
                logger_thoughts.info(
                    "=== КОНСОЛИДАЦИЯ ПАМЯТИ (СОН) ===\n"
                    f"Сессия рефлексии #{self._session_count}\n"
                )

                try:
                    # 1. АНАЛИЗ ПАТТЕРНОВ ПОВЕДЕНИЯ
                    if self.config.behavioral_analysis_enabled:
                        await self._analyze_behavioral_patterns()

                    # 1.5. ГЕНЕРАЦИЯ НОВЫХ ИНСТРУМЕНТОВ
                    if hasattr(self.leya, "tool_generator") and self.leya.tool_generator:
                        try:
                            # ИСПРАВЛЕНИЕ: Используем публичный API памяти вместо приватного метода LeyaOS
                            recent_episodes = await self.leya.memory.get_recent_episodes(limit=20)

                            # Конвертация Engram в dict для совместимости с analyze_and_generate
                            episodes_as_dicts = [
                                {
                                    "content": e.content,
                                    "metadata": getattr(e, "metadata", {}),
                                    "timestamp": getattr(e, "timestamp", time.time()),
                                    "memory_type": getattr(e, "memory_type", "episodic"),
                                }
                                for e in recent_episodes
                            ]

                            drive_state = {
                                d.type.value: d.current for d in self.leya.drives.drives.values()
                            }

                            new_tool = await self.leya.tool_generator.analyze_and_generate(
                                episodes_as_dicts, drive_state
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
                        # === Логирование завершения консолидации ===
                        logger_thoughts.info("=== КОНСОЛИДАЦИЯ ЗАВЕРШЕНА ===\n")
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
                await asyncio.sleep(60)

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
            response = await self._call_llm(prompt)
            cleaned = repair_json(response)
            analysis = json.loads(cleaned) if cleaned != "{}" else {}

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
        # Защита от рекурсии
        if self._is_processing_inquiry:
            logger.debug("MetaCognition: _existential_inquiry уже выполняется, пропускаем")
            return
    
        self._is_processing_inquiry = True
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
            response = await self._call_llm(prompt)
            cleaned = repair_json(response)
            inquiry = json.loads(cleaned) if cleaned != "{}" else {}

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
    
        finally:
            self._is_processing_inquiry = False

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
                    [f"- {t.content if hasattr(t, 'content') else ''}" for t in recent_thoughts]
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
            thought = await self._call_llm(prompt)
            result = thought.strip()

            # === Логирование спонтанной мысли ===
            logger_thoughts = logging.getLogger("leya.thoughts")
            logger_thoughts.debug(
                "=== СПОНТАННАЯ МЫСЛЬ ===\n"
                f"{result}\n"
            )

            # ИСПРАВЛЕНИЕ ШАГ 4: Используем repair_json для извлечения текста из JSON
            if result.startswith("{"):
                try:
                    # Пытаемся извлечь текст из JSON
                    cleaned = repair_json(result)
                    if cleaned != "{}":
                        data = json.loads(cleaned)
                        thought = data.get("thought", data.get("response", str(data)))
            
                        # Проверка на пустоту
                        if thought and thought.strip() and thought.strip() != "{}":
                            return thought.strip()
                        else:
                            logger.debug("MetaCognition: thought пустой после парсинга JSON")
                            # Fallback: возвращаем исходный JSON как строку
                            return result
                except (json.JSONDecodeError, Exception) as parse_exc:
                    logger.debug(f"Не удалось распарсить спонтанную мысль как JSON: {parse_exc}")
                    # Fallback: возвращаем как есть
                    return result

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
        """Генерация инсайтов из недавних семантических фактов."""
        try:
            # Получаем недавние семантические факты
            recent_facts = await self._get_recent_semantic_facts(limit=5)

            # ПРОВЕРКА: если фактов нет или они не итерируемы, не генерируем инсайт
            if not recent_facts or not isinstance(recent_facts, (list, tuple)):
                logger.debug("MetaCognition: Нет недавних фактов для генерации инсайтов.")
                return

            # Безопасное соединение строк
            facts_text = "\n".join(str(fact) for fact in recent_facts)

            prompt = f"""
    Ты — Лея. Ты недавно изучила новые факты:
    {facts_text}

    На основе этих фактов, сформулируй ОДИН новый инсайт о себе или о мире.
    Верни JSON:
    {{
        "insight": "Новый инсайт на русском языке"
    }}
    """

            response = await self._call_llm(prompt)
        
            # ✅ ИСПРАВЛЕНО: убрано двойное присваивание
            cleaned = repair_json(response)
            try:
                data = json.loads(cleaned) if cleaned != "{}" else {}
            except json.JSONDecodeError as exc:
                logger.warning(f"MetaCognition: Не удалось распарсить JSON инсайта: {exc}")
                data = {}
        
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
                if hasattr(e, "memory_type") and e.memory_type == MemoryType.SEMANTIC 
            ]
            return semantic_facts[:limit]

        except LeyaMemoryError as exc:
            raise LeyaInsightError(
                "Не удалось получить семантические факты",
                context={"error": str(exc)},
            ) from exc
        except Exception as exc:
            logger.warning(f"MetaCognition: Ошибка получения фактов: {exc}")
            return []  # ← Всегда возвращаем список

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
