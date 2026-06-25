# web_interface/server.py
import asyncio
import json
import logging
from typing import Dict, Any
from fastapi import FastAPI, WebSocket, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pathlib import Path

logger = logging.getLogger("WebServer")

app = FastAPI(title="LeyaOS Web Interface")

# Пути к статике и шаблонам
BASE_DIR = Path(__file__).parent
app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
templates = Jinja2Templates(directory=BASE_DIR / "templates")

# Глобальная ссылка на WebEnvironment
web_env = None

def init_server(env):
    """Инициализация сервера с ссылкой на WebEnvironment"""
    global web_env
    web_env = env

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/api/state")
async def get_state():
    if not web_env:
        return JSONResponse({"error": "Server not initialized"}, status_code=500)
    
    leya = web_env.leya
    drives = {d.type.value: d.current for d in leya.drives.drives.values()}
    
    # Читаем файлы души
    soul_files = {}
    for filename in ["personality.txt", "values.txt", "rules.txt"]:
        soul_files[filename.replace(".txt", "")] = web_env.soul_manager.read_file(filename)
    
    return {
        "state": leya.state,
        "drives": drives,
        "self_model": await leya.memory.get_self_model_context(),
        "connected_clients": len(web_env.connected_clients),
        "soul": soul_files
    }

@app.post("/api/soul/{filename}")
async def save_soul_file(filename: str, request: Request):
    content = await request.body()
    result = web_env.soul_manager.write_file(filename, content.decode("utf-8"))
    return {"result": result}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await web_env.connect(websocket)
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "user_message":
                await web_env.handle_user_message(data.get("content", ""))
            elif data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        web_env.disconnect(websocket)

async def run_server(env):
    """Запускает uvicorn сервер"""
    import uvicorn
    init_server(env)
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()