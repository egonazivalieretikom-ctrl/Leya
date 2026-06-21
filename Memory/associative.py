import time
import re
import random
import asyncio
from typing import List, Dict, Any, Optional
from Core.logger import log
from Core.state import LeyaState


class AssociativeMemory:
    """
    Ассоциативная память с непроизвольными вспышками (flashbacks).
    
    Философия: Память — это не архив, а живой процесс реконструкции.
    Каждое воспоминание имеет "силу", "эмоциональный заряд" и "последнее время всплытия".
    """
    
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
    
    EMOTIONAL_MARKERS = {
        "positive": ["рад", "счаст", "хорош", "отличн", "весел", "любл", "тепл", "уют", "успех"],
        "negative": ["груст", "плох", "ошибк", "проблем", "страх", "тревог", "боль", "устал"],
        "neutral":  [],
    }
    
    def __init__(self, state: LeyaState, long_term_memory, homeostasis=None):
        self.state = state
        self.ltm = long_term_memory
        self.homeostasis = homeostasis
        self._last_flashback_time = 0.0
        self._flashback_cooldown = 30.0
        self._reconstruction_rate = 0.05
        
        log.info("🧩 Associative Memory initialized (Flashbacks + Reconstruction)")
    
    # ========================================================================
    # АССОЦИАТИВНАЯ АКТИВАЦИЯ
    # ========================================================================
    
    def activate(self, n_results: int = 3) -> List[Dict[str, Any]]:
        """Непроизвольная активация воспоминаний на основе текущего состояния."""
        mood = getattr(self.state, 'emotion', 'neutral')
        keywords = self.MOOD_ASSOCIATIONS.get(mood, self.MOOD_ASSOCIATIONS["neutral"])
        query_words = random.sample(keywords, min(3, len(keywords)))
        query = " ".join(query_words)
        
        try:
            raw_memories = self.ltm.search(query, n_results=n_results * 2)
            if not raw_memories:
                return []
            
            scored_memories = []
            for mem in raw_memories:
                memory_text = mem.get("memory_text", "")
                metadata = mem.get("metadata", {})
                memory_id = mem.get("id")  # 🆕 Получаем ID
                
                resonance = self._compute_resonance(memory_text, metadata, mood)
                
                scored_memories.append({
                    "text": memory_text,
                    "metadata": metadata,
                    "id": memory_id,  # 🆕 Сохраняем ID
                    "resonance": resonance,
                    "raw": mem
                })
            
            scored_memories.sort(key=lambda x: x["resonance"], reverse=True)
            activated = scored_memories[:n_results]
            
            # Применяем реконструкцию с передачей ID
            for mem in activated:
                self._apply_reconstruction(mem)
            
            self._publish_flashbacks(activated)
            return activated
            
        except Exception as e:
            log.error("Associative activation failed", error=str(e))
            return []
    
    # ========================================================================
    # ЯВНЫЙ FLASHBACK
    # ========================================================================
    
    def flashback(self, query: str, n_results: int = 3) -> List[Dict[str, Any]]:
        """Явное воспоминание по запросу."""
        try:
            raw_memories = self.ltm.search(query, n_results=n_results)
            if not raw_memories:
                return []
            
            mood = getattr(self.state, 'emotion', 'neutral')
            results = []
            
            for mem in raw_memories:
                memory_text = mem.get("memory_text", "")
                metadata = mem.get("metadata", {})
                memory_id = mem.get("id")
                
                resonance = self._compute_resonance(memory_text, metadata, mood)
                self._apply_emotional_feedback(memory_text, resonance)
                self._apply_reconstruction({
                    "text": memory_text, 
                    "metadata": metadata, 
                    "id": memory_id  # 🆕 Передаём ID
                })
                
                results.append({
                    "text": memory_text,
                    "metadata": metadata,
                    "id": memory_id,
                    "resonance": resonance
                })
            
            return results
            
        except Exception as e:
            log.error("Flashback failed", error=str(e))
            return []
    
    # ========================================================================
    # РЕЗОНАНС
    # ========================================================================
    
    def _compute_resonance(self, memory_text: str, metadata: Dict, current_mood: str) -> float:
        """Вычисляет резонанс воспоминания с текущим состоянием."""
        resonance = 0.5
        
        # Эмоциональная конгруэнтность
        memory_emotion = metadata.get("mood", "neutral")
        if memory_emotion == current_mood:
            resonance += 0.3
        elif self._emotions_are_similar(memory_emotion, current_mood):
            resonance += 0.15
        elif self._emotions_are_opposite(memory_emotion, current_mood):
            resonance -= 0.2
        
        # Эмоциональный заряд
        emotional_charge = self._compute_emotional_charge(memory_text)
        resonance += abs(emotional_charge) * 0.2
        
        # Сила памяти
        memory_strength = metadata.get("strength", 0.5)
        resonance += (memory_strength - 0.5) * 0.3
        
        # Свежесть
        created_at = metadata.get("created_at", 0)
        if created_at > 0:
            age_hours = (time.time() - created_at) / 3600
            freshness_factor = 1.0 / (1.0 + age_hours / 24.0)
            resonance += (freshness_factor - 0.5) * 0.2
        
        # Недавнее всплытие
        last_recalled = metadata.get("last_recalled", 0)
        if last_recalled > 0:
            minutes_ago = (time.time() - last_recalled) / 60
            if minutes_ago < 10:
                resonance += 0.2
            elif minutes_ago < 60:
                resonance += 0.1
        
        return max(0.0, min(1.0, resonance))
    
    def _emotions_are_similar(self, emotion1: str, emotion2: str) -> bool:
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
        opposites = {
            "flow": ["exhausted", "stressed"],
            "loving": ["lonely"],
            "calm": ["anxious", "stressed"],
            "curious": ["exhausted"],
        }
        return emotion2 in opposites.get(emotion1, [])
    
    def _compute_emotional_charge(self, text: str) -> float:
        text_lower = text.lower()
        positive_count = sum(1 for m in self.EMOTIONAL_MARKERS["positive"] if m in text_lower)
        negative_count = sum(1 for m in self.EMOTIONAL_MARKERS["negative"] if m in text_lower)
        total = positive_count + negative_count
        if total == 0:
            return 0.0
        return (positive_count - negative_count) / total
    
    # ========================================================================
    # ЭМОЦИОНАЛЬНАЯ ОБРАТНАЯ СВЯЗЬ
    # ========================================================================
    
    def _apply_emotional_feedback(self, memory_text: str, resonance: float):
        """Всплывшее воспоминание влияет на текущее состояние."""
        if not self.homeostasis:
            return
        
        intensity = 0.02 * resonance
        charge = self._compute_emotional_charge(memory_text)
        
        if charge > 0.3:
            self.homeostasis.apply_stimulus("dopamine", intensity)
            self.homeostasis.apply_stimulus("endorphins", intensity * 0.5)
            if "Влад" in memory_text or "влад" in memory_text.lower():
                self.homeostasis.apply_stimulus("oxytocin", intensity)
        elif charge < -0.3:
            self.homeostasis.apply_stimulus("cortisol", intensity)
            self.homeostasis.apply_stimulus("oxytocin", -intensity * 0.5)
        else:
            self.homeostasis.apply_stimulus("acetylcholine", intensity * 0.5)
    
    # ========================================================================
    # 🆕 РЕКОНСТРУКЦИЯ ПАМЯТИ (с использованием ID)
    # ========================================================================
    
    def _apply_reconstruction(self, memory: Dict):
        """
        Каждое всплытие воспоминания немного его меняет.
        Биология: reconsolidation — при извлечении память лабильна.
        """
        memory_id = memory.get("id")
        if not memory_id:
            log.debug("Memory reconstruction skipped: no ID")
            return
        
        try:
            metadata = memory.get("metadata", {}).copy()
            
            # Обновляем время последнего всплытия
            metadata["last_recalled"] = time.time()
            
            # Усиливаем/ослабляем память
            current_strength = metadata.get("strength", 0.5)
            resonance = memory.get("resonance", 0.5)
            strength_delta = (resonance - 0.5) * self._reconstruction_rate
            new_strength = max(0.1, min(1.0, current_strength + strength_delta))
            metadata["strength"] = new_strength
            
            # 🆕 Сохраняем обновлённые метаданные через update_metadata
            if hasattr(self.ltm, 'update_metadata'):
                success = self.ltm.update_metadata(memory_id, metadata)
                if success:
                    log.debug(
                        "🧩 Memory reconstructed",
                        id=memory_id[:8],
                        strength=f"{new_strength:.2f}",
                        delta=f"{strength_delta:+.3f}"
                    )
            else:
                log.warning("LongTermMemory doesn't support update_metadata")
            
        except Exception as e:
            log.debug("Memory reconstruction failed", error=str(e))
    
    # ========================================================================
    # ПУБЛИКАЦИЯ В UI
    # ========================================================================
    
    def _publish_flashbacks(self, activated_memories: List[Dict]):
        """Публикует всплывшие воспоминания в UI."""
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