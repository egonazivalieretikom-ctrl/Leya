/**
 * ThoughtsFeed — Feed мыслей Леи с типизацией
 */
class ThoughtsFeed {
    constructor(containerId, maxThoughts = 20) {
        this.container = document.getElementById(containerId);
        this.maxThoughts = maxThoughts;
        this.thoughts = [];
    }

    addThought(thoughtType, content) {
        const thought = {
            type: thoughtType,
            content: content,
            timestamp: new Date(),
            id: Date.now() + Math.random(),
        };

        this.thoughts.unshift(thought);

        // Ограничение количества
        if (this.thoughts.length > this.maxThoughts) {
            this.thoughts = this.thoughts.slice(0, this.maxThoughts);
        }

        this.render();
    }

    getIcon(thoughtType) {
        const icons = {
            'spontaneous': '💭',
            'reflection': '🧠',
            'workspace': '⚡',
            'internal': '🔍',
        };
        return icons[thoughtType] || '💬';
    }

    getLabel(thoughtType) {
        const labels = {
            'spontaneous': 'Спонтанная мысль',
            'reflection': 'Рефлексия',
            'workspace': 'Рабочее пространство',
            'internal': 'Внутренний монолог',
        };
        return labels[thoughtType] || 'Мысль';
    }

    render() {
        this.container.innerHTML = this.thoughts.map(thought => `
            <div class="thought-card thought-${thought.type} fade-in">
                <div class="flex items-start gap-2">
                    <span class="text-xl">${this.getIcon(thought.type)}</span>
                    <div class="flex-1 min-w-0">
                        <div class="text-xs text-gray-400 mb-1">
                            ${this.getLabel(thought.type)} • ${this.formatTime(thought.timestamp)}
                        </div>
                        <div class="text-sm text-gray-200 break-words">
                            ${this.escapeHtml(thought.content)}
                        </div>
                    </div>
                </div>
            </div>
        `).join('');
    }

    formatTime(date) {
        const now = new Date();
        const diff = Math.floor((now - date) / 1000);

        if (diff < 60) return 'только что';
        if (diff < 3600) return `${Math.floor(diff / 60)} мин назад`;
        if (diff < 86400) return `${Math.floor(diff / 3600)} ч назад`;
        return date.toLocaleDateString('ru-RU');
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    clear() {
        this.thoughts = [];
        this.render();
    }
}

// Экспорт в глобальную область
window.ThoughtsFeed = ThoughtsFeed;