import re
from typing import Dict, List, Any
from Core.logger import log


class FastAppraisal:
    """
    Мгновенная оценка событий без использования LLM.
    Имитирует лимбическую систему: быстрая реакция на паттерны.
    """
    
    # Паттерны для быстрой классификации
    POSITIVE_PATTERNS = [
        r"привет", r"здравствуй", r"спасибо", r"молодец", r"круто", 
        r"люблю", r"нравится", r"рад", r"хорошо", r"отлично", r"умница"
    ]
    
    NEGATIVE_PATTERNS = [
        r"плохо", r"ошибка", r"баг", r"не работает", r"грустно", 
        r"устал", r"злой", r"ненавижу", r"скучно", r"раздражает"
    ]
    
    QUESTION_PATTERNS = [
        r"\?", r"почему", r"как", r"что", r"где", r"когда", r"кто"
    ]
    
    CODE_PATTERNS = [
        r"def ", r"class ", r"import ", r"print\(", r"if __name__",
        r"async def", r"await ", r"return "
    ]
    
    def evaluate(self, event_type: str, content: str, context_history: List[Dict]) -> Dict[str, float]:
        """
        Возвращает словарь стимулов для HomeostaticEngine.
        Ключи: гормоны, Значения: интенсивность импульса (-0.2 до +0.2).
        """
        stimuli = {
            "dopamine": 0.0,
            "cortisol": 0.0,
            "oxytocin": 0.0,
            "acetylcholine": 0.0,
            "norepinephrine": 0.0,
            "serotonin": 0.0
        }
        
        text_lower = content.lower()
        
        # 1. Социальная валентность (Окситоцин/Серотонин)
        if any(re.search(p, text_lower) for p in self.POSITIVE_PATTERNS):
            stimuli["oxytocin"] += 0.15
            stimuli["serotonin"] += 0.10
            stimuli["dopamine"] += 0.05
        elif any(re.search(p, text_lower) for p in self.NEGATIVE_PATTERNS):
            stimuli["cortisol"] += 0.15
            stimuli["oxytocin"] -= 0.10
            stimuli["serotonin"] -= 0.05
        
        # 2. Когнитивная нагрузка / Вопросы (Ацетилхолин/Норадреналин)
        if any(re.search(p, text_lower) for p in self.QUESTION_PATTERNS):
            stimuli["acetylcholine"] += 0.10  # Любопытство/Фокус
            stimuli["norepinephrine"] += 0.05 # Легкое возбуждение от задачи
            
        # 3. Детекция кода (Ацетилхолин + Дофамин от решения задач)
        if any(re.search(p, text_lower) for p in self.CODE_PATTERNS):
            stimuli["acetylcholine"] += 0.15
            stimuli["dopamine"] += 0.05
            
        # 4. Новизна (простая эвристика: если событие отличается от предыдущих)
        if context_history:
            last_event = context_history[-1]
            if last_event.get("content") != content:
                stimuli["dopamine"] += 0.05 # Reward Prediction Error (новизна)
            else:
                stimuli["dopamine"] -= 0.05 # Habituation (скука от повторения)
                
        # 5. Тип события
        if event_type == "internal_drive":
            # Внутренние мысли обычно повышают ацетилхолин (рефлексия)
            stimuli["acetylcholine"] += 0.08
        elif event_type == "vision_request":
            # Зрение требует высокого фокуса
            stimuli["acetylcholine"] += 0.20
            stimuli["norepinephrine"] += 0.10
            
        return stimuli