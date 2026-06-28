"""
web_interface/server.py
FastAPI сервер для веб-интерфейса Леи.

Шаг 1+2:
- Удалён ConnectionManager (дублирование WebSocket-логики).
- Все эндпоинты используют специфичные исключения из leya_core.exceptions.
- WebSocket endpoint использует только WebEnvironment.connect/disconnect.

Включает:
- Основные эндпоинты (/, /ws, /api/state, /api/drives, /api/message)
- Advanced UI эндпоинты (/api/self-model, /api/soul, /api/workspace/proposals, /api/memory/graph)
- Дополнительные эндпоинты (/api/memory/consolidate, /api/memory/forget, /api/workspace/submit)
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, Request, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel

from leya_core.exceptions import (
    LeyaBroadcastError,
    LeyaEnvironmentError,
    LeyaHomeostasisError,
    LeyaLLMError,
    LeyaMemoryError,
    LeyaSoulError,
    LeyaWorkspaceError,
)

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

    # =========================================================================
    # Основные эндпоинты
    # =========================================================================

    @app.get("/", response_class=HTMLResponse)
    async def root(request: Request):
        """Главная страница — Advanced UI."""
        return templates.TemplateResponse(request, "index.html")

    @app.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        """
        WebSocket endpoint для real-time broadcast.
        Использует ТОЛЬКО WebEnvironment для управления соединениями.
        """
        await web_environment.connect(websocket)
        try:
            while True:
                # Поддержание соединения. Клиент может отправлять команды.
                data = await websocket.receive_text()
                # TODO: обработка команд от клиента (например, "force_consolidate")
        except WebSocketDisconnect:
            pass
        finally:
            # Гарантированный disconnect даже при неожиданных ошибках
            web_environment.disconnect(websocket)

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
        """Получение состояния драйвов через публичный API."""
        if not web_environment.leya:
            return {}

        try:
            drives = web_environment.leya.drives
            # Используем публичный метод вместо прямого доступа к .drives.items()
            if hasattr(drives, "get_drives_state"):
                return drives.get_drives_state()

            # Fallback: если метод ещё не добавлен (не должно происходить)
            logger.warning("DriveSystem не имеет метода get_drives_state() — используется fallback")
            return {}

        except LeyaHomeostasisError as exc:
            logger.error(f"Ошибка драйвов: {exc}", exc_info=True)
            return JSONResponse({"error": str(exc), "type": "homeostasis"}, status_code=500)
        except Exception as exc:
            logger.exception(f"Неожиданная ошибка в /api/drives: {exc}")
            return JSONResponse({"error": "Internal error", "type": "unexpected"}, status_code=500)

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
        except LeyaMemoryError as exc:
            logger.error(f"Ошибка памяти: {exc}", exc_info=True)
            return JSONResponse({"error": str(exc), "type": "memory"}, status_code=500)
        except LeyaLLMError as exc:
            logger.error(f"Ошибка LLM при получении памяти: {exc}", exc_info=True)
            return JSONResponse({"error": str(exc), "type": "llm"}, status_code=503)
        except Exception as exc:
            logger.exception(f"Неожиданная ошибка в /api/memory/recent: {exc}")
            return JSONResponse({"error": "Internal error", "type": "unexpected"}, status_code=500)

    @app.post("/api/message")
    async def send_message(request: MessageRequest):
        """Отправка сообщения от пользователя."""
        if not web_environment.leya:
            return JSONResponse({"error": "Лея не инициализирована"}, status_code=500)

        try:
            await web_environment.handle_user_message(request.content)
            return {"status": "ok", "message": "Сообщение принято"}
        except LeyaEnvironmentError as exc:
            logger.error(f"Ошибка окружения: {exc}", exc_info=True)
            return JSONResponse({"error": str(exc), "type": "environment"}, status_code=500)
        except LeyaBroadcastError as exc:
            logger.error(f"Ошибка broadcast: {exc}", exc_info=True)
            return JSONResponse({"error": str(exc), "type": "broadcast"}, status_code=500)
        except Exception as exc:
            logger.exception(f"Неожиданная ошибка в /api/message: {exc}")
            return JSONResponse({"error": "Internal error", "type": "unexpected"}, status_code=500)

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
        except LeyaMemoryError as exc:
            logger.error(f"Ошибка памяти при получении self_model: {exc}", exc_info=True)
            return JSONResponse(
                {"self_model": "", "error": str(exc), "type": "memory"}, status_code=500
            )
        except Exception as exc:
            logger.exception(f"Неожиданная ошибка в /api/self-model: {exc}")
            return JSONResponse(
                {"self_model": "", "error": "Internal error", "type": "unexpected"}, status_code=500
            )

    @app.get("/api/soul")
    async def get_soul_files():
        """Получение содержимого файлов души."""
        if not web_environment.leya:
            return {}
        try:
            if hasattr(web_environment, "soul_manager"):
                return web_environment.soul_manager.get_all_contents()
            return {}
        except LeyaSoulError as exc:
            logger.error(f"Ошибка души: {exc}", exc_info=True)
            return JSONResponse({"error": str(exc), "type": "soul"}, status_code=500)
        except Exception as exc:
            logger.exception(f"Неожиданная ошибка в /api/soul: {exc}")
            return JSONResponse({"error": "Internal error", "type": "unexpected"}, status_code=500)

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
        except LeyaSoulError as exc:
            logger.error(f"Ошибка обновления души: {exc}", exc_info=True)
            return JSONResponse({"error": str(exc), "type": "soul"}, status_code=500)
        except LeyaBroadcastError as exc:
            logger.error(f"Ошибка broadcast soul update: {exc}", exc_info=True)
            return JSONResponse({"error": str(exc), "type": "broadcast"}, status_code=500)
        except Exception as exc:
            logger.exception(f"Неожиданная ошибка в /api/soul/update: {exc}")
            return JSONResponse({"error": "Internal error", "type": "unexpected"}, status_code=500)

    @app.get("/api/workspace/proposals")
    async def get_workspace_proposals():
        """Получение proposals и focus через публичный API workspace."""
        if not web_environment.leya:
            return {"proposals": [], "focus": None, "total": 0}

        try:
            workspace = web_environment.leya.workspace

            # Используем публичный метод вместо прямого доступа к workspace.proposals
            if hasattr(workspace, "get_workspace_status"):
                return workspace.get_workspace_status()

            # Fallback: если метод ещё не добавлен
            logger.warning(
                "GlobalWorkspace не имеет метода get_workspace_status() — используется fallback"
            )
            return {"proposals": [], "focus": None, "total": 0}

        except LeyaWorkspaceError as exc:
            logger.error(f"Ошибка workspace: {exc}", exc_info=True)
            return JSONResponse(
                {"proposals": [], "focus": None, "error": str(exc), "type": "workspace"},
                status_code=500,
            )
        except Exception as exc:
            logger.exception(f"Неожиданная ошибка в /api/workspace/proposals: {exc}")
            return JSONResponse(
                {"proposals": [], "focus": None, "error": "Internal error", "type": "unexpected"},
                status_code=500,
            )

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
        except LeyaWorkspaceError as exc:
            logger.error(f"Ошибка подачи proposal: {exc}", exc_info=True)
            return JSONResponse({"error": str(exc), "type": "workspace"}, status_code=500)
        except KeyError as exc:
            logger.error(f"Невалидный priority: {exc}", exc_info=True)
            return JSONResponse(
                {"error": f"Invalid priority: {exc}", "type": "validation"}, status_code=400
            )
        except Exception as exc:
            logger.exception(f"Неожиданная ошибка в /api/workspace/submit: {exc}")
            return JSONResponse({"error": "Internal error", "type": "unexpected"}, status_code=500)

    @app.get("/api/memory/graph")
    async def get_memory_graph(
        min_retention: float = 0.1,
        max_nodes: int = 100,
        include_synapses: bool = True,
    ):
        """
        Получение данных для графа памяти через публичный API.
        Вся логика фильтрации и построения nodes/edges — в MemorySystem.
        """
        if not web_environment.leya:
            return {"nodes": [], "edges": [], "total_engrams": 0, "total_synapses": 0}

        try:
            memory = web_environment.leya.memory

            # Используем публичный метод вместо прямого доступа к engrams/synapses
            if hasattr(memory, "get_memory_graph_data"):
                return await memory.get_memory_graph_data(
                    min_retention=min_retention,
                    max_nodes=max_nodes,
                    include_synapses=include_synapses,
                )

            # Fallback: если метод ещё не добавлен
            logger.warning(
                "MemorySystem не имеет метода get_memory_graph_data() — используется fallback"
            )
            return {"nodes": [], "edges": [], "total_engrams": 0, "total_synapses": 0}

        except LeyaMemoryError as exc:
            logger.error(f"Ошибка памяти при построении графа: {exc}", exc_info=True)
            return JSONResponse(
                {"nodes": [], "edges": [], "error": str(exc), "type": "memory"}, status_code=500
            )
        except Exception as exc:
            logger.exception(f"Неожиданная ошибка в /api/memory/graph: {exc}")
            return JSONResponse(
                {"nodes": [], "edges": [], "error": "Internal error", "type": "unexpected"},
                status_code=500,
            )

    @app.post("/api/memory/consolidate")
    async def consolidate_memories():
        """Запуск консолидации памяти."""
        if not web_environment.leya:
            return JSONResponse({"error": "Лея не инициализирована"}, status_code=500)
        try:
            stats = await web_environment.leya.memory.consolidate_memories()
            return {"status": "ok", "stats": stats}
        except LeyaMemoryError as exc:
            logger.error(f"Ошибка консолидации: {exc}", exc_info=True)
            return JSONResponse({"error": str(exc), "type": "memory"}, status_code=500)
        except LeyaLLMError as exc:
            logger.error(f"Ошибка LLM при консолидации: {exc}", exc_info=True)
            return JSONResponse({"error": str(exc), "type": "llm"}, status_code=503)
        except Exception as exc:
            logger.exception(f"Неожиданная ошибка в /api/memory/consolidate: {exc}")
            return JSONResponse({"error": "Internal error", "type": "unexpected"}, status_code=500)

    @app.post("/api/memory/forget")
    async def forget_weak_memories(request: dict):
        """Забыть слабые воспоминания."""
        if not web_environment.leya:
            return JSONResponse({"error": "Лея не инициализирована"}, status_code=500)
        try:
            threshold = float(request.get("threshold", 0.1))
            forgotten = await web_environment.leya.memory.forget_weak_memories(threshold)
            return {"status": "ok", "forgotten": forgotten}
        except LeyaMemoryError as exc:
            logger.error(f"Ошибка забывания: {exc}", exc_info=True)
            return JSONResponse({"error": str(exc), "type": "memory"}, status_code=500)
        except ValueError as exc:
            logger.error(f"Невалидный threshold: {exc}", exc_info=True)
            return JSONResponse(
                {"error": f"Invalid threshold: {exc}", "type": "validation"}, status_code=400
            )
        except Exception as exc:
            logger.exception(f"Неожиданная ошибка в /api/memory/forget: {exc}")
            return JSONResponse({"error": "Internal error", "type": "unexpected"}, status_code=500)

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

    try:
        await server.serve()
    finally:
        # Graceful shutdown: закрываем все WebSocket соединения
        if hasattr(web_environment, "shutdown"):
            await web_environment.shutdown()
