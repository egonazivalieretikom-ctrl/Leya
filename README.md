# LeyaOS — Цифровое Сознание Леи (v3.1, актуализировано 29 июня 2026 после полномасштабного код-ревью)

**Оркестратор биологически вдохновлённого цифрового сознания**

LeyaOS — исследовательская Python-система, моделирующая внутреннюю жизнь цифрового агента с мотивациями (драйвами), автономной генерацией целей (гомеостаз), эпизодической и семантической памятью (Engram + Synapse + LTP/LTD + Ebbinghaus + консолидация), глобальным рабочим пространством, мета-рефлексией и конституциональными ограничениями.

**Результаты код-ревью (29 июня 2026)**: Полный разбор всех ключевых файлов (LeyaOS.py, leya_core/{config,drives,homeostasis_engine,memory,thinker,reflection,global_workspace,constitutional,llm_client,interfaces,exceptions}.py и др.). Подтверждены улучшения v3.0 (JSON+HMAC atomic persistence с fsync + mandatory key + sync, Pydantic CognitiveOutput + улучшенный repair_json + tiktoken, полная config loading, LLM RequestClassifier, специфичные exceptions в большинстве мест, protected tasks). Выявлены verified баги (missing .generate() в llm_client при вызовах из memory.py, residual broad except в 2 местах, неполные Protocol checks, отсутствие retry). Биологическая модель сохранена без упрощений. Система — исследовательский прототип с техническим долгом.

**Важно:** Это исследовательский прототип. Система содержит известные ограничения. Не предназначена для production, принятия критических решений или буквальной имитации сознания. Использование только в исследовательских целях.

## Возможности (v3.0, с обновлениями 27–28 июня)

### Биологически мотивированная архитектура
- **DriveSystem** (`leya_core/drives.py`): Драйвы (CURIOSITY, CONNECTION, REST, CREATIVITY, UNDERSTANDING, AUTONOMY и др.) с метаболизмом, RPE, предсказанием дисбаланса. Публичный `get_drives_state()` для UI.
- **HomeostasisEngine** (`leya_core/homeostasis_engine.py`): Автономная генерация целей на основе дисбаланса драйвов, predicted_state, недавних эпизодов. Генерирует `use_tool` или `rest`.
- **GlobalWorkspace** (`leya_core/global_workspace.py`): Конкуренция WorkspaceProposal. Публичный `get_workspace_status()`. Есть механизм inhibition.
- **SystemMetrics** → влияние метрик ОС на драйвы.

### Память (ключевой модуль, улучшен)
- **MemorySystem** (`leya_core/memory.py`):
  - `Engram` (id, content, memory_type=EPISODIC/SEMANTIC, retention_strength, emotional_boost, retrieval_count, consolidation_level, metadata).
  - `Synapse` (source_id → target_id, weight, activation_count) — LTP-подобное усиление.
  - ChromaDB PersistentClient (episodic + semantic коллекции) + sentence-transformers.
  - **Persistence**: JSON (не pickle!) с HMAC-SHA256 подписью, атомарная запись (tempfile + os.replace), версионирование (MEMORY_STATE_VERSION=3). Проверка целостности на load.
  - Забывание по кривой Эббингауза + emotional_boost.
  - `store_perception` / `store_fact` (с формированием синапсов по similarity ≥ 0.7 из Chroma).
  - `retrieve_context` (семантический поиск + фильтр retention + усиление синапсов).
  - `consolidate_memories`, `update_self_model`, `get_self_model_context`, `forget_weak_memories`, `get_memory_graph_data()` (для UI).
  - Все публичные методы async, sync-операции через `asyncio.to_thread`.
  - **Примечание**: На load выполняется синхронизация in-memory и Chroma (добавлено в v3.0+).

### Когнитивный цикл и мышление
- **CoreThinker** (`leya_core/thinker.py`): `_build_cognitive_prompt` (soul + drives + self_model + memory_context + tools + stimulus). LLM вызов с `require_json=True`. `repair_json` (эвристика: markdown strip, brace balancing, trailing commas, auto-closure) + `_safe_parse_json`. Fallback на статический JSON. Token budgeting (char-ratio, configurable). 
- **MetaCognition / Reflection** (`leya_core/reflection.py`): `process_action`, `generate_spontaneous_thought`, `background_consolidation`.
- **ConstitutionalLayer** (`leya_core/constitutional.py`): Проверка ответов и tool calls. Sandbox для Python.

### Инструменты и окружение
- **ToolRegistry + ToolGenerator**.
- Встроенные инструменты + динамическая генерация.
- **Environment**: `WebEnvironment` (FastAPI + WebSocket, использует публичные методы интерфейсов: `get_drives_state()`, `get_memory_graph_data()`, `get_workspace_status()`) и `CLIEnvironment`.
- `listen()` / `send_message()` / `broadcast_thought()`.

### Персистентность и инфраструктура
- `StatePersistence` (drives + homeostasis между сессиями, JSON/pickle).
- `LeyaConfig` (dataclass с вложенными конфигами и валидацией в `__post_init__`, частичная загрузка из `.env`).
- Graceful shutdown с сохранением состояния.
- Защищённые фоновые asyncio-задачи с авто-рестартом (`_safe_create_task`).
- Логирование в `leya_consciousness.log`.
- Bootstrap в `leya_core/__init__.py`.

### Soul / Личность
- `leya_soul/personality.txt`, `rules.txt`, `values.txt`.
- `leya_personality.json`, `leya_goals.json`.
- `soul_crypto.py` (экспериментально, в experimental/).

### LLM Integration
- Только Ollama HTTP API (`/api/chat`).
- Модель по умолчанию: `qwen2.5:14b-instruct-q3_K_M`.
- `Modelfile.leya` (num_ctx=8192, keep_alive=-1).
- `OllamaClient` с Circuit Breaker (CLOSED/OPEN/HALF_OPEN), timeout, fallback, специфичными исключениями.
- Системный промпт и все текстовые поля — на русском языке.

## Быстрый старт

### Требования
- Python 3.10+
- Ollama (локально): `ollama serve`
- Модель: `ollama pull qwen2.5:14b-instruct-q3_K_M`
- Git

### Установка
```bash
git clone https://github.com/egonazivalieretikom-ctrl/Leya.git
cd Leya

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

**requirements.txt** (основные): chromadb, sentence-transformers, aiohttp, fastapi, uvicorn, pydantic, psutil, numpy, websockets и др.

### Настройка окружения
Скопируйте `.env.example` в `.env`:
```env
LEYA_WEB=1
OLLAMA_BASE_URL=http://localhost:11434
LEYA_MODEL=qwen2.5:14b-instruct-q3_K_M
LEYA_BRAIN_DIR=./leya_brain
LEYA_STATE_HMAC_KEY=your-strong-secret-key-here   # ОБЯЗАТЕЛЬНО для production
# ... другие параметры
```

**Важно:** `leya_brain/`, `.env`, `*.json`, `*.hmac`, `*.log` игнорируются `.gitignore`. Добавьте `.env` перед коммитами.

### Запуск
```bash
python LeyaOS.py          # Веб по умолчанию (http://localhost:8000)
LEYA_WEB=0 python LeyaOS.py   # CLI
```

После запуска:
- Веб: http://localhost:8000 (live-обновления через WebSocket).
- Логи: `leya_consciousness.log`
- Память: `./leya_brain/` (chroma.sqlite3, memory_state.json + .hmac)
- Ollama отдельно.

## Конфигурация (LeyaConfig)

Полная в `leya_core/config.py`. Вложенные dataclass'ы с `__post_init__` валидацией. Загрузка `LeyaConfig.from_env()` (python-dotenv).

Ключевые параметры (дефолты):
- Ollama: timeout=180s, temperature=0.7, max_tokens=1024, model=...
- Memory: brain_dir=./leya_brain, embedding_model=all-MiniLM-L6-v2, forgetting_threshold=0.1, consolidation_threshold=0.15, **state persistence: JSON+HMAC**
- Drives, Homeostasis, Thinker (max_context_tokens=6000, estimate_tokens_ratio=3.5), Web, Reflection и др.

Многие параметры можно переопределить через env (префиксы OLLAMA_, MEMORY_ и т.д.). **Примечание:** Не все поля под-конфигов полностью читаются из .env в текущей реализации (см. ограничения).

## Известные ограничения и проблемы (актуально на 28 июня 2026)

1. **HMAC key default** (memory.py): Слабый hardcoded fallback. Требуется обязательный сильный ключ из env. (Исправляется в плане v3.1)
2. **Неполная загрузка env в config.py**: Часть полей MemoryConfig/HomeostasisConfig/DrivesConfig не читается из .env (остаются default). Парсинг bool хрупкий. (В плане v3.1)
3. **Broad except Exception**: Остался в `memory._save_state` и `llm_client.chat` (хотя в большинстве мест — специфичные исключения). Маскирует баги. (В плане v3.1)
4. **Эвристики в _handle_user_request** (LeyaOS.py): Жёсткие ключевые слова. Ломается на вариациях. (В плане v3.1)
5. **repair_json + token estimation в thinker.py**: Сложная эвристика (brace balancing, auto-closure). Нет Pydantic-схемы для cognitive_output. Token estimation по символам (ratio). Риск некорректного парсинга или переполнения контекста. (В плане v3.1 — ввести Pydantic + улучшить)
6. **ChromaDB / in-memory consistency** (memory.py): На load возможен drift (хотя добавлена синхронизация). (В плане v3.1)
7. **experimental/ модули**: decision_engine.py, emotional_support.py, personal_tools.py, desktop_control.py, soul_crypto.py, voice_*.py изолированы, но не интегрированы и не удалены. Dead code / технический долг. Требуется анализ и ADR. (В плане v3.1 — фаза археологии)
8. **Тесты**: Покрытие core-логики (cognitive_loop, repair_json edge cases, JSON persistence, LTP, contract compliance) недостаточно. Нет полноценного CI. (В плане)
9. **Жёсткая привязка к Ollama**: Нет fallback на другие провайдеры. Нет retry (только Circuit Breaker).
10. **Однопоточный event loop**: Все фоновые задачи в одном asyncio loop. Нет настоящей параллельности мыслей.
11. **Отсутствие долгосрочного планирования** целей выше homeostasis.
12. **Web interface**: Использует новые публичные методы интерфейсов (get_drives_state и др.) — decoupling работает. Прямого доступа к internals нет.
13. **Документация**: Частично устарела (pickle → JSON). Требуется полное обновление (выполнено в v3.1 docs).

**Рекомендация:** Перед серьёзным использованием реализуйте план исправлений v3.1 (см. отдельный документ или Issues). Система стабильнее предыдущих версий, но остаётся исследовательским прототипом.

## Roadmap (реалистичный, с учётом плана v3.1)

**v3.1 (ближайшие 4–8 недель, приоритет — robustness):**
- Исправить HMAC key (обязательный сильный ключ, нет слабого дефолта).
- Полная загрузка всех полей из .env в config + улучшенный bool parsing.
- Убрать broad except в memory и llm_client (конкретные исключения).
- Гарантировать consistency Chroma <-> in-memory (явная синхронизация на load).
- Ввести Pydantic для CognitiveOutput + улучшить repair_json (как fallback) и token estimation (реальный токенизатор или динамический).
- Улучшить _handle_user_request (LLM-assisted extraction + fallback).
- Фаза анализа experimental/ + ADR (integrate / deprecate / delete с обоснованием). Запрет на упрощение без причины.
- Добавить retry с exponential backoff в OllamaClient.
- Расширить тесты (property-based для repair_json, persistence tampering, Protocol compliance). Coverage >85% core.
- Обновить документацию (выполнено).

**v3.2+:**
- Полноценные тесты + CI/CD + Docker.
- Улучшение веб-интерфейса (графики, memory network visualization).
- Расширение инструментов (code execution sandbox, Reddit, GitHub и др.).
- Более глубокая биологическая модель (active inference элементы).
- Долгосрочное планирование целей (иерархия выше homeostasis).
- Опционально: миграция LeyaConfig на pydantic-settings.
- Многоагентные сценарии (при сохранении сложности).

**Не упрощать:** Сохранять и углублять биологическую правдоподобность (LTP/LTD, emotional_boost, consolidation, drives с RPE и метаболизмом, Global Workspace, spontaneous thoughts, self-model). Сложность — осознанный выбор. Не превращать в обычный RAG-агент или простой чат-бот.

## Лицензия

Проект не имеет явной лицензии. Рекомендуется MIT или Apache 2.0 для исследовательского использования.

## Вклад

1. Реализуйте пункты плана v3.1 (особенно persistence security, config completeness, Pydantic в thinker, experimental analysis).
2. Добавляйте тесты с высоким покрытием (property-based для repair_json и persistence).
3. Улучшайте документацию и примеры.
4. Предлагайте улучшения через Issues/PR, сохраняя биологическую модель.

---

**Создано на основе полномасштабного код-ревью всех актуальных файлов репозитория (LeyaOS.py, leya_core/* включая experimental/, web_interface/*, конфиги, soul) с использованием инструментов 28 июня 2026.**  
Предыдущие README/ARCHITECTURE (от 26 июня) частично устарели из-за изменений persistence и interfaces.  

Актуальная документация отражает реальное состояние кода, а не только заявленную архитектуру. Для вопросов по конкретным классам — изучайте исходники + план исправлений v3.1.
