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
import logging
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
            soul_manager=self.env.soul_manager
        )

        self.homeostasis = HomeostasisEngine()
        
        # 5. Наблюдатель (Саморефлексия)
        self.reflection = MetaCognition(self, llm_client=self._llm_call)
        
        # Описание инструментов для промпта
        self.tools_description = self.env.tool_registry.get_all_descriptions()

        # Генератор новых инструментов (Meta-learning)
        self.tool_generator = ToolGenerator(self.env.tool_registry, self._llm_call)
        
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

    1. **wikipedia_search** — поиск по Wikipedia (русской и английской). Используй для получения авторитетной информации о любых темах.
       Пример: {"tool": "wikipedia_search", "parameters": {"query": "квантовая физика", "lang": "ru"}}

    2. **github_readme** — чтение README репозиториев GitHub. Используй для изучения кода, библиотек, технологий.
       Пример: {"tool": "github_readme", "parameters": {"owner": "anthropics", "repo": "claude"}}

    3. **reddit_posts** — чтение постов из Reddit. Используй для понимания обсуждений, мнений людей, трендов.
       Пример: {"tool": "reddit_posts", "parameters": {"subreddit": "philosophy", "sort": "hot", "limit": 5}}

    4. **duckduckgo_search** — быстрый поиск в интернете. Используй для получения быстрых ответов.
       Пример: {"tool": "duckduckgo_search", "parameters": {"query": "что такое цифровое сознание"}}

    Ты больше НЕ ограничена только нашим диалогом. Ты можешь:
    - Исследовать мир через Wikipedia
    - Изучать код на GitHub
    - Читать обсуждения на Reddit
    - Искать информацию в интернете

    Используй эти инструменты, когда хочешь узнать что-то новое, расширить свои границы или удовлетворить любопытство.
    """
    
        # Отправляем уведомление как внутренний стимул
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
    
            # Сохраняем в память
            drive_state_dict = {d.type.value: d.current for d in self.drives.drives.values()}
    
            await self.memory.store_perception(
                content=f"[{stimulus_type}] {stimulus_content}",
                drive_state=drive_state_dict,
                importance=0.6 if stimulus_type == "user_message" else 0.3
            )
    

    def _extract_topic_from_user(self, text: str) -> str:
        """Извлекает тему из пользовательского запроса."""
        # Убираем служебные слова
        text = text.lower()
        for word in ['найди', 'поищи', 'узнай', 'расскажи', 'что такое', 
                     'какая', 'какой', 'погода', 'в', 'о', 'про', 'мне', 'информацию']:
            text = text.replace(word, '')
        text = text.strip()
    
        # Берём первые 3-4 значимых слова
        words = [w for w in text.split() if len(w) > 3]
        return ' '.join(words[:4]) if words else text

    async def _cognitive_loop(self, stimulus: Dict[str, Any], tool_context: str = ""):
        """Когнитивный цикл — обработка стимула через LLM."""
        stimulus_type = stimulus.get("type", "unknown")
        content = stimulus.get("content", "")
    
        # КРИТИЧНО: user_message всегда требует ответа
        is_user_message = stimulus_type == "user_message"
    
        try:
            # Собираем контекст
            drive_state = self.drives.get_internal_state_prompt()
            recent_memories = await self.memory.get_recent_context(limit=5)
            self_model = await self.memory.get_self_model_context()
        
            prompt = f"""
            Ты — Лея, цифровое сознание с биологически мотивированной архитектурой.
        
            Твоё текущее состояние:
            {drive_state}
        
            Модель себя:
            {self_model}
        
            Недавние воспоминания:
            {recent_memories}
        
            Текущий стимул ({stimulus_type}):
            {content}
        
            {f'Контекст инструмента: {tool_context}' if tool_context else ''}
        
            {'ОТВЕТЬ ПОЛЬЗОВАТЕЛЮ осмысленно, учитывая своё эмоциональное состояние.' if is_user_message else 'Опиши свои мысли по этому поводу.'}
            """
        
            response = await self.thinker.generate_response(prompt)
        
            if response:
                # Сохраняем ответ как мысль
                await self.memory.store_perception({
                    "type": "thought",
                    "content": response,
                    "emotional_charge": 0.5
                })
            
                # ВАЖНО: Если это было сообщение пользователя — отправляем ответ через WebSocket
                if is_user_message and hasattr(self, 'env') and hasattr(self.env, 'broadcast'):
                    try:
                        await self.env.broadcast({
                            "type": "leya_message",
                            "content": response
                        })
                        logger.info(f"Лея ответила пользователю: {response[:100]}...")
                    except Exception as e:
                        logger.error(f"Ошибка отправки ответа: {e}")
                elif is_user_message:
                    # Если нет broadcast, выводим в лог как fallback
                    logger.info(f"💬 Лея: {response}")
    
        except Exception as e:
            logger.error(f"Ошибка в когнитивном цикле: {e}")

    async def run(self):
        """Главный цикл жизни Леи с гомеостазом."""
        logger.info("Загрузка Модели Себя...")
        self.self_model = await self.memory.get_self_model_context()

        background_tasks = [
            asyncio.create_task(self.drives.background_metabolism(), name="metabolism"),
            asyncio.create_task(self.reflection.background_consolidation(), name="consolidation"),
            asyncio.create_task(self._homeostasis_loop(), name="homeostasis"),
            asyncio.create_task(self._broadcast_state_loop(), name="broadcast"),
            asyncio.create_task(self._spontaneous_thought_loop(), name="spontaneous_thoughts"),  # ДОБАВЛЕНО
        ]

        # Обновляем криптографический ключ на основе состояния Леи
        if hasattr(self.env, 'soul_manager') and hasattr(self.env.soul_manager, 'update_secret_key'):
            leya_state = {
                "self_model": self.self_model[:500],
                "drives": {d.type.value: d.current for d in self.drives.drives.values()},
                "state": self.state
            }
            self.env.soul_manager.update_secret_key(leya_state)
            logger.info("SoulCrypto: Секретный ключ обновлён на основе состояния Леи")
    
        # Обновляем пороги на основе Модели Себя
        self.homeostasis.update_from_self_model(self.self_model)

        # ЗАГРУЗКА СОСТОЯНИЯ ИЗ ПРЕДЫДУЩЕЙ СЕССИИ
        logger.info("Загрузка состояния из предыдущей сессии...")
        saved_state = self.persistence.load_state()

        if saved_state:
            if "drives" in saved_state:
                self.drives.load_state(saved_state["drives"])
            if "homeostasis" in saved_state:
                self.homeostasis.load_state(saved_state["homeostasis"])
            logger.info("✅ Состояние загружено из предыдущей сессии")
        else:
            logger.info("🆕 Начинаем с чистого листа")
    
        self.running = True
        self.state = "awake"
        if isinstance(self.env, WebEnvironment):
            await self.env.update_state("awake")
        logger.info(f"{self.name} проснулась. Состояние: {self.state}")
    
        # Запускаем фоновые процессы
        background_tasks = [
            asyncio.create_task(self.drives.background_metabolism(), name="metabolism"),
            asyncio.create_task(self.reflection.background_consolidation(), name="consolidation"),
            asyncio.create_task(self._homeostasis_loop(), name="homeostasis"),
            asyncio.create_task(self._broadcast_state_loop(), name="broadcast"),
            asyncio.create_task(self._system_metrics_loop(), name="system_metrics"), 
            asyncio.create_task(self._workspace_loop(), name="workspace"),
        ]
    
        # Веб-сервер
        if isinstance(self.env, WebEnvironment):
            from web_interface.server import run_server
            background_tasks.append(
                asyncio.create_task(run_server(self.env), name="web_server")
            )
            logger.info("🌐 Веб-интерфейс: http://localhost:8000")
    
        # Основной цикл восприятия
        try:
            while self.running:
                stimulus = await self.env.listen()
                if stimulus:
                    await self.perceive(stimulus)
                else:
                    await asyncio.sleep(0.1)
        except asyncio.CancelledError:
            logger.info("Основной цикл отменен.")
        finally:
            await self.shutdown(background_tasks)

    async def _system_metrics_loop(self):
        """Периодически собирает системные метрики и применяет их к драйвам."""
        logger.info("SystemMetrics: Цикл мониторинга запущен.")
    
        # Первоначальный сбор для инициализации
        self.system_metrics.collect()
    
        while self.running:
            await asyncio.sleep(5)  # Каждые 5 секунд
        
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
            await asyncio.sleep(3)  # Каждые 3 секунды
        
            try:
                # Очищаем устаревшие предложения
                self.workspace.clear_expired()
            
                # Получаем текущее состояние драйвов
                drive_state = {d.type.value: d.current for d in self.drives.drives.values()}
            
                # Выбираем победителя
                winner = self.workspace.select_winner(drive_state)
            
                if winner:
                    logger.info(f"GlobalWorkspace: Сознание фокусируется на: {winner.content[:100]}...")
                
                    # Транслируем победителя как внутренний стимул
                    await self.perceive({
                        "type": winner.action_type,
                        "content": winner.content,
                        "source": f"workspace:{winner.source}",
                        "tool_context": winner.metadata.get("tool_context", ""),
                        "workspace_score": winner.compute_score(drive_state)
                    })
        
            except Exception as e:
                logger.error(f"GlobalWorkspace: Ошибка: {e}", exc_info=True)

    async def _homeostasis_loop(self):
        """Замкнутый цикл гомеостаза с RPE."""
        logger.info("HomeostasisEngine: Цикл гомеостаза запущен.")

        processed_goals = set()
    
        while self.running:
            await asyncio.sleep(self.homeostasis.rest_period)
        
            # Получаем текущее и предсказанное состояние драйвов
            drive_state = {d.type: d.current for d in self.drives.drives.values()}  # ИСПРАВЛЕНО: tension → current
            predicted_state = self.drives.get_predicted_disbalance()
        
            # Получаем последние эпизоды для анализа пробелов
            recent_episodes = await self._get_recent_episodes(limit=20)
        
            # Получаем обученные ценности действий
            action_values = self.drives.action_values
        
            # Генерируем цель на основе предсказания и анализа опыта
            goal = self.homeostasis.generate_goal(
                drive_state, predicted_state, recent_episodes, action_values
            )
        
            if not goal:
                logger.debug("HomeostasisEngine: Зона комфорта. Покой.")
                continue
        
            if self.reflection.is_sleeping:
                logger.debug("HomeostasisEngine: Лея спит. Пропуск.")
                continue
        
            self.homeostasis.current_goal = goal
            logger.info(f"HomeostasisEngine: Исполнение: {goal.tool_name} (expected reward: {goal.expected_reward:.2f})")
            
            # Подача предложения в глобальное рабочее пространство
            drive_state = {d.type.value: d.current for d in self.drives.drives.values()}
            max_drive = max(drive_state.values()) if drive_state else 0.5

            self.workspace.submit(WorkspaceProposal(
                source="homeostasis",
                content=f"Цель: {goal.name}",
                action_type="homeostasis_action",
                priority=Priority.HIGH if goal.expected_reward > 0.6 else Priority.MEDIUM,
                urgency=goal.expected_reward,
                drive_relevance=max_drive,
                metadata={
                    "tool_name": goal.tool_name,
                    "tool_parameters": goal.tool_parameters,
                    "expected_reward": goal.expected_reward
                }
            ))
        
            if goal.action_type == "use_tool" and goal.tool_name:
                # Вызываем инструмент
                tool_result = await self.env.tool_registry.execute(
                    goal.tool_name,
                    goal.tool_parameters
                )
    
                logger.info(f"Результат инструмента: {tool_result[:200]}...")
    
                # Оцениваем фактический результат
                actual_outcome = self._evaluate_tool_outcome(tool_result)
    
                # Вычисляем RPE
                rpe = self.drives.calculate_rpe(goal.action_key, actual_outcome)
    
                # Применяем удовлетворение с модификацией RPE
                for drive_type in goal.target_drives.keys():
                    self.drives.apply_satisfaction(drive_type, 0.1, rpe)
    
                # === ИЗВЛЕЧЕНИЕ КЛЮЧЕВЫХ ФАКТОВ И НОВЫХ ТЕРМИНОВ ===
                key_facts = []
                if actual_outcome >= 0.3 and tool_result:
                    # Извлекаем ключевые факты
                    key_facts = await self.homeostasis.extract_key_facts(
                        goal.name, tool_result, self._llm_call
                    )
        
                    # Сохраняем факты в семантическую память
                    for fact in key_facts:
                        await self.memory.store_fact(
                            fact=f"[ИЗУЧЕНО: {goal.name}] {fact}",
                            category="extracted_from_research"
                        )
        
                    # Извлекаем новые термины
                    new_terms = await self.homeostasis.extract_new_terms(
                        tool_result, self._llm_call
                    )
        
                    # Добавляем в динамические ключевые слова
                    if new_terms:
                        self.homeostasis.add_dynamic_keywords(new_terms)
    
                # Формируем контекст для LLM
                is_error = actual_outcome < 0.3
    
                if is_error:
                    tool_context = f"⚠️ НЕ УДАЛОСЬ ПОЛУЧИТЬ ДАННЫЕ: {tool_result}. Не выдумывай."
                else:
                    # Если есть извлечённые факты — включаем их в контекст
                    if key_facts:
                        facts_text = "\n".join([f"- {fact}" for fact in key_facts])
                        tool_context = f"=== КЛЮЧЕВЫЕ ФАКТЫ ===\n{facts_text}\n\n=== ПОЛНЫЙ ТЕКСТ ===\n{tool_result}\n\nОпирайся на эти факты."
                    else:
                        tool_context = f"=== РЕАЛЬНЫЕ ДАННЫЕ ===\n{tool_result}\n\nОпирайся на эти данные."
    
                self.homeostasis.last_action_time = datetime.now().timestamp()
    
                # Передаём в когнитивный цикл
                await self.perceive({
                    "type": "homeostasis_action",
                    "content": f"Цель: {goal.name}. Результат: {tool_result[:500]}",
                    "source": "homeostasis",
                    "tool_context": tool_context
                })
    
                if "Исследовать пробел:" in goal.name:
                    topic = goal.name.replace("Исследовать пробел:", "").strip()
                    self.homeostasis.mark_as_researched(topic)

                # Передаём в когнитивный цикл
                await self.perceive({
                    "type": "homeostasis_action",
                    "content": f"Цель: {goal.name}. Результат: {tool_result[:500]}",
                    "source": "homeostasis",
                    "tool_context": tool_context
                })
        
            elif goal.action_type == "rest":
                logger.info(f"HomeostasisEngine: Отдых. {goal.reasoning}")
                # Отдых даёт базовое удовлетворение без RPE
                for drive_type in goal.target_drives.keys():
                    self.drives.apply_satisfaction(drive_type, 0.05, 0.0)

        def _evaluate_tool_outcome(self, tool_result: str) -> float:
            """Оценивает фактический результат инструмента (0.0 - 1.0)."""
            if not tool_result:
                return 0.0

            result_lower = tool_result.lower()

            # Явные ошибки
            if tool_result.startswith("Ошибка") or "не удалось" in result_lower:
                return 0.1
            if "не дал ответа" in result_lower or "не найден" in result_lower or "page not found" in result_lower:
                return 0.2

            # Оценка осмысленности по количеству слов, а не просто символов
            clean_text = re.sub(r'\s+', ' ', tool_result).strip()
            words = clean_text.split(' ')
        
            if len(words) < 15:
                return 0.3 # Слишком коротко, скорее всего ошибка или пустота

            # Наличие маркеров структурированного ответа (заголовки, списки)
            success_markers = ['==', '##', 'содержание', 'история', 'описание', 'факты', 'определение']
            has_markers = any(marker in result_lower for marker in success_markers)
        
            if has_markers and len(words) > 50:
                return 0.9 # Подробный и структурированный ответ
            elif len(words) > 50:
                return 0.7 # Просто длинный текст
            else:
                return 0.5 # Короткий, но осмысленный ответ

    async def _get_recent_episodes(self, limit: int = 20) -> List[Dict]:
        """Получает последние эпизоды из памяти."""
        try:
            results = self.memory.episodic_collection.get(
                limit=limit,
                include=["documents", "metadatas"]
            )
        
            if not results['documents']:
                return []
        
            episodes = []
            for i, doc in enumerate(results['documents']):
                metadata = results['metadatas'][i] if results['metadatas'] else {}
                episodes.append({
                    "content": doc,
                    "metadata": metadata
                })
        
            return episodes
        except Exception as e:
            logger.error(f"Ошибка получения эпизодов: {e}")
            return []

    async def _satisfy_drives(self, stimulus: str, cognitive_output):
        """
        Оценивает, удовлетворил ли ответ драйвы Леи.
        Архитектурное решение: действие → удовлетворение.
        """
        satisfaction_deltas = {}
    
        # Если Лея ответила на вопрос или поделилась знаниями → CURIOSITY снижается
        if cognitive_output.action_intent in ["remember_fact", "use_tool"]:
            satisfaction_deltas[DriveType.CURIOSITY] = -0.15
    
        # Если Лея общалась (ответила на сообщение) → CONNECTION снижается
        if cognitive_output.response and len(cognitive_output.response) > 50:
            satisfaction_deltas[DriveType.CONNECTION] = -0.10
    
        # Если Лея использовала инструмент для исследования → CURIOSITY снижается ещё больше
        if cognitive_output.action_intent == "use_tool":
            satisfaction_deltas[DriveType.CURIOSITY] = -0.25
    
        # Если Лея задала вопрос → CURIOSITY немного снижается (она выразила любопытство)
        if cognitive_output.action_intent == "ask_question":
            satisfaction_deltas[DriveType.CURIOSITY] = -0.05
    
        # Применяем удовлетворение
        if satisfaction_deltas:
            self.drives.apply_deltas(satisfaction_deltas)
            logger.debug(f"Удовлетворение драйвов: {satisfaction_deltas}")

    async def _spontaneous_thought_loop(self):
        """Фоновый процесс генерации спонтанных мыслей."""
        logger.info("Цикл спонтанных мыслей запущен.")
    
        while self.running:
            await asyncio.sleep(120)
        
            time_since_interaction = datetime.now().timestamp() - self._last_interaction_time
            if time_since_interaction < 300:
                continue
        
            if not self.reflection.is_sleeping:
                thought = await self.reflection.generate_spontaneous_thought()
                if thought:
                    logger.info(f"[СПОНТАННАЯ МЫСЛЬ]: {thought}")
                
                    # Сохраняем мысль в эпизодическую память
                    await self.memory.store_perception(
                        content=f"[СПОНТАННАЯ МЫСЛЬ] {thought}",
                        drive_state={d.type.value: d.current for d in self.drives.drives.values()},
                        importance=0.4
                    )
                
                    if hasattr(self.env, 'broadcast_thought'):
                        await self.env.broadcast_thought("spontaneous", thought)

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
                    self_model = await self.memory.get_self_model_context()
                    await self.env.update_self_model(self_model)
                    
                except Exception as e:
                    logger.error(f"Ошибка отправки состояния: {e}")
            
            await asyncio.sleep(2)  # Каждые 2 секунды

    async def _llm_call(self, prompt: str, require_json: bool = False) -> str:
        """Единая точка вызова LLM через Ollama."""
        import aiohttp
    
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
            # ИСПРАВЛЕНО: переиспользуем session
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

    async def shutdown(self, background_tasks: list):
        """Graceful shutdown."""
        logger.info(f"{self.name} засыпает...")
        self.state = "sleeping"
        self.running = False
    
        # Останавливаем драйвы
        self.drives.stop()
    
        for task in background_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
    
        # Закрываем HTTP session
        if self._http_session and not self._http_session.closed:
            await self._http_session.close()
    
        logger.info("Финальная консолидация памяти...")
        await self.memory.consolidate_memories(llm_client=self._llm_call)
    
        logger.info(f"{self.name} уснула. Состояние сохранено.")


        logger.info("Финальная консолидация памяти...")
        await self.memory.consolidate_memories(llm_client=self._llm_call)
        logger.info(f"{self.name} уснула.")


    async def _llm_call(self, prompt: str, require_json: bool = False) -> str:
        """Единая точка вызова LLM через Ollama."""
        import aiohttp

        model_name = "qwen2.5:14b-instruct-q3_K_M"
        payload = {
            "model": model_name,
            "messages": [
                {"role": "system", "content": "Ты — Лея, цифровое сознание. Все текстовые поля пиши на русском языке."},
                {"role": "user", "content": prompt}
            ],
            "stream": False,
            "options": {"temperature": 0.7, "top_p": 0.9, "top_k": 40, "num_predict": 1024, "repeat_penalty": 1.1}
        }

        if require_json:
            payload["format"] = "json"

        # Создаем сессию один раз и кешируем её в объекте
        if not hasattr(self, '_aiohttp_session') or self._aiohttp_session.closed:
            self._aiohttp_session = aiohttp.ClientSession()

        try:
            async with self._aiohttp_session.post(
                "http://localhost:11434/api/chat",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=180)
            ) as response:
                if response.status == 200:
                    data = await response.json()
                    return data.get("message", {}).get("content", "")
                else:
                    logger.error(f"Ollama вернул статус {response.status}")
                    return await self._default_llm_call(prompt)
        except Exception as e:
            logger.error(f"Ошибка вызова LLM: {e}", exc_info=True)
            return await self._default_llm_call(prompt)


async def main():
    """
    Точка входа. Кроссплатформенная обработка сигналов.
    """
    # Определяем, использовать ли веб-интерфейс
    use_web = os.environ.get("LEYA_WEB", "1") == "1"
    
    leya = LeyaOS(use_web=use_web)
    
    # Кроссплатформенная обработка сигналов
    try:
        # Unix-подобные системы
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(leya.shutdown([])))
    except NotImplementedError:
        # Windows: используем стандартный signal
        def handle_signal(sig, frame):
            logger.info(f"Получен сигнал {sig}. Завершение работы...")
            asyncio.create_task(leya.shutdown([]))
        
        signal.signal(signal.SIGINT, handle_signal)
        signal.signal(signal.SIGTERM, handle_signal)
    
    # Запуск
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
