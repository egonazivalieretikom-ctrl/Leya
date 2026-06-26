/**
 * MemoryGraph — Интерактивный граф памяти (vis-network)
 */
class MemoryGraph {
    constructor(containerId) {
        this.container = document.getElementById(containerId);
        this.network = null;
        this.nodes = new vis.DataSet();
        this.edges = new vis.DataSet();
        this.highlightedNodes = new Set();
        this.init();
    }

    init() {
        const data = {
            nodes: this.nodes,
            edges: this.edges,
        };

        const options = {
            nodes: {
                shape: 'dot',
                font: {
                    size: 12,
                    color: '#d1d5db',
                    face: 'sans-serif',
                },
                borderWidth: 2,
                shadow: true,
            },
            edges: {
                smooth: {
                    type: 'continuous',
                },
                shadow: true,
            },
            physics: {
                enabled: true,
                solver: 'forceAtlas2Based',
                forceAtlas2Based: {
                    gravitationalConstant: -50,
                    centralGravity: 0.01,
                    springLength: 100,
                    springConstant: 0.08,
                    damping: 0.4,
                    avoidOverlap: 0.5,
                },
                stabilization: {
                    iterations: 100,
                },
            },
            interaction: {
                hover: true,
                tooltipDelay: 200,
                zoomView: true,
                dragView: true,
            },
            layout: {
                improvedLayout: true,
            },
        };

        this.network = new vis.Network(this.container, data, options);

        // Обработчики событий
        this.network.on('click', (params) => {
            if (params.nodes.length > 0) {
                this.onNodeClick(params.nodes[0]);
            }
        });

        this.network.on('hoverNode', (params) => {
            this.container.style.cursor = 'pointer';
        });

        this.network.on('blurNode', (params) => {
            this.container.style.cursor = 'default';
        });
    }

    async loadGraph(minRetention = 0.1, maxNodes = 100) {
        try {
            const response = await fetch(
                `/api/memory/graph?min_retention=${minRetention}&max_nodes=${maxNodes}`
            );
            const data = await response.json();

            this.nodes.clear();
            this.edges.clear();

            if (data.nodes) {
                this.nodes.add(data.nodes);
            }
            if (data.edges) {
                this.edges.add(data.edges);
            }

            // Обновление статистики
            this.updateStats(data.total_engrams, data.total_synapses);

            return data;
        } catch (error) {
            console.error('Ошибка загрузки графа памяти:', error);
            return null;
        }
    }

    highlightNodes(nodeIds) {
        // Сброс предыдущих подсветок
        this.highlightedNodes.forEach(id => {
            this.nodes.update({ id, borderWidth: 2 });
        });

        // Подсветка новых
        nodeIds.forEach(id => {
            this.nodes.update({ id, borderWidth: 5, color: { border: '#ffffff' } });
            this.highlightedNodes.add(id);
        });
    }

    focusNode(nodeId) {
        this.network.focus(nodeId, {
            scale: 1.5,
            animation: {
                duration: 500,
                easingFunction: 'easeInOutQuad',
            },
        });
    }

    onNodeClick(nodeId) {
        const node = this.nodes.get(nodeId);
        if (node) {
            console.log('Клик на энграмму:', node);
            // Можно открыть модальное окно с деталями
            this.showNodeDetails(node);
        }
    }

    showNodeDetails(node) {
        // Простая реализация — alert. В production — модальное окно
        const details = `
ID: ${node.id}
Тип: ${node.memory_type}
Содержание: ${node.label}

Retention: ${node.retention_strength.toFixed(2)}
Извлечений: ${node.retrieval_count}
Эмоциональное усиление: ${node.emotional_boost.toFixed(2)}
        `.trim();

        // Можно заменить на модальное окно
        console.log(details);
    }

    updateStats(totalEng, totalSyn) {
        const statsEl = document.getElementById('memory-stats');
        if (statsEl) {
            statsEl.textContent = `Узлов: ${totalEng} | Связей: ${totalSyn}`;
        }
    }

    exportGraph() {
        const data = {
            nodes: this.nodes.get(),
            edges: this.edges.get(),
            timestamp: new Date().toISOString(),
        };

        const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
        const url = URL.createObjectURL(blob);
        const a = document.createElement('a');
        a.href = url;
        a.download = `leya_memory_graph_${Date.now()}.json`;
        a.click();
        URL.revokeObjectURL(url);
    }

    async consolidate() {
        try {
            const response = await fetch('/api/memory/consolidate', { method: 'POST' });
            const data = await response.json();
            console.log('Консолидация завершена:', data);
            // Перезагрузка графа
            await this.loadGraph();
            return data;
        } catch (error) {
            console.error('Ошибка консолидации:', error);
            return null;
        }
    }

    async forgetWeak(threshold = 0.1) {
        try {
            const response = await fetch('/api/memory/forget', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ threshold }),
            });
            const data = await response.json();
            console.log('Забывание завершено:', data);
            // Перезагрузка графа
            await this.loadGraph();
            return data;
        } catch (error) {
            console.error('Ошибка забывания:', error);
            return null;
        }
    }
}

// Экспорт
window.MemoryGraph = MemoryGraph;