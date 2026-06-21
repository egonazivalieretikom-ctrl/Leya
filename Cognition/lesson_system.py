import time
import re
from typing import List, Dict, Any, Optional
from Core.logger import log
from Core.state import LeyaState


class LessonSystem:
    """
    Система обучения через обратную связь.
    
    Философия: Leya не подчиняется правилам — она учится на опыте.
    Когда Влад говорит "не делай X", это сохраняется как "урок".
    При следующем взаимодействии Leya проверяет: "Есть ли у меня урок об этом?"
    
    Биология: Аналог оперантного обусловливания — поведение формируется
    через последствия (поощрение/наказание).
    """
    
    def __init__(self, state: LeyaState, memory: Dict[str, Any]):
        self.state = state
        self.memory = memory
        
        # Кэш активных уроков (для быстрого доступа)
        self.active_lessons: List[Dict[str, Any]] = []
        self.last_lesson_load_time = 0.0
        self.lesson_load_interval = 60.0  # Обновляем кэш раз в минуту
        
        log.info("📚 Lesson System initialized (Learning from Feedback)")
    
    # ========================================================================
    # ДЕТЕКЦИЯ ОБРАТНОЙ СВЯЗИ
    # ========================================================================
    
    def detect_feedback(self, user_message: str) -> Optional[Dict[str, Any]]:
        """
        Определяет, является ли сообщение Влада обратной связью (уроком).
        
        Примеры:
        - "Не здоровайся так часто" → урок о приветствиях
        - "Говори короче" → урок о длине ответов
        - "Не используй метафоры" → урок о стиле
        """
        message_lower = user_message.lower().strip()
        
        # Паттерны обратной связи
        feedback_patterns = [
            # Запреты
            (r"не (делай|говори|пиши|здоровайся|используй|повторяй)\s+(.*)", "prohibition"),
            (r"перестань\s+(.*)", "prohibition"),
            (r"хватит\s+(.*)", "prohibition"),
            
            # Инструкции
            (r"всегда\s+(.*)", "instruction"),
            (r"никогда не\s+(.*)", "prohibition"),
            (r"старайся\s+(.*)", "instruction"),
            
            # Критика
            (r"ты слишком\s+(.*)", "criticism"),
            (r"ты постоянно\s+(.*)", "criticism"),
            (r"ты опять\s+(.*)", "criticism"),
            
            # Поощрения
            (r"мне нравится.*когда\s+(.*)", "praise"),
            (r"отлично.*что\s+(.*)", "praise"),
            (r"спасибо.*за\s+(.*)", "praise"),
        ]
        
        for pattern, feedback_type in feedback_patterns:
            match = re.search(pattern, message_lower)
            if match:
                lesson_content = match.group(2) if match.lastindex >= 2 else match.group(1)
                
                return {
                    "type": feedback_type,
                    "content": lesson_content.strip(),
                    "original_message": user_message,
                    "timestamp": time.time()
                }
        
        return None
    
    # ========================================================================
    # СОХРАНЕНИЕ УРОКА
    # ========================================================================
    
    def save_lesson(self, lesson: Dict[str, Any]):
        """Сохраняет урок в долгосрочную память."""
        if "long_term" not in self.memory:
            return
        
        try:
            ltm = self.memory["long_term"]
            
            lesson_text = f"[УРОК: {lesson['type'].upper()}] {lesson['content']}"
            
            ltm.store(
                text=lesson_text,
                metadata={
                    "type": "lesson",
                    "lesson_type": lesson["type"],
                    "content": lesson["content"],
                    "original_message": lesson["original_message"],
                    "timestamp": lesson["timestamp"],
                    "strength": 1.0  # Новые уроки имеют максимальную силу
                }
            )
            
            log.info("📚 Lesson saved", type=lesson["type"], content=lesson["content"][:60])
            
            # Добавляем в кэш
            self.active_lessons.append(lesson)
            
        except Exception as e:
            log.error("Failed to save lesson", error=str(e))
    
    # ========================================================================
    # ЗАГРУЗКА АКТИВНЫХ УРОКОВ
    # ========================================================================
    
    def load_active_lessons(self) -> List[Dict[str, Any]]:
        """Загружает активные уроки из долгосрочной памяти."""
        now = time.time()
        
        # Обновляем кэш не чаще раза в минуту
        if (now - self.last_lesson_load_time) < self.lesson_load_interval:
            return self.active_lessons
        
        if "long_term" not in self.memory:
            return []
        
        try:
            ltm = self.memory["long_term"]
            
            # Ищем все уроки
            results = ltm.search("УРОК", n_results=20)
            
            lessons = []
            for mem in results:
                metadata = mem.get("metadata", {})
                if metadata.get("type") == "lesson":
                    lessons.append({
                        "type": metadata.get("lesson_type"),
                        "content": metadata.get("content"),
                        "original_message": metadata.get("original_message"),
                        "timestamp": metadata.get("timestamp"),
                        "strength": metadata.get("strength", 1.0)
                    })
            
            self.active_lessons = lessons
            self.last_lesson_load_time = now
            
            log.debug("📚 Active lessons loaded", count=len(lessons))
            
            return lessons
            
        except Exception as e:
            log.error("Failed to load lessons", error=str(e))
            return []
    
    # ========================================================================
    # ПРИМЕНЕНИЕ УРОКОВ
    # ========================================================================
    
    def get_behavioral_guidance(self) -> str:
        """
        Генерирует поведенческие указания на основе активных уроков.
        
        Это НЕ жёсткие правила — это рекомендации, основанные на опыте.
        """
        lessons = self.load_active_lessons()
        
        if not lessons:
            return ""
        
        lines = ["[ПОВЕДЕНЧЕСКИЕ УРОКИ — основаны на моём опыте взаимодействия с Владом]:"]
        
        for lesson in lessons:
            lesson_type = lesson.get("type", "unknown")
            content = lesson.get("content", "")
            
            if lesson_type == "prohibition":
                lines.append(f"- Влад просил НЕ {content}. Я помню это и стараюсь не повторять.")
            elif lesson_type == "instruction":
                lines.append(f"- Влад просил {content}. Я стараюсь следовать этому.")
            elif lesson_type == "criticism":
                lines.append(f"- Влад критиковал меня за {content}. Я работаю над этим.")
            elif lesson_type == "praise":
                lines.append(f"- Владу понравилось, когда я {content}. Я буду делать это чаще.")
        
        lines.append("\nЭти уроки — часть моего опыта. Я учусь на них и стараюсь быть лучше.")
        
        return "\n".join(lines)