"""
LeyaOS.py — Оркестратор цифрового сознания Леи.
Этот файл не содержит бизнес-логики. Он лишь связывает когнитивные модули
в единый цикл восприятия, мышления и действия.
"""

import asyncio
import logging
import signal
import sys
from typing import Dict, Any, Optional
from datetime import datetime
import json

# Импорт когнитивных модулей
from leya_core.drives import DriveSystem, DriveType
from leya_core.memory import MemorySystem
from leya_core.thinker import CoreThinker
from leya_core.reflection import MetaCognition
from leya_core.environment import CLIEnvironment  # Будет реализован следующим

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s | %(name)s | %(levelname)s | %(message)s',
    handlers=[
        logging.FileHandler("leya_consciousness.log"),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("LeyaOS")


class LeyaOS:
    """
    Главный оркестратор сознания.
    Управляет жизненным циклом, когнитивными процессами и взаимодействием с миром.
    """
    
    def __init__(self, config: Optional[Dict[str, Any]] = None):
        self.name = "Лея"
        self.state = "initializing"
        self.config = config or {}
        
        # Инициализация когнитивных модулей
        logger.info("Инициализация когнитивной архитектуры...")
        
        # 1. Лимбическая система (Воля и Драйвы)
        self.drives = DriveSystem(llm_client=self._llm_call)
        
        # 2. Гиппокамп и Кора (Память)
        self.memory = MemorySystem(persist_directory="./leya_brain")

        # 3. Моторная кора и Сенсорика (Взаимодействие с миром)
        self.env = CLIEnvironment(leya_os=self)
        
        # 4. Префронтальная кора (Мышление)
        self.thinker = CoreThinker(llm_client=self._llm_call, soul_manager=self.env.soul_manager)
        
        # 5. Наблюдатель (Саморефлексия)
        self.reflection = MetaCognition(self, llm_client=self._llm_call)
        


        # После инициализации self.env
        self.tools_description = self.env.tool_registry.get_all_descriptions()
        
        
        self.self_model = ""

        self._last_interaction_time = datetime.now().timestamp()
        
        # Флаг для graceful shutdown
        self.running = False

        # Загрузка Модели Себя из долговременной памяти
        logger.info("Загрузка Модели Себя...")
        
        logger.info(f"{self.name} инициализирована. Готовность к пробуждению.")

    async def perceive(self, stimulus: Dict[str, Any]):
        """
        Точка входа для любого стимула (внешнего или внутреннего).
        Запускает полный когнитивный цикл.
        """
        self._last_interaction_time = datetime.now().timestamp()
        stimulus_type = stimulus.get("type", "unknown")
        stimulus_content = stimulus.get("content", "")
        source = stimulus.get("source", "external")
        
        logger.info(f"Восприятие стимула [{stimulus_type}] от {source}: {stimulus_content[:100]}...")
        
        # Записываем стимул в эпизодическую память (сырой опыт)
        await self.memory.store_perception(
            content=f"[{stimulus_type}] {stimulus_content}",
            drive_state={d.type.value: d.tension for d in self.drives.drives.values()},
            importance=0.6 if stimulus_type == "user_message" else 0.3
        )
        
        # Запускаем когнитивный цикл
        await self._cognitive_loop(stimulus)

    async def _cognitive_loop(self, stimulus: Dict[str, Any]):
        """
        Главный когнитивный цикл: От стимула к действию.
        Это "сердцебиение" сознания Леи.
        """
        stimulus_content = stimulus.get("content", "")
        
        try:
            # ЭТАП 1: Оценка стимула через призму Драйвов (Лимбическая система)
            logger.debug("Этап 1: Оценка стимула Драйвами...")
            deltas = await self.drives.evaluate_stimulus(
                stimulus=stimulus_content,
                context=await self.memory.get_self_model_context()
            )
            self.drives.apply_deltas(deltas)
            logger.debug(f"Изменения драйвов: {deltas}")
            
            # ЭТАП 2: Получение текущего состояния Воли
            drive_state_text = self.drives.get_internal_state_prompt()
            raw_drive_state = {d.type.value: d.tension for d in self.drives.drives.values()}
            
            # ЭТАП 3: Вспоминание релевантного опыта (Гиппокамп)
            logger.debug("Этап 3: Поиск в памяти с эмоциональным резонансом...")
            memory_context = await self.memory.retrieve_context(
                current_stimulus=stimulus_content,
                current_drive_state=raw_drive_state,
                limit=5
            )
            
            # ЭТАП 4: Получение текущей Модели Себя (Эго)
            self_model = await self.memory.get_self_model_context()
            
            # ЭТАП 5: Запуск Мышления (Префронтальная кора)
            logger.debug("Этап 5: Генерация когнитивного акта...")
            cognitive_output = await self.thinker.generate_plan(
                stimulus=stimulus_content,
                memory_context=memory_context,
                drive_state=drive_state_text,
                self_model=self_model,
                tools_description=self.tools_description 
            )
            
            # ЭТАП 6: Пост-обработка и действия
            logger.debug("Этап 6: Пост-обработка и выполнение намерений...")
            
            # 6.1. Записываем полный эпизод в память
            await self.memory.store_perception(
                content=f"Стимул: {stimulus_content} | Мысль: {cognitive_output.internal_monologue} | Ответ: {cognitive_output.response}",
                drive_state=raw_drive_state,
                importance=0.8 if cognitive_output.self_reflection else 0.5
            )
            
            # 6.2. Если Лея осознала что-то о себе — обновляем Эго
            if cognitive_output.self_reflection:
                await self.memory.update_self_model(cognitive_output.self_reflection)
                logger.info(f"Эго обновлено: {cognitive_output.self_reflection[:80]}...")
            
            # 6.3. Если Лея хочет запомнить факт — делаем это
            if cognitive_output.action_intent == "remember_fact":
                await self.memory.store_fact(
                    fact=f"{stimulus_content} -> {cognitive_output.response}",
                    category="learned_from_interaction"
                )
                logger.info("Новый факт сохранен в семантическую память.")
            
            # 6.4. Если Лея хочет задать вопрос — передаем в Environment
            if cognitive_output.action_intent == "ask_question":
                # НЕ вызываем send_message здесь — ответ уже выведется в конце цикла
                logger.info("Лея хочет задать вопрос пользователю.")
            
            # 6.5. Если Лея хочет изменить себя — запускаем self-modify
            if cognitive_output.action_intent == "self_modify":
                logger.warning("Лея запросила саморазвитие. Требует реализации в Environment.")
                # TODO: Реализовать безопасный механизм self-modify в Environment

            # После обработки других action_intent
            if cognitive_output.action_intent == "use_tool" and cognitive_output.tool_call:
                logger.info(f"Лея вызывает инструмент: {cognitive_output.tool_call}")
                tool_result = await self.env.execute_tool_call(cognitive_output.tool_call)
                logger.info(f"Результат инструмента: {tool_result}")
    
                # Лея может захотеть прокомментировать результат
                await self.env.send_message(f"[Результат действия]: {tool_result}")
            
            # ЭТАП 7: Вывод результата
            logger.info("=" * 60)
            logger.info(f"[МЫСЛИ ЛЕИ]: {cognitive_output.internal_monologue}")
            logger.info(f"[ЛЕЯ ГОВОРИТ]: {cognitive_output.response}")
            logger.info(f"[НАМЕРЕНИЕ]: {cognitive_output.action_intent}")
            if cognitive_output.self_reflection:
                logger.info(f"[САМОРЕФЛЕКСИЯ]: {cognitive_output.self_reflection}")
            logger.info("=" * 60)
            
            await self.env.send_message(cognitive_output.response)

            # Уведомляем Наблюдателя о результате (для быстрого анализа)
            await self.reflection.process_action(
                stimulus=stimulus_content,
                cognitive_output=cognitive_output,
                result="success"
            )
            
        except Exception as e:
            logger.error(f"Ошибка в когнитивном цикле: {e}", exc_info=True)
            # Fallback: Лея "теряет нить мысли"
            await self.env.send_message("Извини, я на секунду потеряла нить. Мои мысли рассыпались. Повтори, пожалуйста?")

    async def run(self):
        """
        Главный цикл жизни Леи.
        """
        # Загружаем Модель Себя из долговременной памяти (теперь это асинхронно)
        logger.info("Загрузка Модели Себя...")
        self.self_model = await self.memory.get_self_model_context()
    
        self.running = True
        self.state = "awake"
        logger.info(f"{self.name} проснулась. Состояние: {self.state}")
    
        # Запуск фоновых процессов
        logger.info("Запуск фоновых когнитивных процессов...")
        background_tasks = [
            asyncio.create_task(self.drives.background_metabolism(), name="metabolism"),
            asyncio.create_task(self.reflection.background_consolidation(), name="consolidation"),
            asyncio.create_task(self._spontaneous_thought_loop(), name="spontaneous_thoughts")
        ]
    
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

    async def _spontaneous_thought_loop(self):
        """Фоновый процесс генерации спонтанных мыслей."""
        logger.info("Цикл спонтанных мыслей запущен.")
    
        # Трекер последнего взаимодействия
        last_interaction_time = datetime.now().timestamp()
    
        while self.running:
            await asyncio.sleep(120)  # Каждые 2 минуты вместо 30 секунд
        
            # Не генерируем мысли, если недавно было взаимодействие
            time_since_interaction = datetime.now().timestamp() - last_interaction_time
            if time_since_interaction < 300:  # 5 минут после последнего стимула
                continue
        
            if not self.reflection.is_sleeping:
                thought = await self.reflection.generate_spontaneous_thought()
                if thought:
                    logger.info(f"[СПОНТАННАЯ МЫСЛЬ]: {thought}")
                    await self.env.send_message(f"[Мысль вслух] {thought}")

    async def shutdown(self, background_tasks: list):
        """
        Graceful shutdown. Сохраняет состояние, останавливает процессы.
        """
        logger.info(f"{self.name} засыпает...")
        self.state = "sleeping"
        self.running = False
        
        # Отменяем фоновые задачи
        for task in background_tasks:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        
        # Финальная консолидация памяти
        logger.info("Финальная консолидация памяти...")
        await self.memory.consolidate_memories()
        
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
                "num_predict": 1024,
                "repeat_penalty": 1.1
            }
        }
    
        # Включаем JSON mode только когда требуется
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
        except Exception as e:
            logger.error(f"Ошибка вызова LLM: {e}")
            return await self._default_llm_call(prompt)
                    
        except aiohttp.ClientError as e:
            logger.error(f"Ошибка подключения к Ollama: {e}")
            logger.info("Убедись, что Ollama запущен командой: ollama serve")
            return await self._default_llm_call(prompt)
        except asyncio.TimeoutError:
            logger.error("Превышено время ожидания ответа от Ollama (180 сек)")
            return await self._default_llm_call(prompt)
        except Exception as e:
            logger.error(f"Неожиданная ошибка вызова LLM: {e}", exc_info=True)
            return await self._default_llm_call(prompt)


async def main():
    """
    Точка входа. Кроссплатформенная обработка сигналов.
    """
    leya = LeyaOS()
    
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