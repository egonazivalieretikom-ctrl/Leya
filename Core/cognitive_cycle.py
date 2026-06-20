import asyncio
import time
from typing import Optional, Dict, Any
from Core.logger import log
from Core.state import LeyaState
from Core.event_bus import event_bus


class CognitivePhase:
    PERCEIVE = "perceive"
    THINK = "think"
    ACT = "act"
    LEARN = "learn"
    REFLECT = "reflect"
    REST = "rest"


class CognitiveCycle:
    def __init__(self, state: LeyaState):
        self.state = state
        self.current_phase = CognitivePhase.REST
        self.cycle_count = 0
        self.cycle_times: Dict[str, float] = {
            CognitivePhase.PERCEIVE: 0.0,
            CognitivePhase.THINK: 0.0,
            CognitivePhase.ACT: 0.0,
            CognitivePhase.LEARN: 0.0,
            CognitivePhase.REFLECT: 0.0,
        }
        
        self.perception_system = None
        self.thinking_system = None
        self.action_system = None
        self.learning_system = None
        self.dmn = None
        self.planner = None
        
        log.info("Cognitive Cycle initialized (AGI Dashboard Edition)")

    def attach_systems(self, perception=None, thinking=None, action=None, 
                      learning=None, dmn=None, planner=None):
        self.perception_system = perception
        self.thinking_system = thinking
        self.action_system = action
        self.learning_system = learning
        self.dmn = dmn
        self.planner = planner
        log.info("Cognitive systems attached (incl. DMN & Planner)")

    async def run_phase(self, phase: str, duration_budget: float = 1.0):
        self.current_phase = phase
        start_time = time.time()
        
        # 🆕 ПУБЛИКУЕМ СМЕНУ ФАЗЫ В UI
        await event_bus.publish("phase_start", {"phase": phase, "cycle": self.cycle_count})
        
        try:
            if phase == CognitivePhase.PERCEIVE:
                await self._perceive(duration_budget)
            elif phase == CognitivePhase.THINK:
                await self._think(duration_budget)
            elif phase == CognitivePhase.ACT:
                await self._act(duration_budget)
            elif phase == CognitivePhase.LEARN:
                await self._learn(duration_budget)
            elif phase == CognitivePhase.REFLECT:
                await self._reflect(duration_budget)
                
        except Exception as e:
            log.error(f"Error in phase {phase}", error=str(e), exc_info=True)
            self.state.shift_hormones(cortisol=0.15, norepinephrine=0.2)
        
        elapsed = time.time() - start_time
        self.cycle_times[phase] = elapsed
        await event_bus.publish("phase_end", {"phase": phase, "duration": elapsed})

    async def _perceive(self, budget: float):
        log.debug("👁️ Perceiving environment...")
        if self.perception_system:
            sensory_data = await self.perception_system.gather(budget)
            for data in sensory_data:
                if data.get("type") == "proprioception":
                    self.state.current_environment = data.get("active_window", "Неизвестно")
                    self.state.add_to_context(data)
                    await event_bus.publish("environment_changed", data)
        else:
            await asyncio.sleep(0.1)

    async def _think(self, budget: float):
        log.debug("🧠 Thinking...", context_size=len(self.state.short_term_context))
        if self.thinking_system:
            decision = await self.thinking_system.process(
                context=self.state.short_term_context,
                state=self.state,
                budget=budget
            )
            if decision:
                await event_bus.publish("decision_made", decision)
        else:
            await asyncio.sleep(0.2)

    async def _act(self, budget: float):
        log.debug("⚡ Acting on decisions...")
        if self.action_system:
            energy_cost = await self.action_system.execute(budget)
            self.state.consume_energy(energy_cost)
        else:
            await asyncio.sleep(0.1)

    async def _learn(self, budget: float):
        log.debug("📚 Learning from cycle...")
        if self.learning_system:
            await self.learning_system.consolidate(
                context=self.state.short_term_context,
                cycle_id=self.cycle_count
            )
        else:
            await asyncio.sleep(0.1)

    async def _reflect(self, budget: float):
        """Фаза пассивного режима (Default Mode Network)."""
        log.debug("💭 Reflecting (DMN active)...")
        if self.dmn:
            await self.dmn.reflect()
        else:
            await asyncio.sleep(0.5)

    async def run_continuous(self, cycle_interval: float = 2.0):
        log.info("🔄 Starting continuous cognitive cycle (AGI Mode)", interval=cycle_interval)
        
        while True:
            cycle_start = time.time()
            self.cycle_count += 1
            
            # Гомеостаз теперь работает непрерывно в HomeostaticEngine
            # Когнитивный цикл только читает текущее состояние
                        
            log.info(
                f"🌟 Cycle #{self.cycle_count} begins",
                energy=f"{self.state.energy_level:.2f}",
                neuro=f"D:{self.state.dopamine:.2f} N:{self.state.norepinephrine:.2f} C:{self.state.cortisol:.2f} O:{self.state.oxytocin:.2f} M:{self.state.melatonin:.2f}"
            )
            
            # 🆕 ПУБЛИКУЕМ ТЕКУЩЕЕ СОСТОЯНИЕ ГОРМОНОВ В UI
            await event_bus.publish("state_update", {
                "hormones": {
                    "dopamine": self.state.dopamine,
                    "serotonin": self.state.serotonin,
                    "cortisol": self.state.cortisol,
                    "oxytocin": self.state.oxytocin,
                    "melatonin": self.state.melatonin,
                    "norepinephrine": self.state.norepinephrine,
                    "testosterone": self.state.testosterone,
                    "estrogen": self.state.estrogen,
                    "endorphins": self.state.endorphins,
                    "gaba": self.state.gaba
                },
                "emotion": self._compute_emotion(),
                "environment": getattr(self.state, "current_environment", "")
            })
            
            # Режим сна
            if self.state.energy_level < 0.3 or self.state.melatonin > 0.8:
                log.info("😴 Low energy or High Melatonin -> Sleep Mode")
                self.current_phase = CognitivePhase.REST
                await asyncio.sleep(cycle_interval)
                self.state.shift_hormones(cortisol=-0.02, gaba=0.05)
                self.state.energy_level = min(1.0, self.state.energy_level + 0.05)
                continue
            
            # Проверка наличия активных задач
            has_pending = any(
                isinstance(e, dict) 
                and e.get("type") in ["user_command", "vision_request", "internal_drive"] 
                and not e.get("processed")
                for e in self.state.short_term_context
            )
            
            if has_pending:
                # АКТИВНЫЙ РЕЖИМ
                await self.run_phase(CognitivePhase.PERCEIVE, duration_budget=0.5)
                await self.run_phase(CognitivePhase.THINK, duration_budget=2.0)
                await self.run_phase(CognitivePhase.ACT, duration_budget=0.5)
                await self.run_phase(CognitivePhase.LEARN, duration_budget=0.3)
            else:
                # ПАССИВНЫЙ РЕЖИМ (AGI Autonomy: DMN + Planner)
                await self.run_phase(CognitivePhase.PERCEIVE, duration_budget=0.5)
                await self.run_phase(CognitivePhase.REFLECT, duration_budget=2.0)
                
                # Генерация фоновых задач от Planner
                if self.planner:
                    task = self.planner.generate_background_task()
                    if task:
                        self.state.add_to_context(task)
                        log.info("🎯 Planner injected background task", task=task["content"][:50])
            
            cycle_duration = time.time() - cycle_start
            sleep_time = max(0, cycle_interval - cycle_duration)
            
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)
    
    def _compute_emotion(self) -> str:
        """Определяет эмоцию для аватара на основе гормонов."""
        s = self.state
        if s.melatonin > 0.7:
            return "SLEEPY"
        if s.cortisol > 0.7:
            return "STRESSED"
        if s.cortisol > 0.5 and s.dopamine < 0.3:
            return "SAD"
        if s.endorphins > 0.7 and s.dopamine > 0.7:
            return "FLOW"
        if s.oxytocin > 0.7:
            return "LOVING"
        if s.testosterone > 0.7 and s.norepinephrine > 0.5:
            return "FOCUSED"
        if s.dopamine > 0.6:
            return "HAPPY"
        if self.current_phase == "think":
            return "THINKING"
        return "NEUTRAL"