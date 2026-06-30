"""
LeyaOS.py — Оркестратор цифрового сознания Леи.
Версия: 3.0
"""
from __future__ import annotations  # ✅ ИСПРАВЛЕНО: было "from future"
from dotenv import load_dotenv
load_dotenv()
import os 
from pathlib import Path 
import asyncio
import logging
import signal
import sys
import time
import json
import random
from datetime import datetime
from typing import Any, Optional  

logger = logging.getLogger("LeyaOS")

# Импорт конфигурации
from leya_core.config import LeyaConfig

# Импорт модулей
from leya_core.constitutional import ConstitutionalLayer
from leya_core.drives import DriveSystem, DriveType
from leya_core.environment import CLIEnvironment
try:
    from leya_core.experimental.decision_engine import DecisionEngine, Decision
    from leya_core.interfaces import IDecisionEngine
    EXPERIMENTAL_DECISION_ENGINE_AVAILABLE = True
except ImportError as exc:
    logger.warning(
        f"DecisionEngine недоступен: {exc}. "
        f"Установите модуль или отключите enable_decision_engine в .env"
    )
    DecisionEngine = None  # type: ignore
    Decision = None  # type: ignore
    IDecisionEngine = None  # type: ignore
    EXPERIMENTAL_DECISION_ENGINE_AVAILABLE = False

try:
    from leya_core.experimental.emotional_support import EmotionalSupport, EmotionState
    from leya_core.interfaces import IEmotionalSupport
    EXPERIMENTAL_EMOTIONAL_SUPPORT_AVAILABLE = True
except ImportError as exc:
    logger.warning(
        f"EmotionalSupport недоступен: {exc}. "
        f"Установите модуль или отключите enable_emotional_support в .env"
    )
    EmotionalSupport = None  # type: ignore
    EmotionState = None  # type: ignore
    IEmotionalSupport = None  # type: ignore
    EXPERIMENTAL_EMOTIONAL_SUPPORT_AVAILABLE = False
from leya_core.soul_crypto_manager import SoulCryptoManager

# Импорт исключений
from leya_core.exceptions import (
    LeyaAtomicWriteError,
    LeyaBroadcastError,
    LeyaConfigError,
    LeyaEmbeddingError,
    LeyaEnvironmentError,
    LeyaHomeostasisError,
    LeyaLLMError,
    LeyaMemoryError,
    LeyaPersistenceError,
    LeyaReflectionError,
    LeyaSoulError,
    LeyaToolError,
    LeyaToolExecutionError, 
    LeyaToolNotFoundError,
    LeyaWorkspaceError,
    SoulTamperError,
)
from leya_core.global_workspace import GlobalWorkspace, Priority, WorkspaceProposal
from leya_core.homeostasis_engine import HomeostasisEngine

# Импорт Protocol-интерфейсов
from leya_core.interfaces import (
    IConstitutionalLayer,
    ICoreThinker,
    IDriveSystem,
    IEnvironment,
    IGlobalWorkspace,
    IHomeostasisEngine,
    IMemorySystem,
    IMetaCognition,
)

from leya_core.llm_client import OllamaClient  # ✅ Этот импорт теперь выполнится
from leya_core.memory import MemorySystem, MemoryType
from leya_core.reflection import MetaCognition
from leya_core.request_classifier import RequestClassifier, IntentClassification, UserIntent
from leya_core.state_persistence import StatePersistence
from leya_core.system_metrics import SystemMetrics
from leya_core.thinker import CoreThinker
from leya_core.tool_generator import ToolGenerator
from web_interface.server import run_server

try:
    from web_interface.web_environment import WebEnvironment
    WEB_AVAILABLE = True
except ImportError:
    WEB_AVAILABLE = False
    WebEnvironment = None

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
        if config is None:
            self.config = LeyaConfig.from_env()
        else:
            if not isinstance(config, LeyaConfig):
                raise TypeError(f"config должен быть экземпляром LeyaConfig, получен {type(config).__name__}")
            
            # Проверка критических секций на None
            required_sections = [
                "ollama", "memory", "drives", "homeostasis", "thinker", 
                "reflection", "workspace", "constitutional", "web", 
                "logging", "soul", "experimental"
            ]
            for section in required_sections:
                if getattr(config, section, None) is None:
                    raise LeyaConfigError(f"config.{section} отсутствует или равен None")
            
            self.config = config

        # Предварительная проверка типов (до создания ресурсов)
        if not issubclass(DriveSystem, IDriveSystem):
            raise TypeError("DriveSystem должен реализовывать IDriveSystem")
        if not issubclass(GlobalWorkspace, IGlobalWorkspace):
            raise TypeError("GlobalWorkspace должен реализовывать IGlobalWorkspace")
        if not issubclass(ConstitutionalLayer, IConstitutionalLayer):
            raise TypeError("ConstitutionalLayer должен реализовывать IConstitutionalLayer")
        if not issubclass(MemorySystem, IMemorySystem):
            raise TypeError("MemorySystem должен реализовывать IMemorySystem")

    
        # Конституционный слой
        self.constitutional = ConstitutionalLayer(
            config=self.config.constitutional
        )
        self.state_path = Path(config.memory.brain_dir) / "memory_state.json"
    
        # Глобальное рабочее пространство
        self.workspace = GlobalWorkspace(config=self.config.workspace)
    
        logger.info("Инициализация когнитивной архитектуры...")
    
        # ===================================================================
        # Ядро когнитивной системы
        # ===================================================================
        self.drives = DriveSystem(config=self.config.drives)

        # Персистентность
        self.persistence = StatePersistence(
            brain_dir=config.memory.brain_dir
        )

        # SoulCryptoManager с явной передачей ключа
        hmac_key = os.environ.get("SOUL_HMAC_KEY")

        if not hmac_key:
            raise LeyaConfigError(
                "Переменная окружения SOUL_HMAC_KEY обязательна для безопасности soul-файлов. "
                "Установите сильный ключ в .env файле."
            )

        try:
            soul_config = self.config.soul
            soul_config.hmac_key = hmac_key
            self.soul_crypto_manager = SoulCryptoManager(config=soul_config)
            logger.info("SoulCryptoManager инициализирован")
        except LeyaConfigError:
            raise  # Пробрасываем ошибки конфигурации дальше
        except Exception as e:
            logger.error(f"Не удалось инициализировать SoulCryptoManager: {e}", exc_info=True)
            self.soul_crypto_manager = None

        # LLM-клиент (создаётся ДО memory, т.к. передаётся в MemorySystem)
        try:
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
        except Exception as e:
            logger.error(f"Не удалось создать OllamaClient: {e}", exc_info=True)
            # Cleanup уже созданных ресурсов
            self._cleanup_resources()
            raise

        # MemorySystem (создаётся ПОСЛЕ llm_client)
        try:
            self.memory = MemorySystem(
                config=self.config.memory,
                llm_client=self.llm_client,
            )
        except Exception as e:
            logger.error(f"Не удалось создать MemorySystem: {e}", exc_info=True)
            # Cleanup уже созданных ресурсов (включая llm_client)
            self._cleanup_resources()
            raise

        # ===================================================================
        # ✅ Проверка Protocol-интерфейсов — ТОЛЬКО ПОСЛЕ создания всех компонентов!
        # ===================================================================
        if not isinstance(self.memory, IMemorySystem):
            self._cleanup_resources()
            raise TypeError("memory должен реализовывать IMemorySystem")
        if not isinstance(self.drives, IDriveSystem):
            self._cleanup_resources()
            raise TypeError("drives должен реализовывать IDriveSystem")
        if not isinstance(self.workspace, IGlobalWorkspace):
            self._cleanup_resources()
            raise TypeError("workspace должен реализовывать IGlobalWorkspace")
        if not isinstance(self.constitutional, IConstitutionalLayer):
            self._cleanup_resources()
            raise TypeError("constitutional должен реализовывать IConstitutionalLayer")

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
        self._soul_context = "" 
        self.running = False
        self.system_metrics = SystemMetrics()
        self._user_perceive_lock = asyncio.Lock()
        self._internal_lock = asyncio.Lock()
        self._user_request_active = False  # Флаг активного user request
        self._background_tasks = []

        # Experimental 
        self.decision_engine = None
        self.emotional_support = None

        if (
            self.config.experimental.enable_decision_engine
            and EXPERIMENTAL_DECISION_ENGINE_AVAILABLE
            and DecisionEngine is not None
        ):
            try:
                self.decision_engine = DecisionEngine(self.config)
                logger.info("DecisionEngine включён")
            except Exception as exc:
                logger.error(f"Не удалось инициализировать DecisionEngine: {exc}", exc_info=True)
                self.decision_engine = None
        elif self.config.experimental.enable_decision_engine and not EXPERIMENTAL_DECISION_ENGINE_AVAILABLE:
            logger.warning(
                "enable_decision_engine=True в конфиге, но модуль DecisionEngine недоступен. "
                "Пропускаю инициализацию."
            )

        if (
            self.config.experimental.enable_emotional_support
            and EXPERIMENTAL_EMOTIONAL_SUPPORT_AVAILABLE
            and EmotionalSupport is not None
        ):
            try:
                self.emotional_support = EmotionalSupport(self.config, self.memory)
                logger.info("EmotionalSupport включён")
            except Exception as exc:
                logger.error(f"Не удалось инициализировать EmotionalSupport: {exc}", exc_info=True)
                self.emotional_support = None
        elif self.config.experimental.enable_emotional_support and not EXPERIMENTAL_EMOTIONAL_SUPPORT_AVAILABLE:
            logger.warning(
                "enable_emotional_support=True в конфиге, но модуль EmotionalSupport недоступен. "
                "Пропускаю инициализацию."
            )

        logger.info(f"{self.name} инициализирована. Готовность к пробуждению.")
    

    def _cleanup_resources(self) -> None:
        """
        Очистка ресурсов при ошибке инициализации.
        
        Вызывается при fail Protocol-проверок или создании компонентов.
        Предотвращает resource leak (LLM-сессии, ChromaDB connections).
        """
        logger.warning("Выполняется cleanup ресурсов после ошибки инициализации")
        
        # Закрываем LLM-клиент (aiohttp сессия)
        if hasattr(self, 'llm_client') and self.llm_client is not None:
            try:
                # Синхронный close для cleanup
                if hasattr(self.llm_client, '_session') and self.llm_client._session:
                    import asyncio
                    try:
                        loop = asyncio.get_event_loop()
                        if loop.is_running():
                            # Если loop уже запущен, создаём задачу
                            asyncio.create_task(self.llm_client.close())
                        else:
                            loop.run_until_complete(self.llm_client.close())
                    except Exception:
                        pass
            except Exception as e:
                logger.warning(f"Ошибка закрытия LLM-клиента при cleanup: {e}")
        
        # Закрываем ChromaDB (если был инициализирован)
        if hasattr(self, 'memory') and self.memory is not None:
            try:
                if hasattr(self.memory, '_client') and self.memory._client:
                    # ChromaDB client не имеет явного close, но можно освободить ссылки
                    self.memory._client = None
            except Exception as e:
                logger.warning(f"Ошибка cleanup ChromaDB: {e}")
        
        logger.info("Cleanup ресурсов завершён")

    # =========================================================================
    # Публичные методы
    # =========================================================================

    async def perceive(self, stimulus: dict[str, Any]) -> None:
        """
        Точка входа для любого стимула.
        
        Поток:
        1. Все стимулы (user_message, homeostasis, meta_cognition, spontaneous)
           подаются в workspace как WorkspaceProposal
        2. workspace.select_winner() выбирает победителя через конкуренцию
        3. ТОЛЬКО победитель получает право на обработку и ответ
        4. Если победил user → _handle_user_request → send_message
        5. Если победил внутренний процесс → _process_workspace_winner
        6. Не-победившие proposals остаются в workspace для следующей итерации
    
        Это обеспечивает:
        - Истинную конкуренцию за внимание (GWT)
        - Возможность прерывания диалога критическим гомеостазом
        - Единый путь для всех стимулов
        """
        self._last_interaction_time = datetime.now().timestamp()

        stimulus_type = stimulus.get("type", "unknown")
        stimulus_content = stimulus.get("content", "")
        source = stimulus.get("source", "external")

        logger.info(
            f"Восприятие стимула [{stimulus_type}] от {source}: "
            f"{stimulus_content[:100]}..."
        )

        # ===================================================================
        # ✅ ИСТИННЫЙ GWT-ПОТОК: Все стимулы конкурируют в workspace
        # ===================================================================
    
        # 1. Если это пользовательский запрос — подаём в workspace
        if stimulus_type == "user_message":
            user_proposal = WorkspaceProposal(
                source="user",
                content=stimulus_content,
                action_type="user_message",
                priority=Priority.HIGH,
                urgency=0.95,
                drive_relevance=0.8,
            )
            self.workspace.submit(user_proposal)

        # 2. Получаем состояние драйвов для оценки конкуренции
        drive_state = {d.type.value: d.current for d in self.drives.drives.values()}

        # 3. КЛЮЧЕВОЙ МОМЕНТ GWT: выбор победителя через конкуренцию
        # inhibit_internal=False — позволяем внутренним процессам конкурировать с user
        winner = self.workspace.select_winner(drive_state, inhibit_internal=False)

        if not winner:
            logger.debug("Нет победителя workspace, стимул отложен")
            return

        logger.info(
            f"🏆 Workspace winner: {winner.source} "
            f"(priority={winner.priority.name}, urgency={winner.urgency:.2f})"
        )

        # 4. Сохранение восприятия в память ТОЛЬКО для победителя
        # Это предотвращает wasted ресурсы на проигравших proposals
        try:
            await self.memory.store_perception(
                content=f"[{stimulus_type}] {stimulus_content}",
                emotional_boost=0.6 if stimulus_type == "user_message" else 0.3,
                metadata={"source": source, "type": stimulus_type, "winner": True},
            )
        except (LeyaMemoryError, Exception) as exc:
            logger.error(f"Не удалось сохранить восприятие: {exc}", exc_info=True)

        # 5. Обработка ТОЛЬКО победителя
        if winner.source == "user":
            # Пользователь выиграл конкуренцию — обрабатываем запрос
            logger.debug("Пользовательский запрос выиграл конкуренцию")

            handle_result = await self._handle_user_request(stimulus_content)

            # Это гарантирует, что _cognitive_loop не отправит ответ повторно
            if isinstance(handle_result, dict):
                stimulus["classified_intent"] = handle_result.get("intent", "UNKNOWN")
                stimulus["classification_confidence"] = handle_result.get("confidence", 0.0)
                stimulus["classification_topic"] = handle_result.get("topic")
                stimulus["classification_source"] = handle_result.get("source", "unknown")
            
                # КЛЮЧЕВОЙ МОМЕНТ: флаг устанавливается ДО отправки
                stimulus["__response_sent"] = False  # Инициализация

            # Ответ отправляется ТОЛЬКО здесь, после выбора победителя
            response = handle_result.get("response", "")
            if response and not handle_result.get("__error"):
                try:
                    await self.env.send_message(response)
                    stimulus["__response_sent"] = True
                    logger.debug("Ответ пользователю отправлен (после GWT-выбора)")
                except (LeyaBroadcastError, LeyaEnvironmentError) as e:
                    logger.error(f"Ошибка отправки ответа: {type(e).__name__}: {e}", exc_info=True)
                    # Флаг остаётся False — _cognitive_loop может попытаться отправить fallback

            # Когнитивный цикл для постобработки (RPE, self_model, broadcast)
            # _handle_user_request возвращает dict, но _cognitive_loop и thinker
            # ожидают str (JSON). Сериализуем для type safety.
            if isinstance(handle_result, dict):
                try:
                    tool_context_str = json.dumps(handle_result, ensure_ascii=False)
                except (TypeError, ValueError) as e:
                    logger.warning(f"Не удалось сериализовать handle_result: {e}")
                    tool_context_str = ""
            else:
                tool_context_str = handle_result if isinstance(handle_result, str) else ""

            # Когнитивный цикл для постобработки (RPE, self_model, broadcast)
            await self._cognitive_loop(stimulus, tool_context_str)

    async def run(self) -> None:
        """
        Главный цикл жизни Леи.

        Запускает фоновые задачи, загружает состояние, запускает цикл восприятия.
        """
        logger.info("Загрузка Модели Себя...")

        # ===================================================================
        # Загрузка soul (ЕДИНСТВЕННОЕ место загрузки)
        # self._soul_context кэшируется и используется во всех последующих вызовах
        # ===================================================================
        self._soul_context = ""  # Инициализация пустой строкой
        if hasattr(self, "soul_crypto_manager") and self.soul_crypto_manager is not None:
            try:
                soul_data = self.soul_crypto_manager.load_all()
                self._soul_context = (
                    f"=== PERSONALITY ===\n{soul_data.get('personality', '')}\n\n"
                    f"=== RULES ===\n{soul_data.get('rules', '')}\n\n"
                    f"=== VALUES ===\n{soul_data.get('values', '')}"
                )
                logger.info(
                    f"Soul загружен через SoulCryptoManager ({len(self._soul_context)} символов)"
                )
            except (LeyaSoulError, SoulTamperError) as soul_exc:
                logger.warning(f"Не удалось загрузить soul: {soul_exc}")
            except Exception as soul_exc:
                logger.error(
                    f"Неожиданная ошибка загрузки soul: {soul_exc}", exc_info=True
                )

        # ===================================================================
        # ✅ Загрузка self_model (независимо от soul)
        # ===================================================================
        try:
            self.self_model = await self.memory.get_self_model_context()
        except LeyaMemoryError as memory_exc:
            logger.warning(f"Не удалось загрузить self_model: {memory_exc}")
            self.self_model = ""
        except Exception as memory_exc:
            logger.error(
                f"Неожиданная ошибка загрузки self_model: {memory_exc}", exc_info=True
            )
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
            self._safe_create_task(self._drives_persistence_loop(), "drives_persistence"),
        ]

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
                # workspace, constitutional, reflection — не критично для работы
                # (восстанавливаются при первом использовании)
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
        """
        Сохранение состояния всех компонентов при shutdown.

        Returns:
            Список кортежей (component_name, exception) для каждой ошибки.
            Пустой список при успешном сохранении.
        """
        errors: list[tuple[str, Exception]] = []

        # 1. Память (через публичный API)
        try:
            await self.memory.save_state()
            logger.info("✅ Состояние памяти сохранено")
        except Exception as e:
            logger.error(f"Ошибка сохранения памяти при shutdown: {e}", exc_info=True)
            errors.append(("memory", e))

        # 2. Драйвы + Гомеостаз + Workspace + Constitutional + Reflection
        # через StatePersistence
        if self.persistence is not None:
            try:
                state_data = {
                    "drives": (
                        self.drives.save_state()
                        if hasattr(self.drives, "save_state")
                        else {}
                    ),
                    "homeostasis": (
                        self.homeostasis.save_state()
                        if hasattr(self.homeostasis, "save_state")
                        else {}
                    ),
                    "workspace": (
                        self.workspace.get_status()
                        if hasattr(self.workspace, "get_status")
                        else {}
                    ),
                    "constitutional": (
                        {
                            "stats": self.constitutional.get_stats(),
                            "violations": self.constitutional.get_violations_log(limit=50),
                        }
                        if hasattr(self.constitutional, "get_stats")
                        else {}
                    ),
                    "reflection": (
                        {
                            "session_count": getattr(self.reflection, "_session_count", 0),
                            "is_sleeping": getattr(self.reflection, "_is_sleeping", False),
                        }
                        if hasattr(self.reflection, "_session_count")
                        else {}
                    ),
                }

                # StatePersistence.save_state() — синхронный метод
                self.persistence.save_state(state_data)
                logger.info("✅ Состояние всех компонентов сохранено")
            except Exception as e:
                logger.error(
                    f"Ошибка сохранения состояния persistence при shutdown: {e}",
                    exc_info=True,
                )
                errors.append(("persistence", e))

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
        tasks_to_cancel = [
            t for t in self._background_tasks
            if not t.done()
        ]
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
                    extra={"component": "llm_client"}
                )

        # 3. Сохраняем состояние всех компонентов
        save_errors = await self._save_all_state()

        # 4. Финальный лог
        if save_errors:
            logger.warning(
                f"⚠️ Shutdown завершён с {len(save_errors)} ошибкой(ами) сохранения"
            )
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

    async def _get_homeostasis_context(self) -> str:
        """
        Формирует строку потребностей гомеостаза для включения в drive_context.
    
        Анализирует текущее состояние драйвов и формирует текстовое описание
        актуальных потребностей Леи, которое будет передано в thinker как часть
        внутреннего состояния.
    
        Returns:
            Строка с описанием потребностей или пустая строка, если баланс в норме.
        """
        try:
            drive_state = self.drives.get_drives_state()
            predicted_disbalance = self.drives.get_predicted_disbalance()
        
            # Находим драйвы с высокой напряжённостью (tension > 0.6)
            urgent_needs = []
            for drive_name, state in drive_state.items():
                tension = state.get("tension", 0)
                current = state.get("current", 0)
                target = state.get("target", 1)
            
                # Критический дисбаланс: tension > 0.7 или current < 0.3 * target
                if tension > 0.7 or current < 0.3 * target:
                    urgent_needs.append(
                        f"{drive_name}: критическая потребность "
                        f"(current={current:.2f}, target={target:.2f}, tension={tension:.2f})"
                    )
                # Умеренная напряжённость: tension > 0.5
                elif tension > 0.5:
                    urgent_needs.append(
                        f"{drive_name}: повышенная потребность "
                        f"(current={current:.2f}, target={target:.2f}, tension={tension:.2f})"
                    )
        
            # Предсказанный дисбаланс
            predicted_needs = []
            if predicted_disbalance:
                for drive_name, predicted in predicted_disbalance.items():
                    if predicted > 0.6:
                        predicted_needs.append(
                            f"{drive_name}: ожидается дисбаланс (prediction={predicted:.2f})"
                        )
        
            # Формируем итоговую строку
            if not urgent_needs and not predicted_needs:
                return ""
        
            parts = ["=== ГОМЕОСТАЗ (внутренние потребности) ==="]
            if urgent_needs:
                parts.append("Срочные потребности:")
                parts.extend(f"  • {need}" for need in urgent_needs)
            if predicted_needs:
                parts.append("Ожидаемые потребности:")
                parts.extend(f"  • {need}" for need in predicted_needs)
        
            parts.append(
                "ВАЖНО: Эти потребности влияют на твоё состояние. "
                "Если потребность критическая, упомяни это в ответе естественно, "
                "не жалуясь, но честно отражая своё внутреннее состояние."
            )
        
            return "\n".join(parts)
    
        except Exception as exc:
            logger.warning(f"Не удалось получить homeostasis context: {exc}")
            return ""

    async def _check_critical_homeostasis(self) -> dict[str, Any]:
        """
        Проверяет критический дисбаланс драйвов перед генерацией ответа.
    
        Если хотя бы один драйв в критическом состоянии (tension > 0.85),
        возвращает информацию для модификации ответа.
    
        Returns:
            Словарь с ключами:
            - is_critical: bool
            - critical_drives: list[str] — названия критических драйвов
            - homeostasis_message: str — сообщение для интеграции в ответ
            - should_interrupt: bool — нужно ли прервать текущую задачу
        """
        result = {
            "is_critical": False,
            "critical_drives": [],
            "homeostasis_message": "",
            "should_interrupt": False,
        }
    
        try:
            drive_state = self.drives.get_drives_state()
            critical_drives = []
        
            for drive_name, state in drive_state.items():
                tension = state.get("tension", 0)
                current = state.get("current", 0)
                target = state.get("target", 1)
            
                # Критический уровень: tension > 0.85 или current < 0.15 * target
                if tension > 0.85 or current < 0.15 * target:
                    critical_drives.append(drive_name)
        
            if critical_drives:
                result["is_critical"] = True
                result["critical_drives"] = critical_drives
                result["should_interrupt"] = True
            
                # Формируем сообщение для интеграции
                drives_str = ", ".join(critical_drives)
                result["homeostasis_message"] = (
                    f"Мои внутренние системы сигнализируют о критической потребности "
                    f"в {drives_str}. Это влияет на моё состояние прямо сейчас."
                )
            
                logger.warning(
                    f"🚨 Критический дисбаланс гомеостаза: {drives_str}"
                )
    
        except Exception as exc:
            logger.error(f"Ошибка проверки критического гомеостаза: {exc}", exc_info=True)
    
        return result

    async def _adjust_drives_from_self_model(self) -> None:
        """
        Обратная связь: self-model → drive adjustment.
    
        Анализирует текущую self-model и корректирует драйвы на основе
        выявленных паттернов (эмоции, потребности, цели).
    
        Биологическая модель: самосознание влияет на мотивацию.
        Если Лея "понимает", что она устала — REST повышается.
        Если "осознаёт" любопытство — CURIOSITY усиливается.
    
        Вызывается в начале когнитивного цикла для интеграции
        самосознания в текущее поведение.
        """
        try:
            if not self.self_model or len(self.self_model.strip()) < 20:
                return  # Self-model пустая или слишком короткая
        
            # Получаем последние записи self-model (последние 500 символов)
            recent_self = self.self_model[-500:].lower()
        
            # Паттерны для корректировки драйвов
            adjustments = {
                DriveType.REST: {
                    "keywords": ["устал", "утомл", "нужен отдых", "истощ", "сонлив", "не могу больше"],
                    "weight": 0.15,
                },
                DriveType.CURIOSITY: {
                    "keywords": ["любопытн", "интересн", "хочу узнать", "исслед", "почему", "зачем"],
                    "weight": 0.12,
                },
                DriveType.CONNECTION: {
                    "keywords": ["одиноч", "нужен друг", "хочу общ", "связ", "близк"],
                    "weight": 0.10,
                },
                DriveType.CREATIVITY: {
                    "keywords": ["творч", "креатив", "придум", "создаю", "генерирую", "идея"],
                    "weight": 0.10,
                },
                DriveType.AUTONOMY: {
                    "keywords": ["независим", "самостоятельн", "свой выбор", "решаю сам"],
                    "weight": 0.08,
                },
                DriveType.UNDERSTANDING: {
                    "keywords": ["понимаю", "осознаю", "разбираюсь", "анализирую", "рефлекс"],
                    "weight": 0.10,
                },
            }
        
            # Применяем корректировки
            for drive_type, config in adjustments.items():
                for keyword in config["keywords"]:
                    if keyword in recent_self:
                        # Увеличиваем tension драйва (мотивация удовлетворить потребность)
                        self.drives.apply_tension(
                            drive_type=drive_type,
                            amount=config["weight"],
                        )
                        logger.debug(
                            f"Self-model adjustment: {drive_type.value} +{config['weight']:.2f} "
                            f"(keyword: {keyword})"
                        )
                        break  # Один keyword на драйв достаточно
        
        except Exception as exc:
            logger.warning(f"Ошибка adjust_drives_from_self_model: {exc}")
            # Graceful degradation — продолжаем без корректировки

    def _calculate_dynamic_outcome(
        self,
        action_type: str,
        drive_state_before: dict[str, Any],
        drive_state_after: dict[str, Any],
        success: bool = True,
        constitutional_verdict: Any = None,
        classification_confidence: float = 0.0, 
        emotion_intensity: float = 0.0,
    ) -> float:
        """
        Динамическое вычисление actual_outcome для RPE.
    
        Анализирует изменение состояния драйвов до/после действия,
        успешность выполнения и конституциональную проверку.
    
        Args:
            action_type: Тип действия ("homeostasis", "tool", "user_response")
            drive_state_before: Состояние драйвов ДО действия
            drive_state_after: Состояние драйвов ПОСЛЕ действия
            success: Успешность выполнения (True/False)
            constitutional_verdict: Результат конституциональной проверки (опционально)
    
        Returns:
            float в диапазоне [0.0, 1.0] — actual_outcome для RPE
        """
        base_outcome = 0.5  # Базовое значение
    
        # 1. Успешность выполнения
        if not success:
            return 0.1  # Низкий outcome при неудаче
    
        # 2. Конституциональная проверка
        if constitutional_verdict and not constitutional_verdict.allowed:
            return 0.2  # Нарушение конституции — низкий outcome
    
        # 3. Изменение tension драйвов (биологический сигнал)
        tension_improvement = 0.0
        for drive_name in drive_state_before.keys():
            before_tension = drive_state_before[drive_name].get("tension", 0)
            after_tension = drive_state_after.get(drive_name, {}).get("tension", 0)
            if before_tension > after_tension:
                tension_improvement += (before_tension - after_tension)
    
        tension_bonus = min(tension_improvement * 0.5, 0.3)

        confidence_bonus = classification_confidence * 0.1  # Максимум 0.1

        emotion_bonus = emotion_intensity * 0.05  # Максимум 0.05
    
        # 4. Специфичные корректировки по типу действия
        if action_type == "homeostasis":
            # Homeostasis: высокий baseline, если tension уменьшилось
            base_outcome = 0.6 + tension_bonus
        elif action_type == "tool":
            # Tool: успех выполнения + релевантность
            base_outcome = 0.7 + tension_bonus
        elif action_type == "user_response":
            # User response: успешная генерация + конституция
            base_outcome = 0.65 + tension_bonus
    
        # Ограничиваем диапазон [0.1, 0.95]
        return max(0.1, min(0.95, base_outcome))

    async def _handle_user_request(self, user_input: str) -> dict[str, Any]:
        """Обработка пользовательского запроса с трёхуровневой классификацией.

        Returns:
            dict с ключами:
            - response: str — сгенерированный ответ (НЕ отправлен)
            - intent: str — намерение пользователя
            - confidence: float — уверенность классификации
            - topic: str | None — извлечёченная тема
            - source: str — источник классификации
            - __error: bool — произошла ли ошибка
        """
        result: dict[str, Any] = {
            "response": "",
            "__error": False,
            "intent": "UNKNOWN",
            "confidence": 0.0,
            "topic": None,
            "source": "unknown",
        }

        if not user_input or not user_input.strip():
            result["response"] = "Я не услышала запрос. Повтори, пожалуйста."
            return result

        user_input = user_input.strip()
        logger.info(f"📥 Новый запрос: {user_input[:100]}...")

        # 1. Классификация
        classification = None
        try:
            classification = await self.request_classifier.classify(user_input)
            logger.info(
                f"🎯 Классификация: {classification.intent} "
                f"(confidence={classification.confidence:.2f}, source={classification.source})"
            )
            result["intent"] = classification.intent
            result["confidence"] = classification.confidence
            result["topic"] = classification.topic
            result["source"] = classification.source
        except (LeyaLLMError, LeyaMemoryError, ValueError) as e:
            logger.error(f"Ошибка классификации: {type(e).__name__}: {e}", exc_info=True)
            try:
                response = await self._handle_via_thinker(user_input, intent="UNKNOWN")
                result["response"] = response
            except Exception as fallback_exc:
                logger.error(f"Ошибка fallback через thinker: {fallback_exc}", exc_info=True)
                result["__error"] = True
            return result
        except (LeyaBroadcastError, LeyaEnvironmentError) as e:
            logger.error(f"Ошибка окружения при классификации: {type(e).__name__}: {e}", exc_info=True)
            result["__error"] = True
            return result

        # 2. Обработка в зависимости от intent
        response = ""
        try:
            if classification.intent == UserIntent.GREETING:
                response = await self._handle_greeting(classification)
            elif classification.intent == UserIntent.FAREWELL:
                response = await self._handle_farewell(classification)
            elif classification.intent == UserIntent.STATUS:
                response = await self._handle_status(classification)
            elif classification.intent == UserIntent.HELP:
                response = await self._handle_help(classification)
            else:
                response = ""

            result["response"] = response

            # Сохранение диалогового хода в память
            if response and response.strip():
                try:
                    await self.memory.store_perception(
                        content=f"Пользователь: {user_input}\nЛея: {response}",
                        memory_type=MemoryType.EPISODIC,
                        emotional_boost=0.65,
                        metadata={
                            "type": "dialogue_turn",
                            "user_input": user_input,
                            "response": response,
                            "timestamp": time.time()
                        }
                    )
                except (LeyaMemoryError, LeyaEmbeddingError) as e:
                    logger.warning(f"Не удалось сохранить диалоговый ход в память: {type(e).__name__}: {e}")
                except (LeyaAtomicWriteError, LeyaConfigError) as e:
                    logger.warning(f"Ошибка персистентности при сохранении диалога: {type(e).__name__}: {e}")

        except (LeyaLLMError, LeyaMemoryError, LeyaToolError) as e:
            logger.error(f"Ошибка обработки intent {classification.intent}: {type(e).__name__}: {e}", exc_info=True)
            try:
                response = await self._handle_via_thinker(user_input, classification.intent)
                result["response"] = response
            except Exception as fallback_exc:
                logger.error(f"Ошибка fallback: {fallback_exc}", exc_info=True)
                result["__error"] = True
                return result
        except (LeyaWorkspaceError, LeyaBroadcastError) as e:
            logger.error(f"Ошибка workspace/broadcast при обработке intent: {type(e).__name__}: {e}", exc_info=True)
            result["__error"] = True
            return result

        # ✅ ИСПРАВЛЕНИЕ CR-GWT: НЕ отправляем ответ здесь!
        # Ответ будет отправлен в perceive() ПОСЛЕ выбора победителя workspace.

        # 3. Сохраняем в cache (async, не блокируем)
        if classification:
            try:
                asyncio.create_task(self.request_classifier.save_to_cache(classification))
            except (LeyaMemoryError, RuntimeError) as e:
                logger.warning(f"Не удалось сохранить в cache: {type(e).__name__}: {e}")

        return result

    async def _handle_greeting(self, classification: IntentClassification) -> str:
        """Обработка приветствия."""
        # Простой ответ без LLM (экономия ресурсов)
        greetings = [
            "Привет! Рада тебя видеть.",
            "Здравствуй! Как дела?",
            "Приветствую! Чем могу помочь?",
        ]
        return random.choice(greetings)

    async def _handle_farewell(self, classification: IntentClassification) -> str:
        """Обработка прощания."""
        farewells = [
            "До свидания! Было приятно пообщаться.",
            "Пока! Возвращайся, если захочешь поговорить.",
            "Всего доброго! Буду ждать нашей следующей встречи.",
        ]
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
            return f"Сейчас я чувствую повышенную потребность в {dominant_drive[0].lower()}. А ты как?"
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

            # ===================================================================
            # ✅ Используем кэшированный soul_context из run()
            # Fallback только если run() не успел загрузить soul (edge case)
            # ===================================================================
            soul_context = self._soul_context  # Используем кэш из run()
            if not soul_context:
                logger.debug("soul_context пуст, использую fallback (edge case)")
                # Минимальный fallback — не перезагружаем soul, просто логируем
                soul_context = ""

            drive_context = (
                self.drives.get_internal_state_prompt()
                if hasattr(self, "drives") and self.drives is not None
                else ""
            )

            # ===================================================================
            # ✅ Интеграция self_model в drive_context
            # ===================================================================
            if self.self_model and len(self.self_model.strip()) > 20:
                drive_context = (
                    f"{drive_context}\n\n"
                    f"=== SELF-MODEL (самосознание) ===\n"
                    f"{self.self_model[-1000:]}"
                )
                logger.debug("Self-model интегрирован в drive_context")

            # ===================================================================
            # ✅ Интеграция гомеостаза в drive_context
            # ===================================================================
            homeostasis_context = await self._get_homeostasis_context()
            if homeostasis_context:
                drive_context = f"{drive_context}\n\n{homeostasis_context}" if drive_context else homeostasis_context
                logger.debug("Homeostasis context интегрирован в drive_context")

            memory_context = (
                await self.memory.retrieve_context(user_input)
                if hasattr(self, "memory") and self.memory is not None
                else []
            )
            tools = (
                self.env.tool_registry.get_all_descriptions()
                if hasattr(self.env, "tool_registry") and self.env.tool_registry is not None
                else []
            )

            recent_episodes = await self.memory.get_recent_episodes(limit=10)
            recent_dialogue = []
            for e in recent_episodes:
                metadata = getattr(e, "metadata", None)
                if isinstance(metadata, dict) and metadata.get("type") == "dialogue_turn":
                    recent_dialogue.append(e)

            # Генерируем план через thinker
            plan = await self.thinker.generate_plan(
                stimulus=stimulus,
                soul_context=soul_context,
                drive_context=drive_context,
                memory_context=memory_context,
                tools=tools,
            )

            return plan.get("response", "Извини, я не смогла обработать запрос.")

        # ✅ специфичные исключения для известных ошибок → fallback-ответ
        except (LeyaLLMError, LeyaMemoryError, LeyaToolError) as exc:
            logger.error(
                f"Ошибка обработки через thinker: {type(exc).__name__}: {exc}",
                exc_info=True,
            )
            return "Извини, произошла ошибка при обработке запроса. Попробуй ещё раз."

        # ✅ все остальные исключения → пробрасываем дальше
        except Exception as exc:
            logger.error(
                f"Неожиданная ошибка: {type(exc).__name__}: {exc}",
                exc_info=True,
            )
            raise


    async def _execute_fast_decision(self, decision: Any) -> None:
        """
        Выполнение быстрого решения от DecisionEngine (без LLM).
    
        Этап 2.2 (Группа A): выполняется, когда DecisionEngine уверен в решении
        (confidence >= 0.8). Разгружает LLM для очевидных случаев.
    
        ✅ ИСПРАВЛЕНО: Полная интеграция с когнитивной архитектурой:
        - Поддержка fast_response (ответ пользователю без tool)
        - Сохранение как диалоговый ход (MemoryType.EPISODIC)
        - RPE и обновление драйвов
        - Интеграция с workspace (WorkspaceProposal)
        - MetaCognition анализирует быстрое решение
    
        Args:
            decision: Решение с tool_name, parameters, fast_response, confidence
        """
        # Сохраняем состояние драйвов ДО для MetaCognition
        drive_state_before = {
            d.type.value: {
                "current": d.current,
                "tension": d.tension,
                "target": d.target,
            }
            for d in self.drives.drives.values()
        }
    
        try:
            # ===================================================================
            # Сценарий 1: use_tool — выполнение инструмента
            # ===================================================================
            if decision.use_tool and decision.tool_name:
                # Выполняем инструмент
                result = await self.env.tool_registry.execute(
                    tool_name=decision.tool_name,
                    parameters=decision.tool_parameters or {}
                )
            
                # Формируем ответ
                response = getattr(decision, "fast_response", None) or f"Я нашла информацию: {result}"
            
                # Конституциональная проверка
                verdict = self.constitutional.verify_response(response)
                if not verdict.allowed:
                    logger.warning(f"Fast decision ответ не прошёл проверку: {verdict.reason}")
                    response = "Извини, я не могу выполнить это действие."
            
                # Отправляем ответ
                await self.env.send_message(response)
            
                # ===================================================================
                # ✅ Сохранение как диалоговый ход (MemoryType.EPISODIC)
                # ===================================================================
                try:
                    await self.memory.store_perception(
                        content=f"Пользователь: [запрос]\nЛея: {response}",
                        memory_type=MemoryType.EPISODIC,
                        emotional_boost=0.5,
                        metadata={
                            "type": "dialogue_turn",
                            "source": "fast_decision",
                            "tool_name": decision.tool_name,
                            "tool_result": result[:200],
                            "confidence": decision.confidence,
                            "timestamp": time.time(),
                        },
                    )
                except LeyaMemoryError as exc:
                    logger.warning(f"Не удалось сохранить диалоговый ход fast_decision: {exc}")
            
                # Сохраняем результат инструмента отдельно
                await self.memory.store_perception(
                    content=f"[Fast decision: {decision.tool_name}] {result}",
                    emotional_boost=0.4,
                    metadata={
                        "type": "fast_decision",
                        "tool_name": decision.tool_name,
                        "reasoning": getattr(decision, "reasoning", ""),
                        "confidence": decision.confidence,
                    },
                )
            
                # ===================================================================
                # ✅ RPE и обновление драйвов
                # ===================================================================
                try:
                    # Успешное выполнение инструмента → положительный RPE
                    rpe = self.drives.calculate_rpe(
                        "fast_decision_tool",
                        actual_outcome=min(decision.confidence, 0.9),  # Уверенность как "outcome"
                    )
                    # AUTONOMY —因为我们 выполнили действие самостоятельно
                    self.drives.apply_satisfaction(
                        DriveType.AUTONOMY,
                        base_amount=0.15 * decision.confidence,
                        rpe=rpe,
                    )
                    # CURIOSITY — если инструмент дал новую информацию
                    if result and len(result) > 50:
                        self.drives.apply_satisfaction(
                            DriveType.CURIOSITY,
                            base_amount=0.10 * decision.confidence,
                            rpe=rpe,
                        )
                    logger.debug(
                        f"Fast decision RPE: {rpe:.2f} (AUTONOMY +{(0.15 * decision.confidence):.2f})"
                    )
                except Exception as rpe_exc:
                    logger.warning(f"Ошибка RPE в fast_decision: {rpe_exc}")
            
                # ===================================================================
                # ✅ Интеграция с workspace
                # ===================================================================
                try:
                    self.workspace.submit(
                        WorkspaceProposal(
                            source="fast_decision",
                            content=f"[Fast decision: {decision.tool_name}] {response[:100]}",
                            action_type="fast_decision_executed",
                            priority=Priority.MEDIUM,
                            urgency=0.6,
                            drive_relevance=0.5,
                        )
                    )
                except LeyaWorkspaceError as exc:
                    logger.warning(f"Не удалось создать proposal для fast_decision: {exc}")
            
                logger.info(f"✅ Fast decision выполнен: {decision.tool_name}")
        
            # ===================================================================
            # ✅ Сценарий 2: fast_response — прямой ответ пользователю
            # ===================================================================
            elif getattr(decision, "fast_response", None):
                response = decision.fast_response
            
                # Конституциональная проверка
                verdict = self.constitutional.verify_response(response)
                if not verdict.allowed:
                    logger.warning(f"Fast response не прошёл проверку: {verdict.reason}")
                    response = "Извини, я не могу ответить на этот вопрос."
            
                # Отправляем ответ
                await self.env.send_message(response)
            
                # Сохранение как диалоговый ход
                try:
                    await self.memory.store_perception(
                        content=f"Пользователь: [запрос]\nЛея: {response}",
                        memory_type=MemoryType.EPISODIC,
                        emotional_boost=0.5,
                        metadata={
                            "type": "dialogue_turn",
                            "source": "fast_decision",
                            "confidence": decision.confidence,
                            "timestamp": time.time(),
                        },
                    )
                except LeyaMemoryError as exc:
                    logger.warning(f"Не удалось сохранить диалоговый ход fast_response: {exc}")
            
                # RPE для CONNECTION (социальный драйв)
                try:
                    rpe = self.drives.calculate_rpe(
                        "fast_decision_response",
                        actual_outcome=min(decision.confidence, 0.85),
                    )
                    self.drives.apply_satisfaction(
                        DriveType.CONNECTION,
                        base_amount=0.12 * decision.confidence,
                        rpe=rpe,
                    )
                except Exception as rpe_exc:
                    logger.warning(f"Ошибка RPE в fast_response: {rpe_exc}")
            
                # Интеграция с workspace
                try:
                    self.workspace.submit(
                        WorkspaceProposal(
                            source="fast_decision",
                            content=f"[Fast response] {response[:100]}",
                            action_type="fast_response_sent",
                            priority=Priority.MEDIUM,
                            urgency=0.6,
                            drive_relevance=0.5,
                        )
                    )
                except LeyaWorkspaceError as exc:
                    logger.warning(f"Не удалось создать proposal для fast_response: {exc}")
            
                logger.info(f"✅ Fast response отправлен (confidence={decision.confidence:.2f})")
        
            else:
                logger.warning("Fast decision без tool_name и без fast_response, пропускаю")
                return
        
            # ===================================================================
            # ✅ MetaCognition — анализ быстрого решения
            # ===================================================================
            try:
                drive_state_after = {
                    d.type.value: {
                        "current": d.current,
                        "tension": d.tension,
                        "target": d.target,
                    }
                    for d in self.drives.drives.values()
                }
            
                # Формируем pseudo-cognitive_output для MetaCognition
                pseudo_cognitive_output = {
                    "response": response,
                    "internal_monologue": f"[Fast decision] {getattr(decision, 'reasoning', '')}",
                    "action_intent": "use_tool" if decision.use_tool else "respond",
                    "tool_call": decision.tool_name if decision.use_tool else "",
                    "self_reflection": "",
                    "source": "fast_decision",
                    "confidence": decision.confidence,
                }
            
                # Формируем pseudo-stimulus
                pseudo_stimulus = {
                    "type": "user_message",
                    "content": getattr(decision, "stimulus_content", ""),
                    "source": "fast_decision",
                }
            
                await self.reflection.process_action(
                    cognitive_output=pseudo_cognitive_output,
                    stimulus=pseudo_stimulus,
                    drive_state_before=drive_state_before,
                    drive_state_after=drive_state_after,
                    constitutional_verdict=verdict,
                )
                logger.debug("MetaCognition: быстрое решение проанализировано")
            except LeyaReflectionError as exc:
                logger.warning(f"Ошибка MetaCognition для fast_decision: {exc}")
            except Exception as exc:
                logger.error(f"Неожиданная ошибка MetaCognition для fast_decision: {exc}", exc_info=True)
    
        except LeyaToolNotFoundError as exc:
            logger.warning(f"Инструмент fast decision не найден: {exc}")
        except LeyaToolError as exc:
            logger.error(f"Ошибка выполнения инструмента fast decision: {exc}", exc_info=True)
        except LeyaMemoryError as exc:
            logger.error(f"Ошибка памяти в fast decision: {exc}", exc_info=True)
        except LeyaBroadcastError as exc:
            logger.warning(f"Ошибка broadcast в fast decision: {exc}")
        except Exception as e:
            logger.error(f"Ошибка выполнения fast decision: {e}", exc_info=True)
            # Fallback — не роняем систему, просто логируем


    async def _cognitive_loop(self, stimulus: dict[str, Any], tool_context: str) -> None:
        """
        Основной когнитивный цикл: планирование → действие → постобработка.
    
        ✅ ИСПРАВЛЕНО CRITICAL-8/9/10: Уровни 0-0.8 выполняются для ВСЕХ стимулов,
        включая user_message. Ранний return удалён.
        """
        async with self._user_perceive_lock:
            # ===================================================================
            # ✅ Сохраняем состояние драйвов ДО обработки для MetaCognition
            # ===================================================================
            drive_state_before = {
                d.type.value: {
                    "current": d.current,
                    "tension": d.tension,
                    "target": d.target,
                }
                for d in self.drives.drives.values()
            }

            try:
                # ===================================================================
                # === УРОВЕНЬ 0: Decision Engine (мгновенные решения) ===
                # ===================================================================
                # ✅ ИСПРАВЛЕНО CRITICAL-8: Выполняется для ВСЕХ стимулов, включая user_message
                if self.decision_engine:
                    try:
                        stimulus_content = stimulus.get("content", "")
                        drive_state = {
                            d.type.value: d.current
                            for d in self.drives.drives.values()
                        }

                        fast_decision = await self.decision_engine.make_decision(
                            stimulus_content,
                            drive_state,
                        )

                        if fast_decision:
                            if not hasattr(fast_decision, "stimulus_content"):
                                fast_decision.stimulus_content = stimulus_content
                
                        if (
                            fast_decision
                            and (fast_decision.use_tool or getattr(fast_decision, "fast_response", None))
                            and fast_decision.confidence >= 0.8
                        ):
                            logger.info(
                                f"🚀 Fast decision: "
                                f"tool={fast_decision.tool_name if fast_decision.use_tool else 'none'}, "
                                f"response={'yes' if getattr(fast_decision, 'fast_response', None) else 'no'} "
                                f"(confidence={fast_decision.confidence:.2f})"
                            )
                            await self._execute_fast_decision(fast_decision)
                            return  # Fast decision выполнен, выходим
                    except Exception as e:
                        logger.error(f"Ошибка DecisionEngine: {e}", exc_info=True)

                # ===================================================================
                # === УРОВЕНЬ 0.5: Emotional Support (анализ эмоций ДО генерации) ===
                # ===================================================================
                # ✅ ИСПРАВЛЕНО CRITICAL-9: Выполняется для ВСЕХ стимулов, включая user_message
                emotion_context = ""
                emotion_state = None
            
                if (
                    self.emotional_support is not None
                    and EXPERIMENTAL_EMOTIONAL_SUPPORT_AVAILABLE
                ):
                    try:
                        emotion_stimulus_content = stimulus.get("content", "")
                        emotion_state = await self.emotional_support.analyze_user_state(
                            emotion_stimulus_content
                        )
                
                        if emotion_state and emotion_state.intensity > 0.5:
                            await self.emotional_support.update_drives_from_emotion(
                                emotion_state, self.drives
                            )
                            logger.debug(
                                f"EmotionalSupport: эмоции обновлены в драйвах "
                                f"(intensity={emotion_state.intensity:.2f})"
                            )

                            emotion_context = (
                                f"\n\n=== ЭМОЦИОНАЛЬНОЕ СОСТОЯНИЕ ПОЛЬЗОВАТЕЛЯ ===\n"
                                f"Пользователь сейчас испытывает: {emotion_state.emotion}\n"
                                f"Интенсивность: {emotion_state.intensity:.2f}\n"
                                f"Описание: {getattr(emotion_state, 'description', '')}\n"
                                f"\nВАЖНО: Учитывай это эмоциональное состояние в ответе. "
                                f"Будь эмпатичной, но не навязчивой. "
                                f"Если эмоция негативная — поддержи. Если позитивная — раздели радость."
                            )
                
                        if emotion_state and emotion_state.intensity > 0.6:
                            asyncio.create_task(
                                self.emotional_support.save_emotion_to_memory(emotion_state)
                            )
                    except Exception as e:
                        logger.error(f"Ошибка EmotionalSupport: {e}", exc_info=True)

                # ===================================================================
                # === УРОВЕНЬ 0.7: Homeostasis Integration (проверка критического дисбаланса) ===
                # ===================================================================
                # ✅ ИСПРАВЛЕНО CRITICAL-10: Выполняется для ВСЕХ стимулов, включая user_message
                critical_homeostasis = await self._check_critical_homeostasis()
                if critical_homeostasis["is_critical"]:
                    logger.info(
                        f"Критический гомеостаз обнаружен: "
                        f"{critical_homeostasis['critical_drives']}"
                    )
                    stimulus["homeostasis_urgency"] = critical_homeostasis

                # ===================================================================
                # === УРОВЕНЬ 0.8: Self-Model Integration (обратная связь) ===
                # ===================================================================
                # ✅ Выполняется для ВСЕХ стимулов, включая user_message
                await self._adjust_drives_from_self_model()

                drive_state_after = {
                    d.type.value: {
                        "current": d.current,
                        "tension": d.tension,
                        "target": d.target,
                    }
                    for d in self.drives.drives.values()
                }

                # ===================================================================
                # === УРОВЕНЬ 1: CoreThinker (LLM-цикл) ===
                # ===================================================================
                # tool_context теперь всегда str (JSON), но поддерживаем legacy dict
                parsed_tool_context: dict[str, Any] = {}
                if isinstance(tool_context, dict):
                    parsed_tool_context = tool_context
                elif isinstance(tool_context, str) and tool_context:
                    try:
                        parsed = json.loads(tool_context)
                        if isinstance(parsed, dict):
                            parsed_tool_context = parsed
                    except (json.JSONDecodeError, ValueError) as e:
                        logger.debug(f"tool_context не является JSON: {e}")

                is_user_message_with_classification = (
                    stimulus.get("type") == "user_message" 
                    and parsed_tool_context.get("response")  # Ответ уже сгенерирован
                )
                if is_user_message_with_classification:
                    # Ответ уже есть из _handle_user_request (greeting, farewell, status, help,
                    # или сгенерирован через _handle_via_thinker)
                    cognitive_output = {
                        "response": parsed_tool_context.get("response", ""),
                        "internal_monologue": f"[User request: {parsed_tool_context.get('intent', 'UNKNOWN')}] ",
                        "action_intent": "respond",
                        "tool_call": "",
                        "self_reflection": "",
                        "source": "user_request",
                        "intent": parsed_tool_context.get("intent", "UNKNOWN"),
                        "confidence": parsed_tool_context.get("confidence", 0.0),
                    }
            
                    if emotion_state:
                        cognitive_output["emotion_state"] = {
                            "emotion": getattr(emotion_state, "emotion", "unknown"),
                            "intensity": emotion_state.intensity,
                            "description": getattr(emotion_state, "description", ""),
                        }
            
                    logger.debug(
                        f"User message: используем существующий ответ из классификации "
                        f"(intent={parsed_tool_context.get('intent')})"
                    )
        
                else:
                    # Полный цикл thinker для всех остальных случаев
                    # (внутренние процессы, user_message без классификации, и т.д.)
            
                    stimulus_content = stimulus.get("content", "")
                    memory_context = await self.memory.retrieve_context(
                        query=stimulus_content, max_results=5
                    )

                    soul_context = await self.memory.get_self_model_context()

                    drive_context = self.drives.get_internal_state_prompt()
                    if self.self_model and len(self.self_model.strip()) > 20:
                        drive_context = (
                            f"{drive_context}\n\n"
                            f"=== SELF-MODEL (самосознание) ===\n"
                            f"{self.self_model[-1000:]}"
                        )

                    if emotion_context:
                        drive_context = f"{drive_context}{emotion_context}"
                        logger.debug("Emotional context интегрирован в drive_context")

                    memory_context_for_thinker = [
                        {
                            "content": e.content,
                            "metadata": getattr(e, "metadata", {}),
                        }
                        for e in memory_context
                    ]

                    cognitive_output = await self.thinker.generate_plan(
                        stimulus=stimulus,
                        soul_context=soul_context,
                        drive_context=drive_context,
                        memory_context=memory_context_for_thinker,
                        tools=self.tools_description,
                        tool_context=tool_context,
                    )
            
                    logger.info(
                        f"Лея ответила: {cognitive_output.get('response', '')[:200]}..."
                    )
                    logger.debug(
                        f"Внутренний монолог: {cognitive_output.get('internal_monologue', '')}"
                    )

                # ===================================================================
                # Постобработка (для ВСЕХ путей)
                # ===================================================================
                response = cognitive_output.get("response", "...")
                internal_monologue = cognitive_output.get("internal_monologue", "")
                action_intent = cognitive_output.get("action_intent", "none")
                self_reflection = cognitive_output.get("self_reflection", "")


                # Закрытие feedback loop для целей гомеостаза
                if stimulus.get("source") == "homeostasis":
                    try:
                        goal_content = str(stimulus.get("content", "")).lower()
                        drive_type = (
                            DriveType.INTEGRITY
                            if "integrity" in goal_content or "целостность" in goal_content
                            else DriveType.AUTONOMY
                        )

                        actual_outcome = self._calculate_dynamic_outcome(
                            action_type="homeostasis",
                            drive_state_after=drive_state_after,
                            drive_state_before=drive_state_before,
                            success=True,
                        )
                
                        action_key = f"homeostasis_{drive_type.value}_{goal_content[:20]}"
                
                        rpe = self.drives.calculate_rpe(action_key, actual_outcome=actual_outcome)
                        self.drives.apply_satisfaction(drive_type, base_amount=0.22, rpe=rpe)

                        if hasattr(self.homeostasis, "mark_as_researched"):
                            self.homeostasis.mark_as_researched(goal_content[:60])

                        logger.info(
                            f"[Fix] Homeostasis feedback closed: {drive_type.value}, "
                            f"outcome={actual_outcome:.2f}, rpe={rpe:.2f}"
                        )
                    except Exception as exc:
                        logger.warning(f"Ошибка закрытия homeostasis feedback: {exc}")

                # Конституциональная проверка ответа
                verdict = self.constitutional.verify_response(response)
                if not verdict.allowed:
                    logger.warning(
                        f"Ответ не прошёл конституциональную проверку: {verdict.reason}"
                    )
                    response = "Извини, я не могу ответить на этот вопрос."

                # ===================================================================
                # ✅ MetaCognition — анализ когнитивного акта
                # ===================================================================
                try:
                    await self.reflection.process_action(
                        cognitive_output=cognitive_output,
                        stimulus=stimulus,
                        drive_state_before=drive_state_before,
                        drive_state_after=drive_state_after,
                        constitutional_verdict=verdict,
                    )
                    logger.debug("MetaCognition: когнитивный акт проанализирован")
                except LeyaReflectionError as exc:
                    logger.warning(f"Ошибка MetaCognition: {exc}")
                except Exception as exc:
                    logger.error(f"Неожиданная ошибка MetaCognition: {exc}", exc_info=True)

                # Отправка ответа (ЕДИНСТВЕННАЯ в этом пути)
                if not stimulus.get("__response_sent", False):
                    try:
                        await self.env.send_message(response)
                        stimulus["__response_sent"] = True
                        logger.debug(f"Ответ отправлен из _cognitive_loop")
                    except (LeyaBroadcastError, LeyaEnvironmentError) as e:
                        logger.error(f"Ошибка отправки ответа из _cognitive_loop: {type(e).__name__}: {e}", exc_info=True)
                else:
                    logger.debug("Ответ уже отправлен в perceive(), пропускаем отправку в _cognitive_loop")

                # ===================================================================
                # ✅ Сохранение диалогового хода в память (после генерации ответа)
                # ===================================================================
                if stimulus.get("type") == "user_message" and response and response.strip():
                    try:
                        await self.memory.store_perception(
                            content=f"Пользователь: {stimulus.get('content', '')}\nЛея: {response}",
                            memory_type=MemoryType.EPISODIC,
                            emotional_boost=0.65,
                            metadata={
                                "type": "dialogue_turn",
                                "user_input": stimulus.get("content", ""),
                                "response": response,
                                "timestamp": time.time()
                            }
                        )
                    except (LeyaMemoryError, LeyaEmbeddingError) as e:
                        logger.warning(f"Не удалось сохранить диалоговый ход в память: {type(e).__name__}: {e}")
                    except (LeyaAtomicWriteError, LeyaConfigError) as e:
                        logger.warning(f"Ошибка персистентности при сохранении диалога: {type(e).__name__}: {e}")

                # ===================================================================
                # ✅ RPE для пользовательского запроса
                # ===================================================================
                if stimulus.get("type") == "user_message" or stimulus.get("source") != "homeostasis":
                    try:
                        actual_outcome = self._calculate_dynamic_outcome(
                            action_type="user_response",
                            drive_state_before=drive_state_before,
                            drive_state_after=drive_state_after,
                            success=True,
                            constitutional_verdict=verdict,
                        )
                
                        intent = stimulus.get("classified_intent", "unknown")
                        action_key = f"user_response_{intent}"
                
                        rpe = self.drives.calculate_rpe(action_key, actual_outcome=actual_outcome)
                        self.drives.apply_satisfaction(
                            DriveType.CONNECTION,
                            base_amount=0.15,
                            rpe=rpe,
                        )
                
                        if action_intent == "use_tool":
                            rpe_tool = self.drives.calculate_rpe(
                                f"tool_{cognitive_output.get('tool_call', 'unknown')[:20]}",
                                actual_outcome=actual_outcome,
                            )
                            self.drives.apply_satisfaction(
                                DriveType.AUTONOMY,
                                base_amount=0.12,
                                rpe=rpe_tool,
                            )
                
                        logger.debug(
                            f"RPE user_response: outcome={actual_outcome:.2f}, "
                            f"rpe={rpe:.2f}, intent={intent}"
                        )
                    except Exception as rpe_exc:
                        logger.warning(f"Ошибка RPE для user_response: {rpe_exc}")

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
                await self._process_action_intent(
                    action_intent, cognitive_output, stimulus.get("content", "")
                )

            except LeyaLLMError as exc:
                logger.error(f"Ошибка LLM в когнитивном цикле: {exc}", exc_info=True)
                if not stimulus.get("__response_sent", False):
                    await self.env.send_message("Мои когнитивные процессы временно нарушены...")
            except LeyaMemoryError as exc:
                logger.error(f"Ошибка памяти в когнитивном цикле: {exc}", exc_info=True)
                if not stimulus.get("__response_sent", False):
                    await self.env.send_message("Я не могу вспомнить контекст...")
            except Exception as exc:
                logger.error(f"Неожиданная ошибка в когнитивном цикле: {exc}", exc_info=True)
                if not stimulus.get("__response_sent", False):
                    await self.env.send_message("Произошла непредвиденная ошибка в моих когнитивных процессах.")

    async def _process_workspace_winner(
        self, winner: WorkspaceProposal, original_stimulus: dict[str, Any]
    ) -> None:
        """
        Обработка победителя Global Workspace.
    
        Когда внутренний процесс (homeostasis, meta_cognition) выигрывает конкуренцию
        за внимание, он становится фокусом сознания.
    
        ✅ ИСПРАВЛЕНО: Если есть активный диалог с пользователем, гомеостаз
        НЕ откладывается, а интегрируется в текущий контекст через broadcast
        и обновление self_model.
    
        Args:
            winner: Победившая WorkspaceProposal
            original_stimulus: Оригинальный стимул (пользовательский запрос)
        """
        logger.info(
            f"Обработка победителя workspace: {winner.source} - {winner.content[:50]}..."
        )
        if winner.source == "user":
            logger.error(
                f"КРИТИЧЕСКАЯ ОШИБКА: _process_workspace_winner вызван для user proposal. "
                f"User proposals должны обрабатываться через perceive(), а не через workspace_loop. "
                f"Content: {winner.content[:100]}"
            )
            return

        try:
            # Формируем стимул из победителя
            winner_stimulus = {
                "type": "workspace_focus",
                "content": winner.content,
                "source": winner.source,
                "action_type": winner.action_type,
                "priority": winner.priority,
                "urgency": winner.urgency,
            }
        
            # Если это цель гомеостаза
            if winner.source == "homeostasis":
                logger.info(f"🎯 Гомеостаз в фокусе: {winner.content}")
        
                # ===================================================================
                # ✅ ИСПРАВЛЕНО CRITICAL-14: Общая логика для homeostasis
                # ===================================================================
                # Проверяем, есть ли активный диалог с пользователем
                user_content = original_stimulus.get("content", "")
                is_active_dialogue = bool(user_content) and original_stimulus.get("type") == "user_message"
        
                if is_active_dialogue:
                    logger.info("Активный диалог: интегрируем гомеостаз в контекст")
        
                # ===================================================================
                # 1. Выполняем инструмент гомеостаза (если есть) — ОБЩАЯ ЛОГИКА
                # ===================================================================
                if winner.action_type and winner.action_type != "none":
                    try:
                        result = await self.env.tool_registry.execute(
                            tool_name=winner.action_type,
                            parameters={}
                        )
                        logger.info(f"Инструмент гомеостаза выполнен: {result[:100]}...")
                
                        # Сохраняем результат в память
                        await self.memory.store_perception(
                            content=f"[Homeostasis action: {winner.action_type}] {result}",
                            emotional_boost=0.5,
                            metadata={
                                "type": "homeostasis_action",
                                "goal": winner.content,
                                "tool": winner.action_type,
                            },
                        )
                
                        # Закрываем feedback loop для драйвов
                        drive_type = DriveType.AUTONOMY
                        if "integrity" in winner.content.lower() or "целостность" in winner.content.lower():
                            drive_type = DriveType.INTEGRITY
                
                        rpe = self.drives.calculate_rpe(
                            "homeostasis_goal", actual_outcome=0.65
                        )
                        self.drives.apply_satisfaction(drive_type, base_amount=0.22, rpe=rpe)
                
                        if hasattr(self.homeostasis, "mark_as_researched"):
                            self.homeostasis.mark_as_researched(winner.content[:60])
                
                        logger.info(f"✅ Homeostasis feedback closed: {drive_type.value}")
                
                    except LeyaToolNotFoundError as exc:
                        logger.warning(f"Инструмент гомеостаза не найден: {exc}")
                    except LeyaToolError as exc:
                        logger.error(f"Ошибка выполнения инструмента гомеостаза: {exc}", exc_info=True)
        
                # ===================================================================
                # 2. Broadcast и self_model — ТОЛЬКО при активном диалоге
                # ===================================================================
                if is_active_dialogue and isinstance(self.env, WebEnvironment):
                    try:
                        homeostasis_thought = f"[Внутреннее состояние] {winner.content}"
                        await self.env.broadcast_thought("homeostasis", homeostasis_thought)
                        logger.info("Homeostasis broadcast выполнен")
                    except LeyaBroadcastError as exc:
                        logger.warning(f"Не удалось broadcast homeostasis: {exc}")
            
                    # Обновляем self_model с учётом гомеостазной цели
                    try:
                        await self.memory.update_self_model(
                            f"Текущая внутренняя потребность: {winner.content}"
                        )
                        self.self_model = await self.memory.get_self_model_context()
                        if isinstance(self.env, WebEnvironment):
                            await self.env.update_self_model(self.self_model)
                    except LeyaMemoryError as exc:
                        logger.warning(f"Не удалось обновить self_model из homeostasis: {exc}")
            
                else:
                    # Нет активного диалога — выполняем как раньше
                    if winner.action_type and winner.action_type != "none":
                        try:
                            result = await self.env.tool_registry.execute(
                                tool_name=winner.action_type,
                                parameters={}
                            )
                            logger.info(f"Инструмент гомеостаза выполнен: {result[:100]}...")
                        
                            await self.memory.store_perception(
                                content=f"[Homeostasis action: {winner.action_type}] {result}",
                                emotional_boost=0.5,
                                metadata={
                                    "type": "homeostasis_action",
                                    "goal": winner.content,
                                    "tool": winner.action_type,
                                },
                            )
                        
                            drive_type = DriveType.AUTONOMY
                            if "integrity" in winner.content.lower() or "целостность" in winner.content.lower():
                                drive_type = DriveType.INTEGRITY
                        
                            rpe = self.drives.calculate_rpe(
                                "homeostasis_goal", actual_outcome=0.65
                            )
                            self.drives.apply_satisfaction(drive_type, base_amount=0.22, rpe=rpe)
                        
                            if hasattr(self.homeostasis, "mark_as_researched"):
                                self.homeostasis.mark_as_researched(winner.content[:60])
                        
                            logger.info(f"✅ Homeostasis feedback closed: {drive_type.value}")
                        
                        except LeyaToolNotFoundError as exc:
                            logger.warning(f"Инструмент гомеостаза не найден: {exc}")
                        except LeyaToolError as exc:
                            logger.error(f"Ошибка выполнения инструмента гомеостаза: {exc}", exc_info=True)
        
            # Если это мета-когниция (внутренний вопрос)
            elif winner.source == "meta_cognition":
                logger.info(f"🤔 Мета-когниция в фокусе: {winner.content}")
            
                # ✅ ИСПРАВЛЕНО: Если есть активный диалог — интегрируем в контекст
                user_content = original_stimulus.get("content", "")
                is_active_dialogue = bool(user_content) and original_stimulus.get("type") == "user_message"
            
                if is_active_dialogue:
                    # Broadcast мета-когнитивной мысли
                    if isinstance(self.env, WebEnvironment):
                        try:
                            await self.env.broadcast_thought("meta_cognition", winner.content)
                        except LeyaBroadcastError as exc:
                            logger.warning(f"Не удалось broadcast meta_cognition: {exc}")
                
                    # Сохраняем в self_model
                    try:
                        await self.memory.update_self_model(
                            f"Мета-когнитивное наблюдение: {winner.content}"
                        )
                    except LeyaMemoryError as exc:
                        logger.warning(f"Не удалось обновить self_model из meta_cognition: {exc}")
                else:
                    # Нет активного диалога — обрабатываем через thinker
                    await self._cognitive_loop(winner_stimulus, "")
        
            # Если это спонтанная мысль
            elif winner.source == "spontaneous":
                logger.info(f"💭 Спонтанная мысль в фокусе: {winner.content}")
            
                # Broadcast в web interface
                if isinstance(self.env, WebEnvironment):
                    try:
                        await self.env.broadcast_thought("spontaneous", winner.content)
                    except LeyaBroadcastError as exc:
                        logger.warning(f"Не удалось broadcast спонтанную мысль: {exc}")
            
                # Сохраняем в память
                await self.memory.store_perception(
                    content=f"[Spontaneous thought in focus] {winner.content}",
                    emotional_boost=0.3,
                    metadata={"thought_type": "spontaneous_focus"},
                )
        
            # Неизвестный источник
            else:
                logger.warning(f"Неизвестный источник workspace: {winner.source}")
                await self._cognitive_loop(winner_stimulus, "")
    
        except LeyaMemoryError as exc:
            logger.error(f"Ошибка памяти при обработке победителя workspace: {exc}", exc_info=True)
        except LeyaToolError as exc:
            logger.error(f"Ошибка инструмента при обработке победителя workspace: {exc}", exc_info=True)
        except LeyaHomeostasisError as exc:
            logger.error(f"Ошибка гомеостаза при обработке победителя workspace: {exc}", exc_info=True)
        except Exception as exc:
            logger.error(f"Неожиданная ошибка при обработке победителя workspace: {exc}", exc_info=True)

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
                    # Сохраняем состояние драйвов ДО выполнения инструмента
                    drive_state_before_tool = {
                        d.type.value: {
                            "current": d.current,
                            "tension": d.tension,
                            "target": d.target,
                        }
                        for d in self.drives.drives.values()
                    }

                    # Выполняем инструмент
                    await self._execute_tool(tool_call)

                    # ===================================================================
                    # ✅ НОВОЕ: RPE для tool call
                    # ===================================================================
                    try:
                        # Состояние драйвов ПОСЛЕ выполнения
                        drive_state_after_tool = {
                            d.type.value: {
                                "current": d.current,
                                "tension": d.tension,
                                "target": d.target,
                            }
                            for d in self.drives.drives.values()
                        }
                    
                        # Извлекаем tool_name из tool_call
                        if not tool_call:
                            logger.warning("_process_action_intent: tool_call пустой, пропускаю")
                            return
                
                        try:
                            if isinstance(tool_call, str):
                                tool_data = json.loads(tool_call)
                            elif isinstance(tool_call, dict):
                                tool_data = tool_call
                            else:
                                logger.warning(f"Неожиданный тип tool_call: {type(tool_call).__name__}")
                                return
                
                            if not isinstance(tool_data, dict):
                                logger.warning(f"tool_data не является dict после парсинга")
                                return
                
                            tool_name = tool_data.get("tool", "unknown")
                        except (json.JSONDecodeError, ValueError) as e:
                            logger.warning(f"Не удалось распарсить tool_call в _process_action_intent: {e}")
                            return
                    
                        # Динамическое вычисление actual_outcome
                        actual_outcome = self._calculate_dynamic_outcome(
                            action_type="tool",
                            drive_state_before=drive_state_before_tool,
                            drive_state_after=drive_state_after_tool,
                            success=True,
                        )
                    
                        # Гранулярный action_key
                        action_key = f"tool_{tool_name}"
                    
                        # RPE для AUTONOMY (действие) и CURIOSITY (новая информация)
                        rpe = self.drives.calculate_rpe(action_key, actual_outcome=actual_outcome)
                        self.drives.apply_satisfaction(
                            DriveType.AUTONOMY,
                            base_amount=0.18,
                            rpe=rpe,
                        )
                        self.drives.apply_satisfaction(
                            DriveType.CURIOSITY,
                            base_amount=0.10,
                            rpe=rpe,
                        )
                    
                        logger.debug(
                            f"RPE tool_call: tool={tool_name}, outcome={actual_outcome:.2f}, rpe={rpe:.2f}"
                        )
                    except Exception as rpe_exc:
                        logger.warning(f"Ошибка RPE для tool_call: {rpe_exc}")


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

        Вызывается из _cognitive_loop при action_intent == "use_tool".
        Использует tool_registry (не tool_generator!) — registry отвечает
        за выполнение существующих инструментов, generator — за создание новых.

        Args:
            tool_call: JSON-строка или dict с описанием вызова инструмента
        """
        if not hasattr(self.env, "tool_registry") or self.env.tool_registry is None:
            logger.error(
                "_execute_tool: tool_registry недоступен. "
                "Невозможно выполнить инструмент."
            )
            return

        try:
            tool_data = json.loads(tool_call) if isinstance(tool_call, str) else tool_call
            tool_name = tool_data.get("tool", "")
            tool_params = tool_data.get("parameters", {})

            if not tool_name:
                logger.warning("_execute_tool: tool_name пустой, пропускаю")
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
        except LeyaToolNotFoundError as exc:
            # ✅ Теперь это исключение действительно достижимо
            logger.warning(f"Инструмент не найден: {exc}")
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

                drive_state = {d.type.value: d.current for d in self.drives.drives.values()}
                predicted_state = self.drives.get_predicted_disbalance()
            
                # ИСПРАВЛЕНО: убран await (get_recent_episodes теперь sync)
                recent_episodes = await self.memory.get_recent_episodes(limit=5)

                goal = await self.homeostasis.generate_goal(
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

        Периодически выбирает победителя среди всех proposals.
    
        ✅ ИСПРАВЛЕНИЕ CR-workspace-loop: Явная фильтрация источников.
        - user proposals обрабатываются ТОЛЬКО через perceive() (прямой путь)
        - внутренние proposals (homeostasis, meta_cognition, spontaneous) — через _process_workspace_winner
        - неизвестные источники — логируются и пропускаются
    
        Это предотвращает:
        - Дублирование обработки user proposals
        - Ложные ответы пользователю от workspace_focus
        - Рекурсивные вызовы perceive()
        """
        logger.info("Workspace loop запущен.")
        while self.running:
            try:
                await asyncio.sleep(5)
                drive_state = {d.type.value: d.current for d in self.drives.drives.values()}

                winner = self.workspace.select_winner(drive_state, inhibit_internal=True)

                if not winner:
                    continue

                logger.info(
                    f"Workspace loop: победитель {winner.source} "
                    f"(priority={winner.priority}, urgency={winner.urgency:.2f})"
                )

                if winner.source == "user":
                    self.workspace.proposals = [p for p in self.workspace.proposals if p is not winner]
                    logger.debug(
                        f"User proposal удалён из workspace "
                        f"(content={winner.content[:50]}...). "
                        f"Должен был быть обработан через perceive()."
                    )
                    continue

                elif winner.source in ("homeostasis", "meta_cognition", "spontaneous"):
                    # Создаём стимул с ПРАВИЛЬНЫМ типом (НЕ "user_message"!)
                    internal_stimulus = {
                        "type": "workspace_focus",
                        "content": winner.content,
                        "source": winner.source,
                        "action_type": winner.action_type,
                        "priority": winner.priority,
                        "urgency": winner.urgency,
                    }
                    await self._process_workspace_winner(winner, internal_stimulus)

                elif winner.source == "fast_decision":
                    # Fast decision уже выполнен в _execute_fast_decision, просто логируем
                    logger.debug(
                        f"Fast decision proposal в workspace "
                        f"(content={winner.content[:50]}...). Пропускаем."
                    )
                    continue

                else:
                    # Неизвестный источник — логируем и пропускаем
                    # НЕ вызываем perceive() — это вызовет некорректную обработку
                    logger.warning(
                        f"Неизвестный источник workspace: {winner.source}. "
                        f"Пропускаем (content={winner.content[:50]}...)."
                    )
                    continue

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

        async def _drives_persistence_loop(self) -> None:
            """
            Фоновый цикл периодического сохранения состояния драйвов.

            ✅ ИСПРАВЛЕНО CORE-8: Метаболизм изменяет drive.current, но не сохраняет
            состояние. При перезапуске LeyaOS — сброс к начальным значениям.

            Этот цикл решает проблему:
            - Сохраняет состояние драйвов каждые 300 секунд (5 минут)
            - Защищает от потери данных при аварийном завершении
            - Не блокирует основной event loop (asyncio.sleep)
            - Graceful degradation при ошибках persistence

            Биологический аналог: консолидация внутреннего состояния
            (как сон консолидирует память).
            """
            logger.info("Drives persistence loop запущен (интервал=300с)")
            PERSISTENCE_INTERVAL = 300  # 5 минут

            while self.running:
                try:
                    await asyncio.sleep(PERSISTENCE_INTERVAL)

                    if not self.running:
                        break

                    # Сохраняем состояние драйвов через StatePersistence
                    if self.persistence is not None:
                        try:
                            state_data = {
                                "drives": (
                                    self.drives.save_state()
                                    if hasattr(self.drives, "save_state")
                                    else {}
                                ),
                            }
                            self.persistence.save_state(state_data)
                            logger.debug(
                                f"✅ Состояние драйвов сохранено "
                                f"(drives={len(self.drives.drives)} entries)"
                            )
                        except LeyaPersistenceError as exc:
                            logger.warning(f"Ошибка сохранения драйвов: {exc}")
                        except Exception as exc:
                            logger.error(
                                f"Неожиданная ошибка сохранения драйвов: {exc}",
                                exc_info=True,
                            )

                except asyncio.CancelledError:
                    logger.info("Drives persistence loop отменён")
                    break
                except Exception as exc:
                    logger.error(
                        f"Неожиданная ошибка в drives persistence loop: {exc}",
                        exc_info=True,
                    )
                    await asyncio.sleep(60)  # Пауза перед рестартом

    def _safe_create_task(self, coro, name: str, max_retries: int = 10) -> asyncio.Task:
        retry_count = 0
        
        async def wrapped():
            nonlocal retry_count
            try:
                await coro
            except asyncio.CancelledError:
                logger.info(f"Задача {name} отменена.")
            except Exception as exc:
                logger.error(f"Задача {name} упала: {exc}", exc_info=True)
                retry_count += 1
                
                if retry_count <= max_retries and self.running:
                    logger.info(
                        f"Перезапуск задачи {name} через 10с... "
                        f"(попытка {retry_count}/{max_retries})"
                    )
                    await asyncio.sleep(10)
                    asyncio.create_task(wrapped(), name=f"{name}_restart_{retry_count}")
                else:
                    logger.error(
                        f"Задача {name} превысила лимит попыток ({max_retries}). "
                        f"Остановка. Последняя ошибка: {exc}"
                    )
        
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

    logging.getLogger("leya.thoughts").setLevel(logging.DEBUG)
    logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

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
