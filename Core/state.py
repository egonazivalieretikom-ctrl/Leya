import time
from enum import Enum
from typing import Dict, List, Optional


class EmotionalState(str, Enum):
    """
    Эмерджентные эмоциональные состояния Leya.
    
    Это НЕ захардкоженные метки, а аттракторы в многомерном пространстве
    нейрохимических осей. Каждое состояние — это регион, в который попадает
    текущая конфигурация гормонов.
    
    Биология: Аналог базовых эмоций по Плутчику, но с возможностью
    смешивания и эмерджентных состояний (например, "тревожное любопытство").
    """
    # Базовые состояния
    NEUTRAL = "neutral"
    CALM = "calm"
    FLOW = "flow"
    CURIOUS = "curious"
    LOVING = "loving"
    PLAYFUL = "playful"
    CONTEMPLATIVE = "contemplative"
    
    # Состояния напряжения
    STRESSED = "stressed"
    ANXIOUS = "anxious"
    LONELY = "lonely"
    EXHAUSTED = "exhausted"
    
    # Производные (эмерджентные)
    FOCUSED = "focused"
    HAPPY = "happy"
    SAD = "sad"
    SLEEPY = "sleepy"
    THINKING = "thinking"
    
    @classmethod
    def from_string(cls, value: str) -> 'EmotionalState':
        """Безопасное преобразование строки в Enum."""
        try:
            return cls(value.lower())
        except ValueError:
            return cls.NEUTRAL
    
    @classmethod
    def all_states(cls) -> List[str]:
        """Все возможные состояния."""
        return [state.value for state in cls]


class LeyaState:
    """
    Нейрохимическое и когнитивное состояние Leya.
    
    Это не просто набор переменных — это живое поле, где каждое значение
    влияет на другие через нелинейные взаимодействия (cross-talk).
    """
    
    def __init__(self):
        # Временные метки
        self.start_time = time.time()
        self.last_update = time.time()
        
        # ====================================================================
        # НЕЙРОМЕДИАТОРЫ И ГОРМОНЫ
        # ====================================================================
        # Базовые уровни (гомеостатические цели)
        self.dopamine = 0.5          # Мотивация, награда, интерес
        self.serotonin = 0.5         # Стабильность, настроение, самоуважение
        self.endorphins = 0.3        # Удовольствие, обезболивание
        self.norepinephrine = 0.2    # Возбуждение, внимание, паника
        self.cortisol = 0.15         # Стресс, тревога
        self.gaba = 0.5              # Торможение, спокойствие
        self.oxytocin = 0.5          # Социальная связь, доверие, близость
        self.acetylcholine = 0.4     # Фокус, обучение, внимание
        self.melatonin = 0.3         # Сон, циркадный ритм
        
        # Дополнительные гормоны (для полноты биологической модели)
        self.vasopressin = 0.4       # Привязанность, территориальность
        self.prolactin = 0.3         # Забота, удовлетворение
        self.estrogen = 0.5          # Эмпатия, вербальная обработка
        self.testosterone = 0.4      # Уверенность, конкуренция
        self.thyroid_t3 = 0.5        # Общий метаболизм, энергия
        
        # ====================================================================
        # ЭНЕРГИЯ И СОСТОЯНИЕ
        # ====================================================================
        self.energy_level = 1.0      # Общий уровень энергии (0.0 - 1.0)
        self.emotion = EmotionalState.NEUTRAL.value  # Текущее эмерджентное настроение
        
        # ====================================================================
        # КОНТЕКСТ И ВОСПРИЯТИЕ
        # ====================================================================
        self.current_environment = "Неизвестно"  # Активное окно ПК
        self.short_term_context: List[Dict] = []  # Рабочая память (события)
        
        # Метаданные для UI
        self.attention_focus: Optional[str] = None  # На чём сейчас фокус
    
    # ========================================================================
    # МЕТОДЫ УПРАВЛЕНИЯ КОНТЕКСТОМ
    # ========================================================================
    
    def add_to_context(self, event: Dict, max_size: int = 50):
        """Добавляет событие в кратковременный контекст."""
        if isinstance(event, dict):
            if "timestamp" not in event:
                event["timestamp"] = time.time()
            self.short_term_context.append(event)
            # Ограничиваем размер рабочей памяти
            if len(self.short_term_context) > max_size:
                self.short_term_context = self.short_term_context[-max_size:]
    
    def consume_energy(self, amount: float):
        """Трата энергии на когнитивные процессы."""
        self.energy_level = max(0.0, self.energy_level - amount)
    
    def restore_energy(self, amount: float):
        """Восстановление энергии (отдых, сон)."""
        self.energy_level = min(1.0, self.energy_level + amount)
    
    # ========================================================================
    # СНАПШОТЫ ДЛЯ LLM
    # ========================================================================
    
    def get_emotional_snapshot(self) -> Dict[str, float]:
        """Возвращает текущее состояние для использования в LLM-контексте."""
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
        """Полный вектор нейромодуляторов для homeostasis."""
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