import time
from typing import List, Dict, Any, Optional
from Core.logger import log
from Core.state import LeyaState


class Thalamus:
    """
    Таламус Leya — центр фильтрации и торможения.
    
    Биология: Таламус получает ВСЕ сенсорные сигналы, но пропускает
    в кору (LLM) только самые важные. Это создаёт "прожектор внимания"
    и предотвращает когнитивный шум.
    
    Функции:
    1. Фильтрация: Отсеивает шум (повторяющиеся инсайты, слабые стимулы)
    2. Приоритизация: Решает, что важнее — эмоция, мысль или воспоминание
    3. Торможение: Блокирует фоновые процессы во время фокуса
    """
    
    def __init__(self, state: LeyaState):
        self.state = state
        
        # Параметры фильтрации
        self.noise_threshold = 0.3      # Сигналы ниже этого порога отсеиваются
        self.repetition_penalty = 0.5   # Штраф за повторение одного типа сигнала
        self.max_workspace_items = 3    # Максимум элементов в Global Workspace
        
        # История отфильтрованных сигналов (для детекции повторов)
        self.recent_signals: List[Dict] = []
        self.max_history = 20
        
        log.info("🚦 Thalamus initialized (Sensory Filter + Inhibition)")
    
    # ========================================================================
    # ГЛАВНЫЙ МЕТОД: Фильтрация сигналов
    # ========================================================================
    
    def filter_signals(self, signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Фильтрует входящие сигналы и возвращает только самые важные.
        
        Args:
            signals: Список всех входящих сигналов (мысли, воспоминания, стимулы)
        
        Returns:
            Отфильтрованный список (только то, что попадёт в Global Workspace)
        """
        if not signals:
            return []
        
        filtered = []
        
        for signal in signals:
            # 1. Вычисляем важность сигнала
            importance = self._compute_importance(signal)
            
            # 2. Применяем штраф за повторение
            repetition_penalty = self._compute_repetition_penalty(signal)
            final_importance = importance * repetition_penalty
            
            # 3. Фильтруем по порогу
            if final_importance < self.noise_threshold:
                log.debug("🚦 Signal filtered (too weak)", 
                         type=signal.get("type"), 
                         importance=f"{final_importance:.2f}")
                continue
            
            # 4. Добавляем в отфильтрованный список
            signal["importance"] = final_importance
            filtered.append(signal)
        
        # 5. Сортируем по важности и берём топ-N
        filtered.sort(key=lambda x: x.get("importance", 0), reverse=True)
        result = filtered[:self.max_workspace_items]
        
        # 6. Обновляем историю
        self.recent_signals.extend(result)
        if len(self.recent_signals) > self.max_history:
            self.recent_signals = self.recent_signals[-self.max_history:]
        
        log.debug("🚦 Thalamus filtered", 
                 input_count=len(signals), 
                 output_count=len(result))
        
        return result
    
    # ========================================================================
    # ВЫЧИСЛЕНИЕ ВАЖНОСТИ
    # ========================================================================
    
    def _compute_importance(self, signal: Dict[str, Any]) -> float:
        """
        Вычисляет важность сигнала на основе его типа и контекста.
        
        Биология: Аналог "значимости стимула" — громкий звук важнее шёпота,
        боль важнее прикосновения одежды.
        """
        signal_type = signal.get("type", "unknown")
        content = signal.get("content", "")
        
        # Базовая важность по типу
        base_importance = {
            "user_command": 1.0,           # Сообщения пользователя — ВСЕГДА важны
            "vision_request": 0.9,         # Визуальные запросы — очень важны
            "error_correction": 0.85,      # Ошибки — критически важны
            "internal_drive": 0.6,         # Внутренние драйвы — умеренно важны
            "dmn_insight": 0.5,            # Инсайты DMN — зависят от контекста
            "stream_thought": 0.4,         # Мысли потока — низкий приоритет
            "flashback": 0.45,             # Воспоминания — умеренный приоритет
            "need": 0.55,                  # Потребности — зависят от срочности
        }.get(signal_type, 0.3)
        
        # Модификаторы важности
        
        # 1. Эмоциональный заряд (если есть)
        emotional_charge = signal.get("emotional_charge", 0.0)
        base_importance += abs(emotional_charge) * 0.3
        
        # 2. Срочность (для потребностей)
        urgency = signal.get("urgency", 0.0)
        if urgency > 0:
            base_importance += urgency * 0.4
        
        # 3. Новизна (если сигнал о чём-то новом)
        is_novel = signal.get("is_novel", False)
        if is_novel:
            base_importance += 0.2
        
        # 4. Связь с текущим фокусом внимания
        attention_focus = getattr(self.state, 'attention_focus', None)
        if attention_focus and attention_focus in content:
            base_importance += 0.3
        
        return max(0.0, min(1.0, base_importance))
    
    # ========================================================================
    # ШТРАФ ЗА ПОВТОРЕНИЕ (Торможение)
    # ========================================================================
    
    def _compute_repetition_penalty(self, signal: Dict[str, Any]) -> float:
        """
        Вычисляет штраф за повторение одного типа сигнала.
        
        Биология: Аналог "habituation" — мозг перестаёт реагировать
        на повторяющиеся стимулы (тиканье часов, прикосновение одежды).
        """
        signal_type = signal.get("type", "unknown")
        content = signal.get("content", "")[:50]  # Берём первые 50 символов
        
        # Считаем, сколько раз этот тип сигнала появлялся недавно
        recent_count = sum(
            1 for s in self.recent_signals[-10:]
            if s.get("type") == signal_type and s.get("content", "")[:50] == content
        )
        
        # Применяем штраф
        if recent_count == 0:
            return 1.0  # Новый сигнал — нет штрафа
        elif recent_count == 1:
            return 0.8  # Одно повторение — лёгкий штраф
        elif recent_count == 2:
            return 0.5  # Два повторения — средний штраф
        else:
            return 0.2  # Много повторений — сильный штраф (торможение)
    
    # ========================================================================
    # УПРАВЛЕНИЕ ФОКУСОМ ВНИМАНИЯ
    # ========================================================================
    
    def set_attention_focus(self, focus: str):
        """Устанавливает текущий фокус внимания."""
        self.state.attention_focus = focus
        log.debug("🚦 Attention focus set", focus=focus[:50])
    
    def clear_attention_focus(self):
        """Очищает фокус внимания."""
        self.state.attention_focus = None
        log.debug("🚦 Attention focus cleared")