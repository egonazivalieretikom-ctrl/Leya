import os
import math
import httpx
from Core.logger import log
from dotenv import load_dotenv

load_dotenv()

# Локальный SearXNG через Docker
SEARXNG_URL = os.getenv("SEARXNG_URL", "http://localhost:8888")


def search_web(query: str, max_results: int = 3) -> str:
    """
    Умный поиск: погода через wttr.in, остальное через локальный SearXNG.
    """
    query_lower = query.lower()
    log.info("🔎 search_web called", query=query_lower)
    
    # 🌤️ ПРИОРИТЕТ 0: Погода через wttr.in (работает из РФ)
    weather_keywords = ["погода", "weather", "температура", "осадки", "прогноз"]
    if any(word in query_lower for word in weather_keywords):
        log.info("🌤️ Weather keyword detected, trying wttr.in")
        result = _get_weather_wttr(query)
        if result:
            log.info("✅ wttr.in returned result")
            return result
        else:
            log.warning("⚠️ wttr.in returned empty, falling back to SearXNG")
    
    # 🔍 ПРИОРИТЕТ 1: Локальный SearXNG
    log.info("🔍 Using SearXNG")
    return _search_searxng(query, max_results)


def _get_weather_wttr(query: str) -> str:
    """
    Погода через wttr.in — простой текстовый API, работает из РФ.
    """
    log.info("🌤️ Getting weather via wttr.in", query=query)
    
    try:
        # Извлекаем название города
        city = query.lower()
        stop_words = ["погода", "прогноз", "завтра", "сегодня", "сейчас", "на завтра", 
                      "завтрашний", "прогноз погоды", "weather", "tomorrow", "today", "в"]
        for word in stop_words:
            city = city.replace(word, "")
        city = city.strip(".,!? ")
        
        if not city or len(city) < 2:
            log.warning("Could not extract city name", query=query)
            return ""
        
        # Запрос к wttr.in с форматом
        # %l = локация, %c = условия, %t = температура, %f = ощущается как, 
        # %w = ветер, %h = влажность, %C = описание
        url = f"https://wttr.in/{city}?format=%l:+%c+%t+(ощущается+как+%f),+ветер+%w,+влажность+%h,+%C&lang=ru"
        
        headers = {"User-Agent": "curl/7.68.0"}  # wttr.in требует User-Agent
        response = httpx.get(url, headers=headers, timeout=15.0)
        
        if response.status_code == 200:
            weather_text = response.text.strip()
            log.info("✅ wttr.in weather success", city=city, weather=weather_text[:100])
            return f"Факт: {weather_text}"
        else:
            log.warning("wttr.in failed", status=response.status_code)
            return ""
            
    except Exception as e:
        log.error("wttr.in failed", error=str(e))
        return ""


def _search_searxng(query: str, max_results: int) -> str:
    """
    Поиск через локальный SearXNG с правильными заголовками для обхода botdetection.
    """
    log.info("🔍 Searching via local SearXNG", query=query, url=SEARXNG_URL)
    
    try:
        # 🆕 Добавляем X-Forwarded-For и X-Real-IP для обхода botdetection
        headers = {
            "Accept": "application/json",
            "User-Agent": "LeyaOS/1.0 (Local AGI)",
            "X-Forwarded-For": "127.0.0.1",
            "X-Real-IP": "127.0.0.1"
        }
        
        params = {
            "q": query,
            "format": "json",
            "number_of_results": max_results,
            "language": "ru",
            "categories": "general"
        }
        
        search_url = f"{SEARXNG_URL.rstrip('/')}/search"
        
        response = httpx.get(
            search_url,
            headers=headers,
            params=params,
            timeout=10.0,
            follow_redirects=True
        )
        
        log.debug("SearXNG response", status=response.status_code)
        
        if response.status_code == 200:
            data = response.json()
            results = data.get("results", [])
            
            if not results:
                log.info("SearXNG returned no results", query=query)
                return "Ничего не найдено."
            
            formatted = []
            for r in results[:max_results]:
                title = r.get("title", "").strip()
                content = r.get("content", "").strip()
                if title or content:
                    formatted.append(f"Факт: {title} — {content}")
            
            if formatted:
                log.info("✅ SearXNG search successful", count=len(formatted))
                return "\n".join(formatted)
            else:
                return "Ничего не найдено."
        
        elif response.status_code == 429:
            log.warning("SearXNG rate limit hit")
            return "Поисковый движок временно перегружен. Попробуй позже."
        
        else:
            log.error("SearXNG HTTP error", status=response.status_code)
            return f"Ошибка поиска: HTTP {response.status_code}"
            
    except httpx.ConnectError:
        log.error("SearXNG connection failed. Is Docker running?", url=SEARXNG_URL)
        return (
            "Не удалось подключиться к поисковому движку. "
            "Убедись, что Docker запущен и контейнер SearXNG работает."
        )
    
    except Exception as e:
        log.error("SearXNG search failed", error=str(e))
        return f"Ошибка поиска: {str(e)}"


def calculate(expression: str) -> str:
    """Безопасно вычисляет математические выражения."""
    log.info("🧮 Calculating", expression=expression)
    try:
        allowed_names = {k: v for k, v in math.__dict__.items() if not k.startswith("__")}
        allowed_names.update({"abs": abs, "round": round})
        result = eval(expression, {"__builtins__": {}}, allowed_names)
        return str(result)
    except Exception as e:
        log.error("Calculation failed", error=str(e))
        return f"Ошибка вычисления: {str(e)}"