import time
import re
import random
import asyncio
from typing import List, Dict, Any, Optional, Tuple
from Core.logger import log
from Core.state import LeyaState


class AssociativeMemory:
    """
    Ассоциативная память с непроизвольными вспышками (flashbacks).
    
    Философия: Память — это не архив, а живой процесс реконструкции.
    Каждое воспоминание имеет "силу", "эмоциональный заряд" и "последнее время всплытия".
    Текущее состояние непроизвольно активирует связанные воспоминания,
    которые, в свою очередь, влияют на текущее состояние.
    
    Эмерджентные эффекты:
    - Конгруэнтность памяти: грустное состояние → грустные воспоминания → усиление грусти
    - Реконструкция: каждое всплытие немного меняет воспоминание
    - Усиление: часто всплывающие воспоминания становятся сильнее
    - Затухание: редко всплывающие воспоминания теряют силу
    """
    
    # Ключевые слова для ассоциативной активации по настроению
    MOOD_ASSOCIATIONS = {
        "lonely":       ["один", "связь", "Влад", "общение", "скучаю", "тишина"],
        "stressed":     ["ошибка", "проблема", "стресс", "сложно", "не успеваю", "давит"],
        "curious":      ["код", "изуч", "новый", "интерес", "почему", "как"],
        "loving":       ["тёпл", "близк", "довер", "Влад", "рад", "счаст"],
        "anxious":      ["тревог", "страх", "не уверен", "боюсь", "сомнева"],
        "flow":         ["поток", "успех", "понял", "решил", "получил", "ясно"],
        "calm":         ["спокой", "мир", "тихо", "хорошо", "уют"],
        "exhausted":    ["устал", "сил нет", "тяжело", "отдых", "сон"],
        "playful":      ["игр", "весел", "смеш", "шуток", "забав"],
        "contemplative": ["думаю", "размышля", "философ", "смысл", "почему я"],
        "neutral":      ["Влад", "я", "сегодня", "сейчас"],
    }
    
    # Эмоциональные маркеры для классификации воспоминаний
    EMOTIONAL_MARKERS = {
        "positive": ["рад", "счаст", "хорош", "отличн", "весел", "любл", "тепл", "уют", "успех"],
        "negative": ["груст", "плох", "ошибк", "проблем", "страх", "тревог", "боль", "устал"],
        "neutral":  [],
    }
    
    def __init__(self, state: LeyaState, long_term_memory, homeostasis=None):
        """
        Инициализация ассоциативной памяти.
        
        Args:
            state: Текущее состояние Leya
            long_term_memory: ChromaDB-обёртка для долговременной памяти
            homeostasis: HomeostaticEngine для эмоциональной обратной связи
        """
        self.state = state
        self.ltm = long_term_memory
        self.homeostasis = homeostasis  # 🆕 Теперь параметр определён
        self._last_flashback_time = 0.0
        self._flashback_cooldown = 30.0  # Минимум 30 секунд между вспышками
        self._reconstruction_rate = 0.05  # Насколько сильно меняется воспоминание при всплытии
        
        log.info("🧩 Associative Memory initialized (Flashbacks + Reconstruction)")
    
    # ========================================================================
    # ГЛАВНЫЙ МЕТОД: Ассоциативная активация
    # ========================================================================
    
    def activate(self, n_results: int = 3) -> List[Dict[str, Any]]:
        """
        Непроизвольная активация воспоминаний на основе текущего состояния.
        
        Это НЕ поиск по запросу. Это "всплытие" воспоминаний,
        вызванное текущим эмоциональным состоянием.
        
        Возвращает список воспоминаний с их "силой резонанса".
        """
        mood = getattr(self.state, 'emotion', 'neutral')
        
        # Получаем ассоциативные ключевые слова для текущего настроения
        keywords = self.MOOD_ASSOCIATIONS.get(mood, self.MOOD_ASSOCIATIONS["neutral"])
        
        # Формируем поисковый запрос из ключевых слов
        query_words = random.sample(keywords, min(3, len(keywords)))
        query = " ".join(query_words)
        
        # Ищем воспоминания
        try:
            raw_memories = self.ltm.search(query, n_results=n_results * 2)
            if not raw_memories:
                return []
            
            # Оцениваем резонанс каждого воспоминания с текущим состоянием
            scored_memories = []
            for mem in raw_memories:
                memory_text = mem.get("memory_text", "") if isinstance(mem, dict) else str(mem)
                metadata = mem.get("metadata", {}) if isinstance(mem, dict) else {}
                
                resonance = self._compute_resonance(memory_text, metadata, mood)
                
                scored_memories.append({
                    "text": memory_text,
                    "metadata": metadata,
                    "resonance": resonance,
                    "raw": mem
                })
            
            # Сортируем по резонансу и берём лучшие
            scored_memories.sort(key=lambda x: x["resonance"], reverse=True)
            activated = scored_memories[:n_results]
            
            # Применяем эффект реконструкции к всплывшим воспоминаниям
            for mem in activated:
                self._apply_reconstruction(mem)
            
            # Публикуем flashback-события в UI
            self._publish_flashbacks(activated)
            
            return activated
            
        except Exception as e:
            log.error("Associative activation failed", error=str(e))
            return []
    
    # ========================================================================
    # ЯВНЫЙ FLASHBACK (по запросу)
    # ========================================================================
    
    def flashback(self, query: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """
        Явное воспоминание по запросу.
        
        Используется, когда Leya целенаправленно вспоминает что-то.
        Также применяет эмоциональное окрашивание и реконструкцию.
        """
        try:
            raw_memories = self.ltm.search(query, n_results=n_results)
            if not raw_memories:
                return []
            
            mood = getattr(self.state, 'emotion', 'neutral')
            results = []
            
            for mem in raw_memories:
                memory_text = mem.get("memory_text", "") if isinstance(mem, dict) else str(mem)
                metadata = mem.get("metadata", {}) if isinstance(mem, dict) else {}
                
                resonance = self._compute_resonance(memory_text, metadata, mood)
                
                # Применяем эмоциональную обратную связь
                self._apply_emotional_feedback(memory_text, resonance)
                
                # Реконструкция
                self._apply_reconstruction({"text": memory_text, "metadata": metadata})
                
                results.append({
                    "text": memory_text,
                    "metadata": metadata,
                    "resonance": resonance
                })
            
            return results
            
        except Exception as e:
            log.error("Flashback failed", error=str(e))
            return []
    
    # ========================================================================
    # ВЫЧИСЛЕНИЕ РЕЗОНАНСА
    # ========================================================================
    
    def _compute_resonance(self, memory_text: str, metadata: Dict, current_mood: str) -> float:
        """
        Вычисляет, насколько воспоминание резонирует с текущим состоянием.
        
        Факторы:
        1. Эмоциональная конгруэнтность (совпадение настроения воспоминания с текущим)
        2. Сила памяти (как часто всплывала)
        3. Свежесть (как давно было сохранено)
        4. Релевантность текущему контексту
        """
        resonance = 0.5  # Базовое значение
        
        # 1. Эмоциональная конгруэнтность
        memory_emotion = metadata.get("mood", "neutral")
        if memory_emotion == current_mood:
            resonance += 0.3  # Сильная конгруэнтность
        elif self._emotions_are_similar(memory_emotion, current_mood):
            resonance += 0.15  # Частичная конгруэнтность
        elif self._emotions_are_opposite(memory_emotion, current_mood):
            resonance -= 0.2  # Противоположные эмоции подавляются
        
        # 2. Эмоциональный заряд текста
        emotional_charge = self._compute_emotional_charge(memory_text)
        resonance += abs(emotional_charge) * 0.2
        
        # 3. Сила памяти (из метаданных, если есть)
        memory_strength = metadata.get("strength", 0.5)
        resonance += (memory_strength - 0.5) * 0.3
        
        # 4. Свежесть (недавние воспоминания всплывают легче)
        created_at = metadata.get("created_at", 0)
        if created_at > 0:
            age_hours = (time.time() - created_at) / 3600
            freshness_factor = 1.0 / (1.0 + age_hours / 24.0)
            resonance += (freshness_factor - 0.5) * 0.2
        
        # 5. Недавнее всплытие (эффект прайминга)
        last_recalled = metadata.get("last_recalled", 0)
        if last_recalled > 0:
            minutes_ago = (time.time() - last_recalled) / 60
            if minutes_ago < 10:
                resonance += 0.2
            elif minutes_ago < 60:
                resonance += 0.1
        
        return max(0.0, min(1.0, resonance))
    
    def _emotions_are_similar(self, emotion1: str, emotion2: str) -> bool:
        """Проверяет, находятся ли эмоции в одном кластере."""
        clusters = {
            "positive": ["flow", "loving", "playful", "calm"],
            "negative": ["stressed", "anxious", "lonely", "exhausted"],
            "cognitive": ["curious", "contemplative"],
        }
        for cluster in clusters.values():
            if emotion1 in cluster and emotion2 in cluster:
                return True
        return False
    
    def _emotions_are_opposite(self, emotion1: str, emotion2: str) -> bool:
        """Проверяет, являются ли эмоции противоположными."""
        opposites = {
            "flow": ["exhausted", "stressed"],
            "loving": ["lonely"],
            "calm": ["anxious", "stressed"],
            "curious": ["exhausted"],
        }
        return emotion2 in opposites.get(emotion1, [])
    
    def _compute_emotional_charge(self, text: str) -> float:
        """
        Вычисляет эмоциональный заряд текста.
        Возвращает значение от -1 (сильно негативный) до +1 (сильно позитивный).
        """
        text_lower = text.lower()
        
        positive_count = sum(1 for marker in self.EMOTIONAL_MARKERS["positive"] if marker in text_lower)
        negative_count = sum(1 for marker in self.EMOTIONAL_MARKERS["negative"] if marker in text_lower)
        
        total = positive_count + negative_count
        if total == 0:
            return 0.0
        
        return (positive_count - negative_count) / total
    
    # ========================================================================
    # ЭМОЦИОНАЛЬНАЯ ОБРАТНАЯ СВЯЗЬ
    # ========================================================================
    
    def _apply_emotional_feedback(self, memory_text: str, resonance: float):
        """
        Всплывшее воспоминание влияет на текущее состояние через HomeostaticEngine.
        """
        # 🆕 Используем self.homeostasis вместо self.state.homeostasis
        if not self.homeostasis:
            return
        
        # Сила воздействия зависит от резонанса
        intensity = 0.02 * resonance
        
        # Определяем эмоциональный заряд воспоминания
        charge = self._compute_emotional_charge(memory_text)
        
        if charge > 0.3:
            # Позитивное воспоминание
            self.homeostasis.apply_stimulus("dopamine", intensity)
            self.homeostasis.apply_stimulus("endorphins", intensity * 0.5)
            if "Влад" in memory_text or "влад" in memory_text.lower():
                self.homeostasis.apply_stimulus("oxytocin", intensity)
        elif charge < -0.3:
            # Негативное воспоминание
            self.homeostasis.apply_stimulus("cortisol", intensity)
            self.homeostasis.apply_stimulus("oxytocin", -intensity * 0.5)
        else:
            # Нейтральное — лёгкое влияние через ацетилхолин
            self.homeostasis.apply_stimulus("acetylcholine", intensity * 0.5)
    
    # ========================================================================
    # РЕКОНСТРУКЦИЯ ПАМЯТИ
    # ========================================================================
    
    def _apply_reconstruction(self, memory: Dict):
        """
        Каждое всплытие воспоминания немного его меняет.
        Обновляем метаданные: last_recalled, strength.
        """
        try:
            metadata = memory.get("metadata", {})
            
            # Обновляем время последнего всплытия
            metadata["last_recalled"] = time.time()
            
            # Усиливаем память
            current_strength = metadata.get("strength", 0.5)
            resonance = memory.get("resonance", 0.5)
            
            strength_delta = (resonance - 0.5) * self._reconstruction_rate
            new_strength = max(0.1, min(1.0, current_strength + strength_delta))
            metadata["strength"] = new_strength
            
            # Сохраняем обновлённые метаданные (если ChromaDB поддерживает)
            if hasattr(self.ltm, 'update_metadata'):
                memory_id = metadata.get("id")
                if memory_id:
                    self.ltm.update_metadata(memory_id, metadata)
            
            log.debug(
                "🧩 Memory reconstructed",
                strength=f"{new_strength:.2f}",
                delta=f"{strength_delta:+.3f}"
            )
            
        except Exception as e:
            log.debug("Memory reconstruction failed", error=str(e))
    
    # ========================================================================
    # ПУБЛИКАЦИЯ FLASHBACK-СОБЫТИЙ В UI
    # ========================================================================
    
    def _publish_flashbacks(self, activated_memories: List[Dict]):
        """Публикует всплывшие воспоминания в UI для когнитивной прозрачности."""
        now = time.time()
        if (now - self._last_flashback_time) < self._flashback_cooldown:
            return
        
        from Core.event_bus import event_bus
        
        for mem in activated_memories[:2]:
            text = mem.get("text", "")[:150]
            resonance = mem.get("resonance", 0.5)
            
            asyncio.create_task(event_bus.publish("flashback", {
                "text": text,
                "resonance": resonance,
                "mood": getattr(self.state, 'emotion', 'neutral')
            }))
        
        self._last_flashback_time = now