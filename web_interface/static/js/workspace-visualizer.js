/**
 * WorkspaceVisualizer — Визуализация Global Workspace
 */
class WorkspaceVisualizer {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.proposals = [];
        this.focus = null;
        this.refreshInterval = null;
    }

    startAutoRefresh(intervalMs = 2000) {
        this.refreshInterval = setInterval(() => this.loadProposals(), intervalMs);
        this.loadProposals();
    }

    stopAutoRefresh() {
        if (this.refreshInterval) {
            clearInterval(this.refreshInterval);
            this.refreshInterval = null;
        }
    }

    async loadProposals() {
        try {
            const response = await fetch('/api/workspace/proposals');
            const data = await response.json();

            this.proposals = data.proposals || [];
            this.focus = data.focus;

            this.render();
            return data;
        } catch (error) {
            console.error('Ошибка загрузки proposals:', error);
            return null;
        }
    }

    getPriorityBadge(priority) {
        const colors = {
            'LOW': 'bg-gray-600',
            'MEDIUM': 'bg-blue-600',
            'HIGH': 'bg-amber-600',
            'CRITICAL': 'bg-red-600',
        };
        return `<span class="px-2 py-1 rounded text-xs ${colors[priority] || 'bg-gray-600'}">${priority}</span>`;
    }

    getSourceIcon(source) {
        const icons = {
            'homeostasis': '🏠',
            'spontaneous': '💭',
            'user': '👤',
            'meta_cognition': '🧠',
            'leya': '✨',
            'manual': '🔧',
        };
        return icons[source] || '⚡';
    }

    render() {
        const html = `
            <div class="space-y-2">
                ${this.focus ? this.renderFocus() : ''}
                <div class="text-xs text-gray-400 mb-2">
                    Предложений: ${this.proposals.length}
                </div>
                ${this.proposals.map(p => this.renderProposal(p)).join('')}
            </div>
        `;

        this.container.innerHTML = html;
    }

    renderFocus() {
        return `
            <div class="bg-leya-cyan/10 border-2 border-leya-cyan rounded-lg p-3 mb-4">
                <div class="flex items-center gap-2 mb-2">
                    <span class="text-xl">${this.getSourceIcon(this.focus.source)}</span>
                    <span class="text-sm font-bold text-leya-cyan">Фокус внимания</span>
                </div>
                <div class="text-sm text-gray-100">${this.escapeHtml(this.focus.content)}</div>
                <div class="flex items-center gap-2 mt-2">
                    ${this.getPriorityBadge(this.focus.priority)}
                    <span class="text-xs text-gray-400">${this.focus.action_type}</span>
                </div>
            </div>
        `;
    }

    renderProposal(proposal) {
        const ageClass = proposal.age_seconds < 60 ? 'text-green-400' :
            proposal.age_seconds < 300 ? 'text-yellow-400' : 'text-red-400';

        return `
            <div class="bg-leya-navy border border-leya-cyan/20 rounded-lg p-3 hover:border-leya-cyan/50 transition-colors">
                <div class="flex items-start gap-2">
                    <span class="text-lg">${this.getSourceIcon(proposal.source)}</span>
                    <div class="flex-1 min-w-0">
                        <div class="text-xs text-gray-400 mb-1">
                            ${proposal.source} • <span class="${ageClass}">${this.formatAge(proposal.age_seconds)}</span>
                        </div>
                        <div class="text-sm text-gray-200 break-words mb-2">
                            ${this.escapeHtml(proposal.content)}
                        </div>
                        <div class="flex items-center gap-2 flex-wrap">
                            ${this.getPriorityBadge(proposal.priority)}
                            <div class="flex items-center gap-1">
                                <span class="text-xs text-gray-400">Urgency:</span>
                                <div class="w-16 h-2 bg-leya-dark rounded overflow-hidden">
                                    <div class="h-full bg-amber-500" style="width: ${proposal.urgency * 100}%"></div>
                                </div>
                            </div>
                            <div class="flex items-center gap-1">
                                <span class="text-xs text-gray-400">Relevance:</span>
                                <div class="w-16 h-2 bg-leya-dark rounded overflow-hidden">
                                    <div class="h-full bg-leya-cyan" style="width: ${proposal.drive_relevance * 100}%"></div>
                                </div>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    formatAge(seconds) {
        if (seconds < 60) return `${Math.round(seconds)}с`;
        if (seconds < 3600) return `${Math.round(seconds / 60)}м`;
        return `${Math.round(seconds / 3600)}ч`;
    }

    escapeHtml(text) {
        const div = document.createElement('div');
        div.textContent = text;
        return div.innerHTML;
    }

    async forceSubmit(source, content, priority = 'MEDIUM', urgency = 0.5, driveRelevance = 0.5) {
        try {
            const response = await fetch('/api/workspace/submit', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    source,
                    content,
                    priority,
                    urgency,
                    drive_relevance: driveRelevance,
                }),
            });
            const data = await response.json();
            console.log('Proposal подан:', data);
            // Перезагрузка
            await this.loadProposals();
            return data;
        } catch (error) {
            console.error('Ошибка подачи proposal:', error);
            return null;
        }
    }
}

// Экспорт
window.WorkspaceVisualizer = WorkspaceVisualizer;