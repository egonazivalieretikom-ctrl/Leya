// WebSocket соединение
let ws = null;
let currentSoulFile = 'personality.txt';
let reconnectAttempts = 0;
let currentDrives = {};
let currentState = 'initializing';
const MAX_RECONNECT_ATTEMPTS = 5;

// Элементы DOM
const messagesDiv = document.getElementById('messages');
const userInput = document.getElementById('userInput');
const thoughtsDiv = document.getElementById('thoughts');
const selfModelDiv = document.getElementById('selfModel');
const soulEditor = document.getElementById('soulEditor');
const connectionStatus = document.getElementById('connectionStatus');
const clientCount = document.getElementById('clientCount');
const leyaState = document.getElementById('leyaState');
const leyaAvatar = document.getElementById('leyaAvatar');
const moodIndicator = document.getElementById('moodIndicator');

// Обновление аватара на основе состояния Леи
function updateAvatar(drives, state, hasActiveThought = false) {
    // Скрываем все аватары
    document.querySelectorAll('.avatar-face').forEach(avatar => {
        avatar.style.display = 'none';
    });

    // Определяем доминирующий драйв
    const maxDrive = Object.entries(drives).reduce((max, [key, val]) =>
        val > max.val ? { key, val } : max, { key: '', val: 0 });

    const dominantDrive = maxDrive.key;
    const tension = maxDrive.val;

    // Определяем настроение и показываем соответствующий аватар
    let mood = 'спокойна';
    let moodEmoji = '😊';
    let avatarId = 'avatar-neutral';

    // Состояние сна
    if (state === 'sleeping') {
        avatarId = 'avatar-sleeping';
        mood = 'спит';
        moodEmoji = '💤';
    }
    // Состояние рефлексии
    else if (state === 'reflecting' || hasActiveThought) {
        avatarId = 'avatar-reflecting';
        mood = 'размышляет';
        moodEmoji = '';
    }
    // Высокий CURIOSITY
    else if (dominantDrive === 'curiosity' && tension > 0.6) {
        avatarId = 'avatar-curious';
        mood = 'любопытная';
        moodEmoji = '🧐';
    }
    // Высокий CONNECTION - радость
    else if (dominantDrive === 'connection' && tension < 0.3) {
        avatarId = 'avatar-happy';
        mood = 'радостная';
        moodEmoji = '😄';
    }
    // Высокий CONNECTION tension - одиночество
    else if (dominantDrive === 'connection' && tension > 0.7) {
        avatarId = 'avatar-sad';
        mood = 'одинокая';
        moodEmoji = '😔';
    }
    // Высокий AUTONOMY
    else if (dominantDrive === 'autonomy' && tension > 0.6) {
        avatarId = 'avatar-independent';
        mood = 'независимая';
        moodEmoji = '😼';
    }
    // Высокий INTEGRITY
    else if (dominantDrive === 'integrity' && tension < 0.3) {
        avatarId = 'avatar-harmonious';
        mood = 'гармоничная';
        moodEmoji = '😌';
    }
    // Общий высокий tension - возбуждение
    else if (tension > 0.8) {
        avatarId = 'avatar-excited';
        mood = 'возбуждённая';
        moodEmoji = '🤩';
    }

    // Показываем выбранный аватар
    const selectedAvatar = document.getElementById(avatarId);
    if (selectedAvatar) {
        selectedAvatar.style.display = 'block';
    }

    // Обновляем индикатор настроения
    if (moodIndicator) {
        moodIndicator.textContent = `${moodEmoji} ${mood}`;
    }
}

// Инициализация
document.addEventListener('DOMContentLoaded', () => {
    connectWebSocket();
    loadInitialState();
    setupTabs();

    userInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') sendMessage();
    });
});

// WebSocket
function connectWebSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    ws = new WebSocket(`${protocol}//${window.location.host}/ws`);

    ws.onopen = () => {
        console.log('WebSocket подключен');
        connectionStatus.textContent = '● подключено';
        connectionStatus.className = 'connection connected';
        reconnectAttempts = 0;

        // Пинг каждые 30 секунд
        setInterval(() => {
            if (ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({ type: 'ping' }));
            }
        }, 30000);
    };

    ws.onmessage = (event) => {
        const data = JSON.parse(event.data);
        handleMessage(data);
    };

    ws.onclose = () => {
        console.log('WebSocket отключен');
        connectionStatus.textContent = '● отключено';
        connectionStatus.className = 'connection';

        // Попытка переподключения
        if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
            reconnectAttempts++;
            setTimeout(connectWebSocket, 2000 * reconnectAttempts);
        }
    };

    ws.onerror = (error) => {
        console.error('WebSocket ошибка:', error);
    };
}

// Обработка сообщений
function handleMessage(data) {
    switch (data.type) {
        case 'user_message':
            addMessage(data.content, 'user');
            break;

        case 'leya_response':
            addMessage(data.content, 'leya');
            // Лея ответила - она активна
            updateAvatar(currentDrives, 'awake', false);
            break;

        case 'thought':
            addThought(data.thought_type, data.content);
            // Лея думает - она в рефлексии
            updateAvatar(currentDrives, 'reflecting', true);
            break;

        case 'drives_update':
            currentDrives = data.data;
            updateDrives(data.data);
            updateAvatar(currentDrives, currentState, false);
            break;

        case 'self_model_update':
            selfModelDiv.textContent = data.data;
            break;

        case 'soul_update':
            if (data.data[currentSoulFile]) {
                soulEditor.value = data.data[currentSoulFile];
            }
            break;

        case 'state_update':
            currentState = data.data;
            leyaState.textContent = data.data;
            updateAvatar(currentDrives, currentState, false);
            break;
    }
}

// Добавить сообщение в чат
function addMessage(content, type) {
    const msg = document.createElement('div');
    msg.className = `message ${type}`;
    msg.textContent = content;
    messagesDiv.appendChild(msg);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;

    // Ограничиваем количество сообщений
    while (messagesDiv.children.length > 100) {
        messagesDiv.removeChild(messagesDiv.firstChild);
    }
}

// Добавить мысль
function addThought(type, content) {
    const typeLabels = {
        'internal': '💭 Внутренний монолог',
        'spontaneous': '✨ Спонтанная мысль',
        'reflection': '🔍 Рефлексия'
    };

    const thought = document.createElement('div');
    thought.className = 'thought-item';
    thought.innerHTML = `
        <span class="thought-type">${typeLabels[type] || 'Мысль'}</span>
        ${escapeHtml(content)}
    `;

    thoughtsDiv.insertBefore(thought, thoughtsDiv.firstChild);

    // Ограничиваем количество
    while (thoughtsDiv.children.length > 50) {
        thoughtsDiv.removeChild(thoughtsDiv.lastChild);
    }

    // Также добавляем в чат как системное сообщение
    const msg = document.createElement('div');
    msg.className = 'message thought';
    msg.innerHTML = `<span class="thought-label">${typeLabels[type] || 'Мысль'}</span>${escapeHtml(content)}`;
    messagesDiv.appendChild(msg);
    messagesDiv.scrollTop = messagesDiv.scrollHeight;
}

// Обновить драйвы
function updateDrives(data) {
    Object.entries(data).forEach(([drive, value]) => {
        const percentage = Math.round(value * 100);
        const fill = document.getElementById(`drive${capitalize(drive)}`);
        const valueEl = document.getElementById(`value${capitalize(drive)}`);

        if (fill && valueEl) {
            fill.style.width = `${Math.max(0, Math.min(100, percentage))}%`;
            valueEl.textContent = `${percentage}%`;
        }
    });
}

// Отправить сообщение
function sendMessage() {
    const content = userInput.value.trim();
    if (!content || !ws || ws.readyState !== WebSocket.OPEN) return;

    ws.send(JSON.stringify({
        type: 'user_message',
        content: content
    }));

    userInput.value = '';
}

// Загрузить начальное состояние
async function loadInitialState() {
    try {
        const response = await fetch('/api/state');
        const state = await response.json();

        // Обновляем UI
        currentState = state.state;
        leyaState.textContent = state.state;
        clientCount.textContent = state.connected_clients;

        currentDrives = state.drives;
        updateDrives(state.drives);
        selfModelDiv.textContent = state.self_model;

        // Обновляем аватар
        updateAvatar(currentDrives, currentState, false);

        // Устанавливаем первый файл души
        if (state.soul.personality) {
            soulEditor.value = state.soul.personality;
        }
    } catch (error) {
        console.error('Ошибка загрузки состояния:', error);
    }
}

// Настройка вкладок души
function setupTabs() {
    const tabs = document.querySelectorAll('.soul-tabs .tab');
    tabs.forEach(tab => {
        tab.addEventListener('click', async () => {
            tabs.forEach(t => t.classList.remove('active'));
            tab.classList.add('active');

            currentSoulFile = tab.dataset.file;

            try {
                const response = await fetch('/api/state');
                const state = await response.json();

                const fileName = currentSoulFile.replace('.txt', '');
                soulEditor.value = state.soul[fileName] || '';
            } catch (error) {
                console.error('Ошибка:', error);
            }
        });
    });
}

// Сохранить файл души
async function saveSoulFile() {
    try {
        const response = await fetch(`/api/soul/${currentSoulFile}`, {
            method: 'POST',
            headers: {
                'Content-Type': 'text/plain'
            },
            body: soulEditor.value
        });

        const result = await response.json();
        alert(result.result || 'Сохранено!');
    } catch (error) {
        alert('Ошибка сохранения: ' + error.message);
    }
}

// Утилиты
function capitalize(str) {
    return str.charAt(0).toUpperCase() + str.slice(1);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

