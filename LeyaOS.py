import os
import sys
import asyncio
import uvicorn
from dotenv import load_dotenv

# Загрузка переменных окружения
load_dotenv()
os.environ["ANONYMIZED_TELEMETRY"] = "False"

from Core.brain import Brain
from Core.logger import log
from Core.event_bus import event_bus
from Core.homeostasis import HomeostaticEngine
from UI.server import app


async def main():
    log.info("🌟 Welcome to Leya OS v0.5 (Continuous Consciousness)")
    
    # 1. Инициализация Мозга
    brain = Brain()
    
    # 2. Инициализация Гомеостатического Двигателя
    homeostasis = HomeostaticEngine(brain.state)
    
    # 3. Обработчик потребностей (синхронный мост к async)
    def on_needs(needs):
        """Синхронный колбэк, вызываемый из HomeostaticEngine."""
        for need in needs:
            log.info("🫀 Need generated", type=need["type"], urgency=f"{need['urgency']:.2f}")
            brain.state.add_to_context({
                "type": "internal_drive",
                "content": need["description"],
                "importance": need["urgency"],
                "source": "homeostasis"
            })
    
    homeostasis.on_need_generated(on_needs)
    
    # 4. Передача homeostasis в Cognition Manager (если он уже загружен)
    if hasattr(brain, 'cognition') and brain.cognition:
        brain.cognition.homeostasis = homeostasis
        log.info("🔗 Homeostasis linked to Cognition Manager")
    
    # 5. Обработчик ввода из UI
    async def handle_ui_input(data):
        brain.state.add_to_context(data)
        # Социальный стимул при получении сообщения
        homeostasis.apply_stimulus("oxytocin", 0.05)
        homeostasis.apply_stimulus("dopamine", 0.03)
    
    event_bus.subscribe("ui_input", handle_ui_input)
    
    # 6. Настройка Web UI
    config = uvicorn.Config(app, host="127.0.0.1", port=8000, log_level="warning")
    server = uvicorn.Server(config)
    
    log.info("🌐 Web UI: http://localhost:8000")
    log.info("🫀 Starting Homeostatic Engine + Brain + Web UI...")
    
    # 7. ЗАПУСК ТРЕХ ПАРАЛЛЕЛЬНЫХ ЗАДАЧ
    # Важно: все три должны быть awaitable корутинами
    try:
        await asyncio.gather(
            homeostasis.start(),           # Непрерывная физиология (10Hz)
            server.serve(),                # Web UI (блокирующая корутина)
            brain.start(cycle_interval=2.0) # Когнитивный цикл
        )
    except KeyboardInterrupt:
        log.info("🛑 Shutdown requested")
    finally:
        homeostasis.stop()
        log.info("👋 Leya OS has shut down gracefully.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\n👋 Leya OS interrupted by user.")
        sys.exit(0)
    except Exception as e:
        log.error("💥 Fatal error in main", error=str(e), exc_info=True)
        sys.exit(1)