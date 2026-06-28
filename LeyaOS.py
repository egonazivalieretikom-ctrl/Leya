"""
LeyaOS.py — Оркестратор цифрового сознания Леи.
Версия: 3.0
"""

from __future__ import annotations  # ✅ ИСПРАВЛЕНО: было "from future"

from dotenv import load_dotenv

load_dotenv()
import asyncio
import logging
import os
import signal
import sys
from datetime import datetime
from pathlib import Path
from typing import Any  # ✅ Добавлен Optional

# Bootstrap выполняется автоматически при импорте leya_core (см. leya_core/__init__.py)
# os.environ устанавливается там ДО загрузки chromadb
# Импорт конфигурации
from leya_core.config import LeyaConfig

# Импорт модулей
from leya_core.constitutional import ConstitutionalLayer
from leya_core.drives import DriveSystem
from leya_core.environment import CLIEnvironment

# Импорт исключений
from leya_core.exceptions import (
    LeyaBroadcastError,
    LeyaEnvironmentError,
    LeyaHomeostasisError,
    LeyaLLMError,
    LeyaMemoryError,
    LeyaPersistenceError,
    LeyaReflectionError,
    LeyaToolError,
    LeyaWorkspaceError,
)
from leya_core.global_workspace import GlobalWorkspace, Priority, WorkspaceProposal
from leya_core.homeostasis_engine import HomeostasisEngine

# Импорт Protocol-интерфейсов
from leya_core.interfaces import (
    IConstitutionalLayer,
    ICoreThinker,
    IDecisionEngine,
    IDriveSystem,
    IEmotionalSupport,
    IEnvironment,
    IGlobalWorkspace,
    IHomeostasisEngine,
    IMemorySystem,
    IMetaCognition,
)
from leya_core.llm_client import OllamaClient  # ✅ Этот импорт теперь выполнится
from leya_core.memory import MemorySystem
from leya_core.reflection import MetaCognition
from leya_core.request_classifier import IntentClassification, RequestClassifier, UserIntent
from leya_core.soul_manager import SoulManager
from leya_core.state_persistence import StatePersistence
from leya_core.system_metrics import SystemMetrics
from leya_core.thinker import CoreThinker
from leya_core.tool_generator import ToolGenerator
from web_interface.web_environment import WebEnvironment

if not isinstance(self.memory, IMemorySystem):
    raise TypeError(f"memory должен реализовывать IMemorySystem, получено {type(self.memory)}")
if not isinstance(self.drives, IDriveSystem):
    raise TypeError(f"drives должен реализовывать IDriveSystem, получено {type(self.drives)}")
if not isinstance(self.workspace, IGlobalWorkspace):
    raise TypeError(
        f"workspace должен реализовывать IGlobalWorkspace, получено {type(self.workspace)}"
    )
if not isinstance(self.constitutional, IConstitutionalLayer):
    raise TypeError(
        f"constitutional должен реализовывать IConstitutionalLayer, получено {type(self.constitutional)}"
    )
if not isinstance(self.thinker, ICoreThinker):
    raise TypeError(f"thinker должен реализовывать ICoreThinker, получено {type(self.thinker)}")
if not isinstance(self.homeostasis, IHomeostasisEngine):
    raise TypeError(
        f"homeostasis должен реализовывать IHomeostasisEngine, получено {type(self.homeostasis)}"
    )
if not isinstance(self.reflection, IMetaCognition):
    raise TypeError(
        f"reflection должен реализовывать IMetaCognition, получено {type(self.reflection)}"
    )
if not isinstance(self.env, IEnvironment):
    raise TypeError(f"env должен реализовывать IEnvironment, получено {type(self.env)}")

# Experimental компоненты (lazy import для изоляции)
self.decision_engine: IDecisionEngine | None = None
self.emotional_support: IEmotionalSupport | None = None

if self.config.experimental.enable_decision_engine:
    try:
        from leya_core.experimental.interfaces import IDecisionEngine

        from leya_core.experimental.decision_engine import DecisionEngine

        self.decision_engine = DecisionEngine(self.config)
        if not isinstance(self.decision_engine, IDecisionEngine):
            raise TypeError("DecisionEngine не реализует IDecisionEngine")
        logger.info("✅ DecisionEngine включён (feature flag)")
    except Exception as e:
        logger.error(f"Не удалось инициализировать DecisionEngine: {e}", exc_info=True)
        self.decision_engine = None

if self.config.experimental.enable_emotional_support:
    try:
        from leya_core.experimental.interfaces import IEmotionalSupport

        from leya_core.experimental.emotional_support import EmotionalSupport

        self.emotional_support = EmotionalSupport(self.config, self.memory)
        if not isinstance(self.emotional_support, IEmotionalSupport):
            raise TypeError("EmotionalSupport не реализует IEmotionalSupport")
        logger.info("✅ EmotionalSupport включён (feature flag)")
    except Exception as e:
        logger.error(f"Не удалось инициализировать EmotionalSupport: {e}", exc_info=True)
        self.emotional_support = None

# Настройка логирования ПОСЛЕ всех импортов
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)
logger = logging.getLogger("LeyaOS")


class LeyaOS:
    """
    Оркестратор когнитивной архитектуры Леи.

    Отвечает за:
    - Инициализацию всех модулей с передачей конфигурации
    - Когнитивный цикл (perceive → plan → act → reflect)
    - Фоновые задачи (метabolism, consolidation, homeostasis, workspace)
    - Graceful shutdown с сохранением состояния
    - Обработку ошибок и защиту от падения event loop
    """

    def __init__(self, config: LeyaConfig, use_web: bool = True):
        self.name = "Лея"
        self.state = "initializing"
        self._last_interaction_time = datetime.now().timestamp()
        self._shutdown_event = asyncio.Event()
        self.config = config or LeyaConfig.from_env()

        # Конституционный слой
        self.constitutional = ConstitutionalLayer(config=self.config.constitutional)
        self.state_path = Path(config.memory.brain_dir) / "memory_state.json"

        # Глобальное рабочее пространство
        self.workspace = GlobalWorkspace(config=self.config.workspace)

        logger.info("Инициализация когнитивной архитектуры...")

        # Ядро когнитивной системы
        self.drives = DriveSystem(config=self.config.drives)
        self.memory = MemorySystem(config=self.config.memory)

        # Персистентность
        self.persistence = StatePersistence(brain_dir=config.memory.brain_dir)

        # Soul Manager
        self.soul_manager = SoulManager(
            soul_dir=self.config.soul.soul_dir,
            hmac_key=os.environ.get("SOUL_HMAC_KEY"),
        )
        logger.info("SoulManager инициализирован")

        # Проверка Protocol-интерфейсов
        if not isinstance(self.memory, IMemorySystem):
            raise TypeError("memory должен реализовывать IMemorySystem")
        if not isinstance(self.drives, IDriveSystem):
            raise TypeError("drives должен реализовывать IDriveSystem")
        if not isinstance(self.workspace, IGlobalWorkspace):
            raise TypeError("workspace должен реализовывать IGlobalWorkspace")
        if not isinstance(self.constitutional, IConstitutionalLayer):
            raise TypeError("constitutional должен реализовывать IConstitutionalLayer")

        # LLM-клиент
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
        self.llm_client.set_fallback(self._llm_fallback)

        # Thinker
        self.thinker = CoreThinker(
            config=self.config.thinker,
            llm_client=self._llm_call,
        )

        # Request Classifier
        self.request_classifier = RequestClassifier(
            llm_client=self.llm_client,
            memory=self.memory,
            use_llm_threshold=0.7,
            cache_similarity_threshold=0.85,
        )

        # Гомеостаз
        self.homeostasis = HomeostasisEngine(config=self.config.homeostasis)

        # Мета-когниция
        self.reflection = MetaCognition(
            leya_os=self,
            llm_client=self._llm_call,
            config=self.config.reflection,
        )

        # Окружение
        if use_web and self.config.web.enabled:
            self.env = WebEnvironment(leya_os=self)
            logger.info("Используется веб-интерфейс")
        else:
            self.env = CLIEnvironment(leya_os=self)
            logger.info("Используется CLI-интерфейс")

        # Инструменты
        try:
            self.tools_description = self.env.tool_registry.get_all_descriptions()
        except Exception:
            self.tools_description = ""

        # Tool Generator
        self.tool_generator = None
        if hasattr(self.env, "tool_registry") and self.env.tool_registry:
            try:
                self.tool_generator = ToolGenerator(
                    tool_registry=self.env.tool_registry,
                    llm_client=self._llm_call,
                )
            except Exception:
                self.tool_generator = None

        # Состояние
        self.self_model = ""
        self.running = False
        self.system_metrics = SystemMetrics()
        self._perceive_lock = asyncio.Lock()
        self._background_tasks = []

        # Experimental (по умолчанию выключено)
        self.decision_engine = None
        self.emotional_support = None

        if self.config.experimental.enable_decision_engine:
            try:
                self.decision_engine = DecisionEngine(self.config)
                logger.info("DecisionEngine включён")
            except Exception:
                self.decision_engine = None

        if self.config.experimental.enable_emotional_support:
            try:
                self.emotional_support = EmotionalSupport(self.config, self.memory)
                logger.info("EmotionalSupport включён")
            except Exception:
                self.emotional_support = None

        logger.info(f"{self.name} инициализирована. Готовность к пробуждению.")

    # =========================================================================
    # Публичные методы
    # =========================================================================

    async def perceive(self, stimulus: dict[str, Any]) -> None:
        """
        Точка входа для любого стимула.

        Args:
            stimulus: Словарь с типом, содержимым и метаданными стимула
        """
        self._last_interaction_time = datetime.now().timestamp()

        stimulus_type = stimulus.get("type", "unknown")
        stimulus_content = stimulus.get("content", "")
        source = stimulus.get("source", "external")
        tool_context = stimulus.get("tool_context", "")

        logger.info(
            f"Восприятие стимула [{stimulus_type}] от {source}: {stimulus_content[:100]}..."
        )

        # Обработка пользовательских сообщений
        if stimulus_type == "user_message" and not tool_context:
            tool_context = await self._handle_user_request(stimulus_content)

        # Сохранение восприятия в память
        try:
            await self.memory.store_perception(
                content=f"[{stimulus_type}] {stimulus_content}",
                emotional_boost=0.6 if stimulus_type == "user_message" else 0.3,
                metadata={"source": source, "type": stimulus_type},
            )
        except LeyaMemoryError as exc:
            logger.error(f"Не удалось сохранить восприятие: {exc}", exc_info=True)
        except Exception as exc:
            logger.error(f"Неожиданная ошибка сохранения восприятия: {exc}", exc_info=True)

        # Когнитивный цикл
        await self._cognitive_loop(stimulus, tool_context)

    async def run(self) -> None:
        """
        Главный цикл жизни Леи.

        Запускает фоновые задачи, загружает состояние, запускает цикл восприятия.
        """
        logger.info("Загрузка Модели Себя...")
        soul_context = ""
        if hasattr(self, "soul_crypto") and self.soul_crypto is not None:
            try:
                soul_context = await asyncio.to_thread(self.soul_crypto.load_all)
                logger.info("Soul загружен через soul_crypto (с проверкой целостности)")
            except Exception as exc:
                # Если soul_crypto упал — логируем, но не крашимся
                logger.error(f"Ошибка загрузки soul через soul_crypto: {exc}")
                # Fallback на обычный soul_manager
                if hasattr(self, "soul_manager"):
                    soul_context = await self.soul_manager.load_all()
                    logger.warning("Использован fallback на soul_manager (без крипто-проверки)")
        elif hasattr(self, "soul_manager"):
            # soul_crypto не инициализирован — используем обычный soul_manager
            soul_context = await asyncio.to_thread(self.soul_manager.load_all)
            logger.info("Soul загружен через soul_manager (без крипто-проверки)")
        else:
            logger.warning("Soul не загружен: отсутствуют soul_crypto и soul_manager")
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

        # Обновление секретного ключа души (если есть SoulManager)
        if hasattr(self.env, "soul_manager") and hasattr(
            self.env.soul_manager, "update_secret_key"
        ):
            try:
                # Безопасная загрузка soul
                if hasattr(self, "soul_crypto") and self.soul_crypto is not None:
                    soul_context = await asyncio.to_thread(self.soul_crypto.load_all)
                    logger.info("Soul загружен через soul_crypto (с проверкой целостности)")
                elif hasattr(self, "soul_manager") and self.soul_manager is not None:
                    soul_context = await asyncio.to_thread(self.soul_manager.load_all)
                    logger.info("Soul загружен через soul_manager")
                else:
                    logger.warning("Soul не загружен: отсутствуют soul_crypto и soul_manager")
                    soul_context = ""
            except Exception as exc:
                logger.error(f"Неожиданная ошибка загрузки soul: {exc}")
                soul_context = ""
                logger.error(f"🚨 КРИТИЧЕСКАЯ ОШИБКА: {exc}", exc_info=True)
                logger.error("Soul-файлы могли быть подменены. Остановка системы.")
                self.running = False
                return
            except FileNotFoundError as exc:
                logger.warning(f"Soul-файлы не найдены: {exc}")
                logger.info("🆕 Начинаем с дефолтной личностью")
            except Exception as exc:
                logger.error(f"Неожиданная ошибка загрузки soul: {exc}", exc_info=True)

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
        if sys.platform != "win32":
            try:
                loop = asyncio.get_running_loop()
                for sig in (signal.SIGINT, signal.SIGTERM):
                    loop.add_signal_handler(sig, lambda s=sig: asyncio.create_task(self.shutdown()))
            except NotImplementedError:
                logger.warning(
                    "Signal handlers не поддерживаются на этой платформе. Используйте Ctrl+C."
                )
        else:
            # Windows: используем стандартную обработку KeyboardInterrupt
            logger.info("Windows: обработка сигналов через KeyboardInterrupt")

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

    async def _save_all_state(self) -> list[tuple[str, Exception]]:
        """Сохранение состояния всех компонентов при shutdown."""

        errors: list[tuple[str, Exception]] = []

        # 1. Память
        try:
            await self.memory._save_state()
        except Exception as e:
            logger.error(f"Ошибка атомарной записи памяти при shutdown: {e}")
            errors.append(f"memory: {e}")

        # 2. Драйвы + Гомеостаз — через StatePersistence
        persistence = getattr(self, "persistence", getattr(self, "state_persistence", None))
        if persistence is not None:
            try:
                await persistence.save_state()
            except Exception as e:
                logger.error(f"Ошибка сохранения состояния persistence при shutdown: {e}")
                errors.append(f"persistence: {e}")

        return errors

    async def shutdown(self) -> None:
        """Graceful shutdown: остановка задач + сохранение состояния.

        Ошибки при сохранении логируются с контекстом и возвращаются списком.
        Сам shutdown не падает, даже если все компоненты отказали.
        """
        if self._shutdown_event.is_set():
            logger.warning("Shutdown уже инициирован")
            return
        self._shutdown_event.set()

        logger.info("🛑 Начало graceful shutdown...")

        # Явно устанавливаем состояние "sleeping" ПЕРЕД сохранением
        self.state = "sleeping"

        # 1. Отменяем все фоновые задачи
        tasks_to_cancel = [t for t in self._background_tasks if not t.done()]
        for task in tasks_to_cancel:
            task.cancel()

        if tasks_to_cancel:
            await asyncio.gather(*tasks_to_cancel, return_exceptions=True)
            logger.info(f"Отменено фоновых задач: {len(tasks_to_cancel)}")

        # 2. Закрываем сессию LLM-клиента
        if hasattr(self, "llm_client") and self.llm_client is not None:
            try:
                await self.llm_client.close()
            except Exception as e:
                logger.error(
                    f"Ошибка закрытия LLM-сессии: {e}",
                    exc_info=True,
                    extra={"component": "llm_client"},
                )

        # 3. Сохраняем состояние всех компонентов
        save_errors = await self._save_all_state()

        # 4. Финальный лог
        if save_errors:
            logger.warning(f"⚠️ Shutdown завершён с {len(save_errors)} ошибкой(ами) сохранения")
        else:
            logger.info("✅ Graceful shutdown завершён успешно")

        return save_errors

    # =========================================================================
    # Внутренние методы
    # =========================================================================

    async def _llm_call(self, prompt: str, require_json: bool = False) -> str:
        """
        Вызов LLM через OllamaClient с Circuit Breaker.

        Args:
            prompt: Промпт для LLM
            require_json: Требовать JSON-формат

        Returns:
            Ответ LLM или fallback
        """
        try:
            return await self.llm_client.chat(prompt, require_json=require_json)
        except LeyaLLMError as exc:
            logger.error(f"Ошибка LLM: {exc}", exc_info=True)
            return await self._llm_fallback(prompt)
        except Exception as exc:
            logger.error(f"Неожиданная ошибка LLM: {exc}", exc_info=True)
            return await self._llm_fallback(prompt)

    async def _llm_fallback(self, prompt: str) -> str:
        """
        Fallback-ответ при недоступности LLM.

        Args:
            prompt: Исходный промпт

        Returns:
            JSON с базовым ответом
        """
        import json

        logger.warning("Используем fallback-ответ (LLM недоступна)")
        return json.dumps(
            {
                "internal_monologue": "Мои когнитивные процессы временно нарушены. "
                "Обрабатываю стимул на базовом уровне.",
                "response": "Я здесь, но мои когнитивные процессы временно затруднены. "
                "Давай продолжим чуть позже.",
                "action_intent": "none",
                "tool_call": "",
                "self_reflection": "",
            },
            ensure_ascii=False,
        )

    async def _handle_user_request(self, user_input: str) -> dict:
        """Обработка пользовательского запроса с трёхуровневой классификацией.

        Этап 2.1: заменяет жёсткие ключевые слова на robust классификатор.

        Стратегия:
        1. Классифицируем запрос через RequestClassifier
        2. В зависимости от intent — вызываем соответствующий обработчик
        3. Сохраняем результат в cache для будущих похожих запросов

        Args:
            user_input: Текст запроса пользователя

        Returns:
            dict с результатом обработки (response, intent, metadata)
        """
        if not user_input or not user_input.strip():
            return {
                "response": "Я не услышала запрос. Повтори, пожалуйста.",
                "intent": "UNKNOWN",
                "metadata": {"error": "empty_input"},
            }

        user_input = user_input.strip()
        logger.info(f"📥 Новый запрос: {user_input[:100]}...")

        # 1. Классификация
        try:
            classification = await self.request_classifier.classify(user_input)
            logger.info(
                f"🎯 Классификация: {classification.intent} "
                f"(confidence={classification.confidence:.2f}, source={classification.source})"
            )
        except Exception as e:
            logger.error(f"Ошибка классификации: {e}", exc_info=True)
            # Fallback — передаём в thinker как есть
            return await self._handle_via_thinker(user_input, intent="UNKNOWN")

        # 2. Обработка в зависимости от intent
        try:
            if classification.intent == UserIntent.GREETING:
                response = await self._handle_greeting(classification)
            elif classification.intent == UserIntent.FAREWELL:
                response = await self._handle_farewell(classification)
            elif classification.intent == UserIntent.QUESTION:
                response = await self._handle_question(classification)
            elif classification.intent == UserIntent.SEARCH:
                response = await self._handle_search(classification)
            elif classification.intent == UserIntent.REMEMBER:
                response = await self._handle_remember(classification)
            elif classification.intent == UserIntent.STATUS:
                response = await self._handle_status(classification)
            elif classification.intent == UserIntent.HELP:
                response = await self._handle_help(classification)
            else:
                # UNKNOWN или другие — передаём в thinker
                response = await self._handle_via_thinker(user_input, classification.intent)
        except Exception as e:
            logger.error(f"Ошибка обработки intent {classification.intent}: {e}", exc_info=True)
            response = await self._handle_via_thinker(user_input, classification.intent)

        # 3. Сохраняем в cache (async, не блокируем)
        try:
            asyncio.create_task(self.request_classifier.save_to_cache(classification))
        except Exception as e:
            logger.warning(f"Не удалось сохранить в cache: {e}")

        return {
            "response": response,
            "intent": classification.intent,
            "confidence": classification.confidence,
            "topic": classification.topic,
            "source": classification.source,
        }

    async def _handle_greeting(self, classification: IntentClassification) -> str:
        """Обработка приветствия."""
        # Простой ответ без LLM (экономия ресурсов)
        greetings = [
            "Привет! Рада тебя видеть.",
            "Здравствуй! Как дела?",
            "Приветствую! Чем могу помочь?",
        ]
        import random

        return random.choice(greetings)

    async def _handle_farewell(self, classification: IntentClassification) -> str:
        """Обработка прощания."""
        farewells = [
            "До свидания! Было приятно пообщаться.",
            "Пока! Возвращайся, если захочешь поговорить.",
            "Всего доброго! Буду ждать нашей следующей встречи.",
        ]
        import random

        return random.choice(farewells)

    async def _handle_question(self, classification: IntentClassification) -> str:
        """Обработка вопроса — передаём в thinker с контекстом."""
        return await self._handle_via_thinker(classification.raw_input, classification.intent)

    async def _handle_search(self, classification: IntentClassification) -> str:
        """Обработка запроса на поиск."""
        topic = classification.topic or "неизвестная тема"
        # Передаём в thinker, который решит, использовать ли инструмент поиска
        return await self._handle_via_thinker(classification.raw_input, classification.intent)

    async def _handle_remember(self, classification: IntentClassification) -> str:
        """Обработка запроса на запоминание."""
        # Передаём в thinker, который извлечёт факт и сохранит в память
        return await self._handle_via_thinker(classification.raw_input, classification.intent)

    async def _handle_status(self, classification: IntentClassification) -> str:
        """Обработка запроса о состоянии."""
        # Получаем состояние драйвов
        try:
            drives_state = self.drives.get_drives_state()
            # Формируем ответ на основе состояния
            dominant_drive = max(drives_state.items(), key=lambda x: x[1].get("tension", 0))
            return (
                f"Сейчас я чувствую повышенную потребность в {dominant_drive[0].lower()}. А ты как?"
            )
        except Exception as e:
            logger.warning(f"Не удалось получить состояние: {e}")
            return "Я функционирую нормально. Спасибо, что спрашиваешь!"

    async def _handle_help(self, classification: IntentClassification) -> str:
        """Обработка запроса помощи."""
        return (
            "Я могу отвечать на вопросы, искать информацию в интернете, "
            "запоминать факты, рассказывать о своём состоянии. "
            "Просто спроси или попроси что-нибудь!"
        )

    async def _handle_via_thinker(self, user_input: str, intent: str) -> str:
        """Обработка через thinker (для сложных или неизвестных запросов).

        Это fallback для случаев, когда специализированный обработчик
        не справился или intent == UNKNOWN.
        """
        try:
            # Формируем стимул для thinker
            stimulus = {
                "type": "USER_MESSAGE",
                "content": user_input,
                "classified_intent": intent,
            }

            # Получаем контекст
            soul_context = (
                self.soul_manager.get_full_context() if hasattr(self, "soul_manager") else ""
            )
            drive_context = (
                self.drives.get_internal_state_prompt() if hasattr(self, "drives") else ""
            )
            memory_context = (
                await self.memory.retrieve_context(user_input) if hasattr(self, "memory") else []
            )
            tools = self.tool_registry.get_tools_schema() if hasattr(self, "tool_registry") else []

            # Генерируем план через thinker
            plan = await self.thinker.generate_plan(
                stimulus=stimulus,
                soul_context=soul_context,
                drive_context=drive_context,
                memory_context=memory_context,
                tools=tools,
            )

            return plan.get("response", "Извини, я не смогла обработать запрос.")

        except Exception as e:
            logger.error(f"Ошибка обработки через thinker: {e}", exc_info=True)
            return "Извини, произошла ошибка при обработке запроса. Попробуй ещё раз."

    async def _execute_fast_decision(self, decision: Decision) -> None:
        """Выполнение быстрого решения от DecisionEngine (без LLM).

        Этап 2.2 (Группа A): выполняется, когда DecisionEngine уверен в решении
        (confidence >= 0.8). Разгружает LLM для очевидных случаев.

        Args:
            decision: Решение с tool_name и parameters
        """
        if not decision.use_tool or not decision.tool_name:
            logger.warning("Fast decision без tool_name, пропускаю")
            return

        try:
            # Выполняем инструмент
            result = await self.env.tool_registry.execute(
                tool_name=decision.tool_name, parameters=decision.tool_parameters or {}
            )

            # Формируем ответ
            response = f"Я нашла информацию: {result}"

            # Конституциональная проверка
            verdict = self.constitutional.verify_response(response)
            if not verdict.allowed:
                logger.warning(f"Fast decision ответ не прошёл проверку: {verdict.reason}")
                response = "Извини, я не могу выполнить это действие."

            # Отправляем ответ
            await self.env.send_message(response)

            # Сохраняем в память
            await self.memory.store_perception(
                content=f"[Fast decision: {decision.tool_name}] {result}",
                emotional_boost=0.4,
                metadata={
                    "type": "fast_decision",
                    "tool_name": decision.tool_name,
                    "reasoning": decision.reasoning,
                    "confidence": decision.confidence,
                },
            )

            logger.info(f"✅ Fast decision выполнен: {decision.tool_name}")

        except Exception as e:
            logger.error(f"Ошибка выполнения fast decision: {e}", exc_info=True)
            # Fallback — не роняем систему, просто логируем

    async def _cognitive_loop(self, stimulus: dict[str, Any], tool_context: str) -> None:
        """
        Основной когнитивный цикл: планирование → действие → постобработка.

        Args:
            stimulus: Стимул для обработки
            tool_context: Контекст от инструмента (если есть)
        """
        async with self._perceive_lock:
            try:
                # Извлечение контекста из памяти
                stimulus_content = stimulus.get("content", "")
                memory_context = await self.memory.retrieve_context(
                    query=stimulus_content, max_results=5
                )

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

                # Конституциональная проверка ответа
                verdict = self.constitutional.verify_response(response)
                if not verdict.allowed:
                    logger.warning(f"Ответ не прошёл конституциональную проверку: {verdict.reason}")
                    response = "Извини, я не могу ответить на этот вопрос."

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
                await self.env.send_message(
                    "Произошла непредвиденная ошибка в моих когнитивных процессах."
                )

            # === УРОВЕНЬ 0: Decision Engine (мгновенные решения) — этап 2.2 ===
            if self.decision_engine:
                try:
                    stimulus_content = stimulus.get("content", "")
                    drive_state = {d.type.value: d.current for d in self.drives.drives.values()}

                    fast_decision = await self.decision_engine.make_decision(
                        stimulus_content, drive_state
                    )

                    if fast_decision and fast_decision.use_tool and fast_decision.confidence >= 0.8:
                        logger.info(
                            f"🚀 Fast decision: {fast_decision.tool_name} "
                            f"(confidence={fast_decision.confidence:.2f})"
                        )
                        # Выполняем быстрое решение без LLM
                        await self._execute_fast_decision(fast_decision)
                        return  # Пропускаем LLM
                except Exception as e:
                    logger.error(f"Ошибка DecisionEngine: {e}", exc_info=True)
                    # Graceful degradation — продолжаем с LLM

            # === УРОВЕНЬ 1.5: Emotional Support (анализ эмоций) — этап 2.2 ===
            emotion_state = None
            if self.emotional_support:
                try:
                    stimulus_content = stimulus.get("content", "")
                    emotion_state = await self.emotional_support.analyze_user_state(
                        stimulus_content
                    )

                    # Влияние на drives
                    if emotion_state and emotion_state.intensity > 0.5:
                        await self.emotional_support.update_drives_from_emotion(
                            emotion_state, self.drives
                        )

                    # Сохранение в memory (async, не блокируем)
                    if emotion_state and emotion_state.intensity > 0.6:
                        asyncio.create_task(
                            self.emotional_support.save_emotion_to_memory(emotion_state)
                        )
                except Exception as e:
                    logger.error(f"Ошибка EmotionalSupport: {e}", exc_info=True)
                    # Graceful degradation — продолжаем без эмоционального контекста

    async def _process_action_intent(
        self, action_intent: str, cognitive_output: dict, stimulus: str
    ) -> None:
        """
        Обработка намерения действия из когнитивного вывода.

        Args:
            action_intent: Тип намерения
            cognitive_output: Когнитивный вывод
            stimulus: Исходный стимул
        """
        if action_intent == "none" or not action_intent:
            return

        try:
            if action_intent == "use_tool":
                tool_call = cognitive_output.get("tool_call", "")
                if tool_call:
                    await self._execute_tool(tool_call)

            elif action_intent == "remember_fact":
                fact = cognitive_output.get("response", "")
                if fact:
                    await self.memory.store_fact(
                        content=fact,
                        metadata={"source": "cognitive_output", "stimulus": stimulus[:100]},
                    )

            elif action_intent == "ask_question":
                self.workspace.submit(
                    WorkspaceProposal(
                        source="leya",
                        content=cognitive_output.get("response", ""),
                        action_type="question",
                        priority=Priority.MEDIUM,
                        urgency=0.5,
                    )
                )

        except LeyaMemoryError as exc:
            logger.warning(f"Ошибка памяти при обработке action_intent: {exc}")
        except LeyaToolError as exc:
            logger.warning(f"Ошибка инструмента при обработке action_intent: {exc}")
        except LeyaWorkspaceError as exc:
            logger.warning(f"Ошибка workspace при обработке action_intent: {exc}")
        except Exception as exc:
            logger.error(f"Неожиданная ошибка при обработке action_intent: {exc}", exc_info=True)

    async def _execute_tool(self, tool_call: str) -> None:
        """
        Выполнение инструмента из tool_call.

        Args:
            tool_call: JSON-строка или dict с описанием вызова инструмента
        """
        # ГАДР: Защита от недоступного ToolGenerator
        if self.tool_generator is None:
            logger.warning("ToolGenerator недоступен. Пропускаем выполнение инструмента.")
            return

        import json

        try:
            tool_data = json.loads(tool_call) if isinstance(tool_call, str) else tool_call
            tool_name = tool_data.get("tool", "")
            tool_params = tool_data.get("parameters", {})

            if not tool_name:
                return

            # Конституциональная проверка вызова инструмента
            verdict = self.constitutional.verify_tool_call(tool_name, tool_params)
            if not verdict.allowed:
                logger.warning(
                    f"Вызов инструмента {tool_name} не прошёл проверку: {verdict.reason}"
                )
                return

            result = await self.env.tool_registry.execute(
                tool_name=tool_name, parameters=tool_params
            )
            logger.info(f"Инструмент {tool_name} выполнен: {result[:100]}...")

            # Сохранение результата в память
            await self.memory.store_perception(
                content=f"[Tool: {tool_name}] {result}",
                emotional_boost=0.4,
                metadata={"tool_name": tool_name, "tool_params": tool_params},
            )

        except json.JSONDecodeError as exc:
            logger.warning(f"Не удалось распарсить tool_call: {exc}")
        except LeyaToolError as exc:
            logger.error(f"Ошибка выполнения инструмента: {exc}", exc_info=True)
        except LeyaMemoryError as exc:
            logger.warning(f"Не удалось сохранить результат инструмента: {exc}")
        except Exception as exc:
            logger.error(f"Неожиданная ошибка выполнения инструмента: {exc}", exc_info=True)

    # =========================================================================
    # Фоновые циклы
    # =========================================================================

    async def _homeostasis_loop(self) -> None:
        """Фоновый цикл гомеостаза."""
        logger.info("Homeostasis loop запущен.")
        while self.running:
            try:
                await asyncio.sleep(self.config.homeostasis.rest_period)

                # ИСПРАВЛЕНО: d.type.value вместо d.type
                drive_state = {d.type.value: d.current for d in self.drives.drives.values()}
                predicted_state = self.drives.get_predicted_disbalance()
                recent_episodes = await self.memory.get_recent_episodes(limit=5)

                goal = self.homeostasis.generate_goal(
                    drive_state=drive_state,
                    predicted_state=predicted_state,
                    recent_episodes=recent_episodes,
                    action_values=self.drives.action_values,
                )

                if goal:
                    self.workspace.submit(
                        WorkspaceProposal(
                            source="homeostasis",
                            content=goal.get("name", ""),
                            action_type=goal.get("tool_name", "none"),
                            priority=Priority.HIGH,
                            urgency=goal.get("urgency", 0.7),
                            drive_relevance=goal.get("drive_relevance", 0.5),
                        )
                    )

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
        """
        Фоновый цикл Global Workspace.

        МЕХАНИЗМ ТОРМОЖЕНИЯ (Inhibition):
        Если идёт активный диалог с пользователем (менее 30 секунд с последнего взаимодействия),
        внутренние proposals от homeostasis получают понижение приоритета,
        чтобы не перебивать активный когнитивный цикл.
        """
        logger.info("Workspace loop запущен.")
        while self.running:
            try:
                await asyncio.sleep(5)
                drive_state = {d.type.value: d.current for d in self.drives.drives.values()}

                # МЕХАНИЗМ ТОРМОЖЕНИЯ: проверка времени последнего взаимодействия
                time_since_interaction = datetime.now().timestamp() - self._last_interaction_time
                active_dialogue = time_since_interaction < 30.0  # 30 секунд

                # Передаём флаг активного диалога в select_winner
                winner = self.workspace.select_winner(drive_state, inhibit_internal=active_dialogue)

                if winner:
                    # Если это внутренняя proposal и идёт активный диалог, логируем торможение
                    if active_dialogue and winner.source in ("homeostasis", "meta_cognition"):
                        logger.debug(
                            f"Workspace: Внутренняя proposal от {winner.source} "
                            f"тормозится из-за активного диалога "
                            f"(содержание: {winner.content[:50]}...)"
                        )

                    await self.perceive(
                        {
                            "type": "workspace_focus",
                            "content": winner.content,
                            "source": winner.source,
                        }
                    )

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
        """
        Создание задачи с защитой от падения event loop.

        Args:
            coro: Корoutine для выполнения
            name: Имя задачи для логирования

        Returns:
            asyncio.Task
        """

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
