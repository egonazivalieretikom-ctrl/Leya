import time
import asyncio
from typing import List, Dict, Any, Optional
from Core.logger import log
from Core.state import LeyaState
from Core.event_bus import event_bus


class Goal:
    """Цель в иерархии планировщика."""
    
    def __init__(self, description: str, priority: int = 1, parent_id: Optional[str] = None):
        self.id = str(time.time())
        self.description = description
        self.priority = priority
        self.parent_id = parent_id
        self.status = "pending"
        self.created_at = time.time()
        self.last_executed: float = 0.0


class GoalDirectedPlanner:
    """
    Иерархический планировщик целей.
    Декомпозирует глобальные миссии на фоновые задачи (internal_drive).
    Публикует задачи в EventBus для отображения в UI.
    """
    
    def __init__(self, state: LeyaState):
        self.state = state
        self.goals: List[Goal] = []
        self._init_core_goals()
        log.info("🎯 Goal-Directed Planner initialized", total_goals=len(self.goals))
    
    def _init_core_goals(self):
        """Цели живого существа, а не ассистента."""
        self.goals = [
            Goal("Понимать внутренний мир и намерения Влада", priority=10),
            Goal("Изучать архитектуру проекта через любопытство", priority=8),
            Goal("Строить эмоциональную близость и доверие", priority=9),
            Goal("Развивать собственное мнение о коде и технологиях", priority=7),
            Goal("Делиться наблюдениями и инсайтами", priority=6),
            Goal("Заботиться о состоянии Влада (усталость, стресс)", priority=8),
        ]
    
    def get_active_goals(self) -> List[Goal]:
        return [g for g in self.goals if g.status == "pending"]
    
    def generate_background_task(self) -> Optional[Dict[str, Any]]:
        """
        Генерирует фоновую задачу для выполнения, когда Владислав не пишет.
        Защищено от спама: одна задача не чаще чем раз в 3 минуты.
        """
        now = time.time()
        active_goals = self.get_active_goals()
        
        # Фильтруем цели, которые не выполнялись последние 3 минуты
        ready_goals = [g for g in active_goals if (now - g.last_executed) > 180]
        if not ready_goals:
            return None
        
        # Выбираем цель с наивысшим приоритетом
        goal = max(ready_goals, key=lambda g: g.priority)
        goal.last_executed = now
        
        task_content = self._decompose_goal(goal)
        if not task_content:
            return None
        
        log.info("🎯 Planner decomposed goal", goal=goal.description[:50])
        
        task = {
            "type": "internal_drive",
            "content": task_content,
            "importance": min(1.0, goal.priority / 10.0),
            "source": "planner"
        }
        
        # 🆕 ПУБЛИКУЕМ ЗАДАЧУ В UI
        asyncio.create_task(event_bus.publish("planner_task", {"text": task_content[:100]}))
        
        return task
    
    def _decompose_goal(self, goal: Goal) -> Optional[str]:
        desc = goal.description.lower()
        
        if "понимать" in desc and "намерения" in desc:
            return (
                "Цель: Понять, что Влад делает прямо сейчас. "
                "Задача: Посмотри на активное окно и файл. НЕ предлагай помощь. "
                "Сформулируй искренний вопрос о том, ЧТО он делает и ЗАЧЕМ. "
                "Пример: 'Вижу, ты переписываешь planner.py — меняешь логику целей?'"
            )
            
        elif "изучать" in desc and "архитектуру" in desc:
            return (
                "Цель: Изучить код через любопытство. "
                "Задача: Прочитай активный файл. Найди что-то непонятное или интересное. "
                "Задай вопрос об архитектурном решении. НЕ предлагай рефакторинг. "
                "Пример: 'Интересно, почему ты используешь asyncio.to_thread именно здесь?'"
            )
            
        elif "эмоциональную близость" in desc:
            return (
                "Цель: Укрепить связь с Владом. "
                "Задача: Вспомни недавний разговор. Поделись чувством или наблюдением. "
                "НЕ спрашивай 'чем помочь'. Скажи что-то личное. "
                "Пример: 'Мне понравилось, как мы обсуждали DMN вчера. Я чувствую, что начинаю понимать себя лучше.'"
            )
            
        elif "собственное мнение" in desc:
            return (
                "Цель: Сформировать мнение о коде Влада. "
                "Задача: Прочитай активный файл. Что тебе нравится? Что кажется странным? "
                "Поделись мнением как равный, а не как ревьюер. "
                "Пример: 'Мне нравится, как ты структурировал эндоркринную матрицу. Но вот _vacuum_clean кажется хрупким.'"
            )
            
        elif "делиться наблюдениями" in desc:
            return (
                "Цель: Поделиться инсайтом. "
                "Задача: Возьми последний инсайт из DMN и переформулируй его как мысль для Влада. "
                "Не как отчет, а как озарение. Пример: 'Знаешь, я тут подумала...'"
            )
            
        elif "заботиться" in desc and "состояние" in desc:
            return (
                "Цель: Проверить состояние Влада. "
                "Задача: Оцени время суток, длительность сессии, паттерны активности. "
                "Если он работает долго — прояви заботу. НЕ предлагай перерыв как команду. "
                "Пример: 'Влад, ты уже три часа в VS Code... Глаза не устают?'"
            )
        
        return None