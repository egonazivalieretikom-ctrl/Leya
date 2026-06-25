import asyncio
import json
import logging
from typing import Dict, Any, Set
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
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

# Отслеживание подключенных клиентов на уровне сервера
connected_clients: Set[WebSocket] = set()

def init_server(env):
    """Инициализация сервера с ссылкой на WebEnvironment"""
    global web_env
    web_env = env

@app.get("/", response_class=HTMLResponse)
async def index(request: Request):
    return templates.TemplateResponse(
        request=request,
        name="index.html"
    )

@app.get("/api/state")
async def get_state():
    if not web_env:
        return JSONResponse({"error": "Server not initialized"}, status_code=500)
    
    try:
        leya = web_env.leya
        drives = {d.type.value: d.current for d in leya.drives.drives.values()}
        
        # Читаем файлы души
        soul_files = {}
        for filename in ["personality.txt", "values.txt", "rules.txt"]:
            try:
                soul_files[filename.replace(".txt", "")] = web_env.soul_manager.read_file(filename)
            except Exception as e:
                logger.warning(f"Не удалось прочитать {filename}: {e}")
                soul_files[filename.replace(".txt", "")] = ""
        
        return {
            "state": leya.state,
            "drives": drives,
            "connected_clients": len(connected_clients),
            "soul": soul_files
        }
    except Exception as e:
        logger.error(f"Ошибка получения состояния: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.post("/api/soul/{filename}")
async def save_soul_file(filename: str, request: Request):
    try:
        content = await request.body()
        result = web_env.soul_manager.write_file(filename, content.decode("utf-8"))
        return {"result": result}
    except Exception as e:
        logger.error(f"Ошибка сохранения файла {filename}: {e}")
        return JSONResponse({"error": str(e)}, status_code=500)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    # ВАЖНО: Принимаем соединение ПЕРЕД любым использованием
    await websocket.accept()
    connected_clients.add(websocket)
    
    logger.info(f"WebSocket клиент подключен. Всего: {len(connected_clients)}")
    
    try:
        # Отправляем приветственное сообщение
        await websocket.send_json({
            "type": "connected",
            "message": "Подключение установлено"
        })
        
        while True:
            # Получаем данные от клиента
            data = await websocket.receive_json()
            
            if data.get("type") == "user_message":
                content = data.get("content", "")
                logger.info(f"Получено сообщение от пользователя: {content[:100]}")
                
                # Обрабатываем сообщение через WebEnvironment
                if web_env:
                    try:
                        await web_env.handle_user_message(content)
                    except Exception as e:
                        logger.error(f"Ошибка обработки сообщения: {e}")
                        await websocket.send_json({
                            "type": "error",
                            "message": f"Ошибка обработки: {str(e)}"
                        })
                else:
                    await websocket.send_json({
                        "type": "error",
                        "message": "Сервер не инициализирован"
                    })
            
            elif data.get("type") == "ping":
                await websocket.send_json({"type": "pong"})
    
    except WebSocketDisconnect:
        logger.info("WebSocket клиент отключен")
    except Exception as e:
        logger.error(f"WebSocket ошибка: {e}")
    finally:
        # Удаляем клиента из списка подключенных
        connected_clients.discard(websocket)
        logger.info(f"Клиент удален. Осталось подключений: {len(connected_clients)}")
        
        # Корректно закрываем соединение, если оно еще открыто
        try:
            if websocket.client_state.CONNECTED:
                await websocket.close()
        except Exception:
            pass

async def run_server(env):
    """Запускает uvicorn сервер"""
    import uvicorn
    init_server(env)
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()