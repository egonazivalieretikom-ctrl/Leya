import os
import sys
import asyncio
from Core.logger import log

# 🆕 КРИТИЧНО: Отключаем телеметрию ДО импорта chromadb
os.environ["ANONYMIZED_TELEMETRY"] = "False"
os.environ["CHROMA_TELEMETRY_DISABLED"] = "True"
os.environ["POSTHOG_DISABLED"] = "True"

# 🆕 Заглушка для PostHog (полностью убивает ошибки телеметрии ChromaDB)
try:
    import posthog
    posthog.capture = lambda *args, **kwargs: None
    posthog.disabled = True
    log.debug("✅ PostHog telemetry disabled via monkey-patch")
except ImportError:
    pass  # PostHog не установлен — отлично!
except Exception as e:
    log.debug("PostHog monkey-patch failed", error=str(e))

from dotenv import load_dotenv
load_dotenv()

from Core.brain import Brain
from Core.event_bus import event_bus
from UI.server import app
import uvicorn


async def main():
    """
    Главный цикл Leya OS.
    
    Архитектура:
    - HomeostaticEngine создаётся ОДИН раз в Brain
    - Brain передаёт его всем подсистемам
    - UI и когнитивный цикл используют один и тот же экземпляр
    """
    # ========================================================================
    # 1. ИНИЦИАЛИЗАЦИЯ BRAIN (создаёт HomeostaticEngine внутри себя)
    # ========================================================================
    brain = Brain()
    
    # Получаем homeostasis из brain (единое сердце)
    homeostasis = brain.homeostasis
    
    # Регистрируем обработчик потребностей
    def on_needs(needs):
        for need in needs:
            log.info("🫀 Need generated", type=need["type"], urgency=f"{need['urgency']:.2f}")
            brain.state.add_to_context({
                "type": "internal_drive",
                "content": need["description"],
                "importance": need["urgency"],
                "source": "homeostasis"
            })
    
    homeostasis.on_need_generated(on_needs)
    
    # ========================================================================
    # 2. ОБРАБОТЧИК UI INPUT
    # ========================================================================
    async def handle_ui_input(data):
        """Обрабатывает ввод от Web UI."""
        if data.get("type") in ["user_command", "vision_request"]:
            brain.state.add_to_context(data)
    
    event_bus.subscribe("ui_input", handle_ui_input)
    
    # ========================================================================
    # 3. UVICORN SERVER
    # ========================================================================
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    
    # ========================================================================
    # 4. ПАРАЛЛЕЛЬНЫЙ ЗАПУСК
    # ========================================================================
    try:
        await asyncio.gather(
            homeostasis.start(),           # Единое сердце из brain
            server.serve(),                # Web UI
            brain.start(cycle_interval=2.0) # Когнитивный цикл
        )
    except KeyboardInterrupt:
        print("\n👋 Leya OS interrupted by user.")
        homeostasis.stop()
        sys.exit(0)
    except Exception as e:
        log.error("💥 Fatal error in main", error=str(e), exc_info=True)
        homeostasis.stop()
        sys.exit(1)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Leya OS interrupted by user.")
        sys.exit(0)