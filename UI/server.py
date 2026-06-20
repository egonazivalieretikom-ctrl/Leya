from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from Core.logger import log
from Core.event_bus import event_bus
import json
import asyncio

app = FastAPI()
connected_clients = []

# ============================================================================
# HTML / CSS / JS — AGI Dashboard
# ============================================================================
HTML = """
<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="UTF-8">
<title>Leya OS — AGI Dashboard</title>
<style>
    * { box-sizing: border-box; margin: 0; padding: 0; }
    body { font-family: 'Segoe UI', sans-serif; background: #0d1117; color: #e6edf3; height: 100vh; display: flex; flex-direction: column; overflow: hidden; }
    header { background: #161b22; border-bottom: 1px solid #30363d; padding: 12px 24px; display: flex; align-items: center; gap: 16px; }
    header h1 { font-size: 18px; color: #58a6ff; }
    .status-dot { display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #3fb950; margin-right: 6px; animation: pulse 2s infinite; }
    @keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }
    .main-grid { flex: 1; display: grid; grid-template-columns: 280px 1fr 380px; overflow: hidden; }
    
    /* Avatar Panel */
    .avatar-panel { background: #161b22; border-right: 1px solid #30363d; padding: 20px; display: flex; flex-direction: column; gap: 20px; overflow-y: auto; }
    .avatar-container { display: flex; flex-direction: column; align-items: center; gap: 12px; }
    #avatar-canvas { image-rendering: pixelated; width: 160px; height: 160px; border-radius: 16px; background: #0d1117; border: 2px solid #30363d; }
    .emotion-label { font-size: 14px; color: #f0f6fc; font-weight: 600; text-transform: uppercase; letter-spacing: 1px; }
    .environment-label { font-size: 11px; color: #7d8590; text-align: center; padding: 6px 10px; background: #0d1117; border-radius: 6px; border: 1px solid #30363d; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
    .hormones-section h3 { font-size: 11px; color: #7d8590; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 10px; }
    .hormone { margin-bottom: 8px; }
    .hormone-header { display: flex; justify-content: space-between; font-size: 11px; margin-bottom: 3px; }
    .hormone-name { color: #c9d1d9; } .hormone-value { color: #7d8590; font-family: monospace; }
    .hormone-bar { height: 4px; background: #21262d; border-radius: 2px; overflow: hidden; }
    .hormone-fill { height: 100%; border-radius: 2px; transition: width 0.5s ease; }
    .fill-dopamine{background:linear-gradient(90deg,#f97316,#fbbf24)}.fill-serotonin{background:linear-gradient(90deg,#a855f7,#ec4899)}.fill-cortisol{background:linear-gradient(90deg,#ef4444,#f97316)}.fill-oxytocin{background:linear-gradient(90deg,#ec4899,#f43f5e)}.fill-melatonin{background:linear-gradient(90deg,#6366f1,#8b5cf6)}.fill-norepinephrine{background:linear-gradient(90deg,#dc2626,#ef4444)}.fill-testosterone{background:linear-gradient(90deg,#dc2626,#991b1b)}.fill-estrogen{background:linear-gradient(90deg,#db2777,#f472b6)}.fill-endorphins{background:linear-gradient(90deg,#eab308,#facc15)}.fill-gaba{background:linear-gradient(90deg,#059669,#10b981)}
    
    /* Chat Panel */
    .chat-panel { display: flex; flex-direction: column; overflow: hidden; }
    #chat { flex: 1; overflow-y: auto; padding: 20px; display: flex; flex-direction: column; gap: 12px; }
    .msg { max-width: 75%; padding: 10px 14px; border-radius: 14px; font-size: 14px; line-height: 1.5; word-wrap: break-word; white-space: pre-wrap; }
    .msg.user { background: #1f6feb; color: white; align-self: flex-end; border-bottom-right-radius: 4px; }
    .msg.leya { background: #21262d; color: #e6edf3; align-self: flex-start; border: 1px solid #30363d; border-bottom-left-radius: 4px; }
    .msg.system { align-self: center; color: #7d8590; font-style: italic; font-size: 12px; }
    #input-area { border-top: 1px solid #30363d; padding: 14px 20px; display: flex; gap: 10px; background: #161b22; }
    #msg { flex: 1; padding: 10px 14px; background: #0d1117; border: 1px solid #30363d; color: #e6edf3; border-radius: 8px; outline: none; font-size: 14px; }
    #msg:focus { border-color: #1f6feb; }
    button { padding: 10px 20px; background: #1f6feb; border: none; color: white; cursor: pointer; border-radius: 8px; font-weight: 600; }
    button:hover { background: #388bfd; }
    
    /* Thought Panel */
    .thought-panel { background: #161b22; border-left: 1px solid #30363d; display: flex; flex-direction: column; overflow: hidden; }
    .thought-panel header { background: #161b22; border-bottom: 1px solid #30363d; padding: 12px 16px; }
    .thought-panel header h2 { font-size: 13px; color: #f0f6fc; text-transform: uppercase; letter-spacing: 1px; }
    #thoughts { flex: 1; overflow-y: auto; padding: 12px; display: flex; flex-direction: column; gap: 8px; }
    .thought-item { padding: 10px 12px; border-radius: 8px; font-size: 12px; line-height: 1.5; border-left: 3px solid; background: #0d1117; word-wrap: break-word; }
    .thought-label { font-size: 10px; text-transform: uppercase; letter-spacing: 1px; font-weight: 600; margin-bottom: 4px; opacity: 0.8; }
    .thought-text { color: #c9d1d9; }
    .thought-item.thinking { border-left-color: #a371f7; } .thought-item.thinking .thought-label { color: #a371f7; }
    .thought-item.insight { border-left-color: #fbbf24; } .thought-item.insight .thought-label { color: #fbbf24; }
    .thought-item.kg { border-left-color: #3fb950; } .thought-item.kg .thought-label { color: #3fb950; }
    .thought-item.phase { border-left-color: #58a6ff; } .thought-item.phase .thought-label { color: #58a6ff; }
    .thought-item.file { border-left-color: #f78166; } .thought-item.file .thought-label { color: #f78166; }
    .thought-item.planner { border-left-color: #ec4899; } .thought-item.planner .thought-label { color: #ec4899; }
    .thought-item.fast { border-left-color: #f97316; } .thought-item.fast .thought-label { color: #f97316; }
    
    ::-webkit-scrollbar { width: 8px; } ::-webkit-scrollbar-track { background: #0d1117; } ::-webkit-scrollbar-thumb { background: #30363d; border-radius: 4px; }
</style>
</head>
<body>
<header>
    <h1>🧠 Leya OS v0.5</h1>
    <div style="font-size:12px;color:#7d8590"><span class="status-dot"></span><span id="conn-status">Подключение...</span></div>
</header>
<div class="main-grid">
    <div class="avatar-panel">
        <div class="avatar-container">
            <canvas id="avatar-canvas" width="32" height="32"></canvas>
            <div class="emotion-label" id="emotion-label">NEUTRAL</div>
            <div class="environment-label" id="environment-label">Определение среды...</div>
        </div>
        <div class="hormones-section"><h3>Нейрохимия</h3><div id="hormones-container"></div></div>
    </div>
    <div class="chat-panel">
        <div id="chat"></div>
        <div id="input-area">
            <input type="text" id="msg" placeholder="Напиши Leya..." autocomplete="off">
            <button onclick="sendMsg()">Отправить</button>
        </div>
    </div>
    <div class="thought-panel">
        <header><h2>💭 Поток сознания</h2></header>
        <div id="thoughts"></div>
    </div>
</div>
<script>
var ws = new WebSocket("ws://" + window.location.host + "/ws");
var chat = document.getElementById("chat");
var msgInput = document.getElementById("msg");
var thoughts = document.getElementById("thoughts");

ws.onopen = function() { document.getElementById("conn-status").innerText = "Подключено к ядру"; addSystemMsg("🌟 Система активна."); };
ws.onclose = function() { document.getElementById("conn-status").innerText = "Отключено"; };

ws.onmessage = function(event) {
    var data = JSON.parse(event.data);
    switch(data.type) {
        case "chat": addChatMsg(data.role, data.text); break;
        case "state": updateAvatar(data.emotion); updateHormones(data.hormones); 
            if(data.environment) { document.getElementById("environment-label").innerText = data.environment; }
            if(data.emotion) { document.getElementById("emotion-label").innerText = data.emotion; } break;
        case "thought": addThought("thinking", "💭 Мысль", data.text); break;
        case "insight": addThought("insight", "💡 Инсайт DMN", data.text); break;
        case "kg_fact": addThought("kg", "🕸️ Граф Знаний", data.subject+" → "+data.predicate+" → "+data.object); break;
        case "phase": addThought("phase", "⚙️ Фаза", data.phase); break;
        case "file": addThought("file", "📄 Файл", data.name+" ("+data.language+")"); break;
        case "planner": addThought("planner", "🎯 Планировщик", data.text); break;
        case "fast_reaction": 
            var s = Object.entries(data.stimuli).map(function(e){return e[0]+": "+e[1]}).join(", ");
            addThought("fast", "⚡ Быстрая реакция", s); break;
    }
};

function addChatMsg(role, text) {
    var div = document.createElement("div"); div.className = "msg " + role; div.innerText = text;
    chat.appendChild(div); chat.scrollTop = chat.scrollHeight;
}
function addSystemMsg(text) {
    var div = document.createElement("div"); div.className = "msg system"; div.innerText = text;
    chat.appendChild(div); chat.scrollTop = chat.scrollHeight;
}
function addThought(type, label, text) {
    var item = document.createElement("div"); item.className = "thought-item " + type;
    item.innerHTML = '<div class="thought-label">'+label+'</div><div class="thought-text">'+text+'</div>';
    thoughts.appendChild(item); thoughts.scrollTop = thoughts.scrollHeight;
    while(thoughts.children.length > 50) thoughts.removeChild(thoughts.firstChild);
}

var HORMONE_NAMES = {dopamine:"Дофамин",serotonin:"Серотонин",cortisol:"Кортизол",oxytocin:"Окситоцин",melatonin:"Мелатонин",norepinephrine:"Норадреналин",testosterone:"Тестостерон",estrogen:"Эстроген",endorphins:"Эндорфины",gaba:"ГАМК"};
(function(){var c=document.getElementById("hormones-container");Object.keys(HORMONE_NAMES).forEach(function(k){var d=document.createElement("div");d.className="hormone";d.innerHTML='<div class="hormone-header"><span class="hormone-name">'+HORMONE_NAMES[k]+'</span><span class="hormone-value" id="val-'+k+'">0.00</span></div><div class="hormone-bar"><div class="hormone-fill fill-'+k+'" id="bar-'+k+'" style="width:0%"></div></div>';c.appendChild(d)})})();
function updateHormones(h) { Object.keys(h).forEach(function(k){var b=document.getElementById("bar-"+k),v=document.getElementById("val-"+k);if(b&&v){b.style.width=(h[k]*100)+"%";v.innerText=h[k].toFixed(2)}}) }

// Pixel Avatar
var canvas=document.getElementById("avatar-canvas"),ctx=canvas.getContext("2d");ctx.imageSmoothingEnabled=false;
var PALETTES={NEUTRAL:{skin:"#f4c28a",outline:"#2d1b0e",eye:"#1a1a1a",mouth:"#8b3a3a",bg:"#1e293b"},HAPPY:{skin:"#f4c28a",outline:"#2d1b0e",eye:"#1a1a1a",mouth:"#c23b3b",bg:"#1e3a2e",blush:"#e89090"},THINKING:{skin:"#f4c28a",outline:"#2d1b0e",eye:"#1a1a1a",mouth:"#8b3a3a",bg:"#2d1b4e"},SLEEPY:{skin:"#d4a574",outline:"#2d1b0e",eye:"#2d1b0e",mouth:"#8b3a3a",bg:"#1a1a3e"},STRESSED:{skin:"#e8a878",outline:"#2d1b0e",eye:"#1a1a1a",mouth:"#5a2020",bg:"#3e1a1a",sweat:"#6eb5ff"},FLOW:{skin:"#f4c28a",outline:"#2d1b0e",eye:"#fbbf24",mouth:"#c23b3b",bg:"#3a1e4e",sparkle:"#fbbf24"},FOCUSED:{skin:"#e8a878",outline:"#2d1b0e",eye:"#1a1a1a",mouth:"#5a2020",bg:"#3e2a1a"},SAD:{skin:"#c4a584",outline:"#2d1b0e",eye:"#4a6fa5",mouth:"#5a3a3a",bg:"#1a2a3e",tear:"#6eb5ff"},LOVING:{skin:"#f4c28a",outline:"#2d1b0e",eye:"#1a1a1a",mouth:"#c23b3b",bg:"#3e1a2e",blush:"#e85050",heart:"#ff3860"}};
var FACE=[[0,0,0,0,0,1,1,1,1,1,1,0,0,0,0,0],[0,0,0,1,1,1,1,1,1,1,1,1,1,0,0,0],[0,0,1,1,1,1,2,2,2,2,1,1,1,1,0,0],[0,1,1,1,2,3,3,3,3,3,3,2,1,1,1,0],[0,1,1,2,3,3,3,3,3,3,3,3,2,1,1,0],[1,1,2,3,3,4,4,3,3,4,4,3,3,2,1,1],[1,1,2,3,3,4,4,3,3,4,4,3,3,2,1,1],[1,1,2,3,3,3,3,3,3,3,3,3,3,2,1,1],[1,1,2,3,6,3,3,3,3,3,3,6,3,2,1,1],[1,1,2,3,3,3,5,5,5,5,3,3,3,2,1,1],[1,1,2,3,3,3,3,3,3,3,3,3,3,2,1,1],[0,1,1,2,3,3,3,3,3,3,3,3,2,1,1,0],[0,1,1,1,2,3,3,3,3,3,3,2,1,1,1,0],[0,0,1,1,1,2,2,2,2,2,2,1,1,1,0,0],[0,0,0,1,1,1,1,1,1,1,1,1,1,0,0,0],[0,0,0,0,0,1,1,1,1,1,1,0,0,0,0,0]];
function drawAvatar(emotion){var p=PALETTES[emotion]||PALETTES.NEUTRAL;var cm={0:null,1:p.bg,2:p.outline,3:p.skin,4:p.eye,5:p.mouth,6:p.blush||p.skin,7:p.sparkle||p.heart||p.eye};ctx.fillStyle=p.bg;ctx.fillRect(0,0,32,32);for(var y=0;y<16;y++)for(var x=0;x<16;x++){var v=FACE[y][x];var c=cm[v];if(c){ctx.fillStyle=c;ctx.fillRect(x*2,y*2,2,2)}}}
function updateAvatar(e){drawAvatar(e)} drawAvatar("NEUTRAL");

function sendMsg(){var t=msgInput.value.trim();if(!t)return;ws.send(JSON.stringify({type:"user_input",text:t}));addChatMsg("user",t);msgInput.value=""}
msgInput.addEventListener("keypress",function(e){if(e.key==="Enter")sendMsg()});
</script>
</body>
</html>
"""

# ============================================================================
# FastAPI Endpoints
# ============================================================================
@app.get("/")
async def get():
    return HTMLResponse(HTML)

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    connected_clients.append(websocket)
    log.info("🌐 UI Client connected")
    
    try:
        while True:
            try:
                data = await websocket.receive_text()
                msg = json.loads(data)
                if msg.get("type") == "user_input":
                    log.info("📥 Received from UI", text=msg.get("text", "")[:50])
                    event_data = {"type": "user_command", "content": msg["text"], "importance": 1.0, "source": "web_ui"}
                    if msg.get("image"):
                        event_data["image_base64"] = msg["image"]
                        event_data["type"] = "vision_request"
                    await event_bus.publish("ui_input", event_data)
            except json.JSONDecodeError:
                log.warning("Invalid JSON from UI client")
            except Exception as e:
                log.error("Error processing UI message", error=str(e))
    except WebSocketDisconnect:
        pass
    except Exception as e:
        log.error("WebSocket error", error=str(e))
    finally:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
        log.info("🌐 UI Client disconnected")

# ============================================================================
# Broadcast & Event Subscriptions
# ============================================================================
async def broadcast(data: dict):
    if not connected_clients:
        return
    dead = []
    for client in connected_clients[:]:
        try:
            await client.send_json(data)
        except Exception:
            dead.append(client)
    for c in dead:
        if c in connected_clients:
            connected_clients.remove(c)

async def on_decision_made(data):
    if data and data.get("type") == "response":
        await broadcast({"type": "chat", "role": "leya", "text": data.get("content", "")})

async def on_thought(data):
    if data and data.get("text"):
        await broadcast({"type": "thought", "text": data["text"]})

async def on_dmn_insight(data):
    if data and data.get("text"):
        await broadcast({"type": "insight", "text": data["text"]})

async def on_kg_fact(data):
    if data and all(k in data for k in ["subject", "predicate", "object"]):
        await broadcast({"type": "kg_fact", "subject": data["subject"], "predicate": data["predicate"], "object": data["object"]})

async def on_phase_change(data):
    if data and data.get("phase"):
        await broadcast({"type": "phase", "phase": data["phase"]})

async def on_state_update(data):
    if data:
        await broadcast({"type": "state", "hormones": data.get("hormones", {}), "emotion": data.get("emotion", "NEUTRAL"), "environment": data.get("environment", "")})

async def on_file_changed(data):
    if data and data.get("name"):
        await broadcast({"type": "file", "name": data["name"], "language": data.get("language", ""), "path": data.get("path", "")})

async def on_planner_task(data):
    if data and data.get("text"):
        await broadcast({"type": "planner", "text": data["text"]})

async def on_fast_reaction(data):
    if data and data.get("stimuli"):
        await broadcast({"type": "fast_reaction", "stimuli": data["stimuli"]})

event_bus.subscribe("ui_input", lambda d: None)
event_bus.subscribe("decision_made", on_decision_made)
event_bus.subscribe("thought_process", on_thought)
event_bus.subscribe("dmn_insight", on_dmn_insight)
event_bus.subscribe("kg_fact", on_kg_fact)
event_bus.subscribe("phase_start", on_phase_change)
event_bus.subscribe("state_update", on_state_update)
event_bus.subscribe("file_changed", on_file_changed)
event_bus.subscribe("planner_task", on_planner_task)
event_bus.subscribe("fast_reaction", on_fast_reaction)