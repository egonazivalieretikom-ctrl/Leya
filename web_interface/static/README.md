# LeyaOS Advanced UI — Static Assets

## Структура

static/
├── css/
│ └── leya.css # Основные стили (тёмная нейронная тема)
└── js/
├── leya-ui.js # Главный класс UI (WebSocket, роутинг)
├── drives-chart.js # Chart.js radar для драйвов
└── thoughts-feed.js # Feed мыслей с типизацией


## Технологии

- **Tailwind CSS 4** (через CDN для прототипа)
- **Chart.js 4.4** — визуализация драйвов
- **Vanilla JS** — без фреймворков для простоты

## Тема

- Deep Navy: `#0a1929`
- Electric Cyan: `#00d4ff`
- Warm Amber: `#ffb347`
- Dark Background: `#050d18`

## Broadcast типы

UI подписывается на следующие типы сообщений через WebSocket:

- `leya_response` — ответ Леи
- `user_message` — сообщение пользователя
- `thought` — мысль Леи (с `thought_type`: spontaneous, reflection, workspace, internal)
- `drives_update` — обновление драйвов
- `self_model_update` — обновление само-модели
- `state_update` — изменение состояния (awake, sleeping, etc.)
- `memory_update` — обновление памяти
- `soul_update` — обновление души

## Расширение

Для production рекомендуется:
- React 19 + TypeScript
- Zustand для state management
- TanStack Query для REST
- Vite для сборки