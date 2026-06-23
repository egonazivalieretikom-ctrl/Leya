"""
FastAPI сервер для веб-интерфейса Леи.
Запускается параллельно с LeyaOS.
"""

import asyncio
import logging
import os
from typing import Dict, Any
from contextlib import asynccontextmanager

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.requests import Request

logger = logging.getLogger("WebServer")

# Глобальная ссылка на WebEnvironment
_web_env = None


def set_web_environment(env):
    """Устанавливает глобальную ссылку на WebEnvironment"""
    global _web_env
    _web_env = env


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("WebServer: Запуск")
    yield
    logger.info("WebServer: Остановка")


app = FastAPI(title="LeyaOS Web Interface", lifespan=lifespan)

# Статика и шаблоны
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
app.mount("/static", StaticFiles(directory=os.path.join(BASE_DIR, "static")), name="static")
templates = Jinja2Templates(directory=os.path.join(BASE_DIR, "templates"))


@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    """Главная страница интерфейса"""
    context = {"request": request}
    return templates.TemplateResponse(request, "index.html", context)


@app.get("/api/state")
async def get_state():
    """Возвращает текущее состояние Леи"""
    if not _web_env:
        raise HTTPException(status_code=503, detail="Лея еще не готова")
    
    leya = _web_env.leya
    
    return {
        "state": leya.state,
        "name": leya.name,
        "drives": {d.type.value: d.tension for d in leya.drives.drives.values()},
        "self_model": await leya.memory.get_self_model_context(),
        "soul": {
            "personality": _web_env.soul_manager.read_file("personality.txt"),
            "values": _web_env.soul_manager.read_file("values.txt"),
            "rules": _web_env.soul_manager.read_file("rules.txt"),
        },
        "connected_clients": len(_web_env.connected_clients)
    }


@app.get("/api/memory")
async def get_memory():
    """Возвращает последнюю память"""
    if not _web_env:
        raise HTTPException(status_code=503)
    
    leya = _web_env.leya
    episodes = await leya.memory.get_recent_episodes(limit=10)
    
    return {
        "episodes": episodes,
        "total_episodes": len(episodes)
    }


@app.post("/api/soul/{filename}")
async def update_soul_file(filename: str, content: str):
    """Обновляет файл души (вызывается из UI)"""
    if not _web_env:
        raise HTTPException(status_code=503)
    
    # Разрешаем только .txt файлы из папки души
    if not filename.endswith(".txt"):
        raise HTTPException(status_code=400, detail="Только .txt файлы")
    
    result = _web_env.soul_manager.write_file(filename, content)
    
    # Уведомляем всех клиентов об обновлении
    await _web_env.broadcast_soul_update({
        "personality": _web_env.soul_manager.read_file("personality.txt"),
        "values": _web_env.soul_manager.read_file("values.txt"),
        "rules": _web_env.soul_manager.read_file("rules.txt"),
    })
    
    return {"result": result}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket для real-time коммуникации"""
    if not _web_env:
        await websocket.close(code=1011, reason="Лея еще не готова")
        return
    
    await _web_env.connect(websocket)
    
    try:
        while True:
            # Получаем сообщения от клиента
            data = await websocket.receive_json()
            
            if data.get("type") == "user_message":
                await _web_env.handle_user_message(data.get("content", ""))
            
            elif data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    
    except WebSocketDisconnect:
        _web_env.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket ошибка: {e}")
        _web_env.disconnect(websocket)


async def run_server(web_env, host: str = "0.0.0.0", port: int = 8000):
    """Запускает сервер (вызывается из LeyaOS)"""
    import uvicorn
    
    set_web_environment(web_env)
    
    config = uvicorn.Config(
        app,
        host=host,
        port=port,
        log_level="info",
        access_log=False
    )
    server = uvicorn.Server(config)
    await server.serve()