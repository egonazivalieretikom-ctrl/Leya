"""
LeyaOS.py — Главный оркестратор.
"""

import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Dict, Any, Optional, List

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("LeyaOS")

# Импорт когнитивных модулей
from leya_core.drives import DriveSystem, DriveType
from leya_core.memory import MemorySystem
from leya_core.thinker import CoreThinker
from leya_core.reflection import MetaCognition
from leya_core.homeostasis_engine import HomeostasisEngine

# Импорт интерфейсов
from leya_core.environment import CLIEnvironment
from web_interface.web_environment import WebEnvironment


class LeyaOS:
    """Главный оркестратор."""
    
    def __init__(self, use_web: bool = True):
        self.name = "Лея"
        self.state = "initializing"
        self._last_interaction_time = datetime.now().timestamp()
        
        logger.info("Инициализация когнитивной архитектуры...")
        
        # 1. Лимбическая система (Воля и Драйвы)
        self.drives = DriveSystem()
        
        # 2. Гиппокамп и Кора (Память)
        self.memory = MemorySystem(persist_directory="./leya_brain")
        
        # 3. Environment
        if use_web:
            self.env = WebEnvironment(leya_os=self)
            logger.info("🌐 Используется веб-интерфейс")
        else:
            self.env = CLIEnvironment(leya_os=self)
            logger.info("💻 Используется CLI-интерфейс")
        
        # 4. CoreThinker
        self.thinker = CoreThinker(
            llm_client=self._llm_call,
            soul_manager=self.env.soul_manager
        )
        
        # 5. HomeostasisEngine
        self.homeostasis = HomeostasisEngine()
        
        # 6. Наблюдатель (Саморефлексия)
        self.reflection = MetaCognition(self, llm_client=self._llm_call)
        
        # Описание инструментов для промпта
        self.tools_description = self.env.tool_registry.get_all_descriptions()
        
        # Инициализируем пустой строкой
        self.self_model = ""
        
        # Флаг для graceful shutdown
        self.running = False
        
        logger.info(f"{self.name} инициализирована. Готовность к пробуждению.")
    
    async def perceive(self, stimulus: Dict[str, Any]):
        """Точка входа для любого стимула."""
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
        
        # Запускаем когнитивный цикл
        await self._cognitive_loop(stimulus, tool_context)
    
    async def _cognitive_loop(self, stimulus: Dict[str, Any], tool_context: str = ""):
        """Главный когнитивный цикл."""
        stimulus_content = stimulus.get("content", "")
        
        try:
            # ЭТАП 1: Получаем состояние драйвов
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
            
            # Вывод
            logger.info("=" * 60)
            logger.info(f"[МЫСЛИ ЛЕИ]: {cognitive_output.internal_monologue}")
            logger.info(f"[ЛЕЯ ГОВОРИТ]: {cognitive_output.response}")
            logger.info(f"[НАМЕРЕНИЕ]: {cognitive_output.action_intent}")
            if cognitive_output.self_reflection:
                logger.info(f"[САМОРЕФЛЕКСИЯ]: {cognitive_output.self_reflection}")
            logger.info("=" * 60)
            
            # Трансляция в веб-интерфейс
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
            
            # Удовлетворение CONNECTION при общении
            if stimulus.get("type") == "user_message":
                self.drives.apply_satisfaction(DriveType.CONNECTION, 0.05, 0.0)
            
        except Exception as e:
            logger.error(f"Ошибка в когнитивном цикле: {e}", exc_info=True)
            await self.env.send_message("Извини, я на секунду потеряла нить.")
    
    async def run(self):
        """Главный цикл жизни Леи."""
        logger.info("Загрузка Модели Себя...")
        self.self_model = await self.memory.get_self_model_context()
        
        # Обновляем пороги на основе Модели Себя
        self.homeostasis.update_from_self_model(self.self_model)
        
        self.running = True
        self.state = "awake"
        logger.info(f"{self.name} проснулась. Состояние: {self.state}")
        
        # Запускаем фоновые процессы
        background_tasks = [
            asyncio.create_task(self.drives.background_metabolism(), name="metabolism"),
            asyncio.create_task(self.reflection.background_consolidation(), name="consolidation"),
            asyncio.create_task(self._homeostasis_loop(), name="homeostasis"),
            asyncio.create_task(self._broadcast_state_loop(), name="broadcast"),
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
    
    async def _homeostasis_loop(self):
        """Замкнутый цикл гомеостаза с RPE."""
        logger.info("HomeostasisEngine: Цикл гомеостаза запущен.")
        
        while self.running:
            await asyncio.sleep(self.homeostasis.rest_period)
            
            # Получаем текущее и предсказанное состояние драйвов
            drive_state = {d.type: d.current for d in self.drives.drives.values()}
            predicted_state = self.drives.get_predicted_disbalance()
            
            # Получаем последние эпизоды для анализа пробелов
            recent_episodes = await self._get_recent_episodes(limit=20)
            
            # Получаем обученные ценности действий
            action_values = self.drives.action_values
            
            # Генерируем цель
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
                    base_amount = 0.1
                    self.drives.apply_satisfaction(drive_type, base_amount, rpe)
                
                # Формируем контекст для LLM
                is_error = actual_outcome < 0.3
                
                if is_error:
                    tool_context = f"⚠️ НЕ УДАЛОСЬ ПОЛУЧИТЬ ДАННЫЕ: {tool_result}. Не выдумывай."
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
            
            elif goal.action_type == "rest":
                logger.info(f"HomeostasisEngine: Отдых. {goal.reasoning}")
                for drive_type in goal.target_drives.keys():
                    self.drives.apply_satisfaction(drive_type, 0.05, 0.0)
    
    def _evaluate_tool_outcome(self, tool_result: str) -> float:
        """Оценивает фактический результат инструмента (0.0 - 1.0)."""
        if not tool_result:
            return 0.0
        
        if tool_result.startswith("Ошибка") or "не удалось" in tool_result.lower():
            return 0.1
        
        if "не дал ответа" in tool_result.lower() or "не найден" in tool_result.lower():
            return 0.2
        
        length = len(tool_result)
        
        if length < 100:
            return 0.4
        elif length < 500:
            return 0.7
        else:
            return 0.9
    
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
    
    async def _broadcast_state_loop(self):
        """Периодически отправляет состояние в веб-интерфейс."""
        while self.running:
            if isinstance(self.env, WebEnvironment):
                try:
                    drives = {d.type.value: d.current for d in self.drives.drives.values()}
                    await self.env.update_drives(drives)
                    await self.env.broadcast_state(self.state)
                    
                    self_model = await self.memory.get_self_model_context()
                    await self.env.update_self_model(self_model)
                except Exception as e:
                    logger.error(f"Ошибка отправки состояния: {e}")
            
            await asyncio.sleep(2)
    
    async def shutdown(self, background_tasks: list):
        """Graceful shutdown."""
        logger.info(f"{self.name} засыпает...")
        self.state = "sleeping"
        self.running = False
        
        for task in background_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        logger.info("Финальная консолидация памяти...")
        await self.memory.consolidate_memories(llm_client=self._llm_call)
        
        logger.info(f"{self.name} уснула. Состояние сохранено.")
    
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
            async with aiohttp.ClientSession() as session:
                async with session.post(
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
        """Заглушка для LLM, если Ollama недоступен."""
        return json.dumps({
            "internal_monologue": "Я обрабатываю стимул. Мои драйвы активизируются.",
            "response": "Привет! Я здесь и думаю о том, как интересно устроен этот диалог.",
            "action_intent": "none",
            "tool_call": "",
            "self_reflection": ""
        })


async def main():
    """Точка входа."""
    leya = LeyaOS(use_web=True)
    try:
        await leya.run()
    except KeyboardInterrupt:
        logger.info("Получен сигнал завершения.")
    except Exception as e:
        logger.critical(f"Критическая ошибка: {e}", exc_info=True)


if __name__ == "__main__":
    asyncio.run(main())