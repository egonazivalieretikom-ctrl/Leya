import time
from typing import List, Dict, Any, Optional
from Core.logger import log
from Core.state import LeyaState


class Thalamus:
    """
    Таламус Leya — центр фильтрации и объединения сигналов.
    
    Биология: Таламус не просто фильтрует — он объединяет связанные сигналы
    в единое восприятие. Это создаёт "целостную картину" вместо фрагментов.
    
    Функции:
    1. Фильтрация: Отсеивает шум (повторяющиеся инсайты, слабые стимулы)
    2. Объединение: Сливает связанные сигналы (сообщение + изменение окна)
    3. Приоритизация: Решает, что важнее — эмоция, мысль или воспоминание
    """
    
    def __init__(self, state: LeyaState):
        self.state = state
        
        # Параметры фильтрации
        self.noise_threshold = 0.3
        self.repetition_penalty = 0.5
        self.max_workspace_items = 5  # Увеличили с 3 до 5
        
        # История отфильтрованных сигналов
        self.recent_signals: List[Dict] = []
        self.max_history = 20
        
        log.info("🚦 Thalamus initialized (Filter + Merge + Prioritize)")
    
    # ========================================================================
    # ГЛАВНЫЙ МЕТОД: Фильтрация + Объединение
    # ========================================================================
    
    def filter_and_merge(self, signals: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Фильтрует и объединяет связанные сигналы.
        
        Пример: Если пришло "user_command: Привет" и "environment_changed: VS Code",
        таламус объединит их в единый сигнал:
        "user_command: Привет + environment_context: VS Code"
        """
        if not signals:
            return []
        
        # 1. Фильтрация по важности
        filtered = self._filter_by_importance(signals)
        
        # 2. 🆕 Объединение связанных сигналов
        merged = self._merge_related_signals(filtered)
        
        # 3. Сортировка по важности и ограничение
        merged.sort(key=lambda x: x.get("importance", 0), reverse=True)
        result = merged[:self.max_workspace_items]
        
        # 4. Обновление истории
        self.recent_signals.extend(result)
        if len(self.recent_signals) > self.max_history:
            self.recent_signals = self.recent_signals[-self.max_history:]
        
        log.debug("🚦 Thalamus processed", 
                 input_count=len(signals), 
                 filtered_count=len(filtered),
                 merged_count=len(result))
        
        return result
    
    # ========================================================================
    # ФИЛЬТРАЦИЯ ПО ВАЖНОСТИ
    # ========================================================================
    
    def _filter_by_importance(self, signals: List[Dict]) -> List[Dict]:
        """Отсеивает слабые сигналы."""
        filtered = []
        
        for signal in signals:
            importance = self._compute_importance(signal)
            repetition_penalty = self._compute_repetition_penalty(signal)
            final_importance = importance * repetition_penalty
            
            if final_importance < self.noise_threshold:
                log.debug("🚦 Signal filtered", 
                         type=signal.get("type"), 
                         importance=f"{final_importance:.2f}")
                continue
            
            signal["importance"] = final_importance
            filtered.append(signal)
        
        return filtered
    
    def _compute_importance(self, signal: Dict[str, Any]) -> float:
        """Вычисляет важность сигнала."""
        signal_type = signal.get("type", "unknown")
        content = signal.get("content", "")
        
        # Базовая важность по типу
        base_importance = {
            "user_command": 1.0,
            "vision_request": 0.9,
            "error_correction": 0.85,
            "internal_drive": 0.6,
            "dmn_insight": 0.5,
            "stream_thought": 0.4,
            "flashback": 0.45,
            "need": 0.55,
            "environment_changed": 0.3,  # Низкий приоритет сам по себе
        }.get(signal_type, 0.3)
        
        # Модификаторы
        emotional_charge = signal.get("emotional_charge", 0.0)
        base_importance += abs(emotional_charge) * 0.3
        
        urgency = signal.get("urgency", 0.0)
        if urgency > 0:
            base_importance += urgency * 0.4
        
        attention_focus = getattr(self.state, 'attention_focus', None)
        if attention_focus and attention_focus in content:
            base_importance += 0.3
        
        return max(0.0, min(1.0, base_importance))
    
    def _compute_repetition_penalty(self, signal: Dict[str, Any]) -> float:
        """Штраф за повторение (торможение)."""
        signal_type = signal.get("type", "unknown")
        content = signal.get("content", "")[:50]
        
        recent_count = sum(
            1 for s in self.recent_signals[-10:]
            if s.get("type") == signal_type and s.get("content", "")[:50] == content
        )
        
        if recent_count == 0:
            return 1.0
        elif recent_count == 1:
            return 0.8
        elif recent_count == 2:
            return 0.5
        else:
            return 0.2
    
    # ========================================================================
    # 🆕 ОБЪЕДИНЕНИЕ СВЯЗАННЫХ СИГНАЛОВ
    # ========================================================================
    
    def _merge_related_signals(self, signals: List[Dict]) -> List[Dict]:
        """
        Объединяет связанные сигналы в единое восприятие.
        
        Биология: Когда ты видишь друга и слышишь его голос, мозг сливает
        эти сигналы в единое восприятие "друг рядом".
        """
        if len(signals) <= 1:
            return signals
        
        merged = []
        processed_indices = set()
        
        for i, signal in enumerate(signals):
            if i in processed_indices:
                continue
            
            signal_type = signal.get("type")
            
            # 🆕 Если это сообщение пользователя — ищем связанные контексты
            if signal_type == "user_command":
                merged_signal = signal.copy()
                related_contexts = []
                
                # Ищем связанные сигналы (окружение, файлы, воспоминания)
                for j, other_signal in enumerate(signals):
                    if j == i or j in processed_indices:
                        continue
                    
                    other_type = other_signal.get("type")
                    
                    # Объединяем контекстные сигналы
                    if other_type in ["environment_changed", "file_context", "flashback"]:
                        related_contexts.append(other_signal)
                        processed_indices.add(j)
                
                # Если нашли связанные контексты — объединяем
                if related_contexts:
                    merged_signal["merged_contexts"] = related_contexts
                    merged_signal["importance"] = max(
                        signal.get("importance", 0),
                        max(ctx.get("importance", 0) for ctx in related_contexts)
                    )
                    log.info("🚦 Signals merged", 
                            main_type=signal_type,
                            merged_types=[ctx.get("type") for ctx in related_contexts])
                
                merged.append(merged_signal)
                processed_indices.add(i)
            
            else:
                # Остальные сигналы добавляем как есть
                merged.append(signal)
                processed_indices.add(i)
        
        return merged