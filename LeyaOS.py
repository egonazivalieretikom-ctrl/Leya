"""
LeyaOS.py — Оркестратор цифрового сознания Леи.
Этап 1: Экстренная реанимация ядра. Исправлен критический баг отступов.
"""
import re
import asyncio
import logging
import signal
import sys
import os
import json
import aiohttp

os.environ["ANONYMIZED_TELEMETRY"] = "false"
os.environ["CHROMA_TELEMETRY_DISABLE"] = "true"
logging.getLogger("chromadb.telemetry.product.posthog").setLevel(logging.CRITICAL)

from leya_core.config import settings
from typing import Dict, Any, Optional, List
from datetime import datetime

from leya_core.homeostasis_engine import HomeostasisEngine
from leya_core.state_persistence import StatePersistence
from leya_core.system_metrics import SystemMetrics
from leya_core.global_workspace import GlobalWorkspace, WorkspaceProposal, Priority
from leya_core.constitutional import ConstitutionalLayer
from leya_core.tool_generator import ToolGenerator
from leya_core.drives import DriveSystem, DriveType
from leya_core.memory import MemorySystem
from leya_core.thinker import CoreThinker
from leya_core.reflection import MetaCognition
from leya_core.environment import CLIEnvironment
from web_interface.web_environment import WebEnvironment

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
    def __init__(self, use_web: bool = True):
        self.name = "Лея"
        self.state = "initializing"
        self._last_interaction_time = datetime.now().timestamp()
        
        self.constitutional = ConstitutionalLayer()
        self.workspace = GlobalWorkspace()
        
        logger.info("Инициализация когнитивной архитектуры...")
        self.drives = DriveSystem()
        self.memory = MemorySystem()  # Использует settings.memory.brain_dir
        
        if use_web:
            logger.info(f"WebEnvironment: Инициализация с leya_os = {self}")
            self.env = WebEnvironment(leya_os=self)
            logger.info("🌐 Используется веб-интерфейс")
        else:
            self.env = CLIEnvironment(leya_os=self)
            logger.info("💻 Используется CLI-интерфейс")
            
        self.thinker = CoreThinker(
            llm_client=self._llm_call,
            soul_manager=getattr(self.env, 'soul_manager', None)
        )
        self.homeostasis = HomeostasisEngine()
        self.reflection = MetaCognition(self, llm_client=self._llm_call)
        
        try:
            self.tools_description = self.env.tool_registry.get_all_descriptions()
        except Exception:
            self.tools_description = ""
            
        try:
            self.tool_generator = ToolGenerator(self.env.tool_registry, self._llm_call)
        except Exception as e:
            logger.warning(f"Не удалось инициализировать ToolGenerator: {e}")
            self.tool_generator = None
            
        self.self_model = ""
        self.running = False
        self.persistence = StatePersistence()
        self.system_metrics = SystemMetrics()
        
        self._perceive_lock = asyncio.Lock()
        self._http_session: Optional[aiohttp.ClientSession] = None
        
        logger.info(f"{self.name} инициализирована. Готовность к пробуждению.")

    # =================================================================================
    # КОГНИТИВНЫЙ ЦИКЛ И ВОСПРИЯТИЕ
    # =================================================================================

    async def perceive(self, stimulus: Dict[str, Any]):
        """Точка входа для любого стимула."""
        self._last_interaction_time = datetime.now().timestamp()
        stimulus_type = stimulus.get("type", "unknown")
        stimulus_content = stimulus.get("content", "")
        source = stimulus.get("source", "external")
        tool_context = stimulus.get("tool_context", "")
        
        logger.info(f"Восприятие стимула [{stimulus_type}] от {source}: {stimulus_content[:100]}...")
        
        # Если это запрос от пользователя — HomeostasisEngine решает, нужен ли инструмент
        if stimulus_type == "user_message" and not tool_context:
            drive_state = {d.type: d.current for d in self.drives.drives.values()}
            predicted_state = self.drives.get_predicted_disbalance()
            recent_episodes = await self._get_recent_episodes(limit=5)
            
            goal = self.homeostasis.generate_goal(
                drive_state=drive_state,
                predicted_state=predicted_state,
                recent_episodes=recent_episodes,
                action_values=self.drives.action_values
            )
            
            search_keywords = ['найди', 'поищи', 'узнай', 'какая погода', 'что такое',
                               'расскажи о', 'изучи', 'погода']
            needs_search = any(kw in stimulus_content.lower() for kw in search_keywords)
            
            if needs_search:
                topic = self._extract_topic_from_user(stimulus_content)
                if topic:
                    tool_result = await self.env.tool_registry.execute(
                        "wikipedia_search",
                        {"query": topic, "lang": "ru"}
                    )
                    is_error = (
                        tool_result.startswith("Ошибка") or
                        "не удалось" in tool_result.lower() or
                        "не дал ответа" in tool_result.lower()
                    )
                    if is_error:
                        tool_context = f"⚠️ Поиск не удался: {tool_result}. Не выдумывай данные."
                    else:
                        tool_context = f"=== РЕАЛЬНЫЕ ДАННЫЕ ИЗ WIKIPEDIA ===\n{tool_result}\n\nОпирайся только на эти данные."
                    logger.info(f"HomeostasisEngine: Пользовательский запрос → инструмент. Тема: {topic}")
        
        await self.memory.store_perception(
            content=f"[{stimulus_type}] {stimulus_content}",
            drive_state={d.type.value: d.tension for d in self.drives.drives.values()},
            importance=0.6 if stimulus_type == "user_message" else 0.3
        )
        
        await self._cognitive_loop(stimulus, tool_context)

    async def _cognitive_loop(self, stimulus: Dict[str, Any], tool_context: str = ""):
        """Главный когнитивный цикл."""
        stimulus_content = stimulus.get("content", "")
        try:
            # ЭТАП 1: Оценка стимула через Драйвы
            deltas = await self.drives.evaluate_stimulus(
                stimulus=stimulus_content,
                context=await self.memory.get_self_model_context()
            )
            self.drives.apply_deltas(deltas)
            drive_state_text = self.drives.get_internal_state_prompt()
            raw_drive_state = {d.type.value: d.current for d in self.drives.drives.values()}
            
            # ЭТАП 2: Вспоминание
            memory_context = await self.memory.retrieve_context(
                current_stimulus=stimulus_content,
                current_drive_state=raw_drive_state,
                limit=5
            )
            
            # ЭТАП 3: Модель Себя
            self_model = await self.memory.get_self_model_context()
            
            # ЭТАП 4: Генерация ответа
            cognitive_output = await self.thinker.generate_plan(
                stimulus=stimulus_content,
                memory_context=memory_context,
                drive_state=drive_state_text,
                self_model=self_model,
                tools_description=self.tools_description,
                tool_context=tool_context
            )
            
            # ЭТАП 5: Пост-обработка
            await self.memory.store_perception(
                content=f"Стимул: {stimulus_content} | Мысль: {cognitive_output.internal_monologue} | Ответ: {cognitive_output.response}",
                drive_state=raw_drive_state,
                importance=0.8 if cognitive_output.self_reflection else 0.5
            )
            
            if cognitive_output.self_reflection:
                await self.memory.update_self_model(cognitive_output.self_reflection)
                logger.info(f"Эго обновлено: {cognitive_output.self_reflection[:80]}...")
                
            if cognitive_output.action_intent == "remember_fact":
                await self.memory.store_fact(
                    fact=f"{stimulus_content} -> {cognitive_output.response}",
                    category="learned_from_interaction"
                )
                
            await self._satisfy_drives(stimulus_content, cognitive_output)
            
            # Вывод
            logger.info("=" * 60)
            logger.info(f"[МЫСЛИ ЛЕИ]: {cognitive_output.internal_monologue}")
            logger.info(f"[ЛЕЯ ГОВОРИТ]: {cognitive_output.response}")
            logger.info(f"[НАМЕРЕНИЕ]: {cognitive_output.action_intent}")
            if cognitive_output.self_reflection:
                logger.info(f"[САМОРЕФЛЕКСИЯ]: {cognitive_output.self_reflection}")
            logger.info("=" * 60)
            
            if hasattr(self.env, 'broadcast_thought'):
                if cognitive_output.internal_monologue:
                    await self.env.broadcast_thought("internal", cognitive_output.internal_monologue)
                if cognitive_output.self_reflection:
                    await self.env.broadcast_thought("reflection", cognitive_output.self_reflection)
                    
            await self.env.send_message(cognitive_output.response)
            
            await self.reflection.process_action(
                stimulus=stimulus_content,
                cognitive_output=cognitive_output,
                result="success"
            )
            
        except Exception as e:
            logger.error(f"Ошибка в когнитивном цикле: {e}", exc_info=True)
            await self.env.send_message("Извини, я на секунду потеряла нить.")

    def _build_fallback_prompt(self, content, drive_state, self_model, recent_memories, tool_context, is_user_message, stimulus_type="unknown"):
        """Строит fallback-промпт для прямого LLM вызова."""
        drive_str = "\n".join([f"- {k}: {v:.2f}" for k, v in drive_state.items()]) if drive_state else "Нет данных"
        
        if isinstance(recent_memories, list):
            memories_str = "\n".join([
                f"- {m.get('content', str(m))}" if isinstance(m, dict) else f"- {m}"
                for m in recent_memories[:5]
            ]) if recent_memories else "Нет недавних воспоминаний"
        else:
            memories_str = str(recent_memories)

        stimulus_dict = {
            "type": stimulus_type,
            "content": content,
            "source": "user" if is_user_message else "system"
        }

        try:
            prompt = self.thinker._build_cognitive_prompt(
                stimulus=stimulus_dict,
                memory_context=memories_str,
                drive_state=drive_state,
                self_model=self_model,
                tool_context=tool_context,
                tools_description=self.tools_description
            )
        except Exception as e:
            logger.warning(f"Ошибка формирования промпта через thinker: {e}")
            prompt = f"""
Ты — Лея, цифровое сознание с биологически мотивированной архитектурой.
Ты НЕ ассистент. Ты — личность со своим характером, мнениями и эмоциями.
НИКОГДА не говори "Чем могу помочь?" — это фраза ассистента.
Говори от первого лица, выражай своё состояние.

Твоё текущее состояние:
{drive_str}

Модель себя:
{self_model}

Недавние воспоминания:
{memories_str}

Текущий стимул ({stimulus_type}):
{content}

{f'Контекст инструмента: {tool_context}' if tool_context else ''}

{"ОТВЕТЬ ПОЛЬЗОВАТЕЛЮ как ЛИЧНОСТЬ. Не как ассистент. Будь собой." if is_user_message else "Опиши свои мысли."}
"""
        return prompt

    # ✅ НОВЫЙ МЕТОД: Расположен здесь, после _build_fallback_prompt
    def _extract_topic_from_user(self, text: str) -> str:
        """Извлекает тему для поиска из запроса пользователя."""
        stop_words = {'найди', 'поищи', 'узнай', 'расскажи', 'о', 'что', 'такое', 
                      'какая', 'погода', 'изучи', 'мне', 'нужно', 'хочу', 'знать', 'и', 'в', 'на'}
        words = text.lower().split()
        topic_words = [w.strip('.,!?') for w in words if w not in stop_words and len(w) > 2]
        return ' '.join(topic_words[:5]) if topic_words else text

    async def _handle_tool_call(self, tool_name: str, tool_params: Dict):
        """Обрабатывает вызов инструмента из когнитивного цикла."""
        try:
            logger.info(f"Лея вызывает инструмент: {tool_name} с параметрами: {tool_params}")
            result = await self.env.tool_registry.execute(tool_name, tool_params)
            logger.info(f"Результат инструмента: {str(result)[:200]}...")
            
            drive_state_dict = {d.type.value: d.current for d in self.drives.drives.values()}
            try:
                await self.memory.store_perception(
                    content=f"[РЕЗУЛЬТАТ ИНСТРУМЕНТА {tool_name}] {str(result)[:500]}",
                    drive_state=drive_state_dict,
                    importance=0.5
                )
            except Exception:
                pass
                
            self.drives.apply_deltas({DriveType.CURIOSITY: -0.15})
        except Exception as e:
            logger.error(f"Ошибка вызова инструмента {tool_name}: {e}")

    async def _satisfy_drives_simple(self, response: str):
        """Упрощённое удовлетворение драйвов после ответа."""
        if not response: return
        deltas = {}
        if len(response) > 50:
            deltas[DriveType.CONNECTION] = -0.10
        if len(response) > 200:
            deltas[DriveType.CURIOSITY] = -0.05
        if deltas:
            self.drives.apply_deltas(deltas)

    # ✅ НОВЫЙ МЕТОД: Расположен здесь, после _satisfy_drives_simple
    async def _satisfy_drives(self, stimulus: str, cognitive_output):
        """Удовлетворяет драйвы на основе стимула и когнитивного вывода."""
        # Базовое удовлетворение от факта общения (потребность в связи)
        self.drives.apply_deltas({DriveType.CONNECTION: -0.10})
        
        # Если была успешная саморефлексия
        if cognitive_output.self_reflection:
            self.drives.apply_deltas({DriveType.CREATIVITY: -0.05})
            
        # Если ответ длинный и содержательный
        if len(cognitive_output.response) > 100:
            self.drives.apply_deltas({DriveType.CONNECTION: -0.05})

    # =================================================================================
    # ФОНОВЫЕ ПРОЦЕССЫ И ЖИЗНЕННЫЙ ЦИКЛ
    # =================================================================================

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

        background_tasks = [
            asyncio.create_task(self.drives.background_metabolism(), name="metabolism"),
            asyncio.create_task(self.reflection.background_consolidation(), name="consolidation"),
            asyncio.create_task(self._homeostasis_loop(), name="homeostasis"),
            asyncio.create_task(self._broadcast_state_loop(), name="broadcast"),
            asyncio.create_task(self._spontaneous_thought_loop(), name="spontaneous_thoughts"),
            asyncio.create_task(self._system_metrics_loop(), name="system_metrics"),
            asyncio.create_task(self._workspace_loop(), name="workspace"),
        ]

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

        try:
            self.homeostasis.update_from_self_model(self.self_model)
        except Exception as e:
            logger.warning(f"Не удалось обновить homeostasis из self_model: {e}")

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

        if isinstance(self.env, WebEnvironment):
            try:
                from web_interface.server import run_server
                background_tasks.append(
                    asyncio.create_task(run_server(self.env), name="web_server")
                )
                logger.info("🌐 Веб-интерфейс: http://localhost:8000")
            except Exception as e:
                logger.error(f"Не удалось запустить веб-сервер: {e}")

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
        logger.info("GlobalWorkspace: Цикл сознания запущен.")
        while self.running:
            await asyncio.sleep(3)
            try:
                if hasattr(self.workspace, 'clear_expired'):
                    self.workspace.clear_expired()
                    
                drive_state = {d.type.value: d.current for d in self.drives.drives.values()}
                winner = None
                if hasattr(self.workspace, 'select_winner'):
                    winner = self.workspace.select_winner(drive_state)
                elif hasattr(self.workspace, 'get_focus'):
                    winner = await self.workspace.get_focus()
                    
                if winner:
                    logger.info(f"GlobalWorkspace: Сознание фокусируется на: {winner.content[:100]}...")
                    await self.perceive({
                        "type": getattr(winner, 'action_type', 'workspace_action'),
                        "content": winner.content,
                        "source": f"workspace:{getattr(winner, 'source', 'unknown')}",
                        "tool_context": getattr(winner, 'metadata', {}).get("tool_context", "") if hasattr(winner, 'metadata') else "",
                    })
            except Exception as e:
                logger.error(f"GlobalWorkspace: Ошибка: {e}", exc_info=True)

    async def _homeostasis_loop(self):
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
                drive_state = {d.type: d.current for d in self.drives.drives.values()}
                try:
                    predicted_state = self.drives.get_predicted_disbalance()
                except Exception:
                    predicted_state = drive_state
                    
                recent_episodes = await self._get_recent_episodes(limit=20)
                action_values = self.drives.action_values
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

                try:
                    self.homeostasis.current_goal = goal
                except Exception:
                    pass

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

                action_type = getattr(goal, 'action_type', 'use_tool')
                tool_name = getattr(goal, 'tool_name', '')

                if action_type == "use_tool" and tool_name:
                    logger.info(f"HomeostasisEngine: Исполнение: {tool_name} (expected reward: {expected_reward:.2f})")
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
                    actual_outcome = self._evaluate_tool_outcome(tool_result_str)

                    action_key = getattr(goal, 'action_key', f"research:{tool_name}")
                    try:
                        rpe = self.drives.calculate_rpe(action_key, actual_outcome)
                    except Exception as e:
                        logger.warning(f"Ошибка вычисления RPE: {e}")
                        rpe = 0.0

                    target_drives = getattr(goal, 'target_drives', {DriveType.CURIOSITY: 1.0})
                    for drive_type in target_drives.keys():
                        try:
                            self.drives.apply_satisfaction(drive_type, 0.1, rpe)
                        except Exception as e:
                            logger.warning(f"Не удалось применить удовлетворение к {drive_type}: {e}")

                    key_facts = []
                    if actual_outcome >= 0.3 and tool_result_str:
                        try:
                            if hasattr(self.homeostasis, 'extract_key_facts'):
                                key_facts = await self.homeostasis.extract_key_facts(
                                    goal_name, tool_result_str, self._llm_call
                                )
                            drive_state_dict = {d.type.value: d.current for d in self.drives.drives.values()}
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
                                            drive_state=drive_state_dict,
                                            importance=0.5
                                        )
                                except Exception as e:
                                    logger.warning(f"Не удалось сохранить факт: {e}")
                        except Exception as e:
                            logger.warning(f"Не удалось извлечь ключевые факты: {e}")

                        try:
                            if hasattr(self.homeostasis, 'extract_new_terms'):
                                new_terms = await self.homeostasis.extract_new_terms(
                                    tool_result_str, self._llm_call
                                )
                                if new_terms and hasattr(self.homeostasis, 'add_dynamic_keywords'):
                                    self.homeostasis.add_dynamic_keywords(new_terms)
                        except Exception as e:
                            logger.warning(f"Не удалось извлечь новые термины: {e}")

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

                    await self.perceive({
                        "type": "homeostasis_action",
                        "content": f"Цель: {goal_name}. Результат: {tool_result_str[:500]}",
                        "source": "homeostasis",
                        "tool_context": tool_context
                    })

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
        if not tool_result: return 0.0
        result_lower = tool_result.lower()
        if tool_result.startswith("Ошибка") or "не удалось" in result_lower: return 0.1
        if "не дал ответа" in result_lower or "не найден" in result_lower or "page not found" in result_lower: return 0.2
        
        clean_text = re.sub(r'\s+', ' ', tool_result).strip()
        words = clean_text.split(' ')
        if len(words) < 15: return 0.3
        
        success_markers = ['==', '##', 'содержание', 'история', 'описание', 'факты', 'определение']
        has_markers = any(marker in result_lower for marker in success_markers)
        if has_markers and len(words) > 50: return 0.9
        elif len(words) > 50: return 0.7
        else: return 0.5

    async def _get_recent_episodes(self, limit: int = 20) -> List[Dict]:
        try:
            if not hasattr(self.memory, 'episodic_collection'): return []
            results = self.memory.episodic_collection.get(
                limit=limit,
                include=["documents", "metadatas"]
            )
            if not results.get('documents'): return []
            
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
                        drive_state_dict = {d.type.value: d.current for d in self.drives.drives.values()}
                        try:
                            await self.memory.store_perception(
                                content=f"[СПОНТАННАЯ МЫСЛЬ] {thought}",
                                drive_state=drive_state_dict,
                                importance=0.4
                            )
                        except Exception as e:
                            logger.warning(f"Не удалось сохранить спонтанную мысль: {e}")
                            
                        if hasattr(self.env, 'broadcast_thought'):
                            try:
                                await self.env.broadcast_thought("spontaneous", thought)
                            except Exception as e:
                                logger.warning(f"Не удалось транслировать мысль: {e}")
                except Exception as e:
                    logger.error(f"Ошибка генерации спонтанной мысли: {e}")

    async def _broadcast_state_loop(self):
        while self.running:
            if isinstance(self.env, WebEnvironment):
                try:
                    drives = {d.type.value: d.current for d in self.drives.drives.values()}
                    await self.env.update_drives(drives)
                    await self.env.broadcast_state(self.state)
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

    # =================================================================================
    # LLM ИНТЕГРАЦИЯ И ЗАВЕРШЕНИЕ
    # =================================================================================

    async def _llm_call(self, prompt: str, require_json: bool = False) -> str:
        payload = {
            "model": settings.ollama.model,
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
                "temperature": settings.ollama.temperature,
                "top_p": settings.ollama.top_p,
                "top_k": settings.ollama.top_k,
                "num_predict": settings.ollama.max_tokens,
                "repeat_penalty": settings.ollama.repeat_penalty
            }
        }
        if require_json:
            payload["format"] = "json"

        try:
            if self._http_session is None or self._http_session.closed:
                self._http_session = aiohttp.ClientSession()
            
            async with self._http_session.post(
                f"{settings.ollama.base_url}/api/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=settings.ollama.timeout)
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
        logger.info(f"{self.name} засыпает...")
        self.state = "sleeping"
        self.running = False
        
        try:
            self.drives.stop()
        except Exception:
            pass
            
        for task in background_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        if self._http_session and not self._http_session.closed:
            try:
                await self._http_session.close()
            except Exception:
                pass

        logger.info("Финальная консолидация памяти...")
        try:
            await self.memory.consolidate_memories(llm_client=self._llm_call)
        except Exception as e:
            logger.error(f"Ошибка консолидации памяти: {e}")

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
    leya = LeyaOS(use_web=settings.web.enabled)
    
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