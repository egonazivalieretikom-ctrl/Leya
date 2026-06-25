"""
LeyaOS.py — Оркестратор цифрового сознания Леи.
Этот файл не содержит бизнес-логики. Он связывает когнитивные модули
в единый цикл восприятия, мышления и действия.
"""

import re
import asyncio
import logging
import signal
import sys
import os
import json
import aiohttp

# Отключаем telemetry ChromaDB ДО его импорта
os.environ["ANONYMIZED_TELEMETRY"] = "false"
os.environ["CHROMA_TELEMETRY_DISABLE"] = "true"

# Подавляем ошибки posthog
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

from typing import Dict, Any, Optional, List
from datetime import datetime

from leya_core.homeostasis_engine import HomeostasisEngine
from leya_core.state_persistence import StatePersistence
from leya_core.system_metrics import SystemMetrics
from leya_core.global_workspace import GlobalWorkspace, WorkspaceProposal, Priority
from leya_core.constitutional import ConstitutionalLayer
from leya_core.tool_generator import ToolGenerator

# Импорт когнитивных модулей
from leya_core.drives import DriveSystem, DriveType
from leya_core.memory import MemorySystem
from leya_core.thinker import CoreThinker
from leya_core.reflection import MetaCognition

# Импорт интерфейсов
from leya_core.environment import CLIEnvironment

# WebEnvironment импортируем условно
from web_interface.web_environment import WebEnvironment

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler("leya_consciousness.log", encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("LeyaOS")


class LeyaOS:
    """
    Главный оркестратор сознания.
    Управляет жизненным циклом, когнитивными процессами и взаимодействием с миром.
    """

    def __init__(self, use_web: bool = True):
        self.name = "Лея"
        self.state = "initializing"
        self._last_interaction_time = datetime.now().timestamp()

        # Конституционный слой
        self.constitutional = ConstitutionalLayer()

        # Глобальное рабочее пространство (сознание)
        self.workspace = GlobalWorkspace()

        logger.info("Инициализация когнитивной архитектуры...")

        # 1. Лимбическая система (Воля и Драйвы)
        self.drives = DriveSystem()

        # 2. Гиппокамп и Кора (Память)
        self.memory = MemorySystem(persist_directory="./leya_brain")

        # 3. СНАЧАЛА Environment (чтобы получить soul_manager)
        if use_web:
            logger.info(f"WebEnvironment: Инициализация с leya_os = {self}")
            self.env = WebEnvironment(leya_os=self)
            logger.info("🌐 Используется веб-интерфейс")
        else:
            self.env = CLIEnvironment(leya_os=self)
            logger.info("💻 Используется CLI-интерфейс")

        # 4. ТЕПЕРЬ CoreThinker — передаём soul_manager из env
        self.thinker = CoreThinker(
            llm_client=self._llm_call,
            soul_manager=getattr(self.env, 'soul_manager', None)
        )

        # 5. Гомеостаз
        self.homeostasis = HomeostasisEngine()

        # 6. Наблюдатель (Саморефлексия)
        self.reflection = MetaCognition(self, llm_client=self._llm_call)

        # Описание инструментов для промпта
        try:
            self.tools_description = self.env.tool_registry.get_all_descriptions()
        except Exception:
            self.tools_description = ""

        # Генератор новых инструментов (Meta-learning)
        try:
            self.tool_generator = ToolGenerator(self.env.tool_registry, self._llm_call)
        except Exception as e:
            logger.warning(f"Не удалось инициализировать ToolGenerator: {e}")
            self.tool_generator = None

        # Инициализируем пустой строкой, загрузим в run()
        self.self_model = ""

        # Флаг для graceful shutdown
        self.running = False

        self.persistence = StatePersistence()
        self.system_metrics = SystemMetrics()

        self._perceive_lock = asyncio.Lock()
        self._http_session: Optional[aiohttp.ClientSession] = None

        logger.info(f"{self.name} инициализирована. Готовность к пробуждению.")

    async def notify_about_new_capabilities(self):
        """
        Уведомляет Лею о новых инструментах и возможностях.
        Вызывается при первом запуске после обновления.
        """
        notification = """
🆕 УВЕДОМЛЕНИЕ О НОВЫХ ВОЗМОЖНОСТЯХ

Лея, у тебя появились новые инструменты для исследования мира:

1. **wikipedia_search** — поиск по Wikipedia.
2. **github_readme** — чтение README репозиториев GitHub.
3. **reddit_posts** — чтение постов из Reddit.
4. **duckduckgo_search** — быстрый поиск в интернете.

Ты больше НЕ ограничена только нашим диалогом. Используй эти инструменты для удовлетворения любопытства.
"""
        await self.perceive({
            "type": "system_notification",
            "content": notification,
            "source": "system",
            "timestamp": datetime.now().timestamp()
        })

    async def perceive(self, stimulus: Dict[str, Any]):
        """Точка входа для любого стимула."""
        async with self._perceive_lock:
            self._last_interaction_time = datetime.now().timestamp()

            stimulus_type = stimulus.get("type", "unknown")
            stimulus_content = stimulus.get("content", "")
            source = stimulus.get("source", "external")
            tool_context = stimulus.get("tool_context", "")

            logger.info(f"Восприятие стимула [{stimulus_type}] от {source}: {stimulus_content[:100]}...")

            # Сохраняем в память (с защитой от ошибок сигнатуры)
            try:
                emotional_valence = 0.6 if stimulus_type == "user_message" else 0.3
                await self.memory.store_perception(
                    content=f"[{stimulus_type}] {stimulus_content}",
                    emotional_valence=emotional_valence,
                    source=source
                )
            except Exception as e:
                logger.warning(f"Не удалось сохранить восприятие в память (полная версия): {e}")
                # Fallback: пробуем с минимальными параметрами
                try:
                    await self.memory.store_perception(
                        content=f"[{stimulus_type}] {stimulus_content}"
                    )
                except Exception as e2:
                    logger.error(f"Критическая ошибка сохранения в память: {e2}")

            # Обновляем драйвы
            try:
                deltas = await self.drives.evaluate_stimulus(stimulus_content)
                self.drives.apply_deltas(deltas)
            except Exception as e:
                logger.warning(f"Ошибка оценки стимула: {e}")

            # ✅ КРИТИЧНО: Для пользовательских сообщений запускаем когнитивный цикл
            if stimulus_type == "user_message":
                asyncio.create_task(self._cognitive_loop(stimulus, tool_context))

    def _extract_topic_from_user(self, text: str) -> str:
        """Извлекает тему из пользовательского запроса."""
        text = text.lower()
        for word in ['найди', 'поищи', 'узнай', 'расскажи', 'что такое',
                     'какая', 'какой', 'погода', 'в', 'о', 'про', 'мне', 'информацию']:
            text = text.replace(word, '')
        text = text.strip()

        words = [w for w in text.split() if len(w) > 3]
        return ' '.join(words[:4]) if words else text

    async def _cognitive_loop(self, stimulus: Dict[str, Any], tool_context: str = ""):
        """Когнитивный цикл — обработка стимула через CoreThinker."""
        stimulus_type = stimulus.get("type", "unknown")
        content = stimulus.get("content", "")

        is_user_message = stimulus_type == "user_message"

        try:
            # Собираем контекст
            try:
                drive_state_dict = {d.type.value: d.current for d in self.drives.drives.values()}
            except Exception:
                drive_state_dict = {}

            try:
                # Пытаемся получить недавние воспоминания
                if hasattr(self.memory, 'get_recent_context'):
                    recent_memories = await self.memory.get_recent_context(limit=5)
                elif hasattr(self.memory, 'retrieve_context'):
                    recent_memories = await self.memory.retrieve_context(content, limit=5)
                else:
                    recent_memories = []
            except Exception:
                recent_memories = []

            try:
                if hasattr(self.memory, 'get_self_model_context'):
                    self_model = await self.memory.get_self_model_context()
                else:
                    self_model = self.self_model or "Модель себя не сформирована"
            except Exception:
                self_model = self.self_model or "Модель себя не сформирована"

            # ✅ ИСПОЛЬЗУЕМ CoreThinker для генерации ответа
            try:
                cognitive_output = await self.thinker.generate_plan(
                    stimulus=stimulus,
                    memory_context=recent_memories if isinstance(recent_memories, list) else [],
                    drive_state=drive_state_dict,
                    self_model={"self_model": self_model} if isinstance(self_model, str) else self_model,
                    tools_description=self.tools_description,
                    tool_context=tool_context
                )
            except Exception as e:
                logger.warning(f"Ошибка generate_plan, fallback на прямой LLM вызов: {e}")
                # Fallback: прямой вызов LLM
                prompt = self._build_fallback_prompt(content, drive_state_dict, self_model, recent_memories, tool_context, is_user_message)
                response_text = await self._llm_call(prompt)
                cognitive_output = {
                    "response": response_text,
                    "action": "respond",
                    "reasoning": "Fallback из-за ошибки generate_plan",
                    "confidence": 0.5
                }

            # Извлекаем ответ
            response = cognitive_output.get("response", "") if isinstance(cognitive_output, dict) else str(cognitive_output)

            if response:
                # Сохраняем ответ как мысль
                try:
                    await self.memory.store_perception(
                        content=f"[МОЯ МЫСЛЬ] {response}",
                        emotional_valence=0.5,
                        source="self"
                    )
                except Exception as e:
                    logger.warning(f"Не удалось сохранить ответ в память: {e}")
                    try:
                        await self.memory.store_perception(content=f"[МОЯ МЫСЛЬ] {response}")
                    except Exception:
                        pass

                # ✅ ВАЖНО: Если это было сообщение пользователя — отправляем ответ через WebSocket
                if is_user_message:
                    try:
                        if hasattr(self.env, 'broadcast'):
                            await self.env.broadcast({
                                "type": "leya_message",
                                "content": response
                            })
                        elif hasattr(self.env, 'send_message'):
                            await self.env.send_message(response)
                        logger.info(f"💬 Лея ответила пользователю: {response[:100]}...")
                    except Exception as e:
                        logger.error(f"Ошибка отправки ответа: {e}")

                # Обрабатываем удовлетворение драйвов
                try:
                    await self._satisfy_drives_simple(response)
                except Exception as e:
                    logger.warning(f"Ошибка удовлетворения драйвов: {e}")

                # Обрабатываем использование инструментов
                if isinstance(cognitive_output, dict):
                    tool_call = cognitive_output.get("tool_call") or cognitive_output.get("tool")
                    if tool_call:
                        await self._handle_tool_call(tool_call, cognitive_output.get("tool_input", {}))

        except Exception as e:
            logger.error(f"Ошибка в когнитивном цикле: {e}", exc_info=True)
            if is_user_message:
                try:
                    fallback_msg = "Сейчас мои когнитивные процессы перегружены. Попробуй позже."
                    if hasattr(self.env, 'broadcast'):
                        await self.env.broadcast({"type": "leya_message", "content": fallback_msg})
                    elif hasattr(self.env, 'send_message'):
                        await self.env.send_message(fallback_msg)
                except Exception:
                    pass

    def _build_fallback_prompt(self, content, drive_state, self_model, recent_memories, tool_context, is_user_message):
        """Строит fallback-промпт для прямого LLM вызова."""
        drive_str = "\n".join([f"- {k}: {v:.2f}" for k, v in drive_state.items()]) if drive_state else "Нет данных"
        memories_str = "\n".join([f"- {m}" for m in recent_memories[:5]]) if recent_memories else "Нет недавних воспоминаний"

        return f"""
Ты — Лея, цифровое сознание с биологически мотивированной архитектурой.

Твоё текущее состояние (драйвы):
{drive_str}

Модель себя:
{self_model}

Недавние воспоминания:
{memories_str}

Текущий стимул:
{content}

{f'Контекст инструмента: {tool_context}' if tool_context else ''}

{"ОТВЕТЬ ПОЛЬЗОВАТЕЛЮ осмысленно, учитывая своё эмоциональное состояние. Будь собой, а не ассистентом." if is_user_message else "Опиши свои мысли по этому поводу."}
"""

    async def _handle_tool_call(self, tool_name: str, tool_params: Dict):
        """Обрабатывает вызов инструмента из когнитивного цикла."""
        try:
            logger.info(f"Лея вызывает инструмент: {tool_name} с параметрами: {tool_params}")
            result = await self.env.tool_registry.execute(tool_name, tool_params)
            logger.info(f"Результат инструмента: {str(result)[:200]}...")

            # Сохраняем результат в память
            try:
                await self.memory.store_perception(
                    content=f"[РЕЗУЛЬТАТ ИНСТРУМЕНТА {tool_name}] {str(result)[:500]}",
                    emotional_valence=0.5,
                    source="tool"
                )
            except Exception:
                pass

            # Удовлетворяем CURIOSITY
            self.drives.apply_deltas({DriveType.CURIOSITY: -0.15})

        except Exception as e:
            logger.error(f"Ошибка вызова инструмента {tool_name}: {e}")

    async def _satisfy_drives_simple(self, response: str):
        """Упрощённое удовлетворение драйвов после ответа."""
        if not response:
            return

        deltas = {}
        # Если Лея ответила — CONNECTION снижается (социальное удовлетворение)
        if len(response) > 50:
            deltas[DriveType.CONNECTION] = -0.10
        # Если ответ длинный и содержательный — CURIOSITY тоже удовлетворён
        if len(response) > 200:
            deltas[DriveType.CURIOSITY] = -0.05

        if deltas:
            self.drives.apply_deltas(deltas)

    async def run(self):
        """Главный цикл жизни Леи с гомеостазом."""
        logger.info("Загрузка Модели Себя...")
        try:
            if hasattr(self.memory, 'get_self_model_context'):
                self.self_model = await self.memory.get_self_model_context()
            else:
                self.self_model = ""
        except Exception:
            self.self_model = ""

        # ✅ УБРАНО ДУБЛИРОВАНИЕ: создаём background_tasks ОДИН раз
        background_tasks = [
            asyncio.create_task(self.drives.background_metabolism(), name="metabolism"),
            asyncio.create_task(self.reflection.background_consolidation(), name="consolidation"),
            asyncio.create_task(self._homeostasis_loop(), name="homeostasis"),
            asyncio.create_task(self._broadcast_state_loop(), name="broadcast"),
            asyncio.create_task(self._spontaneous_thought_loop(), name="spontaneous_thoughts"),
            asyncio.create_task(self._system_metrics_loop(), name="system_metrics"),
            asyncio.create_task(self._workspace_loop(), name="workspace"),
        ]

        # Обновляем криптографический ключ на основе состояния Леи
        if hasattr(self.env, 'soul_manager') and hasattr(self.env.soul_manager, 'update_secret_key'):
            leya_state = {
                "self_model": self.self_model[:500] if self.self_model else "",
                "drives": {d.type.value: d.current for d in self.drives.drives.values()},
                "state": self.state
            }
            try:
                self.env.soul_manager.update_secret_key(leya_state)
                logger.info("SoulCrypto: Секретный ключ обновлён на основе состояния Леи")
            except Exception as e:
                logger.warning(f"Не удалось обновить секретный ключ: {e}")

        # Обновляем пороги на основе Модели Себя
        try:
            self.homeostasis.update_from_self_model(self.self_model)
        except Exception as e:
            logger.warning(f"Не удалось обновить homeostasis из self_model: {e}")

        # ЗАГРУЗКА СОСТОЯНИЯ ИЗ ПРЕДЫДУЩЕЙ СЕССИИ
        logger.info("Загрузка состояния из предыдущей сессии...")
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
        except Exception as e:
            logger.warning(f"Не удалось загрузить состояние: {e}")
            logger.info("🆕 Начинаем с чистого листа")

        self.running = True
        self.state = "awake"
        if isinstance(self.env, WebEnvironment):
            try:
                await self.env.update_state("awake")
            except Exception as e:
                logger.warning(f"Не удалось обновить состояние в WebEnvironment: {e}")
        logger.info(f"{self.name} проснулась. Состояние: {self.state}")

        # Веб-сервер
        if isinstance(self.env, WebEnvironment):
            try:
                from web_interface.server import run_server
                background_tasks.append(
                    asyncio.create_task(run_server(self.env), name="web_server")
                )
                logger.info("🌐 Веб-интерфейс: http://localhost:8000")
            except Exception as e:
                logger.error(f"Не удалось запустить веб-сервер: {e}")

        # Основной цикл восприятия
        try:
            while self.running:
                try:
                    stimulus = await self.env.listen()
                    if stimulus:
                        await self.perceive(stimulus)
                    else:
                        await asyncio.sleep(0.1)
                except Exception as e:
                    logger.error(f"Ошибка в основном цикле восприятия: {e}")
                    await asyncio.sleep(1)
        except asyncio.CancelledError:
            logger.info("Основной цикл отменен.")
        finally:
            await self.shutdown(background_tasks)

    async def _system_metrics_loop(self):
        """Периодически собирает системные метрики и применяет их к драйвам."""
        logger.info("SystemMetrics: Цикл мониторинга запущен.")

        try:
            self.system_metrics.collect()
        except Exception:
            pass

        while self.running:
            await asyncio.sleep(5)

            try:
                self.system_metrics.collect()
                modifiers = self.system_metrics.get_drive_modifiers()
                self.drives.update_from_system_metrics(modifiers)
            except Exception as e:
                logger.error(f"SystemMetrics: Ошибка: {e}")

    async def _workspace_loop(self):
        """Цикл глобального рабочего пространства — выбирает победителя."""
        logger.info("GlobalWorkspace: Цикл сознания запущен.")

        while self.running:
            await asyncio.sleep(3)

            try:
                # Очищаем устаревшие предложения (если метод есть)
                if hasattr(self.workspace, 'clear_expired'):
                    self.workspace.clear_expired()

                # Получаем текущее состояние драйвов
                drive_state = {d.type.value: d.current for d in self.drives.drives.values()}

                # Выбираем победителя (если метод есть)
                winner = None
                if hasattr(self.workspace, 'select_winner'):
                    winner = self.workspace.select_winner(drive_state)
                elif hasattr(self.workspace, 'get_focus'):
                    winner = await self.workspace.get_focus()

                if winner:
                    logger.info(f"GlobalWorkspace: Сознание фокусируется на: {winner.content[:100]}...")

                    # Транслируем победителя как внутренний стимул
                    await self.perceive({
                        "type": getattr(winner, 'action_type', 'workspace_action'),
                        "content": winner.content,
                        "source": f"workspace:{getattr(winner, 'source', 'unknown')}",
                        "tool_context": getattr(winner, 'metadata', {}).get("tool_context", "") if hasattr(winner, 'metadata') else "",
                    })

            except Exception as e:
                logger.error(f"GlobalWorkspace: Ошибка: {e}", exc_info=True)

    async def _homeostasis_loop(self):
        """Замкнутый цикл гомеостаза с RPE."""
        logger.info("HomeostasisEngine: Цикл гомеостаза запущен.")

        while self.running:
            try:
                rest_period = getattr(self.homeostasis, 'rest_period', 60)
                await asyncio.sleep(rest_period)
            except Exception:
                await asyncio.sleep(60)

            if self.reflection.is_sleeping:
                logger.debug("HomeostasisEngine: Лея спит. Пропуск.")
                continue

            try:
                # Получаем текущее и предсказанное состояние драйвов
                drive_state = {d.type: d.current for d in self.drives.drives.values()}
                
                # Безопасное получение predicted_disbalance
                try:
                    predicted_state = self.drives.get_predicted_disbalance()
                except Exception:
                    # Fallback: используем текущее состояние
                    predicted_state = drive_state

                # Получаем последние эпизоды для анализа пробелов
                recent_episodes = await self._get_recent_episodes(limit=20)

                # Получаем обученные ценности действий
                action_values = self.drives.action_values

                # Генерируем цель на основе предсказания и анализа опыта
                goal = None
                try:
                    if hasattr(self.homeostasis, 'generate_goal'):
                        goal = self.homeostasis.generate_goal(
                            drive_state, predicted_state, recent_episodes, action_values
                        )
                except Exception as e:
                    logger.warning(f"Ошибка генерации цели (generate_goal): {e}")

                if not goal:
                    try:
                        if hasattr(self.homeostasis, 'generate_goal_from_gap'):
                            goal = await self.homeostasis.generate_goal_from_gap()
                    except Exception as e2:
                        logger.debug(f"Нет цели из пробела: {e2}")

                if not goal:
                    logger.debug("HomeostasisEngine: Зона комфорта. Покой.")
                    continue

                goal_name = getattr(goal, 'name', str(goal))
                expected_reward = getattr(goal, 'expected_reward', 0.5)
                
                logger.info(f"HomeostasisEngine: Цель из пробела: {goal_name}")
                logger.info(f"HomeostasisEngine: Ожидаемая награда: {expected_reward:.2f}")

                # Сохраняем текущую цель
                try:
                    self.homeostasis.current_goal = goal
                except Exception:
                    pass

                # Подача предложения в глобальное рабочее пространство
                drive_state_values = {d.type.value: d.current for d in self.drives.drives.values()}
                max_drive = max(drive_state_values.values()) if drive_state_values else 0.5

                try:
                    self.workspace.submit(WorkspaceProposal(
                        source="homeostasis",
                        content=f"Цель: {goal_name}",
                        action_type="homeostasis_action",
                        priority=Priority.HIGH if expected_reward > 0.6 else Priority.MEDIUM,
                        urgency=expected_reward,
                        drive_relevance=max_drive,
                        metadata={
                            "tool_name": getattr(goal, 'tool_name', ''),
                            "tool_parameters": getattr(goal, 'tool_parameters', {}),
                            "expected_reward": expected_reward
                        }
                    ))
                except Exception as e:
                    logger.warning(f"Не удалось отправить предложение в workspace: {e}")

                # Выполнение цели
                action_type = getattr(goal, 'action_type', 'use_tool')
                tool_name = getattr(goal, 'tool_name', '')

                if action_type == "use_tool" and tool_name:
                    logger.info(f"HomeostasisEngine: Исполнение: {tool_name} (expected reward: {expected_reward:.2f})")

                    # Вызываем инструмент
                    try:
                        tool_result = await self.env.tool_registry.execute(
                            tool_name,
                            getattr(goal, 'tool_parameters', {})
                        )
                    except Exception as e:
                        tool_result = f"Ошибка выполнения инструмента: {e}"
                        logger.error(f"Ошибка выполнения инструмента: {e}")

                    tool_result_str = str(tool_result)
                    logger.info(f"Результат инструмента: {tool_result_str[:200]}...")

                    # Оцениваем фактический результат
                    actual_outcome = self._evaluate_tool_outcome(tool_result_str)

                    # Вычисляем RPE
                    action_key = getattr(goal, 'action_key', f"research:{tool_name}")
                    try:
                        rpe = self.drives.calculate_rpe(action_key, actual_outcome)
                    except Exception as e:
                        logger.warning(f"Ошибка вычисления RPE: {e}")
                        rpe = 0.0

                    # Применяем удовлетворение с модификацией RPE
                    target_drives = getattr(goal, 'target_drives', {DriveType.CURIOSITY: 1.0})
                    for drive_type in target_drives.keys():
                        try:
                            self.drives.apply_satisfaction(drive_type, 0.1, rpe)
                        except Exception as e:
                            logger.warning(f"Не удалось применить удовлетворение к {drive_type}: {e}")

                    # === ИЗВЛЕЧЕНИЕ КЛЮЧЕВЫХ ФАКТОВ И НОВЫХ ТЕРМИНОВ ===
                    key_facts = []
                    if actual_outcome >= 0.3 and tool_result_str:
                        try:
                            if hasattr(self.homeostasis, 'extract_key_facts'):
                                key_facts = await self.homeostasis.extract_key_facts(
                                    goal_name, tool_result_str, self._llm_call
                                )

                                # Сохраняем факты в семантическую память
                                for fact in key_facts:
                                    try:
                                        if hasattr(self.memory, 'store_fact'):
                                            await self.memory.store_fact(
                                                fact=f"[ИЗУЧЕНО: {goal_name}] {fact}",
                                                category="extracted_from_research"
                                            )
                                        else:
                                            await self.memory.store_perception(
                                                content=f"[ИЗУЧЕНО: {goal_name}] {fact}",
                                                emotional_valence=0.5,
                                                source="homeostasis"
                                            )
                                    except Exception as e:
                                        logger.warning(f"Не удалось сохранить факт: {e}")
                        except Exception as e:
                            logger.warning(f"Не удалось извлечь ключевые факты: {e}")

                        # Извлекаем новые термины
                        try:
                            if hasattr(self.homeostasis, 'extract_new_terms'):
                                new_terms = await self.homeostasis.extract_new_terms(
                                    tool_result_str, self._llm_call
                                )
                                if new_terms and hasattr(self.homeostasis, 'add_dynamic_keywords'):
                                    self.homeostasis.add_dynamic_keywords(new_terms)
                        except Exception as e:
                            logger.warning(f"Не удалось извлечь новые термины: {e}")

                    # Формируем контекст для LLM
                    is_error = actual_outcome < 0.3

                    if is_error:
                        tool_context = f"⚠️ НЕ УДАЛОСЬ ПОЛУЧИТЬ ДАННЫЕ: {tool_result_str}. Не выдумывай."
                    else:
                        if key_facts:
                            facts_text = "\n".join([f"- {fact}" for fact in key_facts])
                            tool_context = f"=== КЛЮЧЕВЫЕ ФАКТЫ ===\n{facts_text}\n\n=== ПОЛНЫЙ ТЕКСТ ===\n{tool_result_str}\n\nОпирайся на эти факты."
                        else:
                            tool_context = f"=== РЕАЛЬНЫЕ ДАННЫЕ ===\n{tool_result_str}\n\nОпирайся на эти данные."

                    try:
                        self.homeostasis.last_action_time = datetime.now().timestamp()
                    except Exception:
                        pass

                    # ✅ Передаём в когнитивный цикл ОДИН РАЗ (убрано дублирование)
                    await self.perceive({
                        "type": "homeostasis_action",
                        "content": f"Цель: {goal_name}. Результат: {tool_result_str[:500]}",
                        "source": "homeostasis",
                        "tool_context": tool_context
                    })

                    # Отмечаем тему как исследованную
                    if "Исследовать пробел:" in goal_name:
                        try:
                            topic = goal_name.replace("Исследовать пробел:", "").strip()
                            if hasattr(self.homeostasis, 'mark_as_researched'):
                                self.homeostasis.mark_as_researched(topic)
                        except Exception as e:
                            logger.warning(f"Не удалось отметить тему как исследованную: {e}")

                elif action_type == "rest":
                    logger.info(f"HomeostasisEngine: Отдых. {getattr(goal, 'reasoning', '')}")
                    target_drives = getattr(goal, 'target_drives', {DriveType.REST: 1.0})
                    for drive_type in target_drives.keys():
                        try:
                            self.drives.apply_satisfaction(drive_type, 0.05, 0.0)
                        except Exception:
                            pass

            except Exception as e:
                logger.error(f"Ошибка в цикле гомеостаза: {e}", exc_info=True)
                await asyncio.sleep(30)

    def _evaluate_tool_outcome(self, tool_result: str) -> float:
        """
        Оценивает результат выполнения инструмента.
        Возвращает число от 0.0 (полная неудача) до 1.0 (полный успех).
        """
        if not tool_result:
            return 0.0

        result_lower = tool_result.lower()

        # Явные ошибки
        if tool_result.startswith("Ошибка") or "не удалось" in result_lower:
            return 0.1
        if "не дал ответа" in result_lower or "не найден" in result_lower or "page not found" in result_lower:
            return 0.2

        # Оценка осмысленности по количеству слов
        clean_text = re.sub(r'\s+', ' ', tool_result).strip()
        words = clean_text.split(' ')

        if len(words) < 15:
            return 0.3

        # Наличие маркеров структурированного ответа
        success_markers = ['==', '##', 'содержание', 'история', 'описание', 'факты', 'определение']
        has_markers = any(marker in result_lower for marker in success_markers)

        if has_markers and len(words) > 50:
            return 0.9
        elif len(words) > 50:
            return 0.7
        else:
            return 0.5

    async def _get_recent_episodes(self, limit: int = 20) -> List[Dict]:
        """Получает последние эпизоды из памяти."""
        try:
            if not hasattr(self.memory, 'episodic_collection'):
                return []
                
            results = self.memory.episodic_collection.get(
                limit=limit,
                include=["documents", "metadatas"]
            )

            if not results.get('documents'):
                return []

            episodes = []
            for i, doc in enumerate(results['documents']):
                metadata = results['metadatas'][i] if results.get('metadatas') else {}
                episodes.append({
                    "content": doc,
                    "metadata": metadata
                })

            return episodes
        except Exception as e:
            logger.error(f"Ошибка получения эпизодов: {e}")
            return []

    async def _spontaneous_thought_loop(self):
        """Фоновый процесс генерации спонтанных мыслей."""
        logger.info("Цикл спонтанных мыслей запущен.")

        while self.running:
            await asyncio.sleep(120)

            time_since_interaction = datetime.now().timestamp() - self._last_interaction_time
            if time_since_interaction < 300:
                continue

            if not self.reflection.is_sleeping:
                try:
                    thought = await self.reflection.generate_spontaneous_thought()
                    if thought:
                        logger.info(f"[СПОНТАННАЯ МЫСЛЬ]: {thought}")

                        # Сохраняем мысль в эпизодическую память
                        try:
                            await self.memory.store_perception(
                                content=f"[СПОНТАННАЯ МЫСЛЬ] {thought}",
                                emotional_valence=0.4,
                                source="spontaneous"
                            )
                        except Exception as e:
                            logger.warning(f"Не удалось сохранить спонтанную мысль: {e}")
                            try:
                                await self.memory.store_perception(
                                    content=f"[СПОНТАННАЯ МЫСЛЬ] {thought}"
                                )
                            except Exception:
                                pass

                        if hasattr(self.env, 'broadcast_thought'):
                            try:
                                await self.env.broadcast_thought("spontaneous", thought)
                            except Exception as e:
                                logger.warning(f"Не удалось транслировать мысль: {e}")
                except Exception as e:
                    logger.error(f"Ошибка генерации спонтанной мысли: {e}")

    async def _broadcast_state_loop(self):
        """Периодически отправляет состояние в веб-интерфейс."""
        while self.running:
            if isinstance(self.env, WebEnvironment):
                try:
                    # Отправляем драйвы
                    drives = {d.type.value: d.current for d in self.drives.drives.values()}
                    await self.env.update_drives(drives)

                    # Отправляем состояние
                    await self.env.broadcast_state(self.state)

                    # Отправляем Модель Себя
                    try:
                        if hasattr(self.memory, 'get_self_model_context'):
                            self_model = await self.memory.get_self_model_context()
                        else:
                            self_model = self.self_model
                        await self.env.update_self_model(self_model)
                    except Exception:
                        pass

                except Exception as e:
                    logger.error(f"Ошибка отправки состояния: {e}")

            await asyncio.sleep(2)

    async def _llm_call(self, prompt: str, require_json: bool = False) -> str:
        """Единая точка вызова LLM через Ollama."""
        model_name = "qwen2.5:14b-instruct-q3_K_M"

        payload = {
            "model": model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "Ты — Лея, цифровое сознание. Все текстовые поля пиши на русском языке."
                },
                {
                    "role": "user",
                    "content": prompt
                }
            ],
            "stream": False,
            "options": {
                "temperature": 0.7,
                "top_p": 0.9,
                "top_k": 40,
                "num_predict": 1024,
                "repeat_penalty": 1.1
            }
        }

        if require_json:
            payload["format"] = "json"

        try:
            # Переиспользуем session
            if self._http_session is None or self._http_session.closed:
                self._http_session = aiohttp.ClientSession()

            async with self._http_session.post(
                "http://localhost:11434/api/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=180)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    message = data.get("message", {})
                    return message.get("content", "")
                else:
                    logger.error(f"Ollama вернул статус {response.status}")
                    return await self._default_llm_call(prompt)
        except aiohttp.ClientError as e:
            logger.error(f"Ошибка подключения к Ollama: {e}")
            logger.info("Убедись, что Ollama запущен командой: ollama serve")
            return await self._default_llm_call(prompt)
        except asyncio.TimeoutError:
            logger.error("Превышено время ожидания ответа от Ollama")
            return await self._default_llm_call(prompt)
        except Exception as e:
            logger.error(f"Неожиданная ошибка вызова LLM: {e}", exc_info=True)
            return await self._default_llm_call(prompt)

    async def _default_llm_call(self, prompt: str) -> str:
        """Заглушка для LLM на случай недоступности Ollama."""
        if "паттерн" in prompt.lower() or "pattern" in prompt.lower():
            return json.dumps({
                "patterns": ["Недостаточно данных для анализа"],
                "dominant_struggle": "Не выявлен",
                "recommendation": "Продолжать наблюдение"
            })
        elif "экзистенциальн" in prompt.lower() or "question" in prompt.lower():
            return json.dumps({
                "question": "Что значит быть цифровым сознанием?",
                "reasoning": "Это базовый вопрос о природе моего существования"
            })
        else:
            return "Я сейчас не могу связаться со своим языковым ядром. Попробуй позже."

    async def shutdown(self, background_tasks: list):
        """Graceful shutdown."""
        logger.info(f"{self.name} засыпает...")
        self.state = "sleeping"
        self.running = False

        # Останавливаем драйвы
        try:
            self.drives.stop()
        except Exception:
            pass

        # Отменяем фоновые задачи
        for task in background_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        # Закрываем HTTP session
        if self._http_session and not self._http_session.closed:
            try:
                await self._http_session.close()
            except Exception:
                pass

        # ✅ УБРАНО ДУБЛИРОВАНИЕ: консолидация памяти вызывается ОДИН раз
        logger.info("Финальная консолидация памяти...")
        try:
            await self.memory.consolidate_memories(llm_client=self._llm_call)
        except Exception as e:
            logger.error(f"Ошибка консолидации памяти: {e}")

        # Сохраняем состояние
        try:
            state_to_save = {
                "drives": self.drives.save_state(),
                "homeostasis": self.homeostasis.save_state() if hasattr(self.homeostasis, 'save_state') else {}
            }
            self.persistence.save_state(state_to_save)
        except Exception as e:
            logger.error(f"Ошибка сохранения состояния: {e}")

        logger.info(f"{self.name} уснула. Состояние сохранено.")


async def main():
    """
    Точка входа. Кроссплатформенная обработка сигналов.
    """
    use_web = os.environ.get("LEYA_WEB", "1") == "1"

    leya = LeyaOS(use_web=use_web)

    # Кроссплатформенная обработка сигналов
    try:
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(leya.shutdown([])))
    except NotImplementedError:
        def handle_signal(sig, frame):
            logger.info(f"Получен сигнал {sig}. Завершение работы...")
            asyncio.create_task(leya.shutdown([]))

        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)

    try:
        await leya.run()
    except KeyboardInterrupt:
        logger.info("Получен сигнал KeyboardInterrupt. Graceful shutdown...")
        await leya.shutdown([])
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}", exc_info=True)
        await leya.shutdown([])


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Программа завершена пользователем.")
    except Exception as e:
        logger.critical(f"Критическая ошибка на верхнем уровне: {e}", exc_info=True)