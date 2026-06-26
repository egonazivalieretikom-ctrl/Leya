/**
 * SelfModelPanel — Панель само-модели и души
 */
class SelfModelPanel {
    constructor() {
        this.selfModel = '';
        this.soulFiles = {};
        this.refreshInterval = null;
    }

    startAutoRefresh(intervalMs = 5000) {
        this.refreshInterval = setInterval(() => this.loadSelfModel(), intervalMs);
        this.loadSelfModel();
        this.loadSoulFiles();
    }

    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }

    async loadSelfModel() {
        try {
            const response = await fetch('/api/self-model');
            const data = await response.json();
            this.selfModel = data.self_model || '';
            this.renderSelfModel();
            return data;
        } catch (error) {
            console.error('Ошибка загрузки self_model:', error);
            return null;
        }
    }

    async loadSoulFiles() {
        try {
            const response = await fetch('/api/soul');
            const data = await response.json();
            this.soulFiles = data;
            this.renderSoulFiles();
            return data;
        } catch (error) {
            console.error('Ошибка загрузки soul files:', error);
            return null;
        }
    }

    renderSelfModel() {
        const container = document.getElementById('self-model-content');
        if (container) {
            container.textContent = this.selfModel || 'Модель себя ещё не сформирована.';
        }
    }

    renderSoulFiles() {
        const container = document.getElementById('soul-files-editor');
        if (!container) return;

        const html = Object.entries(this.soulFiles).map(([filename, content]) => `
            <div class="mb-4">
                <div class="flex items-center justify-between mb-2">
                    <h4 class="text-sm font-semibold text-leya-cyan">${filename}</h4>
                    <button 
                        onclick="window.selfModelPanel.saveSoulFile('${filename}')"
                        class="px-3 py-1 bg-leya-cyan text-leya-dark text-xs rounded hover:bg-leya-cyan/80"
                    >
                        Сохранить
                    </button>
                </div>
                <textarea 
                    id="soul-${filename.replace('.', '-')}"
                    class="w-full h-32 bg-leya-dark border border-leya-cyan/30 rounded p-2 text-sm text-gray-100 font-mono resize-y"
                >${this.escapeHtml(content)}</textarea>
            </div>
        `).join('');

        container.innerHTML = html || '<p class="text-gray-500">Файлы души не найдены</p>';
    }

    async saveSoulFile(filename) {
        const textarea = document.getElementById(`soul-${filename.replace('.', '-')}`);
        if (!textarea) return;

        const content = textarea.value;

        try {
            const response = await fetch('/api/soul/update', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ filename, content }),
            });
            const data = await response.json();

            if (data.status === 'ok') {
                console.log(`Файл ${filename} сохранён`);
                // Показ уведомления
                this.showNotification(`✅ ${filename} сохранён`);
            } else {
                console.error('Ошибка сохранения:', data.error);
                this.showNotification(`❌ Ошибка: ${data.error}`, 'error');
            }
        } catch (error) {
            console.error('Ошибка сохранения файла:', error);
            this.showNotification('❌ Ошибка сети', 'error');
        }
    }

    showNotification(message, type = 'success') {
        const notification = document.createElement('div');
        notification.className = `fixed top-4 right-4 px-4 py-2 rounded-lg shadow-lg z-50 ${type === 'error' ? 'bg-red-600' : 'bg-green-600'
            } text-white`;
        notification.textContent = message;
        document.body.appendChild(notification);

        setTimeout(() => {
            notification.remove();
        }, 3000);
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }
}

// Экспорт
window.SelfModelPanel = SelfModelPanel;