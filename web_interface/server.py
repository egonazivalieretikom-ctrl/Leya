"""
web_interface/server.py
FastAPI сервер для веб-интерфейса Леи.

Включает:
- Основные эндпоинты (/, /ws, /api/state, /api/drives, /api/message)
- Advanced UI эндпоинты (/api/self-model, /api/soul, /api/workspace/proposals, /api/memory/graph)
- Дополнительные эндпоинты (/api/memory/consolidate, /api/memory/forget, /api/workspace/submit)
"""
from __future__ import annotations

import json
import logging
import time
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
    # Основные эндпоинты
    # =========================================================================

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        """Главная страница — Advanced UI."""
        return templates.TemplateResponse(request, "index.html")

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
        if not web_environment.leya:
            return {"state": "unknown", "name": "Лея"}
        return {
            "state": web_environment.leya.state,
            "name": web_environment.leya.name,
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

    # =========================================================================
    # Advanced UI эндпоинты
    # =========================================================================

    @app.get("/api/self-model")
    async def get_self_model():
        """Получение текущей само-модели."""
        if not web_environment.leya:
            return {"self_model": ""}
        try:
            self_model = await web_environment.leya.memory.get_self_model_context()
            return {"self_model": self_model}
        except Exception as e:
            logger.error(f"Ошибка получения self_model: {e}")
            return {"self_model": "", "error": str(e)}

    @app.get("/api/soul")
    async def get_soul_files():
        """Получение содержимого файлов души."""
        if not web_environment.leya:
            return {}
        try:
            if hasattr(web_environment, "soul_manager"):
                return web_environment.soul_manager.get_all_contents()
            return {}
        except Exception as e:
            logger.error(f"Ошибка получения soul files: {e}")
            return {}

    @app.post("/api/soul/update")
    async def update_soul_file(request: dict):
        """Обновление файла души."""
        if not web_environment.leya:
            return JSONResponse({"error": "Лея не инициализирована"}, status_code=500)
        try:
            filename = request.get("filename")
            content = request.get("content", "")
            if not filename:
                return JSONResponse({"error": "filename не указан"}, status_code=400)
            if hasattr(web_environment, "soul_manager"):
                result = web_environment.soul_manager.write_file(filename, content)
                await web_environment.broadcast_soul_update(
                    web_environment.soul_manager.get_all_contents()
                )
                return {"status": "ok", "result": result}
            return JSONResponse({"error": "SoulManager не доступен"}, status_code=500)
        except Exception as e:
            logger.error(f"Ошибка обновления soul file: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.get("/api/workspace/proposals")
    async def get_workspace_proposals():
        """Получение текущих proposals из workspace."""
        if not web_environment.leya:
            return {"proposals": [], "focus": None}
        try:
            workspace = web_environment.leya.workspace
            proposals = [
                {
                    "id": i,
                    "source": p.source,
                    "content": p.content,
                    "action_type": p.action_type,
                    "priority": p.priority.name,
                    "urgency": p.urgency,
                    "drive_relevance": p.drive_relevance,
                    "timestamp": p.timestamp,
                    "age_seconds": time.time() - p.timestamp,
                }
                for i, p in enumerate(workspace.proposals)
            ]
            focus = workspace.get_focus()
            focus_data = None
            if focus:
                focus_data = {
                    "source": focus.source,
                    "content": focus.content,
                    "action_type": focus.action_type,
                    "priority": focus.priority.name,
                }
            return {"proposals": proposals, "focus": focus_data, "total": len(proposals)}
        except Exception as e:
            logger.error(f"Ошибка получения proposals: {e}")
            return {"proposals": [], "focus": None, "error": str(e)}

    @app.post("/api/workspace/submit")
    async def force_submit_proposal(request: dict):
        """Принудительная подача proposal в workspace."""
        if not web_environment.leya:
            return JSONResponse({"error": "Лея не инициализирована"}, status_code=500)
        try:
            from leya_core.global_workspace import Priority
            workspace = web_environment.leya.workspace
            proposal = workspace.force_submit(
                source=request.get("source", "manual"),
                content=request.get("content", ""),
                action_type=request.get("action_type", "none"),
                priority=Priority[request.get("priority", "MEDIUM").upper()],
                urgency=float(request.get("urgency", 0.5)),
                drive_relevance=float(request.get("drive_relevance", 0.5)),
            )
            return {"status": "ok", "proposal_id": id(proposal)}
        except Exception as e:
            logger.error(f"Ошибка подачи proposal: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.get("/api/memory/graph")
    async def get_memory_graph(
        min_retention: float = 0.1,
        max_nodes: int = 100,
        include_synapses: bool = True,
    ):
        """Получение данных для графа памяти (узлы и рёбра)."""
        if not web_environment.leya:
            return {"nodes": [], "edges": []}
        try:
            memory = web_environment.leya.memory
            engrams = [
                e for e in memory.engrams.values()
                if e.retention_strength >= min_retention
            ]
            engrams.sort(key=lambda e: e.retention_strength, reverse=True)
            engrams = engrams[:max_nodes]

            nodes = []
            for engram in engrams:
                color = "#00d4ff" if engram.memory_type.value == "episodic" else "#ffb347"
                size = 10 + min(30, engram.retrieval_count * 2)
                label = engram.content[:50] + "..." if len(engram.content) > 50 else engram.content
                nodes.append({
                    "id": engram.id,
                    "label": label,
                    "title": (
                        f"<b>{engram.memory_type.value}</b><br>{engram.content}<br><br>"
                        f"Retention: {engram.retention_strength:.2f}<br>"
                        f"Retrievals: {engram.retrieval_count}<br>"
                        f"Emotional: {engram.emotional_boost:.2f}"
                    ),
                    "color": {
                        "background": color,
                        "border": color,
                        "highlight": {"background": "#ffffff", "border": color},
                    },
                    "size": size,
                    "memory_type": engram.memory_type.value,
                    "retention_strength": engram.retention_strength,
                    "retrieval_count": engram.retrieval_count,
                    "emotional_boost": engram.emotional_boost,
                })

            edges = []
            if include_synapses:
                node_ids = {n["id"] for n in nodes}
                for synapse in memory.synapses.values():
                    if synapse.source_id in node_ids and synapse.target_id in node_ids:
                        edges.append({
                            "from": synapse.source_id,
                            "to": synapse.target_id,
                            "width": 1 + synapse.weight * 5,
                            "color": {
                                "color": f"rgba(0, 212, 255, {synapse.weight})",
                                "highlight": "#ffffff",
                            },
                            "title": f"Weight: {synapse.weight:.2f}<br>Activations: {synapse.activation_count}",
                        })

            return {
                "nodes": nodes,
                "edges": edges,
                "total_engrams": len(memory.engrams),
                "total_synapses": len(memory.synapses),
            }
        except Exception as e:
            logger.error(f"Ошибка получения графа памяти: {e}")
            return {"nodes": [], "edges": [], "error": str(e)}

    @app.post("/api/memory/consolidate")
    async def consolidate_memories():
        """Запуск консолидации памяти."""
        if not web_environment.leya:
            return JSONResponse({"error": "Лея не инициализирована"}, status_code=500)
        try:
            stats = await web_environment.leya.memory.consolidate_memories()
            return {"status": "ok", "stats": stats}
        except Exception as e:
            logger.error(f"Ошибка консолидации: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.post("/api/memory/forget")
    async def forget_weak_memories(request: dict):
        """Забыть слабые воспоминания."""
        if not web_environment.leya:
            return JSONResponse({"error": "Лея не инициализирована"}, status_code=500)
        try:
            threshold = float(request.get("threshold", 0.1))
            forgotten = await web_environment.leya.memory.forget_weak_memories(threshold)
            return {"status": "ok", "forgotten": forgotten}
        except Exception as e:
            logger.error(f"Ошибка забывания: {e}")
            return JSONResponse({"error": str(e)}, status_code=500)

    @app.get("/favicon.ico")
    async def favicon():
        """Пустой favicon, чтобы не было 404."""
        from fastapi.responses import Response
        return Response(content=b"", media_type="image/x-icon")

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