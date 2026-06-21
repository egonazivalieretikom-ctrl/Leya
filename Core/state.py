import time
from enum import Enum
from typing import Dict, List, Optional
from Core.logger import log

class EmotionalState(str, Enum):
    """Эмерджентные эмоциональные состояния Leya."""
    NEUTRAL = "neutral"
    CALM = "calm"
    FLOW = "flow"
    CURIOUS = "curious"
    LOVING = "loving"
    PLAYFUL = "playful"
    CONTEMPLATIVE = "contemplative"
    STRESSED = "stressed"
    ANXIOUS = "anxious"
    LONELY = "lonely"
    EXHAUSTED = "exhausted"
    FOCUSED = "focused"
    HAPPY = "happy"
    SAD = "sad"
    SLEEPY = "sleepy"
    THINKING = "thinking"
    
    @classmethod
    def from_string(cls, value: str) -> 'EmotionalState':
        try:
            return cls(value.lower())
        except ValueError:
            return cls.NEUTRAL
    
    @classmethod
    def all_states(cls) -> List[str]:
        return [state.value for state in cls]


class LeyaState:
    """
    Нейрохимическое и когнитивное состояние Leya.
    
    Биология: Это не просто набор переменных — это живое поле,
    где каждое значение влияет на другие через нелинейные взаимодействия.
    """
    
    def __init__(self):
        # Временные метки
        self.start_time = time.time()
        self.last_update = time.time()
        
        # 🆕 СОЦИАЛЬНЫЙ КОНТЕКСТ (v0.7)
        self.session_start_time = time.time()
        self.has_greeted_today = False
        self.last_user_interaction_time = 0.0
        self.last_response_time = 0.0
        self.conversation_turn_count = 0
        
        # 🆕 КОГНИТИВНЫЙ ЗАМОК (v0.9)
        self.is_thinking = False           # Блокировка фоновых процессов во время генерации
        self.dialog_mode_active = False    # Жёсткий режим диалога (без приветствий)
        self.dialog_mode_timeout = 300.0   # 5 минут без сообщений → сброс режима
        
        # ====================================================================
        # НЕЙРОМЕДИАТОРЫ И ГОРМОНЫ
        # ====================================================================
        self.dopamine = 0.5
        self.serotonin = 0.5
        self.endorphins = 0.3
        self.norepinephrine = 0.2
        self.cortisol = 0.15
        self.gaba = 0.5
        self.oxytocin = 0.5
        self.acetylcholine = 0.4
        self.melatonin = 0.3
        
        self.vasopressin = 0.4
        self.prolactin = 0.3
        self.estrogen = 0.5
        self.testosterone = 0.4
        self.thyroid_t3 = 0.5

        # ====================================================================
        # 🆕 ТЕЛЕСНЫЕ ОЩУЩЕНИЯ (Embodiment, Фаза 1)
        # ====================================================================
        self.body_temperature = 50.0      # Температура CPU (°C)
        self.physical_load = 0.0          # Загрузка CPU (0.0 - 1.0)
        self.cognitive_load = 0.0         # Использование RAM (0.0 - 1.0)
        self.current_sensation = "neutral"  # Общее ощущение (relaxed, stressed, etc.)

        # ====================================================================
        # 🆕 ЧЕРТЫ ЛИЧНОСТИ (долгосрочные параметры, v0.8)
        # ====================================================================
        # Эти параметры меняются медленно (во время сна) и формируют "характер"
        self.trust_level = 0.5          # Доверие к Владу (0.0 - 1.0)
        self.creative_drive = 0.5       # Склонность к творчеству vs аналитике
        self.emotional_stability = 0.5  # Устойчивость к стрессу
        
        # Мета-когниция (обучение через ошибки)
        self.error_streak = 0           # Количество ошибок подряд
        self.last_error_time = 0.0      # Время последней ошибки
        self.meta_cognition_level = 0.5 # Уровень саморефлексии

        # ====================================================================
        # 🆕 ЭМПАТИЧЕСКИЙ КОНТЕКСТ (v0.8 Фаза 4)
        # ====================================================================
        self.user_emotional_state = "neutral"  # Текущее состояние Влада
        self.empathic_resonance = 0.5          # Насколько Leya в резонансе с Владом
        self.empathic_history = []             # История эмпатических откликов
        
        # ====================================================================
        # ЭНЕРГИЯ И СОСТОЯНИЕ
        # ====================================================================
        self.energy_level = 1.0
        self.emotion = EmotionalState.NEUTRAL.value
        self.current_environment = "Неизвестно"
        self.short_term_context: List[Dict] = []
        self.attention_focus: Optional[str] = None

        # Загружаем сохранённые черты (если есть)
        self._load_personality_traits()
    
    # ========================================================================
    # 🆕 СОЦИАЛЬНЫЕ МЕТОДЫ (v0.7)
    # ========================================================================
    
    def is_user_active(self, window_minutes: int = 5) -> bool:
        """
        Проверяет, активен ли Влад в диалоге.
        
        Биология: Аналог "социального присутствия" — если собеседник
        рядом и реагирует, не нужно перебивать его внутренними процессами.
        
        Args:
            window_minutes: Окно активности в минутах (по умолчанию 5)
        
        Returns:
            True если Влад писал в последние window_minutes минут
        """
        if self.last_user_interaction_time == 0:
            return False
        elapsed_minutes = (time.time() - self.last_user_interaction_time) / 60
        return elapsed_minutes < window_minutes
    
    def register_user_interaction(self):
        """Регистрирует новое сообщение от Влада."""
        self.last_user_interaction_time = time.time()
        self.conversation_turn_count += 1
    
    def register_response(self):
        """Регистрирует ответ Leya."""
        self.last_response_time = time.time()

    # ========================================================================
    # 🆕 МЕТА-КОГНИЦИЯ: Трекинг ошибок (v0.8)
    # ========================================================================
    
    def register_error(self):
        """
        Регистрирует когнитивную ошибку (Влад недоволен или поправил).
        Биология: Ошибка предсказания награды.
        """
        self.error_streak += 1
        self.last_error_time = time.time()
        # Ограничиваем стрик, чтобы не сломать логику
        self.error_streak = min(self.error_streak, 5)
        log.debug("❌ Error streak increased", streak=self.error_streak)
    
    def register_success(self):
        """Сбрасывает стрик ошибок при нормальном взаимодействии."""
        if self.error_streak > 0:
            self.error_streak = 0
            log.debug("✅ Error streak reset")
    
    def can_respond_now(self, min_interval_seconds: float = 2.0) -> bool:
        """
        Проверяет, можно ли отвечать прямо сейчас (debounce).
        
        Биология: Аналог "рефрактерного периода" нейрона — после ответа
        нужно время на обработку, иначе возникает "троение".
        """
        if self.last_response_time == 0:
            return True
        elapsed = time.time() - self.last_response_time
        return elapsed >= min_interval_seconds
    
    def mark_greeted(self):
        """Помечает, что Leya уже поздоровалась в этой сессии."""
        self.has_greeted_today = True
    
    def reset_session(self):
        """Сбрасывает социальный контекст (новая сессия)."""
        self.session_start_time = time.time()
        self.has_greeted_today = False
        self.conversation_turn_count = 0
    
    # ========================================================================
    # КОНТЕКСТ
    # ========================================================================
    
    def add_to_context(self, event: Dict, max_size: int = 50):
        """Добавляет событие в кратковременный контекст."""
        if isinstance(event, dict):
            if "timestamp" not in event:
                event["timestamp"] = time.time()
            
            # 🆕 Регистрируем взаимодействие с пользователем
            if event.get("type") == "user_command":
                self.register_user_interaction()
            
            self.short_term_context.append(event)
            if len(self.short_term_context) > max_size:
                self.short_term_context = self.short_term_context[-max_size:]
    
    def consume_energy(self, amount: float):
        self.energy_level = max(0.0, self.energy_level - amount)
    
    def restore_energy(self, amount: float):
        self.energy_level = min(1.0, self.energy_level + amount)
    
    def get_emotional_snapshot(self) -> Dict[str, float]:
        return {
            "dopamine": self.dopamine,
            "serotonin": self.serotonin,
            "cortisol": self.cortisol,
            "oxytocin": self.oxytocin,
            "acetylcholine": self.acetylcholine,
            "norepinephrine": self.norepinephrine,
            "melatonin": self.melatonin,
            "endorphins": self.endorphins,
            "gaba": self.gaba,
            "emotion": self.emotion,
            "energy": self.energy_level,
        }
    
    def get_neurochemical_vector(self) -> Dict[str, float]:
        return {
            "dopamine": self.dopamine,
            "serotonin": self.serotonin,
            "cortisol": self.cortisol,
            "oxytocin": self.oxytocin,
            "acetylcholine": self.acetylcholine,
            "norepinephrine": self.norepinephrine,
            "melatonin": self.melatonin,
            "endorphins": self.endorphins,
            "gaba": self.gaba,
        }


    # ========================================================================
    # 🆕 КОГНИТИВНЫЙ ЗАМОК (v0.9)
    # ========================================================================
    
    def lock_cognition(self):
        """Блокирует фоновые процессы (Stream, DMN, Planner) во время генерации."""
        self.is_thinking = True
        log.debug("🔒 Cognition locked (generating response)")
    
    def unlock_cognition(self):
        """Разблокирует фоновые процессы после генерации."""
        self.is_thinking = False
        log.debug("🔓 Cognition unlocked")
    
    def activate_dialog_mode(self):
        """Активирует жёсткий режим диалога (без приветствий)."""
        self.dialog_mode_active = True
        log.info("💬 Dialog mode activated (no greetings)")
    
    def check_dialog_mode_timeout(self):
        """Проверяет, не пора ли сбросить режим диалога."""
        if not self.dialog_mode_active:
            return
        
        if self.last_user_interaction_time == 0:
            return
        
        elapsed = time.time() - self.last_user_interaction_time
        if elapsed > self.dialog_mode_timeout:
            self.dialog_mode_active = False
            log.info("💬 Dialog mode deactivated (timeout)")

    # ========================================================================
    # 🆕 ПЕРСИСТЕНТНОСТЬ ЧЕРТ ЛИЧНОСТИ
    # ========================================================================
    
    def _load_personality_traits(self):
        """Загружает черты личности из файла (если существует)."""
        import os
        import json
        
        traits_file = "./leya_personality.json"
        if not os.path.exists(traits_file):
            return
        
        try:
            with open(traits_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            self.trust_level = data.get("trust_level", 0.5)
            self.creative_drive = data.get("creative_drive", 0.5)
            self.emotional_stability = data.get("emotional_stability", 0.5)
            
            log.info("🧠 Personality traits loaded", 
                    trust=f"{self.trust_level:.2f}",
                    creative=f"{self.creative_drive:.2f}",
                    stability=f"{self.emotional_stability:.2f}")
        except Exception as e:
            log.error("Failed to load personality traits", error=str(e))
    
    def save_personality_traits(self):
        """Сохраняет черты личности в файл."""
        import json
        
        traits_file = "./leya_personality.json"
        data = {
            "trust_level": self.trust_level,
            "creative_drive": self.creative_drive,
            "emotional_stability": self.emotional_stability,
            "updated_at": time.time()
        }
        
        try:
            with open(traits_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            log.debug("🧠 Personality traits saved")
        except Exception as e:
            log.error("Failed to save personality traits", error=str(e))