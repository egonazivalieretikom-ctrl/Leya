/**
 * DrivesChart — Chart.js radar для визуализации драйвов Леи
 */
class DrivesChart {
    constructor(canvasId) {
        this.canvas = document.getElementById(canvasId);
        this.chart = null;
        this.drives = {};
        this.init();
    }

    init() {
        const ctx = this.canvas.getContext('2d');

        this.chart = new Chart(ctx, {
            type: 'radar',
            data: {
                labels: [],
                datasets: [{
                    label: 'Текущее значение',
                    data: [],
                    backgroundColor: 'rgba(0, 212, 255, 0.2)',
                    borderColor: 'rgba(0, 212, 255, 1)',
                    borderWidth: 2,
                    pointBackgroundColor: 'rgba(0, 212, 255, 1)',
                    pointBorderColor: '#fff',
                    pointHoverBackgroundColor: '#fff',
                    pointHoverBorderColor: 'rgba(0, 212, 255, 1)',
                }]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                scales: {
                    r: {
                        beginAtZero: true,
                        max: 1,
                        ticks: {
                            stepSize: 0.2,
                            color: '#9ca3af',
                            backdropColor: 'transparent',
                        },
                        grid: {
                            color: 'rgba(0, 212, 255, 0.1)',
                        },
                        angleLines: {
                            color: 'rgba(0, 212, 255, 0.1)',
                        },
                        pointLabels: {
                            color: '#d1d5db',
                            font: {
                                size: 11,
                            }
                        }
                    }
                },
                plugins: {
                    legend: {
                        display: false,
                    },
                    tooltip: {
                        backgroundColor: '#0a1929',
                        borderColor: '#00d4ff',
                        borderWidth: 1,
                        titleColor: '#00d4ff',
                        bodyColor: '#d1d5db',
                    }
                }
            }
        });
    }

    update(drivesData) {
        // drivesData: {curiosity: 0.5, connection: 0.3, ...}
        const labels = Object.keys(drivesData);
        const values = Object.values(drivesData);

        this.chart.data.labels = labels.map(l => l.charAt(0).toUpperCase() + l.slice(1));
        this.chart.data.datasets[0].data = values;
        this.chart.update('none'); // Без анимации для производительности

        this.drives = drivesData;
    }

    getDriveValue(driveName) {
        return this.drives[driveName] || 0;
    }
}

// Экспорт в глобальную область
window.DrivesChart = DrivesChart;