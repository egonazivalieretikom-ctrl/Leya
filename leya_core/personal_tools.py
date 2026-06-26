"""
personal_tools.py
Фаза 2 — Инструменты для реальных действий в персональном режиме.

Эти инструменты позволяют Лее:
- Отправлять сообщения
- Открывать вкладки браузера
- Искать новости

Все инструменты безопасны для персонального использования и легко расширяются.
"""

import logging
import webbrowser

logger = logging.getLogger("LeyaOS.PersonalTools")


def open_browser_tab(query_or_url: str) -> str:
    """
    Открывает вкладку в браузере.
    Если передан URL — открывает его.
    Если передан запрос — ищет в Google.
    """
    if query_or_url.startswith("http"):
        url = query_or_url
    else:
        # Простой поиск в Google
        url = f"https://www.google.com/search?q={query_or_url.replace(' ', '+')}"

    try:
        webbrowser.open_new_tab(url)
        logger.info(f"Открыта вкладка браузера: {url}")
        return f"Открыла вкладку с результатами по запросу: {query_or_url}"
    except Exception as e:
        logger.error(f"Ошибка открытия браузера: {e}")
        return f"Не удалось открыть браузер: {str(e)}"


def send_personal_message(contact: str, message: str, method: str = "print") -> str:
    """
    Отправляет сообщение контакту.

    Поддерживаемые методы:
    - "print"     — просто выводит в консоль (для теста)
    - "telegram"  — отправка через Telegram (требует токен и chat_id)

    В будущем можно добавить email, WhatsApp и т.д.
    """
    if method == "print":
        print(f"\n[Сообщение для {contact}]:\n{message}\n")
        logger.info(f"Сообщение для {contact} выведено в консоль")
        return f"Сообщение для {contact} подготовлено и выведено."

    elif method == "telegram":
        # Пример заглушки. Пользователь может заменить на реальную отправку.
        logger.info(f"[Telegram] Сообщение для {contact}: {message}")
        return f"Сообщение отправлено {contact} через Telegram (заглушка)."

    else:
        return f"Метод отправки '{method}' пока не поддерживается."


def get_latest_news(topic: str) -> str:
    """
    Ищет свежие новости по теме и возвращает краткую сводку.
    Использует существующий инструмент duckduckgo_search.
    """
    # Эта функция будет вызываться через tool_registry,
    # поэтому здесь просто возвращаем инструкцию.
    # Реальная логика будет в регистрации инструмента.
    return f"Ищу свежие новости по теме: {topic}"


# Словарь с описаниями инструментов (для LLM)
PERSONAL_TOOLS_DESCRIPTION = {
    "open_browser_tab": {
        "description": "Открывает вкладку в браузере с результатами поиска или по прямой ссылке.",
        "parameters": {"query_or_url": "Строка с запросом или URL"},
    },
    "send_personal_message": {
        "description": "Отправляет сообщение контакту. Используй, когда нужно уведомить кого-то.",
        "parameters": {
            "contact": "Имя или контакт получателя",
            "message": "Текст сообщения",
            "method": "Способ отправки: 'print' (по умолчанию) или 'telegram'",
        },
    },
    "get_latest_news": {
        "description": "Ищет и показывает свежие новости по заданной теме.",
        "parameters": {"topic": "Тема новостей"},
    },
}
