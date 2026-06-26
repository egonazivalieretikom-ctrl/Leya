/**
 * LeyaUI — Главный класс UI Леи
 * Подписывается на WebSocket и рендерит все broadcast типы
 */
class LeyaUI {
    constructor() {
        this.ws = null;
        this.reconnectAttempts = 0;
        this.maxReconnectAttempts = 5;
        this.reconnectDelay = 2000;

        // Компоненты
        this.drivesChart = new DrivesChart('drives-radar-chart');
        this.thoughtsFeed = new ThoughtsFeed('thoughts-feed');
        this.chatContainer = document.getElementById('chat-container');
        this.messageForm = document.getElementById('message-form');
        this.messageInput = document.getElementById('message-input');
        this.statusIndicator = document.getElementById('status-indicator');

        this.init();
    }

    init() {
        this.connectWebSocket();
        this.setupEventListeners();
        this.loadInitialState();
    }

    connectWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;

        try {
            this.ws = new WebSocket(wsUrl);

            this.ws.onopen = () => {
                console.log('WebSocket подключен');
                this.reconnectAttempts = 0;
                this.updateStatus('awake');
            };

            this.ws.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.handleMessage(data);
                } catch (error) {
                    console.error('Ошибка парсинга WebSocket сообщения:', error);
                }
            };

            this.ws.onclose = () => {
                console.log('WebSocket отключен');
                this.updateStatus('disconnected');
                this.attemptReconnect();
            };

            this.ws.onerror = (error) => {
                console.error('WebSocket ошибка:', error);
            };
        } catch (error) {
            console.error('Ошибка подключения WebSocket:', error);
            this.attemptReconnect();
        }
    }

    attemptReconnect() {
        if (this.reconnectAttempts < this.maxReconnectAttempts) {
            this.reconnectAttempts++;
            console.log(`Попытка переподключения ${this.reconnectAttempts}/${this.maxReconnectAttempts}...`);
            setTimeout(() => this.connectWebSocket(), this.reconnectDelay);
        } else {
            console.error('Превышено максимальное количество попыток переподключения');
            this.updateStatus('error');
        }
    }

    handleMessage(data) {
        const { type, content, thought_type, data: payload } = data;

        switch (type) {
            case 'leya_response':
                this.addChatMessage('leya', content);
                break;

            case 'user_message':
                this.addChatMessage('user', content);
                break;

            case 'thought':
                this.thoughtsFeed.addThought(thought_type, content);
                break;

            case 'drives_update':
                this.drivesChart.update(payload);
                this.updateDrivesList(payload);
                break;

            case 'self_model_update':
                console.log('Self-model обновлен:', payload);
                break;

            case 'state_update':
                this.updateStatus(payload);
                break;

            case 'memory_update':
                console.log('Memory обновлена:', payload);
                break;

            case 'soul_update':
                console.log('Soul обновлена:', payload);
                break;

            default:
                console.warn('Неизвестный тип сообщения:', type);
        }
    }

    addChatMessage(sender, content) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `message message-${sender} fade-in`;

        const senderLabel = sender === 'user' ? 'Вы' : 'Лея';
        messageDiv.innerHTML = `
            <div class="text-xs text-gray-400 mb-1">${senderLabel}</div>
            <div class="text-gray-100">${this.escapeHtml(content)}</div>
        `;

        this.chatContainer.appendChild(messageDiv);
        this.chatContainer.scrollTop = this.chatContainer.scrollHeight;
    }

    updateDrivesList(drivesData) {
        const drivesList = document.getElementById('drives-list');
        drivesList.innerHTML = Object.entries(drivesData).map(([name, value]) => {
            const percentage = Math.round(value * 100);
            const level = value < 0.4 ? 'low' : value < 0.7 ? 'medium' : 'high';

            return `
                <div class="tooltip" data-tooltip="${name}: ${percentage}%">
                    <div class="flex items-center justify-between text-xs mb-1">
                        <span class="text-gray-300 capitalize">${name}</span>
                        <span class="text-gray-400">${percentage}%</span>
                    </div>
                    <div class="drive-bar">
                        <div class="drive-bar-fill ${level}" style="width: ${percentage}%"></div>
                    </div>
                </div>
            `;
        }).join('');
    }

    updateStatus(state) {
        const statusMap = {
            'awake': { color: 'bg-green-500', text: 'Awake' },
            'sleeping': { color: 'bg-blue-500', text: 'Sleeping' },
            'initializing': { color: 'bg-yellow-500', text: 'Initializing' },
            'disconnected': { color: 'bg-red-500', text: 'Disconnected' },
            'error': { color: 'bg-red-500', text: 'Error' },
        };

        const status = statusMap[state] || statusMap['disconnected'];
        this.statusIndicator.innerHTML = `
            <span class="w-2 h-2 rounded-full ${status.color} animate-pulse"></span>
            <span class="text-sm text-gray-300">${status.text}</span>
        `;
    }

    setupEventListeners() {
        this.messageForm.addEventListener('submit', (e) => {
            e.preventDefault();
            this.sendMessage();
        });
    }

    sendMessage() {
        const content = this.messageInput.value.trim();
        if (!content) return;

        // Отправка через REST API
        fetch('/api/message', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify({ content }),
        })
            .then(response => response.json())
            .then(data => {
                console.log('Сообщение отправлено:', data);
                this.messageInput.value = '';
            })
            .catch(error => {
                console.error('Ошибка отправки сообщения:', error);
            });
    }

    async loadInitialState() {
        try {
            // Загрузка начального состояния
            const [stateRes, drivesRes] = await Promise.all([
                fetch('/api/state'),
                fetch('/api/drives'),
            ]);

            const state = await stateRes.json();
            const drives = await drivesRes.json();

            this.updateStatus(state.state || 'initializing');
            this.drivesChart.update(drives);
            this.updateDrivesList(drives);
        } catch (error) {
            console.error('Ошибка загрузки начального состояния:', error);
        }
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    window.leyaUI = new LeyaUI();
});