"""
desktop_control.py
Фаза 4 — Desktop integration и проактивность

Этот модуль позволяет Лее:
- Более мощно управлять браузером
- Выполнять простые действия на рабочем столе (опционально)
- Запускать проактивные фоновые задачи (мониторинг календаря, репозиториев и т.д.)

Для максимальной мощности рекомендуется установить:
pip install playwright
playwright install
"""

import asyncio
import logging
import webbrowser

logger = logging.getLogger("LeyaOS.DesktopControl")


class DesktopControl:
    """
    Класс для управления рабочим столом и браузером в персональном режиме.
    """

    def __init__(self):
        self.browser_available = True
        logger.info("DesktopControl инициализирован.")

    def open_browser(self, query_or_url: str, new_tab: bool = True) -> str:
        """
        Открывает браузер.
        Улучшенная версия из Phase 2.
        """
        try:
            if query_or_url.startswith(("http://", "https://")):
                url = query_or_url
            else:
                url = f"https://www.google.com/search?q={query_or_url.replace(' ', '+')}"

            if new_tab:
                webbrowser.open_new_tab(url)
            else:
                webbrowser.open(url)

            logger.info(f"Открыт браузер: {url}")
            return f"Открыла браузер с результатами по: {query_or_url}"

        except Exception as e:
            logger.error(f"Ошибка открытия браузера: {e}")
            return f"Не удалось открыть браузер: {str(e)}"

    async def open_browser_advanced(self, url: str) -> str:
        """
        Более продвинутое открытие браузера с использованием Playwright (опционально).
        Если Playwright не установлен — падает обратно на webbrowser.
        """
        try:
            from playwright.async_api import async_playwright

            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=False)
                page = await browser.new_page()
                await page.goto(url)
                logger.info(f"Playwright открыл: {url}")
                return f"Открыла продвинутую вкладку: {url}"
        except ImportError:
            # Fallback на обычный браузер
            return self.open_browser(url)
        except Exception as e:
            logger.error(f"Ошибка Playwright: {e}")
            return self.open_browser(url)

    async def monitor_repository(self, owner: str, repo: str, interval_minutes: int = 30):
        """
        Пример проактивной задачи: периодически проверять репозиторий на GitHub.
        Можно запускать в фоне.
        """
        logger.info(f"Запущен мониторинг репозитория {owner}/{repo}")
        while True:
            # Здесь можно добавить проверку новых коммитов/PR через GitHub API
            logger.info(f"[Проактивно] Проверка репозитория {owner}/{repo}...")
            await asyncio.sleep(interval_minutes * 60)

    async def check_calendar(self):
        """
        Пример проактивной задачи: проверка календаря.
        В реальности нужно подключать Google Calendar API или Outlook.
        """
        logger.info("[Проактивно] Проверка календаря...")
        # Здесь можно добавить реальную логику
        await asyncio.sleep(3600)  # раз в час


# Готовые инструменты для регистрации
def create_desktop_tools(desktop: DesktopControl):
    """Возвращает словарь инструментов для регистрации в ToolRegistry."""

    async def open_browser_tool(query_or_url: str) -> str:
        return desktop.open_browser(query_or_url)

    async def open_browser_advanced_tool(url: str) -> str:
        return await desktop.open_browser_advanced(url)

    return {
        "open_browser_tab": open_browser_tool,
        "open_browser_advanced": open_browser_advanced_tool,
    }
