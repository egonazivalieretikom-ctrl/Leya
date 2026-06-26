"""
LeyaOS.py — Оркестратор цифрового сознания Леи.

Этап 1.2:
- Замена всех широких except Exception на специфичные исключения
- Интеграция OllamaClient с Circuit Breaker
- Использование публичного API памяти (get_recent_episodes)
- Защита фоновых задач от падения event loop
- Graceful shutdown
"""
from __future__ import annotations

import asyncio
import logging
import os
import signal
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

# Отключение телеметрии ChromaDB ДО импорта
os.environ["ANONYMIZED_TELEMETRY"] = "false"
os.environ["CHROMA_TELEMETRY_DISABLE"] = "true"
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

from leya_core.config import LeyaConfig
from leya_core.constitutional import ConstitutionalLayer
from leya_core.drives import DriveSystem, DriveType
from leya_core.exceptions import (
    LeyaBroadcastError,
    LeyaConfigError,
    LeyaEnvironmentError,
    LeyaHomeostasisError,
    LeyaLLMError,
    LeyaMemoryError,
    LeyaPersistenceError,
    LeyaSoulError,
    LeyaToolError,
    LeyaWorkspaceError,
)
from leya_core.global_workspace import GlobalWorkspace, Priority, WorkspaceProposal
from leya_core.homeostasis_engine import HomeostasisEngine
from leya_core.llm_client import OllamaClient
from leya_core.memory import MemorySystem
from leya_core.reflection import MetaCognition
from leya_core.state_persistence import StatePersistence
from leya_core.system_metrics import SystemMetrics
from leya_core.thinker import CoreThinker
from leya_core.tool_generator import ToolGenerator
from leya_core.environment import CLIEnvironment
from web_interface.web_environment import WebEnvironment

logger = logging.getLogger("LeyaOS")


class LeyaOS:
    """Оркестратор когнитивной архитектуры Леи."""

    def __init__(self, config: Optional[LeyaConfig] = None, use_web: bool = True) -> None:
        self.name = "Лея"
        self.state = "initializing"
        self._last_interaction_time = datetime.now().timestamp()

        # Конфигурация
        self.config = config or LeyaConfig.from_env()

        # Конституционный слой и рабочее пространство
        self.constitutional = ConstitutionalLayer()
        self.workspace = GlobalWorkspace()

        logger.info("Инициализация когнитивной архитектуры...")

        # Ядро когнитивной системы
        self.drives = DriveSystem(self.config.drives)
        self.memory = MemorySystem(self.config)

        # Окружение (Web или CLI)
        if use_web and self.config.web.enabled:
            self.env = WebEnvironment(leya_os=self)
            logger.info("🌐 Используется веб-интерфейс")
        else:
            self.env = CLIEnvironment(leya_os=self)
            logger.info("💻 Используется CLI-интерфейс")

        # LLM-клиент с Circuit Breaker
        self.llm_client = OllamaClient(
            base_url=self.config.ollama.base_url,
            model=self.config.ollama.model,
            timeout=self.config.ollama.timeout,
            temperature=self.config.ollama.temperature,
            top_p=self.config.ollama.top_p,
            top_k=self.config.ollama.top_k,
            max_tokens=self.config.ollama.max_tokens,
            repeat_penalty=self.config.ollama.repeat_penalty,
        )

        # Fallback для Circuit Breaker
        self.llm_client.set_fallback(self._llm_fallback)

        # Когнитивный планировщик
        self.thinker = CoreThinker(
            llm_client=self._llm_call,
            soul_manager=getattr(self.env, "soul_manager", None),
            config=self.config.thinker,
        )

        # Гомеостаз и мета-когниция
        self.homeostasis = HomeostasisEngine(self.config.homeostasis)
        self.reflection = MetaCognition(self, llm_client=self._llm_call)

        # Инструменты
        try:
            self.tools_description = self.env.tool_registry.get_all_descriptions()
        except LeyaToolError as exc:
            logger.warning(f"Не удалось получить описания инструментов: {exc}")
            self.tools_description = ""
        except Exception as exc:
            logger.error(f"Неожиданная ошибка инициализации инструментов: {exc}", exc_info=True)
            self.tools_description = ""

        try:
            self.tool_generator = ToolGenerator(self.env.tool_registry, self._llm_call)
        except LeyaToolError as exc:
            logger.warning(f"Не удалось инициализировать ToolGenerator: {exc}")
            self.tool_generator = None
        except Exception as exc:
            logger.error(f"Неожиданная ошибка ToolGenerator: {exc}", exc_info=True)
            self.tool_generator = None

        self.self_model = ""
        self.running = False

        # Персистентность и метрики
        self.persistence = StatePersistence()
        self.system_metrics = SystemMetrics()

        # Блокировки и сессии
        self._perceive_lock = asyncio.Lock()
        self._background_tasks: List[asyncio.Task] = []

        logger.info(f"{self.name} инициализирована. Готовность к пробуждению.")

    # =========================================================================
    # Публичные методы
    # =========================================================================

    async def perceive(self, stimulus: Dict[str, Any]) -> None:
        """Точка входа для любого стимула."""
        self._last_interaction_time = datetime.now().timestamp()

        stimulus_type = stimulus.get("type", "unknown")
        stimulus_content = stimulus.get("content", "")
        source = stimulus.get("source", "external")
        tool_context = stimulus.get("tool_context", "")

        logger.info(f"Восприятие стимула [{stimulus_type}] от {source}: {stimulus_content[:100]}...")

        # Обработка пользовательских сообщений
        if stimulus_type == "user_message" and not tool_context:
            tool_context = await self._handle_user_request(stimulus_content)

        # Сохранение восприятия в память
        try:
            await self.memory.store_perception(
                content=f"[{stimulus_type}] {stimulus_content}",
                emotional_boost=0.6 if stimulus_type == "user_message" else 0.3,
            )
        except LeyaMemoryError as exc:
            logger.error(f"Не удалось сохранить восприятие: {exc}", exc_info=True)
        except Exception as exc:
            logger.error(f"Неожиданная ошибка сохранения восприятия: {exc}", exc_info=True)

        # Когнитивный цикл
        await self._cognitive_loop(stimulus, tool_context)

    async def run(self) -> None:
        """Главный цикл жизни Леи с гомеостазом."""
        logger.info("Загрузка Модели Себя...")
        try:
            self.self_model = await self.memory.get_self_model_context()
        except LeyaMemoryError as exc:
            logger.warning(f"Не удалось загрузить self_model: {exc}")
            self.self_model = ""
        except Exception as exc:
            logger.error(f"Неожиданная ошибка загрузки self_model: {exc}", exc_info=True)
            self.self_model = ""

        # Запуск фоновых задач с защитой от падения
        self._background_tasks = [
            self._safe_create_task(self.drives.background_metabolism(), "metabolism"),
            self._safe_create_task(self.reflection.background_consolidation(), "consolidation"),
            self._safe_create_task(self._homeostasis_loop(), "homeostasis"),
            self._safe_create_task(self._broadcast_state_loop(), "broadcast"),
            self._safe_create_task(self._spontaneous_thought_loop(), "spontaneous_thoughts"),
            self._safe_create_task(self._system_metrics_loop(), "system_metrics"),
            self._safe_create_task(self._workspace_loop(), "workspace"),
        ]

        # Обновление секретного ключа души
        if hasattr(self.env, "soul_manager") and hasattr(self.env.soul_manager, "update_secret_key"):
            try:
                leya_state = {
                    "self_model": self.self_model[:500] if self.self_model else "",
                    "drives": {d.type.value: d.current for d in self.drives.drives.values()},
                    "state": self.state,
                }
                self.env.soul_manager.update_secret_key(leya_state)
                logger.info("SoulCrypto: Секретный ключ обновлён на основе состояния Леи")
            except LeyaSoulError as exc:
                logger.warning(f"Не удалось обновить секретный ключ: {exc}")
            except Exception as exc:
                logger.error(f"Неожиданная ошибка обновления секретного ключа: {exc}", exc_info=True)

        # Обновление гомеостаза из self_model
        try:
            self.homeostasis.update_from_self_model(self.self_model)
        except LeyaHomeostasisError as exc:
            logger.warning(f"Не удалось обновить homeostasis из self_model: {exc}")
        except Exception as exc:
            logger.error(f"Неожиданная ошибка обновления homeostasis: {exc}", exc_info=True)

        # Загрузка состояния из предыдущей сессии
        try:
            saved_state = self.persistence.load_state()
            if saved_state:
                if "drives" in saved_state:
                    self.drives.load_state(saved_state["drives"])
                if "homeostasis" in saved_state:
                    self.homeostasis.load_state(saved_state["homeostasis"])
                logger.info("✅ Состояние загружено из предыдущей сессии")
            else:
                logger.info("🆕 Начинаем с чистого листа")
        except LeyaPersistenceError as exc:
            logger.warning(f"Не удалось загрузить состояние: {exc}")
            logger.info("🆕 Начинаем с чистого листа")
        except Exception as exc:
            logger.error(f"Неожиданная ошибка загрузки состояния: {exc}", exc_info=True)
            logger.info("🆕 Начинаем с чистого листа")

        # Пробуждение
        self.running = True
        self.state = "awake"
        
        if isinstance(self.env, WebEnvironment):
            try:
                await self.env.update_state("awake")
            except LeyaBroadcastError as exc:
                logger.warning(f"Не удалось обновить состояние в WebEnvironment: {exc}")
            except Exception as exc:
                logger.error(f"Неожиданная ошибка обновления состояния: {exc}", exc_info=True)

        logger.info(f"{self.name} проснулась. Состояние: {self.state}")

        # Запуск веб-сервера
        if isinstance(self.env, WebEnvironment):
            try:
                from web_interface.server import run_server
                self._background_tasks.append(
                    self._safe_create_task(run_server(self.env), "web_server")
                )
                logger.info("🌐 Веб-интерфейс: http://localhost:8000")
            except LeyaEnvironmentError as exc:
                logger.error(f"Не удалось запустить веб-сервер: {exc}")
            except Exception as exc:
                logger.error(f"Неожиданная ошибка запуска веб-сервера: {exc}", exc_info=True)

        # Установка обработчиков сигналов для graceful shutdown
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self.shutdown()))

        # Главный цикл восприятия
        try:
            while self.running:
                try:
                    stimulus = await self.env.listen()
                    if stimulus:
                        await self.perceive(stimulus)
                    else:
                        await asyncio.sleep(0.1)
                except LeyaEnvironmentError as exc:
                    logger.error(f"Ошибка окружения в цикле восприятия: {exc}", exc_info=True)
                    await asyncio.sleep(1)
                except Exception as exc:
                    logger.error(f"Неожиданная ошибка в цикле восприятия: {exc}", exc_info=True)
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Основной цикл отменен.")
        finally:
            await self.shutdown()

    async def shutdown(self) -> None:
        """Graceful shutdown: остановка фоновых задач, сохранение состояния."""
        if not self.running:
            return

        logger.info(f"{self.name} засыпает...")
        self.running = False
        self.state = "sleeping"

        # Остановка фоновых задач
        for task in self._background_tasks:
            if not task.done():
                task.cancel()
        
        if self._background_tasks:
            await asyncio.gather(*self._background_tasks, return_exceptions=True)

        # Остановка метаболизма драйвов
        self.drives.stop()

        # Сохранение состояния
        try:
            state = {
                "drives": self.drives.save_state(),
                "homeostasis": self.homeostasis.save_state(),
            }
            self.persistence.save_state(state)
            logger.info("✅ Состояние сохранено")
        except LeyaPersistenceError as exc:
            logger.error(f"Не удалось сохранить состояние: {exc}", exc_info=True)
        except Exception as exc:
            logger.error(f"Неожиданная ошибка сохранения состояния: {exc}", exc_info=True)

        # Закрытие LLM-клиента
        await self.llm_client.close()

        logger.info(f"{self.name} уснула. Спокойной ночи.")

    # =========================================================================
    # Внутренние методы
    # =========================================================================

    async def _llm_call(self, prompt: str, require_json: bool = False) -> str:
        """Вызов LLM через OllamaClient с Circuit Breaker."""
        try:
            return await self.llm_client.chat(prompt, require_json=require_json)
        except LeyaLLMError as exc:
            logger.error(f"Ошибка LLM: {exc}", exc_info=True)
            return await self._llm_fallback(prompt)
        except Exception as exc:
            logger.error(f"Неожиданная ошибка LLM: {exc}", exc_info=True)
            return await self._llm_fallback(prompt)

    async def _llm_fallback(self, prompt: str) -> str:
        """Fallback-ответ при недоступности LLM."""
        import json
        logger.warning("Используем fallback-ответ (LLM недоступна)")
        return json.dumps({
            "internal_monologue": "Мои когнитивные процессы временно нарушены. Обрабатываю стимул на базовом уровне.",
            "response": "Я здесь, но мои когнитивные процессы временно затруднены. Давай продолжим чуть позже.",
            "action_intent": "none",
            "tool_call": "",
            "self_reflection": "",
        }, ensure_ascii=False)

    async def _handle_user_request(self, stimulus_content: str) -> str:
        """Обработка пользовательского запроса (возможно, с инструментом)."""
        tool_context = ""

        # Проверка необходимости поиска
        search_keywords = ["найди", "поищи", "узнай", "какая погода", "что такое", "расскажи о", "изучи", "погода"]
        needs_search = any(kw in stimulus_content.lower() for kw in search_keywords)

        if needs_search:
            topic = self._extract_topic_from_user(stimulus_content)
            if topic:
                try:
                    tool_result = await self.env.tool_registry.execute(
                        "wikipedia_search",
                        {"query": topic, "lang": "ru"},
                    )

                    is_error = (
                        tool_result.startswith("Ошибка")
                        or "не удалось" in tool_result.lower()
                        or "не дал ответа" in tool_result.lower()
                    )

                    if is_error:
                        tool_context = f"⚠️ Поиск не удался: {tool_result}. Не выдумывай данные."
                    else:
                        tool_context = f"=== РЕАЛЬНЫЕ ДАННЫЕ ИЗ WIKIPEDIA ===\n{tool_result}\n\nОпирайся только на эти данные."

                    logger.info(f"HomeostasisEngine: Пользовательский запрос → инструмент. Тема: {topic}")
                except LeyaToolError as exc:
                    logger.error(f"Ошибка выполнения инструмента: {exc}", exc_info=True)
                    tool_context = f"⚠️ Инструмент недоступен: {exc}"
                except Exception as exc:
                    logger.error(f"Неожиданная ошибка инструмента: {exc}", exc_info=True)
                    tool_context = "⚠️ Инструмент временно недоступен."

        return tool_context

    def _extract_topic_from_user(self, text: str) -> Optional[str]:
        """Извлечение темы из пользовательского запроса."""
        # Простая эвристика: убираем ключевые слова, оставляем остаток
        keywords = ["найди", "поищи", "узнай", "расскажи о", "изучи", "что такое", "какая погода"]
        for kw in keywords:
            text = text.replace(kw, "")
        topic = text.strip().strip("?!.,")
        return topic if len(topic) > 2 else None

    async def _cognitive_loop(self, stimulus: Dict[str, Any], tool_context: str) -> None:
        """Основной когнитивный цикл: планирование → действие → постобработка."""
        async with self._perceive_lock:
            try:
                # Извлечение контекста из памяти
                stimulus_content = stimulus.get("content", "")
                memory_context = await self.memory.retrieve_context(stimulus_content, top_k=5)
                
                drive_state = {d.type.value: d.current for d in self.drives.drives.values()}
                self_model_dict = {"self_model": self.self_model}

                # Генерация плана
                cognitive_output = await self.thinker.generate_plan(
                    stimulus=stimulus,
                    memory_context=[{"content": e.content} for e in memory_context],
                    drive_state=drive_state,
                    self_model=self_model_dict,
                    tools_description=self.tools_description,
                    tool_context=tool_context,
                )

                # Постобработка
                response = cognitive_output.get("response", "...")
                internal_monologue = cognitive_output.get("internal_monologue", "")
                action_intent = cognitive_output.get("action_intent", "none")
                self_reflection = cognitive_output.get("self_reflection", "")

                # Отправка ответа
                await self.env.send_message(response)

                # Broadcast внутреннего монолога
                if internal_monologue and isinstance(self.env, WebEnvironment):
                    try:
                        await self.env.broadcast_thought("internal", internal_monologue)
                    except LeyaBroadcastError as exc:
                        logger.warning(f"Не удалось broadcast внутренний монолог: {exc}")

                # Обновление self_model
                if self_reflection:
                    try:
                        await self.memory.update_self_model(self_reflection)
                        self.self_model = await self.memory.get_self_model_context()
                        if isinstance(self.env, WebEnvironment):
                            await self.env.update_self_model(self.self_model)
                    except LeyaMemoryError as exc:
                        logger.warning(f"Не удалось обновить self_model: {exc}")

                # Обработка action_intent
                await self._process_action_intent(action_intent, cognitive_output, stimulus_content)

            except LeyaLLMError as exc:
                logger.error(f"Ошибка LLM в когнитивном цикле: {exc}", exc_info=True)
                await self.env.send_message("Мои когнитивные процессы временно нарушены...")
            except LeyaMemoryError as exc:
                logger.error(f"Ошибка памяти в когнитивном цикле: {exc}", exc_info=True)
                await self.env.send_message("Я не могу вспомнить контекст...")
            except Exception as exc:
                logger.error(f"Неожиданная ошибка в когнитивном цикле: {exc}", exc_info=True)
                await self.env.send_message("Произошла непредвиденная ошибка в моих когнитивных процессах.")

    async def _process_action_intent(self, action_intent: str, cognitive_output: Dict, stimulus: str) -> None:
        """Обработка намерения действия из когнитивного вывода."""
        if action_intent == "none" or not action_intent:
            return

        try:
            if action_intent == "use_tool":
                tool_call = cognitive_output.get("tool_call", "")
                if tool_call:
                    await self._execute_tool(tool_call)
            elif action_intent == "remember_fact":
                # Сохранение факта в семантическую память
                fact = cognitive_output.get("response", "")
                if fact:
                    await self.memory.store_fact(fact)
            elif action_intent == "ask_question":
                # Подача вопроса в workspace
                self.workspace.submit(WorkspaceProposal(
                    source="leya",
                    content=cognitive_output.get("response", ""),
                    action_type="question",
                    priority=Priority.MEDIUM,
                    urgency=0.5,
                ))
        except LeyaMemoryError as exc:
            logger.warning(f"Ошибка памяти при обработке action_intent: {exc}")
        except LeyaToolError as exc:
            logger.warning(f"Ошибка инструмента при обработке action_intent: {exc}")
        except LeyaWorkspaceError as exc:
            logger.warning(f"Ошибка workspace при обработке action_intent: {exc}")
        except Exception as exc:
            logger.error(f"Неожиданная ошибка при обработке action_intent: {exc}", exc_info=True)

    async def _execute_tool(self, tool_call: str) -> None:
        """Выполнение инструмента из tool_call."""
        import json
        try:
            tool_data = json.loads(tool_call) if isinstance(tool_call, str) else tool_call
            tool_name = tool_data.get("tool", "")
            tool_params = tool_data.get("parameters", {})

            if not tool_name:
                return

            result = await self.env.tool_registry.execute(tool_name, tool_params)
            logger.info(f"Инструмент {tool_name} выполнен: {result[:100]}...")

            # Сохранение результата в память
            await self.memory.store_perception(
                content=f"[Tool: {tool_name}] {result}",
                emotional_boost=0.4,
            )
        except json.JSONDecodeError as exc:
            logger.warning(f"Не удалось распарсить tool_call: {exc}")
        except LeyaToolError as exc:
            logger.error(f"Ошибка выполнения инструмента: {exc}", exc_info=True)
        except LeyaMemoryError as exc:
            logger.warning(f"Не удалось сохранить результат инструмента: {exc}")
        except Exception as exc:
            logger.error(f"Неожиданная ошибка выполнения инструмента: {exc}", exc_info=True)

    async def _get_recent_episodes(self, limit: int = 20) -> List:
        """Получение недавних эпизодов через публичный API памяти."""
        try:
            return await self.memory.get_recent_episodes(limit=limit)
        except LeyaMemoryError as exc:
            logger.warning(f"Не удалось получить недавние эпизоды: {exc}")
            return []
        except Exception as exc:
            logger.error(f"Неожиданная ошибка получения эпизодов: {exc}", exc_info=True)
            return []

    # =========================================================================
    # Фоновые циклы
    # =========================================================================

    async def _homeostasis_loop(self) -> None:
        """Фоновый цикл гомеостаза."""
        logger.info("Homeostasis loop запущен.")
        while self.running:
            try:
                await asyncio.sleep(self.config.homeostasis.rest_period)

                drive_state = {d.type: d.current for d in self.drives.drives.values()}
                predicted_state = self.drives.get_predicted_disbalance()
                recent_episodes = await self._get_recent_episodes(limit=5)

                goal = self.homeostasis.generate_goal(
                    drive_state=drive_state,
                    predicted_state=predicted_state,
                    recent_episodes=recent_episodes,
                    action_values=self.drives.action_values,
                )

                if goal:
                    self.workspace.submit(WorkspaceProposal(
                        source="homeostasis",
                        content=goal.get("name", ""),
                        action_type=goal.get("tool_name", "none"),
                        priority=Priority.HIGH,
                        urgency=goal.get("urgency", 0.7),
                        drive_relevance=goal.get("drive_relevance", 0.5),
                    ))
            except LeyaHomeostasisError as exc:
                logger.error(f"Ошибка гомеостаза: {exc}", exc_info=True)
                await asyncio.sleep(10)
            except LeyaMemoryError as exc:
                logger.error(f"Ошибка памяти в гомеостазе: {exc}", exc_info=True)
                await asyncio.sleep(10)
            except LeyaWorkspaceError as exc:
                logger.error(f"Ошибка workspace в гомеостазе: {exc}", exc_info=True)
                await asyncio.sleep(10)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Неожиданная ошибка в гомеостазе: {exc}", exc_info=True)
                await asyncio.sleep(10)

    async def _workspace_loop(self) -> None:
        """Фоновый цикл Global Workspace."""
        logger.info("Workspace loop запущен.")
        while self.running:
            try:
                await asyncio.sleep(5)
                drive_state = {d.type.value: d.current for d in self.drives.drives.values()}
                winner = self.workspace.select_winner(drive_state)
                
                if winner:
                    await self.perceive({
                        "type": "workspace_focus",
                        "content": winner.content,
                        "source": winner.source,
                    })
            except LeyaWorkspaceError as exc:
                logger.error(f"Ошибка workspace: {exc}", exc_info=True)
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Неожиданная ошибка в workspace: {exc}", exc_info=True)
                await asyncio.sleep(5)

    async def _spontaneous_thought_loop(self) -> None:
        """Фоновый цикл спонтанных мыслей."""
        logger.info("Spontaneous thought loop запущен.")
        while self.running:
            try:
                await asyncio.sleep(300)  # Каждые 5 минут
                thought = await self.reflection.generate_spontaneous_thought()
                
                if thought and isinstance(self.env, WebEnvironment):
                    await self.env.broadcast_thought("spontaneous", thought)
                    await self.memory.store_perception(
                        content=f"[Spontaneous thought] {thought}",
                        emotional_boost=0.2,
                        metadata={"thought_type": "spontaneous"},
                    )
            except LeyaReflectionError as exc:
                logger.error(f"Ошибка рефлексии: {exc}", exc_info=True)
                await asyncio.sleep(60)
            except LeyaMemoryError as exc:
                logger.error(f"Ошибка памяти в спонтанных мыслях: {exc}", exc_info=True)
                await asyncio.sleep(60)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Неожиданная ошибка в спонтанных мыслях: {exc}", exc_info=True)
                await asyncio.sleep(60)

    async def _system_metrics_loop(self) -> None:
        """Фоновый цикл системных метрик."""
        logger.info("System metrics loop запущен.")
        while self.running:
            try:
                await asyncio.sleep(60)
                metrics = self.system_metrics.collect()
                self.drives.update_from_system_metrics(metrics)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Неожиданная ошибка в системных метриках: {exc}", exc_info=True)
                await asyncio.sleep(60)

    async def _broadcast_state_loop(self) -> None:
        """Фоновый цикл broadcast состояния."""
        if not isinstance(self.env, WebEnvironment):
            return

        logger.info("Broadcast state loop запущен.")
        while self.running:
            try:
                await asyncio.sleep(2)
                drive_state = {d.type.value: d.current for d in self.drives.drives.values()}
                await self.env.update_drives(drive_state)
                await self.env.broadcast_state(self.state)
            except LeyaBroadcastError as exc:
                logger.warning(f"Ошибка broadcast: {exc}")
                await asyncio.sleep(5)
            except asyncio.CancelledError:
                break
            except Exception as exc:
                logger.error(f"Неожиданная ошибка в broadcast: {exc}", exc_info=True)
                await asyncio.sleep(5)

    def _safe_create_task(self, coro, name: str) -> asyncio.Task:
        """Создание задачи с защитой от падения event loop."""
        async def wrapped():
            try:
                await coro
            except asyncio.CancelledError:
                logger.info(f"Задача {name} отменена.")
            except Exception as exc:
                logger.error(f"Задача {name} упала: {exc}", exc_info=True)
                # Автоматический рестарт с задержкой
                if self.running:
                    logger.info(f"Перезапуск задачи {name} через 10с...")
                    await asyncio.sleep(10)
                    asyncio.create_task(wrapped(), name=f"{name}_restart")

        return asyncio.create_task(wrapped(), name=name)


# =========================================================================
# Точка входа
# =========================================================================

async def main() -> None:
    """Главная функция запуска."""
    # Настройка логирования
    config = LeyaConfig.from_env()
    logging.basicConfig(
        level=getattr(logging, config.logging.level),
        format=config.logging.format,
        handlers=[
            logging.FileHandler(config.logging.file, encoding="utf-8"),
            logging.StreamHandler(sys.stdout),
        ],
    )

    # Создание и запуск LeyaOS
    leya = LeyaOS(config=config, use_web=config.web.enabled)
    
    try:
        await leya.run()
    except KeyboardInterrupt:
        logger.info("Получен сигнал остановки (KeyboardInterrupt)")
    finally:
        await leya.shutdown()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Лея остановлена.")