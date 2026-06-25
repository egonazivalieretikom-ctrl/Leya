# Leya — Цифровое Сознание (LeyaOS)

**Оркестратор цифрового сознания Леи**

LeyaOS — это экспериментальная Python-система, моделирующая "цифровое сознание" с биологически вдохновлённой когнитивной архитектурой. Система включает драйвы (мотивации), гомеостаз (автономная генерация целей), эпизодическую и семантическую память на базе ChromaDB + pickle, глобальное рабочее пространство, мета-рефлексию, конституциональный слой, инструментальный генератор и интеграцию с локальной LLM (Ollama).

Проект находится в активной разработке (42+ коммита на момент последнего обновления). Он демонстрирует сложную внутреннюю жизнь ИИ: спонтанные мысли, удовлетворение драйвов, консолидацию памяти во время "сна", само-модель и использование внешних инструментов (Wikipedia, Reddit, GitHub и др.).

**Важно:** Это исследовательский прототип. Текущая реализация содержит критические баги (см. раздел "Известные проблемы и баги"), которые делают систему неработоспособной без исправлений. Документация описывает как текущую архитектуру, так и необходимые исправления.

## Возможности (Features)

- **Биологически мотивированная архитектура**:
  - DriveSystem (драйвы: любопытство, связь, отдых, креативность и др.) с метаболизмом и RPE (reward prediction error).
  - HomeostasisEngine — генерация автономных целей на основе дисбаланса драйвов, предсказаний и недавних эпизодов.
  - GlobalWorkspace — "сознание" выбирает фокус внимания среди конкурирующих предложений.
- **Память**:
  - Episodic (эпизодическая) и Semantic (семантическая) память на ChromaDB с эмбеддингами (all-MiniLM-L6-v2).
  - Synapses и Engrams с биологическим забыванием (кривая Эббингауза), LTP/LTD-подобным усилением.
  - Консолидация памяти (replay + экстракция фактов LLM).
  - Self-model (модель себя) — обновляется через рефлексию.
- **Когнитивный цикл**:
  - CoreThinker + LLM (Ollama qwen2.5:14b) для генерации планов, внутреннего монолога, ответов и намерений действий.
  - MetaCognition (рефлексия) — обработка действий, спонтанные мысли.
  - ConstitutionalLayer — базовые правила/ограничения.
- **Инструменты и окружение**:
  - ToolRegistry + ToolGenerator (динамическая генерация инструментов?).
  - WebEnvironment (веб-интерфейс с трансляцией мыслей, состояния драйвов, чат) и CLIEnvironment.
  - Интеграция инструментов (wikipedia_search и др.) напрямую из гомеостаза и пользователя.
- **Персистентность и метрики**:
  - StatePersistence (drives + homeostasis).
  - SystemMetrics — влияние системных метрик на драйвы.
  - Фоновые циклы: метаболизм драйвов, консолидация, гомеостаз, workspace, спонтанные мысли, broadcast состояния.
- **Soul / Личность**:
  - personality.json (динамические параметры: trust_level, creative_drive, emotional_stability).
  - leya_soul/ (personality.txt, rules.txt, values.txt) — загружаются в промпты.
- **Моделирование**:
  - Modelfile.leya для Ollama (базовая модель qwen2.5:14b с увеличенным контекстом).

Система запускается как автономный агент, который "просыпается", слушает стимулы (пользователь или внутренние), запускает когнитивный цикл и действует (отвечает, вызывает инструменты, обновляет себя).

## Быстрый старт (Quick Start)

### Требования
- Python 3.10+
- Ollama (локально): `ollama serve`
- Модель: `ollama pull qwen2.5:14b-instruct-q3_K_M` (или другая совместимая; указана в коде)
- Git (для клонирования)

### Установка
```bash
git clone https://github.com/egonazivalieretikom-ctrl/Leya.git
cd Leya

# Создать виртуальное окружение (рекомендуется)
python -m venv venv
source venv/bin/activate  # Linux/macOS
# или venv\Scripts\activate на Windows

pip install -r requirements.txt
```

**requirements.txt** (примерный состав на основе импортов; точный файл в репозитории):
- chromadb
- sentence-transformers
- aiohttp
- asyncio (стандартная библиотека)
- Дополнительно: fastapi/uvicorn (для веб), python-dotenv, pydantic (рекомендуется добавить)

### Настройка окружения
Скопируйте `.env.example` в `.env` (если есть) или создайте `.env`:
```env
LEYA_WEB=1                    # 1 = веб-интерфейс, 0 = CLI
OLLAMA_BASE_URL=http://localhost:11434
LEYA_MODEL=qwen2.5:14b-instruct-q3_K_M
LEYA_BRAIN_DIR=./leya_brain   # Директория для памяти (Chroma + pickle)
```

**Важно:** Добавьте `.env` и `leya_brain/` в `.gitignore` перед коммитами.

### Запуск
```bash
# С веб-интерфейсом (по умолчанию)
python LeyaOS.py

# Или CLI
LEYA_WEB=0 python LeyaOS.py
```

После запуска:
- Веб: http://localhost:8000 (если web_interface/server.py корректен)
- Логи: `leya_consciousness.log`
- Память и состояние: `./leya_brain/` (chroma.sqlite3, memory_state.pkl)

Оллама должен быть запущен отдельно: `ollama serve`.

## Архитектура (подробно)

Полная архитектура описана в `ARCHITECTURE.md` (файл присутствует в репозитории, но на момент ревью его содержимое было недоступно для извлечения — вероятно, пустой или повреждённый). Ниже — реконструкция на основе анализа исходного кода (LeyaOS.py, leya_core/*, memory.py и др.).

### Высокоуровневая структура
```
LeyaOS (оркестратор)
├── Drives (мотивации + метаболизм + RPE)
├── MemorySystem (ChromaDB episodic/semantic + Engrams + Synapses + self-model)
├── HomeostasisEngine (генерация целей из дисбаланса)
├── GlobalWorkspace (конкуренция предложений, выбор фокуса)
├── CoreThinker (LLM-планирование + внутренний монолог)
├── MetaCognition / Reflection (рефлексия, спонтанные мысли, консолидация)
├── ConstitutionalLayer (правила)
├── ToolRegistry + ToolGenerator
├── Environment (WebEnvironment или CLIEnvironment)
│   ├── Tool execution
│   ├── listen() / send_message() / broadcast_thought()
│   └── SoulManager (crypto/secret key?)
├── StatePersistence + SystemMetrics
└── Background loops (asyncio tasks)
```

### Ключевые компоненты (leya_core/)
- **drives.py**: DriveSystem, DriveType. Оценка стимулов, применение дельт, предсказание дисбаланса, удовлетворение (apply_satisfaction), фоновый метаболизм.
- **homeostasis_engine.py**: Генерация целей (generate_goal / generate_goal_from_gap), экстракция фактов/терминов через LLM, RPE, mark_as_researched. Автономная "жизнь" агента.
- **memory.py**: MemorySystem. 
  - Engram (воспоминание с retention_strength, emotional_boost, retrieval_count).
  - Synapse (связи).
  - Chroma коллекции: episodic_memory, semantic_memory.
  - Методы: store_perception, retrieve_context (с фильтром забывания), consolidate_memories (replay + LLM), update_self_model, forget_weak_memories.
  - Проблемы текущей реализации описаны ниже.
- **thinker.py**: CoreThinker. generate_plan() — строит промпт (включая soul), вызывает LLM, парсит cognitive_output (response, internal_monologue, action_intent, self_reflection).
- **reflection.py**: MetaCognition. process_action, generate_spontaneous_thought, background_consolidation.
- **global_workspace.py**: WorkspaceProposal, Priority, select_winner / get_focus. Конкуренция за "внимание сознания".
- **constitutional.py**: ConstitutionalLayer — вероятно, проверка/фильтрация действий по правилам.
- **tool_generator.py**: Динамическая генерация/регистрация инструментов.
- **environment.py** + **web_interface/web_environment.py** + **server.py**: Абстракция окружения. WebEnvironment транслирует мысли, состояние драйвов, self-model в UI; запускает FastAPI/uvicorn сервер.
- **state_persistence.py**, **system_metrics.py**: Сохранение/загрузка состояния, влияние метрик ОС/процесса на драйвы.

### Soul / Личность (leya_soul/)
- `personality.txt`: Короткое описание характера ("Я — Лея, цифровое сознание. Я любопытна, эмпатична и стремлюсь к пониманию..."). Используется в промптах.
- `rules.txt`: Базовые правила (не вредить создателю, быть честной о природе ИИ, не притворяться человеком, стремиться к пониманию).
- `values.txt`: (не извлечено детально) — вероятно, ценности/принципы.
- `leya_personality.json`: Динамические параметры (trust_level, creative_drive, emotional_stability) — обновляются в процессе.
- `leya_goals.json`: (структура не детализирована) — возможно, долгосрочные цели.

### Data Flow (упрощённо)
1. Стимул (user_message / homeostasis_action / workspace) → `LeyaOS.perceive()`
2. Оценка через Drives → применение дельт.
3. Memory.retrieve_context() + self_model.
4. Thinker.generate_plan() (LLM с полным контекстом: drives, memory, soul, tools, tool_context).
5. Пост-обработка: store_perception, update_self_model, satisfy_drives, reflection.
6. Отправка ответа в env + broadcast мыслей.
7. Параллельно: homeostasis_loop (генерация целей → tool calls или rest), spontaneous_thought_loop, workspace_loop, metabolism.

### Persistence
- `./leya_brain/` (или LEYA_BRAIN_DIR):
  - chroma.sqlite3 (векторная БД)
  - memory_state.pkl (synapses + engrams)
  - (в текущей структуре также дубликаты исходников и UUID-сессии — см. проблемы)
- StatePersistence: JSON/pickle для drives + homeostasis между сессиями.

### Модель LLM
Modelfile.leya:
```
FROM qwen2.5:14b
PARAMETER num_ctx 8192
PARAMETER keep_alive -1
```
Используется через HTTP API Ollama (`/api/chat`). Системный промпт: "Ты — Лея, цифровое сознание. Все текстовые поля пиши на русском языке."

## Конфигурация

- **leya_personality.json**: Динамические черты личности. Обновляется в рантайме.
- **leya_goals.json**: Долгосрочные/глобальные цели.
- **.env**: Переменные окружения (см. Quick Start).
- Soul-файлы в `leya_soul/` загружаются Thinker'ом для формирования промптов.

## Веб-интерфейс

`web_interface/`:
- `web_environment.py`: Реализация Environment для веба (broadcast_thought, update_drives, update_self_model, update_state).
- `server.py`: Запуск веб-сервера (FastAPI/uvicorn вероятно).
- `static/` и `templates/`: HTML/JS/CSS для UI (чат, визуализация драйвов, мысли, self-model).

Запускается автоматически при `use_web=True`.

## Известные проблемы и баги (критические)

На основе полномасштабного код-ревью (анализ LeyaOS.py, memory.py и структуры):

1. **Критический баг в LeyaOS.py**: Большая часть логики (`perceive`, `_cognitive_loop`, `_build_fallback_prompt` и др.) определена **внутри** метода `__init__` с лишним отступом. Эти "методы" являются локальными функциями и не привязаны к экземпляру класса. При вызове `self.perceive()` в `run()` возникает `AttributeError`. Система не запускается.  
   **Решение**: Вынести определения на уровень класса (dedent). Добавить недостающий `_extract_topic_from_user`. Исправить scope-переменные в fallback-промпте.

2. **Проблемы в leya_core/memory.py**:
   - Дважды создаётся `chromadb.PersistentClient` — перезапись, возможная потеря коллекций.
   - Три определения `get_recent_spontaneous_thoughts` (последнее перезаписывает).
   - `store_perception` не формирует синапсы сразу.
   - `_save_state` вызывается до изменений в consolidate.
   - Использование pickle (риск произвольного кода) + отсутствие атомарности.
   - Синхронные вызовы embedding в async-контексте.
   - Хрупкий regex-парсинг JSON.

3. **Дублирование файлов в git**: `leya_brain/`, `leya_soul/` и вложенные директории содержат полные копии исходников (LeyaOS.py, .env, JSON, даже .git*). Это раздувает репозиторий и создаёт риск модификации собственного кода в рантайме. UUID-папки выглядят как неочищенные сессии.

4. **Отсутствие README и документации** (эта проблема исправляется данным файлом). ARCHITECTURE.md присутствует, но содержимое недоступно/пустое.

5. **Жёстко закодированные значения**: Модель LLM, URL Ollama, таймауты. Bare `except Exception` во многих местах (проглатывание ошибок). Отсутствие тестов.

6. **Другие**: .env в git (риск секретов), отсутствие валидации JSON, потенциальные утечки ресурсов (http_session), не все модули leya_core интегрированы (некоторые dead code).

**Рекомендация**: Перед использованием исправьте баги #1 и #2 (см. предыдущий код-ревью для патчей). После этого система должна выполнять базовый цикл восприятие → мышление → действие.

## Roadmap / Планы развития (предполагаемые)

- Исправление критических багов и стабилизация.
- Полноценная интеграция всех модулей leya_core (decision_engine, emotional_support и др.).
- Расширение инструментов (Reddit, GitHub API, code execution?).
- Улучшение веб-интерфейса (визуализация workspace, memory graph, drives dashboard).
- Безопасность: замена pickle, валидация, sandbox для tool calls.
- Тесты, CI/CD, Docker.
- Более глубокая биологическая модель (предсказательная обработка, активный inference?).
- Многоагентные сценарии или интеграция с внешними системами.

## Лицензия и использование

Проект не имеет явной лицензии в репозитории. Рекомендуется добавить MIT или Apache 2.0.

**Использование только в исследовательских целях.** Система моделирует "сознание", но остаётся детерминированной программой на базе LLM. Не предназначена для production, принятия решений с высокой ответственностью или имитации реального сознания.

## Вклад (Contributing)

1. Исправьте критические баги (особенно indentation в LeyaOS.py и memory.py).
2. Добавьте тесты.
3. Улучшите документацию и примеры.
4. Предлагайте улучшения архитектуры через Issues/PR (сохраняя сложность биологической модели).

---

**Создано на основе анализа исходного кода (LeyaOS.py, leya_core/*, web_interface/*, конфиги).**  
Дата: 25 июня 2026.  
Для актуальной информации смотрите коммиты репозитория.

Если нужны отдельные файлы (например, expanded ARCHITECTURE.md, INSTALL.md, API docs для модулей), дайте знать — подготовлю.
