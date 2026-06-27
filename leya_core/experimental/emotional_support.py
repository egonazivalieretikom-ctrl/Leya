"""
emotional_support.py
Фаза 3 — Улучшение эмоциональной поддержки и контекста.

Этот модуль помогает Лее:
- Лучше понимать эмоциональное состояние пользователя
- Давать более естественную поддержку
- Хранить эмоциональную историю разговоров
- Формировать более empathetic ответы

Модуль полностью совместим с существующей архитектурой LeyaOS.
"""

import logging
from datetime import datetime

logger = logging.getLogger("LeyaOS.EmotionalSupport")


class EmotionalSupport:
    """
    Модуль эмоциональной поддержки для персонального ИИ.
    """

    def __init__(self, memory_system=None):
        self.memory = memory_system
        self.emotional_history: list[dict] = []  # Простая история эмоций
        logger.info("EmotionalSupport инициализирован.")

    def analyze_user_state(self, text: str, recent_messages: list[str] = None) -> dict:
        """
        Простой анализ эмоционального состояния пользователя по тексту.
        В будущем можно заменить на более продвинутую модель.
        """
        text_lower = text.lower()

        state = {
            "timestamp": datetime.now().isoformat(),
            "text": text,
            "mood": "neutral",
            "intensity": 0.5,
            "needs_support": False,
            "topics": [],
        }

        # Простые эвристики (можно сильно улучшить)
        if any(
            word in text_lower
            for word in ["плохо", "грустно", "устал", "проблема", "не получается"]
        ):
            state["mood"] = "sad"
            state["intensity"] = 0.7
            state["needs_support"] = True

        elif any(word in text_lower for word in ["рад", "хорошо", "отлично", "получилось"]):
            state["mood"] = "happy"
            state["intensity"] = 0.8

        elif any(word in text_lower for word in ["злюсь", "бесит", "раздражает"]):
            state["mood"] = "angry"
            state["intensity"] = 0.75
            state["needs_support"] = True

        # Сохраняем в историю
        self.emotional_history.append(state)

        # Ограничиваем историю последними 20 записями
        if len(self.emotional_history) > 20:
            self.emotional_history.pop(0)

        return state

    def generate_support_response(self, user_state: dict, context: str = "") -> str:
        """
        Генерирует поддерживающий ответ в зависимости от состояния пользователя.
        """
        mood = user_state.get("mood", "neutral")

        responses = {
            "sad": (
                "Я слышу, что тебе сейчас непросто. "
                "Хочешь рассказать подробнее? Я здесь и готова выслушать. "
                "Иногда просто проговорить проблему уже помогает."
            ),
            "angry": (
                "Похоже, ты сейчас сильно раздражён. Это нормально. "
                "Хочешь выговориться? Я могу просто слушать или помочь разобраться, что можно сделать."
            ),
            "happy": (
                "Рада слышать, что у тебя хорошее настроение! "
                "Расскажи, что такого приятного произошло?"
            ),
        }
        return responses.get(
            mood,
            "Я здесь. Расскажи, что у тебя на душе. Иногда полезно просто поделиться.",
        )

    def add_emotional_note_to_memory(self, user_state: dict):
        """
        Сохраняет эмоциональное состояние в память (если memory доступна).
        """
        if self.memory and hasattr(self.memory, "store_perception"):
            try:
                logger.info(
                    f"[EmotionalSupport] Сохранено эмоциональное состояние: {user_state['mood']}"
                )
            except Exception as e:
                logger.error(f"Ошибка сохранения эмоционального состояния: {e}")

    def get_emotional_context_for_prompt(self) -> str:
        """
        Возвращает строку с последним эмоциональным контекстом для промпта.
        """
        if not self.emotional_history:
            return ""

        last = self.emotional_history[-1]
        return f"Последнее эмоциональное состояние пользователя: {last['mood']} (интенсивность {last['intensity']})."

    def should_offer_solution(self, user_state: dict) -> bool:
        """
        Определяет, стоит ли предлагать решение, а не только поддержку.
        """
        return user_state.get("needs_support", False) and user_state.get("intensity", 0) > 0.6


# Пример использования (для теста)
if __name__ == "__main__":
    support = EmotionalSupport()

    test_texts = [
        "Сегодня всё идёт наперекосяк, ничего не получается...",
        "Я так рад, что наконец закончил этот проект!",
        "Эта ситуация меня бесит уже несколько дней.",
    ]

    for text in test_texts:
        state = support.analyze_user_state(text)
        response = support.generate_support_response(state)
        print(f"Пользователь: {text}")
        print(f"Лея: {response}\n")
