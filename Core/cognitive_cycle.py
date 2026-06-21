import asyncio
import time
from typing import Optional, Dict, Any
from Core.logger import log
from Core.state import LeyaState
from Core.event_bus import event_bus


class CognitivePhase:
    """
    Фазы когнитивного цикла.
    
    PERCEIVE — сбор сенсорных данных
    THINK — обработка событий, генерация ответа
    ACT — выполнение действий
    LEARN — консолидация памяти
    REFLECT — DMN (инсайты, рефлексия)
    STREAM — поток сознания (непрерывный внутренний монолог)
    REST — сон/отдых
    """
    PERCEIVE = "perceive"
    THINK = "think"
    ACT = "act"
    LEARN = "learn"
    REFLECT = "reflect"
    STREAM = "stream"
    REST = "rest"


class CognitiveCycle:
    """
    Когнитивный цикл Leya v0.9.
    
    Эволюция: от реактивного (отвечает на стимулы) к непрерывному
    (генерирует поток сознания даже в тишине).
    
    v0.9: Интеграция Таламуса (фильтрация + объединение сигналов)
    и Sleep Consolidation (формирование личности во сне).
    
    Архитектура:
    - При наличии событий: PERCEIVE → THINK → ACT → LEARN
    - При отсутствии событий: PERCEIVE → THALAMUS → STREAM или REFLECT
    - Во сне: REST + SLEEP CONSOLIDATION
    """
    
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
            CognitivePhase.STREAM: 0.0,
        }
        
        # Подсистемы
        self.perception_system = None
        self.thinking_system = None
        self.action_system = None
        self.learning_system = None
        self.dmn = None
        self.planner = None
        self.stream = None
        self.sleep_consolidation = None
        self.thalamus = None
        
        log.info("Cognitive Cycle initialized (v0.9 - Thalamus + Sleep Integration)")

    def attach_systems(self, perception=None, thinking=None, action=None,
                       learning=None, dmn=None, planner=None, stream=None,
                       sleep_consolidation=None, thalamus=None):
        """Привязывает все подсистемы к когнитивному циклу."""
        self.perception_system = perception
        self.thinking_system = thinking
        self.action_system = action
        self.learning_system = learning
        self.dmn = dmn
        self.planner = planner
        self.stream = stream
        self.sleep_consolidation = sleep_consolidation
        self.thalamus = thalamus
        log.info("Cognitive systems attached (v0.9 - All Phases)")

    # ========================================================================
    # ЗАПУСК ФАЗЫ
    # ========================================================================
    
    async def run_phase(self, phase: str, duration_budget: float = 1.0):
        """Запускает одну фазу когнитивного цикла."""
        self.current_phase = phase
        start_time = time.time()
        
        # Публикуем смену фазы в UI
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
            elif phase == CognitivePhase.STREAM:
                await self._stream(duration_budget)
                
        except Exception as e:
            log.error(f"Error in phase {phase}", error=str(e), exc_info=True)
            # При ошибке — стрессовый стимул через гомеостаз
            if hasattr(self, 'homeostasis') and self.homeostasis:
                self.homeostasis.apply_stimulus("cortisol", 0.1)
        
        elapsed = time.time() - start_time
        self.cycle_times[phase] = elapsed
        await event_bus.publish("phase_end", {"phase": phase, "duration": elapsed})

    # ========================================================================
    # РЕАЛИЗАЦИЯ ФАЗ
    # ========================================================================
    
    async def _perceive(self, budget: float):
        """
        Сбор сенсорных данных из окружения.
        
        Биология: Аналог зрительной коры — обработка всех типов сенсорных входов.
        """
        log.debug("👁️ Perceiving environment...")
        if self.perception_system:
            sensory_data = await self.perception_system.gather(budget)
            
            for data in sensory_data:
                if not isinstance(data, dict):
                    continue
                
                data_type = data.get("type")
                
                # Обрабатываем ВСЕ типы сенсорных данных
                if data_type == "proprioception":
                    # Проприоцепция — знание о среде ПК
                    self.state.current_environment = data.get("active_window", "Неизвестно")
                    self.state.add_to_context(data)
                    await event_bus.publish("environment_changed", data)
                    log.debug("🖥️ Environment updated", window=self.state.current_environment)
                
                elif data_type == "file_context":
                    # Файловый контекст — Leya видит код
                    self.state.add_to_context(data)
                    await event_bus.publish("file_context", data)
                    log.info(
                        "📄 File perceived",
                        name=data.get("file_name", "?"),
                        language=data.get("language", "?")
                    )
                
                elif data_type == "vision":
                    # Визуальный вход (камера)
                    self.state.add_to_context(data)
                    await event_bus.publish("vision_input", data)
                
                else:
                    # Другие типы сенсорных данных
                    self.state.add_to_context(data)
        else:
            await asyncio.sleep(0.1)

    async def _think(self, budget: float):
        """Обработка событий и генерация ответа."""
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
        """Выполнение действий."""
        log.debug("⚡ Acting on decisions...")
        if self.action_system:
            energy_cost = await self.action_system.execute(budget)
            self.state.consume_energy(energy_cost)
        else:
            await asyncio.sleep(0.1)

    async def _learn(self, budget: float):
        """Консолидация памяти."""
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

    async def _stream(self, budget: float):
        """
        Фаза потока сознания.
        
        Генерирует субъективную мысль, которая:
        - Зависит от текущего настроения
        - Влияет на состояние (эмоциональная обратная связь)
        - Сохраняется в память
        - Публикуется в UI
        """
        log.debug("🌊 Stream of consciousness...")
        if self.stream:
            thought = await self.stream.generate_stream()
            if thought:
                log.info("🌊 Stream generated", thought=thought[:80])
        else:
            await asyncio.sleep(0.3)

    # ========================================================================
    # ГЛАВНЫЙ НЕПРЕРЫВНЫЙ ЦИКЛ
    # ========================================================================
    
    async def run_continuous(self, cycle_interval: float = 2.0):
        """
        Непрерывный когнитивный цикл.
        
        v0.9: Интеграция Таламуса и Sleep Consolidation.
        
        Логика:
        - Если есть необработанные события → активный режим (PERCEIVE → THINK → ACT → LEARN)
        - Если событий нет → пассивный режим (PERCEIVE → THALAMUS → STREAM или REFLECT)
        - Во сне → REST + SLEEP CONSOLIDATION
        """
        log.info("🔄 Starting continuous cognitive cycle (v0.9 - Thalamus + Sleep)", 
                 interval=cycle_interval)
        
        # Счётчик для чередования STREAM и REFLECT
        passive_cycle_counter = 0
        
        while True:
            cycle_start = time.time()
            self.cycle_count += 1
            
            log.info(
                f"🌟 Cycle #{self.cycle_count} begins",
                energy=f"{self.state.energy_level:.2f}",
                mood=str(getattr(self.state, 'emotion', 'neutral')),
                neuro=f"D:{self.state.dopamine:.2f} N:{self.state.norepinephrine:.2f} "
                      f"C:{self.state.cortisol:.2f} O:{self.state.oxytocin:.2f} "
                      f"A:{self.state.acetylcholine:.2f} M:{self.state.melatonin:.2f}"
            )
            
            # Публикуем текущее состояние в UI (для Dashboard)
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
                    "gaba": self.state.gaba,
                },
                "emotion": str(getattr(self.state, 'emotion', 'neutral')),
                "environment": getattr(self.state, 'current_environment', '')
            })
            
            # ====================================================================
            # РЕЖИМ СНА + КОНСОЛИДАЦИЯ
            # ====================================================================
            if self.state.energy_level < 0.3 or self.state.melatonin > 0.8:
                log.info("😴 Sleep Mode activated")
                self.current_phase = CognitivePhase.REST
                
                # 🆕 Запускаем консолидацию опыта (если ещё не запускали недавно)
                if self.sleep_consolidation:
                    consolidation_result = await self.sleep_consolidation.consolidate_experience()
                    if consolidation_result:
                        log.info(
                            "🌙 Consolidation complete",
                            insights=len(consolidation_result.get("insights", []))
                        )
                
                await asyncio.sleep(cycle_interval)
                # Во сне восстанавливаем энергию
                self.state.energy_level = min(1.0, self.state.energy_level + 0.05)
                continue
            
            # ====================================================================
            # ПРОВЕРКА НАЛИЧИЯ АКТИВНЫХ ЗАДАЧ
            # ====================================================================
            has_pending = any(
                isinstance(e, dict)
                and e.get("type") in ["user_command", "vision_request", "internal_drive"]
                and not e.get("processed")
                for e in self.state.short_term_context
            )
            
            if has_pending:
                # ============================================================
                # АКТИВНЫЙ РЕЖИМ: обработка событий
                # ============================================================
                await self.run_phase(CognitivePhase.PERCEIVE, duration_budget=0.5)
                await self.run_phase(CognitivePhase.THINK, duration_budget=2.0)
                await self.run_phase(CognitivePhase.ACT, duration_budget=0.5)
                await self.run_phase(CognitivePhase.LEARN, duration_budget=0.3)
                # Сбрасываем счётчик пассивного режима
                passive_cycle_counter = 0
            else:
                # ============================================================
                # ПАССИВНЫЙ РЕЖИМ: Таламус + непрерывный внутренний опыт
                # ============================================================
                await self.run_phase(CognitivePhase.PERCEIVE, duration_budget=0.5)
                
                # 🆕 ШАГ 1: Сбор всех фоновых сигналов
                background_signals = []
                
                # Поток сознания
                if self.stream:
                    stream_thought = await self.stream.generate_stream()
                    if stream_thought:
                        background_signals.append({
                            "type": "stream_thought",
                            "content": stream_thought,
                            "timestamp": time.time()
                        })
                
                # DMN инсайты (каждый 3-й цикл)
                passive_cycle_counter += 1
                if passive_cycle_counter % 3 == 0:
                    if self.dmn:
                        dmn_insight = await self.dmn.reflect()
                        if dmn_insight:
                            background_signals.append({
                                "type": "dmn_insight",
                                "content": dmn_insight,
                                "timestamp": time.time()
                            })
                
                # 🆕 ШАГ 2: Фильтрация + Объединение через Таламус
                if self.thalamus and background_signals:
                    merged_signals = self.thalamus.filter_and_merge(background_signals)
                    
                    # Добавляем объединённые сигналы в контекст
                    for signal in merged_signals:
                        self.state.add_to_context(signal)
                        log.info(
                            "🚦 Signal passed to Workspace",
                            type=signal.get("type"),
                            importance=f"{signal.get('importance', 0):.2f}",
                            has_merged_contexts="merged_contexts" in signal
                        )
                else:
                    # Если таламуса нет — добавляем всё (старое поведение)
                    for signal in background_signals:
                        self.state.add_to_context(signal)
                
                # Генерация фоновых задач от Planner
                if self.planner:
                    task = await self.planner.generate_background_task()
                    if task:
                        # 🆕 Пропускаем задачу через Таламус
                        if self.thalamus:
                            filtered_task = self.thalamus.filter_and_merge([task])
                            if filtered_task:
                                self.state.add_to_context(filtered_task[0])
                                log.info(
                                    "🎯 Planner task passed to Workspace",
                                    task=filtered_task[0]["content"][:60],
                                    importance=f"{filtered_task[0].get('importance', 0):.2f}"
                                )
                        else:
                            self.state.add_to_context(task)
                            log.info(
                                "🎯 Planner injected background task",
                                task=task["content"][:60],
                                importance=f"{task['importance']:.2f}"
                            )
            
            # ====================================================================
            # ПАУЗА МЕЖДУ ЦИКЛАМИ
            # ====================================================================
            cycle_duration = time.time() - cycle_start
            sleep_time = max(0, cycle_interval - cycle_duration)
            
            if sleep_time > 0:
                await asyncio.sleep(sleep_time)