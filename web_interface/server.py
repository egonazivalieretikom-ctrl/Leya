"""
web_interface/server.py — FastAPI веб-сервер для Леи.
"""

import os
import logging

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles

logger = logging.getLogger("WebServer")

app = FastAPI(title="Leya OS")

# Пути к файлам
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
STATIC_DIR = os.path.join(BASE_DIR, "static")
TEMPLATES_DIR = os.path.join(BASE_DIR, "templates")

# Монтируем статические файлы
if os.path.exists(STATIC_DIR):
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


# Храним ссылку на web_environment
_web_env = None


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Главная страница — чат с Леей."""
    template_path = os.path.join(TEMPLATES_DIR, "index.html")
    
    if os.path.exists(template_path):
        with open(template_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    
    return HTMLResponse("<h1>Leya OS</h1><p>Template not found</p>")


@app.get("/api/state")
async def get_state():
    """Возвращает текущее состояние Леи."""
    if not _web_env:
        return {
            "state": "initializing",
            "drives": {"curiosity": 0.3, "connection": 0.3, "integrity": 0.2, "autonomy": 0.3},
            "self_model": "",
            "connected_clients": 0,
            "soul": {
                "personality": "",
                "values": "",
                "rules": ""
            }
        }
    
    drives = {d.type.value: d.current for d in _web_env.leya.drives.drives.values()}
    self_model = await _web_env.leya.memory.get_self_model_context()
    
    # Читаем файлы души
    soul = {
        "personality": _web_env.soul_manager.read_file("personality.txt"),
        "values": _web_env.soul_manager.read_file("values.txt"),
        "rules": _web_env.soul_manager.read_file("rules.txt")
    }
    
    return {
        "state": _web_env.state.state,
        "drives": drives,
        "self_model": self_model,
        "connected_clients": _web_env.state.connected_clients,
        "soul": soul
    }


@app.post("/api/soul/{filename}")
async def save_soul_file(filename: str, request: Request):
    """Сохраняет файл души."""
    if not _web_env:
        return {"error": "Not initialized"}
    
    try:
        content = await request.text()
        result = _web_env.soul_manager.write_file(filename, content)
        
        # Транслируем обновление всем клиентам
        await _web_env.broadcast({
            "type": "soul_update",
            "data": {filename: content}
        })
        
        return {"result": result}
    except Exception as e:
        logger.error(f"Ошибка сохранения файла: {e}")
        return {"error": str(e)}


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint для коммуникации с Леей."""
    await websocket.accept()
    
    if not _web_env:
        await websocket.send_json({"type": "error", "data": "WebEnvironment not initialized"})
        await websocket.close()
        return
    
    # Подключаем клиента
    await _web_env.connect(websocket)
    
    try:
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type", "user_message")
            content = data.get("content", "")
            
            if message_type == "user_message" and content:
                # Транслируем сообщение пользователя всем клиентам
                await _web_env.broadcast({
                    "type": "user_message",
                    "content": content
                })
                # Отправляем в когнитивный цикл
                await _web_env.receive_user_message(content)
            
            elif message_type == "ping":
                # Пинг-понг для поддержания соединения
                pass
            
            elif message_type == "read_soul_file":
                filename = data.get("filename", "")
                if filename:
                    content = _web_env.soul_manager.read_file(filename)
                    await websocket.send_json({
                        "type": "soul_file_content",
                        "data": {"filename": filename, "content": content}
                    })
            
            elif message_type == "list_soul_files":
                files = _web_env.soul_manager.list_files()
                await websocket.send_json({
                    "type": "soul_files_list",
                    "data": {"files": files}
                })
    
    except WebSocketDisconnect:
        await _web_env.disconnect(websocket)
    except Exception as e:
        logger.error(f"WebSocket ошибка: {e}", exc_info=True)
        await _web_env.disconnect(websocket)


async def run_server(web_environment):
    """
    Запускает веб-сервер.
    Вызывается из LeyaOS.
    """
    global _web_env
    _web_env = web_environment
    
    import uvicorn
    
    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=8000,
        log_level="info"
    )
    server = uvicorn.Server(config)
    logger.info("WebServer: Запуск")
    await server.serve()