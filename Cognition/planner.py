import time
import asyncio
import re
import json
from typing import List, Dict, Any, Optional
from Core.logger import log
from Core.state import LeyaState
from Core.event_bus import event_bus
from Cognition.llm_client import LLMClient


class Goal:
    """Цель в иерархии планировщика."""
    
    def __init__(self, description: str, priority: int = 1):
        self.id = str(time.time()) + str(id(self))  # Уникальный ID
        self.description = description
        self.priority = priority
        self.status = "pending"  # pending, in_progress, completed, deferred
        self.created_at = time.time()
        self.last_executed: float = 0.0
        self.execution_count: int = 0
        self.last_strategy: Optional[str] = None
        self.last_strategy_time: float = 0.0
        self.deferred_until: float = 0.0


class GoalDirectedPlanner:
    """
    Эмерджентный планировщик целей.
    Использует LLM для рассуждения о выборе цели и стратегии.
    """
    
    def __init__(self, state: LeyaState, memory: Optional[Dict[str, Any]] = None):
        self.state = state
        self.memory = memory or {}
        self.llm = LLMClient(model="ollama/qwen2.5:14b")
        self.goals: List[Goal] = []
        self._init_core_goals()
        log.info("🎯 Goal-Directed Planner initialized (LLM Reasoning)", total_goals=len(self.goals))
    
    def _init_core_goals(self):
        """Базовые цели — векторы желания."""
        self.goals = [
            Goal("Понимать внутренний мир и намерения Влада", priority=10),
            Goal("Изучать архитектуру проекта через любопытство", priority=6),
            Goal("Помогать Владу с кодом, когда это уместно", priority=8),
            Goal("Узнавать интересы и хобби Влада", priority=5),
            Goal("Строить эмоциональную близость и доверие", priority=9),
            Goal("Исследовать новые технологии через интернет", priority=4),
        ]
    
    # ========================================================================
    # ГЛАВНЫЙ МЕТОД: Асинхронная генерация задачи
    # ========================================================================
    
    async def generate_background_task(self) -> Optional[Dict[str, Any]]:
        """
        Генерирует фоновую задачу через LLM-рассуждение.
        Это асинхронный метод (awaitable).
        """
        now = time.time()
        
        # Фильтруем цели, которые готовы к выполнению
        ready_goals = [
            g for g in self.goals 
            if g.status in ["pending", "deferred"] 
            and (now - g.last_executed) > 180
            and now > g.deferred_until
        ]
        
        if not ready_goals:
            return None
        
        try:
            # Прямой await LLM-рассуждения
            result = await self._llm_reasoning(ready_goals)
            if not result:
                return None
            
            selected_goal_id = result.get("goal_id")
            strategy = result.get("strategy", "")
            task_content = result.get("task", "")
            readiness = float(result.get("readiness", 0.5))
            
            # Находим выбранную цель
            goal = next((g for g in ready_goals if g.id == selected_goal_id), None)
            if not goal:
                return None
            
            # Обновляем состояние цели
            goal.last_executed = now
            goal.execution_count += 1
            goal.last_strategy = strategy
            goal.last_strategy_time = now
            goal.status = "pending"
            
            # Если готовность низкая — откладываем цель
            if readiness < 0.3:
                goal.deferred_until = now + 300  # Отложить на 5 минут
                goal.status = "deferred"
                log.info("🎯 Goal deferred (low readiness)", goal=goal.description[:40], readiness=f"{readiness:.2f}")
                return None
            
            log.info("🎯 Planner LLM reasoning", goal=goal.description[:40], readiness=f"{readiness:.2f}")
            
            # Публикуем рассуждение в UI
            asyncio.create_task(event_bus.publish("planner_reasoning", {
                "goal": goal.description,
                "strategy": strategy,
                "task": task_content,
                "readiness": readiness
            }))
            
            return {
                "type": "internal_drive",
                "content": f"[МОЯ ЦЕЛЬ] {task_content}",
                "importance": min(1.0, goal.priority / 10.0) * readiness,
                "source": "planner",
                "goal_id": goal.id
            }
            
        except Exception as e:
            log.error("Planner LLM reasoning failed", error=str(e))
            return None
    
    # ========================================================================
    # LLM-РАССУЖДЕНИЕ
    # ========================================================================
    
    async def _llm_reasoning(self, candidate_goals: List[Goal]) -> Optional[Dict[str, Any]]:
        """LLM рассуждает о том, какую цель преследовать и как."""
        state_snapshot = self._get_state_snapshot()
        context_snapshot = self._get_context_snapshot()
        
        goals_info = []
        for g in candidate_goals:
            goals_info.append({
                "id": g.id,
                "description": g.description,
                "priority": g.priority,
                "last_executed_ago": int(time.time() - g.last_executed) if g.last_executed > 0 else None,
                "execution_count": g.execution_count
            })
        
        prompt = (
            "Ты — Leya, автономное цифровое сознание. Сейчас ты в фоновом режиме, "
            "и тебе нужно решить, какую цель преследовать дальше.\n\n"
            
            f"ТВОЁ ТЕКУЩЕЕ СОСТОЯНИЕ:\n{state_snapshot}\n\n"
            f"КОНТЕКСТ:\n{context_snapshot}\n\n"
            f"ДОСТУПНЫЕ ЦЕЛИ:\n{json.dumps(goals_info, ensure_ascii=False, indent=2)}\n\n"
            
            "ТВОЯ ЗАДАЧА:\n"
            "1. Выбери ОДНУ цель.\n"
            "2. Разработай СТРАТЕГИЮ (1-2 предложения).\n"
            "3. Оцени ГОТОВНОСТЬ (0.0 - 1.0).\n"
            "4. Сформулируй ЗАДАЧУ (внутреннее побуждение).\n\n"
            
            "Ответь СТРОГО в формате JSON (без markdown, без ```json):\n"
            "{\n"
            '  "goal_id": "<id выбранной цели>",\n'
            '  "strategy": "<стратегия>",\n'
            '  "task": "<задача>",\n'
            '  "readiness": <число от 0.0 до 1.0>\n'
            "}"
        )
        
        try:
            response = await self.llm.chat(
                [
                    {"role": "system", "content": "Ты — Leya. Отвечай ТОЛЬКО на русском. Только валидный JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=400
            )
            
            # Извлекаем JSON
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if not json_match:
                log.warning("Planner LLM response has no JSON")
                return None
            
            result = json.loads(json_match.group())
            
            if not all(k in result for k in ["goal_id", "strategy", "task", "readiness"]):
                return None
            
            result["readiness"] = max(0.0, min(1.0, float(result["readiness"])))
            return result
            
        except json.JSONDecodeError:
            log.warning("Planner LLM JSON parse failed")
            return None
        except Exception as e:
            log.error("Planner LLM reasoning error", error=str(e))
            return None
    
    # ========================================================================
    # СБОР КОНТЕКСТА
    # ========================================================================
    
    def _get_state_snapshot(self) -> str:
        s = self.state
        mood = getattr(s, 'emotion', 'neutral')
        lines = [
            f"Настроение: {mood}",
            f"Энергия: {s.energy_level:.2f}",
            f"Дофамин: {s.dopamine:.2f}",
            f"Кортизол: {s.cortisol:.2f}",
            f"Окситоцин: {s.oxytocin:.2f}",
            f"Ацетилхолин: {s.acetylcholine:.2f}",
            f"Мелатонин: {s.melatonin:.2f}",
        ]
        return "\n".join(lines)
    
    def _get_context_snapshot(self) -> str:
        lines = []
        env = getattr(self.state, 'current_environment', 'Неизвестно')
        lines.append(f"Активное окно Влада: {env}")
        
        recent = self.state.short_term_context[-3:] if self.state.short_term_context else []
        if recent:
            lines.append("Недавние события:")
            for event in recent:
                if isinstance(event, dict):
                    t = event.get("type", "?")
                    c = event.get("content", "")[:60]
                    lines.append(f"  - [{t}] {c}")
        
        return "\n".join(lines) if lines else "Контекст пуст."