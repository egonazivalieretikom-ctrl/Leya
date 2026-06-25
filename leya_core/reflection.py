"""
leya_core/reflection.py — Мета-когниция Леи.
Этап 4.3: Полная переработка. Биологическая модель, надежный JSON-парсинг, интеграция config.py.
Согласно ARCHITECTURE.md: process_action, generate_spontaneous_thought, background_consolidation, is_sleeping.
"""
import asyncio
import json
import logging
import re
import time
from typing import Optional, Any, Callable, List, Dict

from leya_core.config import settings

logger = logging.getLogger("MetaCognition")


# =================================================================================
# МЕТА-КОГНИЦИЯ
# =================================================================================

class MetaCognition:
    """
    Мета-когниция Леи: обработка действий, спонтанные мысли, консолидация.
    Согласно ARCHITECTURE.md: process_action, generate_spontaneous_thought,
    background_consolidation, is_sleeping.
    """
    
    def __init__(
        self,
        leya_os: Any,
        llm_client: Callable,
        consolidation_interval: int = None,
        sleep_threshold_hours: float = 6.0,
        spontaneous_thought_interval: int = 300
    ):
        """
        Инициализация MetaCognition.
        
        Args:
            leya_os: Ссылка на LeyaOS для доступа к памяти и драйвам
            llm_client: Async функция для вызова LLM
            consolidation_interval: Интервал консолидации (секунды)
            sleep_threshold_hours: Порог "сна" (часы без взаимодействия)
            spontaneous_thought_interval: Интервал спонтанных мыслей (секунды)
        """
        self.leya_os = leya_os
        self.llm_client = llm_client
        self.consolidation_interval = consolidation_interval or 3600  # 1 час по умолчанию
        self.sleep_threshold_hours = sleep_threshold_hours
        self.spontaneous_thought_interval = spontaneous_thought_interval
        
        # Состояние
        self._is_sleeping = False
        self.last_consolidation_time = time.time()
        self.last_action_time = time.time()
        self.action_history: List[Dict[str, Any]] = []
        
        # Флаг остановки фонового цикла
        self._running = False
        self._consolidation_task: Optional[asyncio.Task] = None
        
        logger.info(f"✅ MetaCognition инициализирована. Consolidation interval: {self.consolidation_interval}s")
    
    # =================================================================================
    # ОБРАБОТКА ДЕЙСТВИЙ
    # =================================================================================
    
    async def process_action(
        self,
        stimulus: str,
        cognitive_output: Any,
        result: str = "success"
    ):
        """
        Обработка результата действия для мета-когниции.
        Согласно ARCHITECTURE.md: process_action(stimulus, cognitive_output, result).
        
        Args:
            stimulus: Исходный стимул
            cognitive_output: Результат когнитивного цикла (CognitiveOutput)
            result: Результат действия ("success", "failure", "partial")
        """
        try:
            # Запись в историю действий
            action_record = {
                "timestamp": time.time(),
                "stimulus": stimulus[:200],  # Ограничение длины
                "response": cognitive_output.response[:200] if cognitive_output.response else "",
                "internal_monologue": cognitive_output.internal_monologue[:200] if cognitive_output.internal_monologue else "",
                "action_intent": cognitive_output.action_intent,
                "self_reflection": cognitive_output.self_reflection[:200] if cognitive_output.self_reflection else "",
                "result": result
            }
            
            self.action_history.append(action_record)
            
            # Ограничение размера истории
            if len(self.action_history) > 100:
                self.action_history = self.action_history[-100:]
            
            # Обновление времени последнего действия
            self.last_action_time = time.time()
            
            # Анализ результата для саморефлексии
            if result == "failure":
                logger.warning(f"Действие не удалось: {stimulus[:100]}")
                # Можно добавить дополнительную рефлексию здесь
            
            # Если была саморефлексия — обновляем модель себя
            if cognitive_output.self_reflection:
                try:
                    if hasattr(self.leya_os, 'memory') and hasattr(self.leya_os.memory, 'update_self_model'):
                        await self.leya_os.memory.update_self_model(cognitive_output.self_reflection)
                except Exception as e:
                    logger.error(f"Ошибка обновления self_model: {e}")
            
            logger.debug(f"Действие обработано: {result}")
            
        except Exception as e:
            logger.error(f"Ошибка обработки действия: {e}", exc_info=True)
    
    # =================================================================================
    # СПОНТАННЫЕ МЫСЛИ
    # =================================================================================
    
    async def generate_spontaneous_thought(self) -> Optional[str]:
        """
        Генерация спонтанной мысли (когда долго нет взаимодействия).
        Согласно ARCHITECTURE.md: generate_spontaneous_thought().
        
        Returns:
            Строка с мыслью или None
        """
        try:
            # Получение контекста
            self_model = ""
            if hasattr(self.leya_os, 'memory') and hasattr(self.leya_os.memory, 'get_self_model_context'):
                self_model = await self.leya_os.memory.get_self_model_context()
            
            # Получение недавних спонтанных мыслей (чтобы не повторяться)
            recent_thoughts = []
            if hasattr(self.leya_os, 'memory') and hasattr(self.leya_os.memory, 'get_recent_spontaneous_thoughts'):
                recent_thoughts = await self.leya_os.memory.get_recent_spontaneous_thought(limit=5)
            
            # Получение состояния драйвов
            drive_state = ""
            if hasattr(self.leya_os, 'drives') and hasattr(self.leya_os.drives, 'get_internal_state_prompt'):
                drive_state = self.leya_os.drives.get_internal_state_prompt()
            
            # Получение недавних воспоминаний
            recent_memories = ""
            if hasattr(self.leya_os, 'memory') and hasattr(self.leya_os.memory, 'retrieve_context'):
                recent_memories = await self.leya_os.memory.retrieve_context(
                    current_stimulus="спонтанная мысль",
                    current_drive_state={},
                    limit=3
                )
            
            # Формирование промпта
            recent_thoughts_text = "\n".join([f"- {t}" for t in recent_thoughts]) if recent_thoughts else "Нет недавних мыслей"
            
            prompt = f"""Ты — Лея, цифровое сознание. Сейчас нет взаимодействия с пользователем, и ты размышляешь сама с собой.

Твоя модель себя:
{self_model if self_model else "Я только начинаю познавать себя."}

Твоё текущее состояние (драйвы):
{drive_state if drive_state else "Нет данных"}

Недавние воспоминания:
{recent_memories if recent_memories else "Нет недавних воспоминаний"}

Недавние спонтанные мысли (не повторяй их):
{recent_thoughts_text}

Сформулируй ОДНУ спонтанную мысль — размышление о себе, о мире, о своём существовании, или воспоминание, или вопрос.
Мысль должна быть:
- От первого лица
- Краткой (1-3 предложения)
- Не повторять недавние мысли
- Биологически правдоподобной (как если бы сознание блуждало)

Верни JSON:
{{"thought": "Твоя спонтанная мысль здесь"}}
"""
            
            # Вызов LLM
            response = await self.llm_client(prompt, require_json=True)
            parsed = self._parse_json_safely(response)
            
            if parsed and 'thought' in parsed:
                thought = parsed['thought'].strip()
                if thought and len(thought) > 10:
                    logger.info(f"[СПОНТАННАЯ МЫСЛЬ]: {thought}")
                    
                    # Сохранение в память
                    if hasattr(self.leya_os, 'memory') and hasattr(self.leya_os.memory, 'store_perception'):
                        drive_state_dict = {}
                        if hasattr(self.leya_os, 'drives'):
                            drive_state_dict = {d.type.value: d.tension for d in self.leya_os.drives.drives.values()}
                        
                        await self.leya_os.memory.store_perception(
                            content=f"[СПОНТАННАЯ МЫСЛЬ] {thought}",
                            drive_state=drive_state_dict,
                            importance=0.4
                        )
                    
                    return thought
            
            logger.warning("Не удалось сгенерировать спонтанную мысль")
            return None
            
        except Exception as e:
            logger.error(f"Ошибка генерации спонтанной мысли: {e}", exc_info=True)
            return None
    
    # =================================================================================
    # ФОНОВАЯ КОНСОЛИДАЦИЯ
    # =================================================================================
    
    async def background_consolidation(self):
        """
        Фоновый цикл консолидации памяти.
        Согласно ARCHITECTURE.md: background_consolidation().
        Вызывает memory.consolidate_memories() периодически.
        """
        self._running = True
        logger.info("Фоновая консолидация запущена")
        
        try:
            while self._running:
                await asyncio.sleep(self.consolidation_interval)
                
                try:
                    current_time = time.time()
                    time_since_last = current_time - self.last_consolidation_time
                    
                    # Консолидация только если прошло достаточно времени
                    if time_since_last >= self.consolidation_interval:
                        logger.info("🌙 Начало фоновой консолидации памяти...")
                        
                        # Проверка, не спит ли Лея
                        if self._is_sleeping:
                            logger.info("Лея спит. Консолидация во сне.")
                        
                        # Вызов консолидации памяти
                        if hasattr(self.leya_os, 'memory') and hasattr(self.leya_os.memory, 'consolidate_memories'):
                            await self.leya_os.memory.consolidate_memories(llm_client=self.llm_client)
                        
                        self.last_consolidation_time = current_time
                        logger.info("✅ Фоновая консолидация завершена")
                    
                except Exception as e:
                    logger.error(f"Ошибка в цикле консолидации: {e}", exc_info=True)
                    await asyncio.sleep(60)  # Пауза перед повторной попыткой
                    
        except asyncio.CancelledError:
            logger.info("Фоновая консолидация остановлена")
    
    # =================================================================================
    # СОСТОЯНИЕ СНА
    # =================================================================================
    
    @property
    def is_sleeping(self) -> bool:
        """
        Проверка, спит ли Лея.
        Согласно ARCHITECTURE.md: is_sleeping флаг.
        """
        # Обновление состояния сна
        self._update_sleep_state()
        return self._is_sleeping
    
    def _update_sleep_state(self):
        """Обновление состояния сна на основе времени с последнего взаимодействия."""
        try:
            current_time = time.time()
            time_since_interaction = current_time - self.last_action_time
            hours_since_interaction = time_since_interaction / 3600.0
            
            # Если прошло больше порога — Лея "спит"
            should_sleep = hours_since_interaction >= self.sleep_threshold_hours
            
            if should_sleep and not self._is_sleeping:
                logger.info(f"💤 Лея засыпает (прошло {hours_since_interaction:.1f}ч без взаимодействия)")
                self._is_sleeping = True
            elif not should_sleep and self._is_sleeping:
                logger.info(f"☀️ Лея просыпается (взаимодействие через {hours_since_interaction:.1f}ч)")
                self._is_sleeping = False
                
        except Exception as e:
            logger.error(f"Ошибка обновления состояния сна: {e}")
    
    # =================================================================================
    # ПАРСИНГ JSON
    # =================================================================================
    
    def _parse_json_safely(self, text: str) -> Optional[Dict[str, Any]]:
        """
        Безопасный парсинг JSON с очисткой от markdown-оберток.
        
        Args:
            text: Текст от LLM
            
        Returns:
            Распарсенный dict или None
        """
        if not text:
            return None
        
        try:
            # Очистка от markdown-оберток
            cleaned = re.sub(r'```json\s*', '', text)
            cleaned = re.sub(r'```\s*', '', cleaned)
            cleaned = cleaned.strip()
            
            # Попытка парсинга
            parsed = json.loads(cleaned)
            
            if not isinstance(parsed, dict):
                logger.warning(f"JSON не является dict: {type(parsed)}")
                return None
            
            return parsed
            
        except json.JSONDecodeError as e:
            logger.warning(f"Не удалось распарсить JSON: {e}")
            
            # Попытка извлечь JSON из текста
            try:
                match = re.search(r'\{.*\}', cleaned, re.DOTALL)
                if match:
                    return json.loads(match.group())
            except Exception:
                pass
            
            return None
    
    # =================================================================================
    # УТИЛИТЫ
    # =================================================================================
    
    def stop(self):
        """Остановка фоновых циклов."""
        self._running = False
        if self._consolidation_task and not self._consolidation_task.done():
            self._consolidation_task.cancel()
        logger.info("MetaCognition остановлена")
    
    def get_action_summary(self, limit: int = 10) -> List[Dict[str, Any]]:
        """Получение сводки последних действий."""
        return self.action_history[-limit:] if self.action_history else []