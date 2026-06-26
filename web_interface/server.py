"""
web_interface/server.py
FastAPI сервер для веб-интерфейса Леи.

Этап 4:
- Jinja2 шаблоны вместо hardcoded HTML
- Статические файлы (CSS, JS)
- WebSocket для real-time broadcast
- REST API для состояния, драйвов, памяти
"""
from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path
from typing import Any, Dict

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

logger = logging.getLogger(__name__)

# Путь к директории web_interface
WEB_DIR = Path(__file__).parent


class MessageRequest(BaseModel):
    """Модель запроса сообщения."""
    content: str


def create_app(web_environment) -> FastAPI:
    """
    Создание FastAPI приложения.
    
    Args:
        web_environment: Экземпляр WebEnvironment
        
    Returns:
        FastAPI приложение
    """
    app = FastAPI(title="LeyaOS — Цифровое Сознание Леи")

    # Статические файлы
    app.mount("/static", StaticFiles(directory=WEB_DIR / "static"), name="static")

    # Jinja2 шаблоны
    templates = Jinja2Templates(directory=WEB_DIR / "templates")

    # WebSocket менеджер
    class ConnectionManager:
        def __init__(self):
            self.active_connections: list[WebSocket] = []

        async def connect(self, websocket: WebSocket):
            await websocket.accept()
            self.active_connections.append(websocket)
            logger.info(f"WebSocket клиент подключен. Всего: {len(self.active_connections)}")

        def disconnect(self, websocket: WebSocket):
            self.active_connections.remove(websocket)
            logger.info(f"WebSocket клиент отключен. Всего: {len(self.active_connections)}")

        async def broadcast(self, message: dict):
            for connection in self.active_connections:
                try:
                    await connection.send_json(message)
                except Exception as e:
                    logger.warning(f"Ошибка отправки WebSocket сообщения: {e}")

    manager = ConnectionManager()

    # =========================================================================
    # Routes
    # =========================================================================

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        """Главная страница — Advanced UI."""
        return templates.TemplateResponse("index.html", {"request": request})

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """WebSocket endpoint для real-time broadcast."""
        await manager.connect(websocket)
        
        # Регистрация в WebEnvironment для получения broadcast'ов
        web_environment.connected_clients.add(websocket)
        
        try:
            while True:
                # Поддержание соединения
                data = await websocket.receive_text()
                # Можно обрабатывать команды от клиента, если нужно
        except WebSocketDisconnect:
            manager.disconnect(websocket)
            web_environment.connected_clients.discard(websocket)

    @app.get("/api/state")
    async def get_state():
        """Получение текущего состояния Леи."""
        return {
            "state": web_environment.leya.state if web_environment.leya else "unknown",
            "name": web_environment.leya.name if web_environment.leya else "Лея",
        }

    @app.get("/api/drives")
    async def get_drives():
        """Получение состояния драйвов."""
        if not web_environment.leya:
            return {}
        
        return {
            drive_type.value: drive.current
            for drive_type, drive in web_environment.leya.drives.drives.items()
        }

    @app.get("/api/memory/recent")
    async def get_recent_memory(limit: int = 20):
        """Получение недавних эпизодов памяти."""
        if not web_environment.leya:
            return []
        
        try:
            episodes = await web_environment.leya.memory.get_recent_episodes(limit=limit)
            return [
                {
                    "id": e.id,
                    "content": e.content,
                    "memory_type": e.memory_type.value,
                    "retention_strength": e.retention_strength,
                    "timestamp": e.timestamp,
                }
                for e in episodes
            ]
        except Exception as e:
            logger.error(f"Ошибка получения памяти: {e}")
            return []

    @app.post("/api/message")
    async def send_message(request: MessageRequest):
        """Отправка сообщения от пользователя."""
        if not web_environment.leya:
            return JSONResponse({"error": "Лея не инициализирована"}, status_code=500)
        
        try:
            # Добавление в очередь ввода
            await web_environment.handle_user_message(request.content)
            return {"status": "ok", "message": "Сообщение принято"}
        except Exception as e:
            logger.error(f"Ошибка обработки сообщения: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.get("/api/thoughts")
    async def get_thoughts(limit: int = 10):
        """Получение недавних мыслей."""
        if not web_environment.leya:
            return []
        
        try:
            thoughts = await web_environment.leya.memory.get_recent_spontaneous_thoughts(limit=limit)
            return [
                {
                    "content": t.content,
                    "timestamp": t.timestamp,
                    "thought_type": t.metadata.get("thought_type", "spontaneous"),
                }
                for t in thoughts
            ]
        except Exception as e:
            logger.error(f"Ошибка получения мыслей: {e}")
            return []

    return app


async def run_server(web_environment):
    """
    Запуск веб-сервера.
    
    Args:
        web_environment: Экземпляр WebEnvironment
    """
    import uvicorn
    
    app = create_app(web_environment)
    
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info",
    )
    server = uvicorn.Server(config)
    
    await server.serve()