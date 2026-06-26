/**
 * LeyaUI — Главный класс UI Леи (обновлённая версия с новыми панелями)
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
        this.memoryGraph = null;
        this.workspaceVisualizer = null;
        this.selfModelPanel = null;

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
        this.setupTabs();
    }

    setupTabs() {
        // Инициализация компонентов при первом переключении на вкладку
        const tabButtons = document.querySelectorAll('.tab-button');
        tabButtons.forEach(btn => {
            btn.addEventListener('click', () => {
                const tabName = btn.textContent.trim().split(' ')[1].toLowerCase();
                this.activateTab(tabName);
            });
        });
    }

    activateTab(tabName) {
        // Скрытие всех вкладок
        document.querySelectorAll('.tab-content').forEach(el => el.classList.add('hidden'));
        document.querySelectorAll('.tab-button').forEach(btn => {
            btn.classList.remove('active', 'text-leya-cyan', 'border-b-2', 'border-leya-cyan');
            btn.classList.add('text-gray-400');
        });

        // Показ выбранной вкладки
        const tabEl = document.getElementById(`tab-${tabName}`);
        if (tabEl) {
            tabEl.classList.remove('hidden');
        }

        // Активация кнопки
        const buttons = document.querySelectorAll('.tab-button');
        buttons.forEach(btn => {
            if (btn.textContent.toLowerCase().includes(tabName)) {
                btn.classList.add('active', 'text-leya-cyan', 'border-b-2', 'border-leya-cyan');
                btn.classList.remove('text-gray-400');
            }
        });

        // Инициализация компонентов при первом открытии
        if (tabName === 'memory' && !this.memoryGraph) {
            this.memoryGraph = new MemoryGraph('memory-graph-container');
            this.memoryGraph.loadGraph();
        } else if (tabName === 'workspace' && !this.workspaceVisualizer) {
            this.workspaceVisualizer = new WorkspaceVisualizer('workspace-container');
            this.workspaceVisualizer.startAutoRefresh(2000);
        } else if (tabName === 'self' && !this.selfModelPanel) {
            this.selfModelPanel = new SelfModelPanel();
            this.selfModelPanel.startAutoRefresh(5000);
        }
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

            // ИСПРАВЛЕНИЕ ШАГ 4: Exponential backoff
            const delay = this.reconnectDelay * Math.pow(2, this.reconnectAttempts - 1);
            const maxDelay = 30000; // Максимум 30 секунд
            const actualDelay = Math.min(delay, maxDelay);

            console.log(`Попытка переподключения ${this.reconnectAttempts}/${this.maxReconnectAttempts} через ${actualDelay / 1000}с...`);

            // Показываем статус переподключения
            this.updateStatus('reconnecting');

            setTimeout(() => this.connectWebSocket(), actualDelay);
        } else {
            console.error('Превышено максимальное количество попыток переподключения');
            this.updateStatus('error');

            // Показываем ошибку пользователю
            this.addChatMessage('system', '❌ Не удалось подключиться к Лее. Проверьте соединение и перезагрузите страницу.');
        }
    }

    handleMessage(data) {
        const { type, content, thought_type, data: payload } = data;

        try {
            switch (type) {
                case 'leya_response':
                    this.addChatMessage('leya', content);
                    break;

                case 'user_message':
                    this.addChatMessage('user', content);
                    break;

                case 'thought':
                    // ИСПРАВЛЕНИЕ ШАГ 4: Try/catch вокруг вызова компонента
                    try {
                        if (this.thoughtsFeed) {
                            this.thoughtsFeed.addThought(thought_type, content);
                        }
                    } catch (thoughtError) {
                        console.error('Ошибка добавления мысли в feed:', thoughtError);
                    }
                    break;

                case 'drives_update':
                    // ИСПРАВЛЕНИЕ ШАГ 4: Try/catch вокруг вызова компонента
                    try {
                        if (this.drivesChart && payload) {
                            this.drivesChart.update(payload);
                            this.updateDrivesList(payload);
                        }
                    } catch (drivesError) {
                        console.error('Ошибка обновления драйвов:', drivesError);
                    }
                    break;

                case 'self_model_update':
                    try {
                        if (this.selfModelPanel) {
                            this.selfModelPanel.loadSelfModel();
                        }
                    } catch (selfModelError) {
                        console.error('Ошибка обновления self_model:', selfModelError);
                    }
                    break;

                case 'state_update':
                    this.updateStatus(payload);
                    break;

                case 'memory_update':
                    try {
                        if (this.memoryGraph) {
                            this.memoryGraph.loadGraph();
                        }
                    } catch (memoryError) {
                        console.error('Ошибка обновления памяти:', memoryError);
                    }
                    break;

                case 'soul_update':
                    try {
                        if (this.selfModelPanel) {
                            this.selfModelPanel.loadSoulFiles();
                        }
                    } catch (soulError) {
                        console.error('Ошибка обновления души:', soulError);
                    }
                    break;

                // ИСПРАВЛЕНИЕ ШАГ 4: Обработка action_intent и tool_call
                case 'action_intent':
                    this.handleActionIntent(payload);
                    break;

                case 'tool_call':
                    this.handleToolCall(payload);
                    break;

                // ИСПРАВЛЕНИЕ ШАГ 4: Fallback mode indicator
                case 'fallback_mode':
                    this.showFallbackMode(payload);
                    break;

                default:
                    console.warn('Неизвестный тип сообщения:', type);
            }
        } catch (error) {
            console.error('Критическая ошибка обработки сообщения:', error, data);
        }
    }

    handleActionIntent(payload) {
        if (!payload || !payload.intent) return;

        const intentMessages = {
            'think': '🤔 Лея размышляет...',
            'respond': '💬 Лея готовит ответ...',
            'search': '🔍 Лея ищет информацию...',
            'rest': '😴 Лея отдыхает...',
            'explore': '🧭 Лея исследует...',
        };

        const message = intentMessages[payload.intent] || `⚡ Действие: ${payload.intent}`;
        this.addChatMessage('system', message);
    }

    handleToolCall(payload) {
        if (!payload || !payload.tool_name) return;

        const message = `🛠️ Лея использует инструмент: ${payload.tool_name}`;
        this.addChatMessage('system', message);
    }

    showFallbackMode(payload) {
        const isFallback = payload && payload.active;
        const indicator = document.getElementById('fallback-indicator');

        if (!indicator) {
            // Создаём индикатор, если его нет
            const newIndicator = document.createElement('div');
            newIndicator.id = 'fallback-indicator';
            newIndicator.className = 'fixed top-4 right-4 bg-amber-600 text-white px-4 py-2 rounded-lg shadow-lg z-50 hidden';
            newIndicator.innerHTML = '⚠️ Fallback Mode: LLM недоступен';
            document.body.appendChild(newIndicator);
        }

        const fallbackIndicator = document.getElementById('fallback-indicator');
        if (isFallback) {
            fallbackIndicator.classList.remove('hidden');
        } else {
            fallbackIndicator.classList.add('hidden');
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

    updateStatus(status) {
        const indicator = document.getElementById('status-indicator');
        if (!indicator) return;

        const statusMap = {
            'awake': { text: 'Awake', color: 'bg-green-500' },
            'sleeping': { text: 'Sleeping', color: 'bg-blue-500' },
            'disconnected': { text: 'Disconnected', color: 'bg-red-500' },
            'reconnecting': { text: 'Reconnecting...', color: 'bg-yellow-500 animate-pulse' },
            'error': { text: 'Error', color: 'bg-red-600' },
        };

        const statusInfo = statusMap[status] || { text: status, color: 'bg-gray-500' };

        indicator.innerHTML = `
        <span class="w-2 h-2 rounded-full ${statusInfo.color}"></span>
        <span class="text-sm text-gray-300">${statusInfo.text}</span>
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

        fetch('/api/message', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
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

// Глобальные функции для модальных окон
function showForceSubmitModal() {
    document.getElementById('force-submit-modal').classList.remove('hidden');
}

function hideForceSubmitModal() {
    document.getElementById('force-submit-modal').classList.add('hidden');
}

function switchTab(tabName) {
    if (window.leyaUI) {
        window.leyaUI.activateTab(tabName);
    }
}

// Обработчик формы force submit
document.addEventListener('DOMContentLoaded', () => {
    const form = document.getElementById('force-submit-form');
    if (form) {
        form.addEventListener('submit', async (e) => {
            e.preventDefault();

            const source = document.getElementById('fs-source').value;
            const content = document.getElementById('fs-content').value;
            const priority = document.getElementById('fs-priority').value;
            const urgency = parseFloat(document.getElementById('fs-urgency').value);

            if (window.leyaUI && window.leyaUI.workspaceVisualizer) {
                await window.leyaUI.workspaceVisualizer.forceSubmit(
                    source, content, priority, urgency, 0.5
                );
            }

            hideForceSubmitModal();
        });
    }
});

// Инициализация при загрузке страницы
document.addEventListener('DOMContentLoaded', () => {
    window.leyaUI = new LeyaUI();
});