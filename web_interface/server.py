import asyncio
import logging
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from starlette.requests import Request
import uvicorn

logger = logging.getLogger("WebServer")

# Глобальное множество подключенных WebSocket-клиентов
connected_clients: set = set()

app = FastAPI(title="Leya Web Interface")

# Подключаем статику и шаблоны, если они есть
static_dir = os.path.join(os.path.dirname(__file__), "static")
templates_dir = os.path.join(os.path.dirname(__file__), "templates")

if os.path.exists(static_dir):
    app.mount("/static", StaticFiles(directory=static_dir), name="static")

templates = Jinja2Templates(directory=templates_dir) if os.path.exists(templates_dir) else None

# Глобальная ссылка на окружение
web_env = None

def init_app(environment):
    """Инициализирует веб-приложение с окружением."""
    global web_env
    web_env = environment

@app.get("/", response_class=HTMLResponse)
async def get_index(request: Request):
    """Главная страница веб-интерфейса."""
    if templates:
        try:
            return templates.TemplateResponse(name="index.html", request=request)
        except Exception as e:
            logger.warning(f"Не удалось загрузить шаблон index.html: {e}")
    
    # Fallback на встроенный HTML
    return HTMLResponse(content="""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Лея - Цифровое сознание</title>
        <meta charset="utf-8">
        <style>
            body { 
                font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; 
                max-width: 800px; 
                margin: 50px auto; 
                padding: 20px;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
            }
            h1 { 
                font-size: 3em; 
                margin-bottom: 10px;
                text-shadow: 2px 2px 4px rgba(0,0,0,0.3);
            }
            .status { 
                padding: 20px; 
                background: rgba(255,255,255,0.2); 
                border-radius: 10px; 
                margin: 20px 0;
                backdrop-filter: blur(10px);
            }
            .status strong {
                display: inline-block;
                width: 120px;
            }
            p { 
                line-height: 1.6;
                background: rgba(255,255,255,0.1);
                padding: 15px;
                border-radius: 5px;
            }
            code {
                background: rgba(0,0,0,0.3);
                padding: 2px 6px;
                border-radius: 3px;
                font-family: 'Courier New', monospace;
            }
        </style>
    </head>
    <body>
        <h1>🧠 Лея</h1>
        <div class="status">
            <strong>Статус:</strong> Веб-интерфейс запущен<br>
            <strong>WebSocket:</strong> <code>ws://localhost:8000/ws</code>
        </div>
        <p>
            HTML-шаблоны не найдены. Создайте папку <code>web_interface/templates</code> 
            и добавьте файл <code>index.html</code> для кастомного интерфейса.
        </p>
    </body>
    </html>
    """)

@app.get("/api/state")
async def get_state():
    """REST API для получения состояния Леи."""
    if not web_env:
        return {"error": "Environment not initialized"}
    
    try:
        # Получаем состояние из web_env
        state = {
            "status": "awake",
            "drives": {},
            "self_model": ""
        }
        
        # Если есть доступ к leya_os, получаем реальное состояние
        if hasattr(web_env, 'leya_os'):
            leya = web_env.leya_os
            state["drives"] = {d.type.value: d.current for d in leya.drives.drives.values()}
            state["self_model"] = await leya.memory.get_self_model_context()
        
        return state
    except Exception as e:
        logger.error(f"Ошибка получения состояния: {e}")
        return {"error": str(e)}

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    """WebSocket endpoint для взаимодействия с Леей."""
    if not web_env:
        await websocket.close(code=1011, reason="Environment not initialized")
        return
    
    # Принимаем WebSocket соединение
    await websocket.accept()
    
    # СНАЧАЛА добавляем клиента
    connected_clients.add(websocket)
    
    # ПОТОМ логируем с правильным счетчиком
    logger.info(f"WebSocket клиент подключен. Всего клиентов: {len(connected_clients)}")
    
    try:
        while True:
            data = await websocket.receive_json()
            if data.get("type") == "user_message":
                content = data.get("content", "")
                if content:
                    await web_env.handle_user_message(content)
    except WebSocketDisconnect:
        logger.info("WebSocket клиент отключен")
    except Exception as e:
        logger.error(f"WebSocket error: {e}", exc_info=True)
    finally:
        connected_clients.discard(websocket)
        if web_env:
            await web_env.disconnect(websocket)
        logger.info(f"Клиент удален. Осталось клиентов: {len(connected_clients)}")

async def run_server(environment):
    """Точка входа для запуска веб-сервера из LeyaOS."""
    init_app(environment)
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()