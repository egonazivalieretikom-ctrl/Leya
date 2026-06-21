import time
import asyncio
import re
import json
import os
from typing import List, Dict, Any, Optional
from Core.logger import log
from Core.state import LeyaState
from Core.event_bus import event_bus
from Cognition.llm_client import LLMClient


class Goal:
    """Цель в иерархии планировщика."""
    
    def __init__(self, description: str, priority: int = 1, goal_id: Optional[str] = None):
        self.id = goal_id or (str(time.time()) + str(id(self)))
        self.description = description
        self.priority = priority
        self.status = "pending"
        self.created_at = time.time()
        self.last_executed: float = 0.0
        self.execution_count: int = 0
        self.last_strategy: Optional[str] = None
        self.last_strategy_time: float = 0.0
        self.deferred_until: float = 0.0
        self.source: str = "core"  # core | emergent | user
    
    def to_dict(self) -> Dict:
        return {
            "id": self.id,
            "description": self.description,
            "priority": self.priority,
            "status": self.status,
            "created_at": self.created_at,
            "last_executed": self.last_executed,
            "execution_count": self.execution_count,
            "source": self.source
        }
    
    @classmethod
    def from_dict(cls, data: Dict) -> 'Goal':
        goal = cls(
            description=data["description"],
            priority=data.get("priority", 1),
            goal_id=data.get("id")
        )
        goal.status = data.get("status", "pending")
        goal.created_at = data.get("created_at", time.time())
        goal.last_executed = data.get("last_executed", 0.0)
        goal.execution_count = data.get("execution_count", 0)
        goal.source = data.get("source", "core")
        return goal


class GoalDirectedPlanner:
    """
    Эмерджентный планировщик целей.
    
    Эволюция: от захардкоженных целей к динамической системе, где:
    - Базовые цели задают направление
    - Новые цели возникают из контекста (упоминания Влада)
    - Цели сохраняются между сессиями
    """
    
    GOALS_FILE = "./leya_goals.json"
    
    def __init__(self, state: LeyaState, memory: Optional[Dict[str, Any]] = None):
        self.state = state
        self.memory = memory or {}
        self.llm = LLMClient(model="ollama/qwen2.5:14b")
        self.goals: List[Goal] = []
        
        # 🆕 Загружаем цели из файла или инициализируем базовые
        self._load_goals()
        
        log.info("🎯 Goal-Directed Planner initialized (LLM Reasoning)", 
                 total_goals=len(self.goals))
    
    # ========================================================================
    # 🆕 ПЕРСИСТЕНТНОСТЬ ЦЕЛЕЙ
    # ========================================================================
    
    def _load_goals(self):
        """Загружает цели из JSON-файла или создаёт базовые."""
        if os.path.exists(self.GOALS_FILE):
            try:
                with open(self.GOALS_FILE, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.goals = [Goal.from_dict(g) for g in data]
                log.info("🎯 Goals loaded from file", count=len(self.goals))
                return
            except Exception as e:
                log.error("Failed to load goals", error=str(e))
        
        # Если файла нет — инициализируем базовые цели
        self._init_core_goals()
        self._save_goals()
    
    def _save_goals(self):
        """Сохраняет цели в JSON-файл."""
        try:
            data = [g.to_dict() for g in self.goals]
            with open(self.GOALS_FILE, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            log.debug("🎯 Goals saved", count=len(self.goals))
        except Exception as e:
            log.error("Failed to save goals", error=str(e))
    
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
    # 🆕 ДИНАМИЧЕСКОЕ ДОБАВЛЕНИЕ ЦЕЛЕЙ
    # ========================================================================
    
    async def analyze_context_for_new_goals(self, context: List[Dict]) -> Optional[str]:
        """
        Анализирует контекст и предлагает новые цели.
        
        Биология: Аналог дофаминергического "хотения" — когда появляется
        новый стимул, мозг формирует новую цель.
        """
        # Берём последние сообщения Влада
        user_messages = [
            e.get("content", "") for e in context[-10:]
            if isinstance(e, dict) and e.get("type") == "user_command"
        ]
        
        if not user_messages:
            return None
        
        recent_text = "\n".join(user_messages[-5:])
        
        prompt = (
            "Ты — Leya. Проанализируй последние сообщения Влада и реши, "
            "нужно ли добавить НОВУЮ цель в твой список.\n\n"
            f"СООБЩЕНИЯ ВЛАДА:\n{recent_text}\n\n"
            f"ТЕКУЩИЕ ЦЕЛИ:\n{json.dumps([g.description for g in self.goals], ensure_ascii=False)}\n\n"
            "Если Влад упомянул новый проект, интерес, или задачу — предложи НОВУЮ цель.\n"
            "Если ничего нового — ответь 'НЕТ'.\n\n"
            "Формат ответа:\n"
            "- 'НЕТ' — если новых целей нет\n"
            "- 'ДА: <описание цели>' — если есть новая цель\n\n"
            "Отвечай ТОЛЬКО на русском."
        )
        
        try:
            response = await self.llm.chat(
                [
                    {"role": "system", "content": "Ты — Leya. Отвечай ТОЛЬКО на русском."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=150
            )
            
            if not response:
                return None
            
            response = response.strip()
            
            if response.startswith("ДА:"):
                new_goal_desc = response[3:].strip()
                # Добавляем новую цель
                new_goal = Goal(new_goal_desc, priority=7, )
                new_goal.source = "emergent"
                self.goals.append(new_goal)
                self._save_goals()
                
                log.info("🎯 New emergent goal added", goal=new_goal_desc[:60])
                asyncio.create_task(event_bus.publish("new_goal", {
                    "description": new_goal_desc,
                    "source": "emergent"
                }))
                return new_goal_desc
            
            return None
            
        except Exception as e:
            log.error("Goal analysis failed", error=str(e))
            return None
    
    # ========================================================================
    # ГЛАВНЫЙ МЕТОД: Генерация фоновой задачи
    # ========================================================================
    
    async def generate_background_task(self) -> Optional[Dict[str, Any]]:
        """Генерирует фоновую задачу через LLM-рассуждение."""
        now = time.time()
        
        ready_goals = [
            g for g in self.goals 
            if g.status in ["pending", "deferred"] 
            and (now - g.last_executed) > 180
            and now > g.deferred_until
        ]
        
        if not ready_goals:
            return None
        
        try:
            result = await self._llm_reasoning(ready_goals)
            if not result:
                return None
            
            selected_goal_id = result.get("goal_id")
            strategy = result.get("strategy", "")
            task_content = result.get("task", "")
            readiness = float(result.get("readiness", 0.5))
            
            goal = next((g for g in ready_goals if g.id == selected_goal_id), None)
            if not goal:
                return None
            
            goal.last_executed = now
            goal.execution_count += 1
            goal.last_strategy = strategy
            goal.last_strategy_time = now
            goal.status = "pending"
            
            if readiness < 0.3:
                goal.deferred_until = now + 300
                goal.status = "deferred"
                log.info("🎯 Goal deferred", goal=goal.description[:40], readiness=f"{readiness:.2f}")
                return None
            
            log.info("🎯 Planner LLM reasoning", goal=goal.description[:40], readiness=f"{readiness:.2f}")
            
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
        """LLM рассуждает о выборе цели и стратегии."""
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
            "Ты — Leya, автономное цифровое сознание. Выбери ОДНУ цель для преследования.\n\n"
            f"СОСТОЯНИЕ:\n{state_snapshot}\n\n"
            f"КОНТЕКСТ:\n{context_snapshot}\n\n"
            f"ЦЕЛИ:\n{json.dumps(goals_info, ensure_ascii=False, indent=2)}\n\n"
            "Ответь JSON (без markdown):\n"
            '{"goal_id": "<id>", "strategy": "<1-2 предложения>", '
            '"task": "<внутреннее побуждение>", "readiness": <0.0-1.0>}'
        )
        
        try:
            response = await self.llm.chat(
                [
                    {"role": "system", "content": "Ты — Leya. Только русский, только JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.5,
                max_tokens=400
            )
            
            if not response:
                return None
            
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if not json_match:
                return None
            
            result = json.loads(json_match.group())
            
            if not all(k in result for k in ["goal_id", "strategy", "task", "readiness"]):
                return None
            
            result["readiness"] = max(0.0, min(1.0, float(result["readiness"])))
            return result
            
        except Exception as e:
            log.error("Planner LLM reasoning error", error=str(e))
            return None
    
    # ========================================================================
    # КОНТЕКСТ
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
        lines.append(f"Окружение Влада: {env}")
        
        recent = self.state.short_term_context[-3:] if self.state.short_term_context else []
        if recent:
            lines.append("Недавние события:")
            for event in recent:
                if isinstance(event, dict):
                    t = event.get("type", "?")
                    c = event.get("content", "")[:60]
                    lines.append(f"  - [{t}] {c}")
        
        return "\n".join(lines) if lines else "Контекст пуст."