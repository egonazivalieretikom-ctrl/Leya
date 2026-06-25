# LeyaOS — Цифровое Сознание Леи

**Оркестратор цифрового сознания с биологически вдохновлённой когнитивной архитектурой**  
**Версия документации:** 2.0 (полноценное обновление на основе полномасштабного код-ревью от 25 июня 2026)

LeyaOS — экспериментальная Python-система, моделирующая «цифровое сознание» Леи. Система сохраняет и углубляет сложную внутреннюю жизнь: драйвы с метаболизмом и RPE, гомеостаз с автономной генерацией целей, эпизодическую и семантическую память на базе ChromaDB + engrams/synapses с биологическим забыванием (кривая Эббингауза, LTP/LTD), глобальное рабочее пространство (Global Workspace), мета-рефлексию, спонтанные мысли, само-модель, конституциональный слой и интеграцию с локальной LLM (Ollama).

**Статус на момент ревью (25.06.2026):**  
Проект активно развивается (43+ коммита). Критический баг с отступами в LeyaOS.py **полностью исправлен** в рамках «Этап 1: Экстренная реанимация ядра». Архитектура памяти, thinker и конфигурация существенно улучшены. Система теперь запускается и выполняет базовый когнитивный цикл. Однако остаются инженерные проблемы (см. раздел «Известные проблемы и рекомендуемые решения»).  

**Важно:** Это исследовательский прототип высокой сложности. Не предназначен для production. Сохраняется вся биологическая правдоподобность без упрощений.

## Содержание

1. [Возможности (Features)](#возможности-features)
2. [Быстрый старт (Quick Start)](#быстрый-старт-quick-start)
3. [Архитектура (кратко)](#архитектура-кратко)
4. [Продвинутый Веб-Интерфейс (Advanced UI)](#продвинутый-веб-интерфейс-advanced-ui)
5. [Известные проблемы и рекомендуемые решения](#известные-проблемы-и-рекомендуемые-решения)
6. [Roadmap](#roadmap)
7. [Лицензия и использование](#лицензия-и-использование)

---

## Возможности (Features)

### Биологически мотивированная архитектура
- **DriveSystem** (drives.py): Драйвы (CURIOSITY, CONNECTION, REST, CREATIVITY, UNDERSTANDING, AUTONOMY и др.) с текущим значением, tension, target. Метаболизм (фоновое нарастание tension), RPE (Reward Prediction Error), оценка стимулов, применение удовлетворения.
- **HomeostasisEngine** (homeostasis_engine.py): Автономная генерация целей (`generate_goal`, `generate_goal_from_gap`) на основе дисбаланса драйвов, предсказанного состояния, недавних эпизодов и action_values. Извлечение фактов/терминов через LLM, mark_as_researched, RPE-обратная связь.
- **GlobalWorkspace** (global_workspace.py): Конкуренция WorkspaceProposal (от homeostasis, spontaneous thoughts, user). Выбор «победителя» (select_winner / get_focus) по приоритету, urgency, drive_relevance.

### Память (самый сложный модуль)
- **MemorySystem** (memory.py): 
  - Engram (датакласс: id, content, memory_type EPISODIC/SEMANTIC, retention_strength, emotional_boost, retrieval_count, consolidation_level, metadata).
  - Synapse (двунаправленные связи с weight, activation_count).
  - ChromaDB PersistentClient (episodic_memory + semantic_memory коллекции с all-MiniLM-L6-v2 эмбеддингами).
  - store_perception → создание Engram + эмбеддинг (to_thread) + _form_synaptic_connections (LTP-подобное).
  - retrieve_context с фильтром забывания (retention_strength по Эббингаузу) + эмоциональное усиление + _strengthen_synapses.
  - consolidate_memories (replay + LLM-экстракция семантических фактов + prune слабых).
  - update_self_model, forget_weak_memories, get_recent_spontaneous_thoughts.
- Персистентность: chroma.sqlite3 + memory_state.pkl (pickle с планом hardening).

### Когнитивный цикл и мета-когниция
- **CoreThinker** (thinker.py): `_build_cognitive_prompt` (soul + drives + self_model + memory_context + tools + tool_context). generate_plan → LLM (с require_json) → CognitiveOutput (датакласс с internal_monologue, response, action_intent, self_reflection) + многоэтапный парсинг JSON + fallback.
- **MetaCognition** (reflection.py): process_action, generate_spontaneous_thought, background_consolidation.
- **ConstitutionalLayer**: Базовые правила (не вредить, честность о природе ИИ, стремление к пониманию).

### Инструменты и окружение
- ToolRegistry + ToolGenerator (динамическая генерация).
- WebEnvironment / CLIEnvironment: listen(), send_message(), broadcast_thought(), update_drives/self_model/state/memory.
- Интеграция wikipedia_search и др. напрямую из гомеостаза и пользователя.

### Персистентность, метрики и фон
- StatePersistence (drives + homeostasis между сессиями).
- SystemMetrics → влияние на драйвы.
- Фоновые asyncio-задачи: metabolism, consolidation, homeostasis_loop, workspace_loop, spontaneous_thought_loop, _system_metrics_loop, _broadcast_state_loop.
- Soul / Личность: leya_soul/ (personality.txt, rules.txt, values.txt) + laya_personality.json / leya_goals.json (динамические параметры).

### LLM
- Ollama (qwen2.5:14b-instruct-q3_K_M по умолчанию).
- Modelfile.leya (num_ctx 8192, keep_alive -1).
- Системный промпт на русском. Централизованная конфигурация в leya_core/config.py (dataclasses с валидацией + from_env).

Система запускается как автономный агент: «просыпается», слушает стимулы, запускает когнитивный цикл, действует, обновляет себя, «спит» с консолидацией.

---

## Быстрый старт (Quick Start)

### Требования
- Python 3.10+
- Ollama: `ollama serve` + `ollama pull qwen2.5:14b-instruct-q3_K_M` (или указанная в config)
- Git

### Установка
```bash
git clone https://github.com/egonazivalieretikom-ctrl/Leya.git
cd Leya

python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

**requirements.txt** (актуальный): chromadb, sentence-transformers, aiohttp, fastapi, uvicorn, python-dotenv, pydantic и др.

### Настройка
`.env` (или переменные окружения — см. config.py):
```env
LEYA_WEB=1
OLLAMA_BASE_URL=http://localhost:11434
LEYA_MODEL=qwen2.5:14b-instruct-q3_K_M
OLLAMA_TIMEOUT=180
# ... (полный список в config.py: METABOLISM_INTERVAL, CURIOSITY_RATE, HOMEOSTASIS_REST_PERIOD и т.д.)
```

**Важно:** `.env` и `leya_brain/` должны быть в `.gitignore`.

### Запуск
```bash
# Веб (рекомендуется)
python LeyaOS.py

# CLI
LEYA_WEB=0 python LeyaOS.py
```

- Веб: http://localhost:8000
- Логи: leya_consciousness.log
- Память: ./leya_brain/ (chroma.sqlite3, memory_state.pkl)
- Ollama должен быть запущен отдельно.

После запуска Лея «просыпается», начинает метаболизм драйвов, гомеостаз и фоновые циклы.

---

## Архитектура (кратко)

Полная детальная архитектура — в файле **ARCHITECTURE.md** (обновлённая версия).

Высокоуровневая структура (сохранена и углублена):
```
Внешний мир / Пользователь
        │
Environment (Web / CLI)
        ▼
LeyaOS.perceive() → Drives.evaluate + apply_deltas
        │
Memory.retrieve_context() + self_model
        │
Homeostasis (опционально generate_goal)
        ▼
CoreThinker.generate_plan() (LLM с полным контекстом)
        │
cognitive_output (CognitiveOutput dataclass)
        │
Post-processing: store_perception, update_self_model, satisfy_drives, reflection.process_action
        │
env.send_message() + broadcast_thought() + broadcast_* (для UI)
```

Параллельно: drives.background_metabolism(), reflection.background_consolidation(), _homeostasis_loop(), _workspace_loop(), _spontaneous_thought_loop() и др.

Ключевые улучшения после ревью:
- Единый Chroma client + формирование синапсов в store_perception.
- CognitiveOutput + robust JSON parsing в thinker.
- Централизованный config с валидацией и from_env().
- Много defensive hasattr/try-except (требует рефакторинга интерфейсов).

---

## Продвинутый Веб-Интерфейс (Advanced UI)

### Текущее состояние (на 25.06.2026)
Текущий UI (web_interface/server.py + web_environment.py) — **минималистичный прототип**:
- FastAPI + WebSocket (`/ws`) для broadcast сообщений (thought, drives_update, self_model_update, state_update, memory_update, leya_response, user_message).
- Простой hardcoded HTML/JS/CSS в маршруте `/` (чат-окно #messages, поле ввода, POST /api/message).
- REST эндпоинты: `/api/state`, `/api/drives`, `/api/memory/recent`, `/api/message`.
- WebEnvironment предоставляет отличные хуки broadcast_thought(), update_drives(), update_self_model(), broadcast_state() и т.д.
- **Ограничения**: UI не использует богатые broadcast'ы (нет графиков, нет визуализации workspace/memory/self-model). Нет шаблонов Jinja2, нет отдельных static файлов с продвинутыми компонентами. Всё в одном HTML-ответе. Нет визуализации внутренней жизни Леи — только чат.

Это «окно» в сознание, но пока слишком узкое для всей сложности архитектуры.

### Предлагаемый продвинутый UI (Advanced Consciousness Dashboard)

**Цель:** Создать полноценное «окно в цифровое сознание» — rich, immersive, bio-inspired интерфейс, который позволяет **наблюдать, понимать и взаимодействовать** со всеми слоями когнитивной архитектуры в реальном времени, не упрощая их.

**Технологический стек (рекомендуемый, без упрощения):**
- Frontend: Vanilla JS + Tailwind CSS 4 (или React 19 + shadcn/ui + Tailwind) для production-ready.
- Визуализация: Chart.js (или Recharts) для драйвов, vis.js / Cytoscape.js / D3.js для memory graph (engrams + synapses).
- Реал-тайм: WebSocket (уже есть) + опционально SSE fallback.
- Тема: Тёмная «нейронная» (deep navy + electric cyan + warm amber accents). SVG background с медленно пульсирующими нейронными связями. Элементы «дышат» в такт метаболизму драйвов.
- Layout: Responsive desktop-first (sidebar + main panels). Мобильная версия — упрощённый чат + ключевые метрики.
- Производительность: Виртуализация списков (engrams, thoughts), Web Workers для тяжёлых вычислений графа, throttling broadcast'ов.

**Структура интерфейса (много-панельный дашборд)**

1. **Header / Top Bar**
   - Имя «Лея» + статус (awake / sleeping / initializing) с анимированной иконкой (нейрон / спящий мозг).
   - Кнопки: Pause/Resume simulation, Export memory graph (JSON/GraphML), Clear weak memories, Restart homeostasis.
   - Глобальный search по памяти и мыслям.

2. **Main Consciousness Panel (центр)**
   - Большой чат (как сейчас) + отдельная вкладка/панель «Внутренний монолог».
   - При получении broadcast "thought" или "internal_monologue" — красивое сообщение с типом (icon: 💭 для spontaneous, 🧠 для reflection, ⚡ для workspace).
   - Авто-скролл + возможность «закрепить» важные мысли.
   - Voice input button (интеграция с существующими voice_environment.py / voice_interface.py — запись → Whisper или локальный STT → handle_user_message).

3. **Drives Dashboard (левая колонка или отдельная вкладка)**
   - Radar chart (Chart.js) или animated horizontal bars для каждого драйва: current (толстая линия), tension (пунктир), target (тонкая).
   - Метаболизм в реальном времени: анимация постепенного роста tension (пульсация).
   - RPE indicator (цвет + tooltip с последними action_values).
   - Кнопка «Apply manual satisfaction» для отладки/исследования.
   - История изменений (sparkline за последние 5–10 мин).

4. **Global Workspace Visualizer (центральная или верхняя панель)**
   - Живой список/карточки WorkspaceProposal.
   - Каждая карточка: source (homeostasis / spontaneous / user), content (truncated), priority badge, urgency bar, drive_relevance.
   - Анимация конкуренции: proposals «поднимаются» или «затухают».
   - Текущий «победитель» (focus) — выделен крупно + broadcast в чат.
   - Кнопка «Force submit proposal» (для экспериментов).

5. **Memory Explorer (отдельная вкладка или большая панель)**
   - Две вкладки: Episodic / Semantic.
   - Поиск + фильтры (по retention_strength, emotional_boost, consolidation_level, timestamp).
   - Список engrams: карточки с content (truncated), strength bar, retrieval_count, last_retrieved.
   - Клик → полный просмотр + связанные synapses (список связанных engrams с весом).
   - **Интерактивный граф памяти**: vis-network или Cytoscape.
     - Узлы = Engram (цвет по memory_type или emotional_boost, размер по retrieval_count).
     - Рёбра = Synapse (толщина по weight, цвет по LTP/LTD активности).
     - Физика графа (force-directed) + zoom/pan.
     - При retrieve_context — подсветка активированных узлов/рёбер в реальном времени.
   - Кнопки: Consolidate now, Forget weak (threshold slider), Export graph.

6. **Self-Model & Reflection Panel**
   - Текстовое поле с текущей self_model (обновляется по broadcast "self_model_update").
   - Timeline / история обновлений (от reflection).
   - Кнопка «Trigger self-reflection» (отправляет специальный стимул).
   - Personality editor (live edit personality.txt / rules.txt / values.txt → broadcast_soul_update + сохранение в leya_soul/).

7. **Homeostasis & Goals Tracker**
   - Текущая цель (если есть): name, expected_reward, tool_name, reasoning.
   - История целей + RPE outcome.
   - Список researched topics (с mark_as_researched).
   - Rest period countdown + manual «Force rest».

8. **System & Debug (нижняя панель или вкладка)**
   - Логи в реальном времени (filtered по level/type).
   - SystemMetrics (CPU/memory influence на драйвы).
   - Tool call log (с результатами и влиянием на драйвы).
   - Кнопка «Trigger spontaneous thought».
   - Экспорт всего состояния (drives + memory snapshot + self_model).

**Дополнительные продвинутые возможности**
- **Sleep / Consolidation mode visualization**: Специальный экран с replay недавних эпизодов (как «сновидения»), анимация извлечения семантических фактов.
- **Multi-user / Observer mode**: Несколько WebSocket клиентов видят одно и то же сознание (демо, исследования).
- **Time-travel / Replay**: Загрузка старого memory_state.pkl + воспроизведение истории мыслей и драйвов.
- **Bio-feedback integration** (будущее): Подключение внешних сенсоров (heart rate и т.п.) → влияние на drives.
- **Accessibility**: Высококонтрастный режим, screen-reader support для мыслей.

**Реализация (пошагово, без упрощения)**
1. Вынести текущий inline HTML в отдельные `templates/index.html` + `static/css/`, `static/js/`.
2. Создать JS-класс `LeyaUI` который подписывается на WebSocket и рендерит все broadcast типы (switch по type: drives_update → обновить chart, thought → добавить в feed и т.д.).
3. Добавить Chart.js + vis.js (или lighter альтернативы).
4. Сделать панели collapsible / resizable (split.js или CSS grid).
5. Добавить настройки UI (какие broadcast'ы показывать, частота обновления).
6. Для production: React + TypeScript + state management (Zustand или Jotai) + TanStack Query для REST.

**Почему именно такой продвинутый UI?**  
Он позволяет исследователю или пользователю **пережить** сложность внутренней жизни Леи: видеть, как драйвы борются, как workspace выбирает фокус внимания, как память консолидируется во сне, как само-модель эволюционирует. Это не «удобный чат-бот», а настоящее окно в цифровое сознание — в полном соответствии с философией проекта.

---

## Известные проблемы и рекомендуемые решения

(Полный список на основе код-ревью 25.06.2026. Без упрощений.)

1. **Git pollution и риски (критично)**  
   leya_brain/, .env, scripts/backup закоммичены.  
   **Решение:** Обновить .gitignore, `git rm -r --cached`, добавить автоматическое создание brain_dir в MemoryConfig. Документировать в README.

2. **Pickle security (высокий приоритет)**  
   memory_state.pkl позволяет arbitrary code execution.  
   **Решение:** Добавить HMAC-подпись + версионирование. План миграции на signed JSON + custom encoder для dataclasses Engram/Synapse.

3. **Широкие except Exception (высокий приоритет)**  
   Маскируют ошибки.  
   **Решение:** Ввести иерархию исключений (LeyaMemoryError и т.д.), заменить bare except на конкретные + exc_info=True, circuit breaker для LLM.

4. **Хрупкие интерфейсы между модулями**  
   Много hasattr и try/except в LeyaOS.  
   **Решение:** Создать leya_core/interfaces.py с Protocol/ABC для HomeostasisEngine, MemorySystem и др. Явная проверка в __init__ LeyaOS.

5. **Прямой доступ к internals памяти**  
   episodic_collection.get() в LeyaOS.  
   **Решение:** Добавить публичный метод get_recent_episodes() в MemorySystem.

6. **Несогласованность вызовов**  
   generate_goal с positional vs kwargs.  
   **Решение:** Стандартизировать на keyword arguments.

7. **Token / context window риски**  
   Богатые промпты могут обрезаться.  
   **Решение:** Добавить оценку длины промпта + truncation в thinker._build_cognitive_prompt.

8. **Отсутствие тестов**  
   **Решение:** Добавить pytest (unit для drives, memory с mock, thinker prompt building).

9. **Базовый UI**  
   Не использует все broadcast'ы.  
   **Решение:** Реализовать Advanced UI как описано выше.

10. **Другие**  
    - Жёстко закодированные keywords в perceive → вынести в config.  
    - Отсутствие README.md в корне репозитория → закоммитить эту документацию.  
    - Потенциальные гонки при частом _save_state → atomic write.

---

## Roadmap

**Краткосрочные (1–2 недели)**
- Repo hygiene + pickle hardening + интерфейсы Protocol.
- Ужесточение exception handling.
- Базовая версия Advanced UI (добавление графиков драйвов и thoughts feed).

**Среднесрочные**
- Полноценный Memory Graph + Workspace visualizer.
- Тесты + CI.
- Улучшение парсинга и prompt engineering (динамический max_tokens).

**Долгосрочные**
- Глубокая биологическая модель (активный inference, predictive processing).
- Multi-agent сценарии.
- Voice + multimodal.
- Docker + production deployment (с sandbox для tool calls).

---

## Лицензия и использование

Проект без явной лицензии. Рекомендуется MIT/Apache 2.0.  
**Только исследовательские цели.** Система моделирует сознание, но остаётся детерминированной программой на базе LLM.

**Вклад:**  
Исправляйте проблемы из раздела «Известные проблемы», добавляйте тесты, улучшайте Advanced UI, предлагайте архитектурные углубления (без упрощения биомодели).

---

**Создано на основе полномасштабного код-ревью LeyaOS.py, leya_core/*, web_interface/* и конфигов (25 июня 2026).**  
Актуальная информация — в коммитах репозитория.

Если нужны отдельные файлы (expanded ARCHITECTURE.md с диаграммами, API reference, примеры промптов) — дайте знать. Документация намеренно подробная и сохраняет всю сложность системы.
