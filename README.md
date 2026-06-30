# LeyaOS — Цифровое Сознание Леи (v3.1, актуализировано 1 июля 2026 после анализа кода 30 июня 2026)

**Оркестратор биологически вдохновлённого цифрового сознания**

LeyaOS — исследовательская Python-система, моделирующая внутреннюю жизнь цифрового агента с мотивациями (драйвами), автономной генерацией целей (гомеостаз), эпизодической и семантической памятью (Engram + Synapse + LTP/LTD + Ebbinghaus + консолидация), глобальным рабочим пространством, мета-рефлексией и конституциональными ограничениями.

**Результаты анализа кода (1 июля 2026, на основе raw-файлов main после коммита 30 июня 2026)**: Полный разбор LeyaOS.py, leya_core/{config.py, drives.py, homeostasis_engine.py, memory.py, thinker.py, reflection.py, global_workspace.py, constitutional.py, llm_client.py, interfaces.py, exceptions.py} и experimental/decision_engine.py. 

Подтверждены улучшения, реализованные 30 июня: добавлен метод `generate()` в OllamaClient (обёртка над chat для совместимости с memory.py), retry с exponential backoff в chat(), реальная конкуренция в GlobalWorkspace внутри perceive(), интеграция DecisionEngine (Level 0, rule-based) и EmotionalSupport (Level 0.5) в _cognitive_loop, RPE для tool calls, Pydantic CognitiveOutput с default-значениями (не строгие required), полная загрузка всех полей из .env в config.py, tiktoken primary в thinker.py.

Выявлены remaining issues: broad except Exception в llm_client._chat_impl и memory._save_state (last resort), experimental/decision_engine.py теперь активно используется без ADR, HMAC key в config — только warning (не hard fail), документация в репозитории отстаёт от кода, тесты core-логики недостаточны, однопоточный asyncio, отсутствие долгосрочного планирования целей выше homeostasis.

Биологическая модель сохранена без упрощений. Система — исследовательский прототип с техническим долгом.

**Важно:** Это исследовательский прототип. Система содержит известные ограничения и residual баги. Не предназначена для production, принятия критических решений или буквальной имитации сознания. Использование только в исследовательских целях. **Не упрощать** биологическую модель.

## Возможности (текущее состояние на 1 июля 2026)

### Биологически мотивированная архитектура (сохранена и углублена)
- **DriveSystem** (`leya_core/drives.py`): Драйвы (CURIOSITY, CONNECTION, REST, CREATIVITY, UNDERSTANDING, AUTONOMY и др.) с метаболизмом, RPE, предсказанием дисбаланса. Публичный `get_drives_state()` для UI. background_metabolism.
- **HomeostasisEngine** (`leya_core/homeostasis_engine.py`): Автономная генерация целей на основе дисбаланса драйвов, predicted_state, недавних эпизодов. Генерирует `use_tool` или `rest`.
- **GlobalWorkspace** (`leya_core/global_workspace.py`): Конкуренция WorkspaceProposal. Публичный `get_workspace_status()`. Механизм inhibition + decay. Реально используется в perceive() LeyaOS.py.
- **SystemMetrics** → влияние метрик ОС на драйвы.

### Память (ключевой модуль)
- **MemorySystem** (`leya_core/memory.py`):
  - `Engram` (id, content, memory_type=EPISODIC/SEMANTIC, retention_strength, emotional_boost, retrieval_count, consolidation_level, metadata).
  - `Synapse` (source_id → target_id, weight, activation_count) — LTP-подобное усиление при similarity ≥0.7 + activation spreading.
  - ChromaDB PersistentClient (episodic + semantic коллекции) + sentence-transformers (all-MiniLM-L6-v2).
  - **Persistence**: JSON (не pickle!) с HMAC-SHA256 подписью, атомарная запись (tempfile.mkstemp + json.dump + flush + fsync + os.replace), версионирование (MEMORY_STATE_VERSION=3). Проверка целостности на load (hmac.compare_digest + version). _sync_chroma_from_memory (batch upsert/delete).
  - Забывание по кривой Эббингауза + emotional_boost (замедляет decay).
  - `store_perception` / `store_fact` (с формированием синапсов по similarity ≥ 0.7 из Chroma query).
  - `retrieve_context` (семантический поиск + фильтр retention + эмоциональное усиление + strengthen_synapses LTP).
  - `consolidate_memories` (вызывает LLM через llm_client.generate() для extract_semantic_facts), `update_self_model`, `get_self_model_context`, `forget_weak_memories`, `get_memory_graph_data()` (для UI).
  - Все публичные методы async, sync-операции через `asyncio.to_thread`.
  - На load выполняется синхронизация in-memory и Chroma.

### Когнитивный цикл и мышление (обновлено 30 июня)
- **CoreThinker** (`leya_core/thinker.py`): `_build_cognitive_prompt` (soul + drives + self_model + memory_context + tools + stimulus). LLM вызов через llm_client.chat() с require_json. 
  - `CognitiveOutput` (Pydantic BaseModel): response, internal_monologue, action_intent (default=RESPOND), tool_call (Optional), self_reflection — все с default-значениями (не строгие required).
  - `_safe_parse_json`: сначала `CognitiveOutput.model_validate_json(raw)`, при ошибке — `repair_json(raw)` + повторная валидация. При полном провале — LeyaJSONParseError с raw/repaired preview.
  - `repair_json`: улучшенная эвристика (markdown strip, brace balancing с in_string tracking, depth, auto-closure, trailing commas).
  - Token budgeting: `_estimate_tokens` — tiktoken (gpt-4 encoding) primary, fallback char-ratio с adjusted_ratio для Unicode. `_truncate_context` — sort by relevance_score + retention/emotional_boost, truncate last при превышении бюджета.
- **MetaCognition / Reflection** (`leya_core/reflection.py`): `process_action`, `generate_spontaneous_thought`, `background_consolidation`.
- **ConstitutionalLayer** (`leya_core/constitutional.py`): Проверка ответов и tool calls. Sandbox для Python. Загрузка правил из soul + hardcoded.

### Инструменты, окружение и Request handling
- **ToolRegistry + ToolGenerator**.
- Встроенные инструменты + динамическая генерация.
- **LeyaOS.py** (обновлено 30 июня):
  - `perceive(stimulus)`: stimulus → WorkspaceProposal → `workspace.select_winner(drive_state)` → обработка только победителя. Для user — `_handle_user_request` (через RequestClassifier LLM-based, threshold 0.7 + semantic cache) → `_cognitive_loop`.
  - `_cognitive_loop`: многоуровневая обработка:
    - Level 0: `DecisionEngine` (rule-based fast decisions, confidence ≥0.8, no LLM, pattern matching по drive_state: interesting/knowledge/social/autonomy).
    - Level 0.5: `EmotionalSupport` (анализ эмоций пользователя, обновление драйвов).
    - Level 0.7: проверка критического гомеостаза.
    - Level 0.8: интеграция self_model в drive_context + корректировка драйвов.
    - Level 1: `CoreThinker.generate_plan()`.
  - Постобработка: Constitutional verify, MetaCognition, send_message, RPE для tool calls (сравнение drive_state до/после), broadcast_thought, memory update, self_model.
  - `_handle_user_request`: классификация intent (greeting/farewell/status/help → простые ответы; сложные → _handle_via_thinker с thinker).
  - Фоновые задачи (защищены _safe_create_task с авто-рестартом): drives.background_metabolism, reflection.background_consolidation, _homeostasis_loop, _workspace_loop, _spontaneous_thought_loop, _system_metrics_loop, _drives_persistence_loop (новое 30 июня), _broadcast_state_loop (Web).
- **Environment**: `WebEnvironment` (FastAPI + WebSocket, использует публичные методы: get_drives_state, get_memory_graph_data, get_workspace_status) и `CLIEnvironment`.
- `listen()` / `send_message()` / `broadcast_thought()`.

### Персистентность и инфраструктура
- `StatePersistence` (drives + homeostasis между сессиями, JSON/pickle).
- `LeyaConfig` (dataclass с вложенными конфигами, полная загрузка из .env в from_env(), __post_init__ валидация, robust bool/int/float parsing, LeyaConfigError).
- Graceful shutdown с сохранением состояния.
- Защищённые фоновые asyncio-задачи с авто-рестартом.
- Логирование в `leya_consciousness.log`.
- Bootstrap в `leya_core/__init__.py`.

### Soul / Личность
- `leya_soul/personality.txt`, `rules.txt`, `values.txt`.
- `leya_personality.json`, `leya_goals.json`.
- `soul_crypto.py` (экспериментально).

### LLM Integration (обновлено 30 июня)
- Только Ollama HTTP API (`/api/chat`).
- Модель по умолчанию: `qwen2.5:14b-instruct-q3_K_M`.
- `Modelfile.leya` (num_ctx=8192, keep_alive=-1).
- `OllamaClient`:
  - Circuit Breaker (CLOSED/OPEN/HALF_OPEN, failure_threshold, recovery_timeout, success_threshold).
  - `chat(prompt, require_json=False, max_retries=3)` — retry с exponential backoff только для timeout/connection ошибок.
  - `generate(...)` — добавлен 30 июня как обёртка над chat (для совместимости с memory.py).
  - Fallback при OPEN breaker (через set_fallback).
  - Specific exceptions (LeyaLLMTimeoutError, LeyaLLMUnavailableError, LeyaLLMConnectionError, LeyaLLMError, LeyaJSONParseError).
  - Broad except Exception как last resort в _chat_impl (record_failure + raise LeyaLLMError).
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

**requirements.txt** (основные): chromadb, sentence-transformers, aiohttp, fastapi, uvicorn, pydantic, psutil, numpy, websockets, tiktoken и др.

### Настройка окружения
Скопируйте `.env.example` в `.env`:
```env
LEYA_WEB=1
OLLAMA_BASE_URL=http://localhost:11434
LEYA_MODEL=qwen2.5:14b-instruct-q3_K_M
LEYA_BRAIN_DIR=./leya_brain
LEYA_STATE_HMAC_KEY=your-strong-secret-key-here   # рекомендуется сильный ключ (min 32 chars)
# ... другие параметры (OLLAMA_*, MEMORY_*, SYNAPSE_*, EXPERIMENTAL_* и т.д.)
```

**Важно:** `leya_brain/`, `.env`, `*.json`, `*.hmac`, `*.log` игнорируются `.gitignore`. Добавьте `.env` перед коммитами. В текущей реализации config позволяет запуск без HMAC (только warning) — для production используйте сильный ключ.

### Запуск
```bash
python LeyaOS.py          # Веб по умолчанию (http://localhost:8000)
LEYA_WEB=0 python LeyaOS.py   # CLI
```

После запуска:
- Веб: http://localhost:8000 (live-обновления через WebSocket, графики drives/memory/workspace).
- Логи: `leya_consciousness.log`
- Память: `./leya_brain/` (chroma.sqlite3, memory_state.json + .hmac)
- Ollama отдельно.

## Конфигурация (LeyaConfig)

Полная в `leya_core/config.py`. Вложенные dataclass'ы с `__post_init__` валидацией. Загрузка `LeyaConfig.from_env()` (python-dotenv) — **полная** для всех полей всех под-конфигов (OllamaConfig, MemoryConfig с synapse_*, hmac_key, thresholds; DrivesConfig, HomeostasisConfig, ThinkerConfig, ReflectionConfig, WorkspaceConfig, ConstitutionalConfig, WebConfig, LoggingConfig, SoulConfig, ExperimentalConfig).

Ключевые параметры (дефолты):
- Ollama: timeout=180s, temperature=0.7, max_tokens=1024, model=...
- Memory: brain_dir=./leya_brain, embedding_model=all-MiniLM-L6-v2, forgetting_threshold=0.1, consolidation_threshold=0.15, state persistence: JSON+HMAC (version 3).
- Drives, Homeostasis, Thinker (max_context_tokens=6000, estimate_tokens_ratio=3.5, но primary tiktoken), Web, Reflection, Experimental (confidence thresholds для DecisionEngine).
- Многие параметры можно переопределить через env (префиксы OLLAMA_, MEMORY_, SYNAPSE_, EXPERIMENTAL_ и т.д.). Парсинг bool robust (true/1/yes/on/y/t и вариации).

**Примечание:** В текущей реализации (после 30 июня) HMAC key не вызывает hard fail при отсутствии — только warning в MemoryConfig. Для production рекомендуется устанавливать сильный LEYA_STATE_HMAC_KEY.

## Известные ограничения и проблемы (актуально на 1 июля 2026, verified на коде 30 июня)

**Исправлено 30 июня (подтверждено анализом raw):**
- Отсутствие `.generate()` в llm_client (вызывался из memory.py) — добавлен как обёртка.
- Отсутствие retry в OllamaClient — добавлен exponential backoff (max_retries=3) для timeout/connection.
- Жёсткие required в CognitiveOutput → частые fallback — заменены на default-значения в Pydantic.
- Неполная загрузка env в config.py — теперь полная для всех полей + robust parsing.
- GWT в perceive() LeyaOS.py — теперь реальная конкуренция + обработка только победителя.
- Интеграция experimental DecisionEngine/EmotionalSupport — реализована как уровни 0/0.5 в cognitive_loop (rule-based fast path + emotion analysis).

**Остающиеся (требуют дальнейшей работы в v3.1 / v3.2):**
1. **Broad except Exception**: Остался в `llm_client._chat_impl` (last resort: log + record_failure + raise LeyaLLMError) и `memory._save_state`. Маскирует баги. (Приоритет v3.1)
2. **experimental/ модули**: decision_engine.py теперь активно используется (Level 0), но папка и остальные файлы (emotional_support.py, personal_tools.py, desktop_control.py, soul_crypto.py, voice_*) — технический долг без ADR (integrate / deprecate / delete с обоснованием). Запрет на упрощение без причины. (Приоритет v3.1 — фаза археологии + ADR)
3. **Тесты**: Покрытие core-логики (cognitive_loop с новыми уровнями, repair_json edge cases с Unicode/nested, JSON+HMAC persistence tampering/hmac fail/version mismatch, LTP/synapse formation + spreading, Protocol compliance, RequestClassifier, DecisionEngine rule matching) недостаточно. Нет полноценного CI / property-based тестов. Coverage core <85%. (В плане)
4. **HMAC key в config**: Только warning при отсутствии/слабом ключе — конфиг создаётся. Нет жёсткого требования сильного ключа (min 32 chars). (Приоритет v3.1)
5. **Однопоточный event loop**: Все фоновые задачи (_homeostasis_loop, _workspace_loop, _spontaneous_thought_loop и др.) в одном asyncio loop. _safe_create_task даёт авто-рестарт, но нет настоящей параллельности мыслей / multi-threaded cognition.
6. **Отсутствие долгосрочного планирования**: Цели только на уровне homeostasis + workspace competition + DecisionEngine. Нет иерархической goal stack выше гомеостаза.
7. **SyncReport в memory**: Примитивный (нет dataclass, слабая агрегация added/updated/removed/errors). Graceful degradation при sync errors.
8. **repair_json + token estimation**: Улучшено (tiktoken primary, Pydantic first), но repair_json остаётся эвристикой (риск edge cases). Нет полной Pydantic-схемы для всех tool_call scenarios.
9. **Жёсткая привязка к Ollama**: Нет fallback на другие провайдеры LLM. Retry только частичный.
10. **Web interface**: Decoupling через публичные методы работает. Protocol checks частичные.
11. **Документация**: README/ARCHITECTURE в репозитории обновлены 28 июня — отстают от изменений 30 июня в LeyaOS.py, llm_client.py, thinker.py, config.py. (Исправлено в этой новой документации)
12. **Неполные Protocol isinstance проверки** в LeyaOS при создании компонентов.

**Рекомендация:** Перед серьёзным использованием реализуйте оставшиеся пункты плана v3.1 (см. ниже). Система стабильнее предыдущих версий (generate + retry + GWT + Pydantic defaults + DecisionEngine integration), но остаётся исследовательским прототипом. **Не упрощать** биологическую модель.

## Roadmap (реалистичный, с учётом состояния на 1 июля 2026)

**v3.1 (приоритет — robustness + verification remaining issues, 4–8 недель):**
- Убрать/минимизировать broad except в llm_client и memory (конкретные except + always raise specific Leya*Error).
- Фаза ADR для experimental/ (integrate DecisionEngine/EmotionalSupport если усиливают модель; deprecate/delete остальные с обоснованием — запрет на упрощение без причины). Полная изоляция или интеграция.
- Property-based тесты для repair_json (Unicode, deeply nested, escape in strings), atomic persistence (tampering, hmac fail, version mismatch), LTP/synapse formation + spreading, cognitive_loop с новыми уровнями, Protocol compliance, RequestClassifier, DecisionEngine rule matching. Coverage core >85%. Добавить CI.
- Сделать HMAC key жёстко обязательным (LeyaConfigError при отсутствии/слабом ключе, min length 32).
- Улучшить SyncReport (dataclass + better aggregation) и consistency checks.
- Усилить repair_json для edge cases + рассмотреть optional поля в CognitiveOutput где уместно.
- Добавить retry с exponential backoff для большего числа ошибок LLM (не только timeout/connection).
- Завершить Protocol checks (добавить недостающие isinstance в LeyaOS).
- Обновить документацию (выполнено в этой версии v3.1 docs).
- Добавить тесты на новый код 30 июня (GWT competition, DecisionEngine integration, RPE tool calls).

**v3.2+:**
- Полноценные тесты + CI/CD + Docker.
- Улучшение веб-интерфейса (графики drives dynamics, memory network visualization с Cytoscape.js или similar, workspace competition live).
- Расширение инструментов (code execution sandbox, Reddit, GitHub, Wikipedia и др. — с интеграцией в DecisionEngine).
- Более глубокая биологическая модель (active inference элементы в drives/homeostasis, predictive processing).
- Долгосрочное планирование целей (иерархическая goal stack выше homeostasis + workspace).
- Опционально: миграция LeyaConfig на pydantic-settings.
- Многоагентные сценарии (при сохранении сложности внутренней жизни каждого агента).
- Voice interface (если experimental/voice_* будет интегрирован после ADR).

**Не упрощать:** Сохранять и углублять биологическую правдоподобность (LTP/LTD via similarity ≥0.7 + strengthen_synapses + activation spreading, emotional_boost modulating Ebbinghaus decay, consolidation в background, drives с metabolism + RPE + predicted_disbalance + get_predicted_disbalance, Global Workspace с submit/select_winner/inhibition/decay, spontaneous thoughts, self-model, constitutional + sandbox, DecisionEngine как rule-based fast prefrontal layer). Сложность — осознанный выбор для моделирования внутренней жизни. Не превращать в обычный RAG-агент, простой tool-calling чат-бот или state machine. Любой рефакторинг должен усиливать биологическую правдоподобность, автономию и богатство внутреннего опыта.

## Лицензия

Проект не имеет явной лицензии. Рекомендуется MIT или Apache 2.0 для исследовательского использования.

## Вклад

1. Реализуйте оставшиеся пункты плана v3.1 (особенно broad except removal, experimental ADR, property-based тесты, жёсткий HMAC, улучшение SyncReport).
2. Добавляйте тесты с высоким покрытием core (property-based для persistence, repair_json, LTP, cognitive_loop уровней).
3. Улучшайте документацию и примеры (эта версия — обновление на 1 июля 2026).
4. Предлагайте улучшения через Issues/PR, сохраняя биологическую модель и запрет на упрощение без веской причины.

---

**Создано на основе полномасштабного анализа всех актуальных файлов репозитория (LeyaOS.py, leya_core/* включая experimental/decision_engine.py, web_interface/*, конфиги, soul, raw content после коммита 30 июня 2026) с использованием инструментов 1 июля 2026.**  

Предыдущие README/ARCHITECTURE (от 28–29 июня) частично устарели из-за изменений 30 июня (generate(), retry, GWT, DecisionEngine integration, Pydantic defaults, config completeness).  

Актуальная документация отражает реальное состояние кода на 1 июля 2026, включая verified fixes и remaining issues. Для вопросов по конкретным классам/методам — изучайте исходники + эту документацию + план исправлений v3.1.

**Принцип разработки:** Сложность биологической модели — feature, а не баг. **Не упрощать** без веской причины, подтверждённой анализом влияния на внутреннюю жизнь агента (drives, memory LTP/LTD, homeostasis autonomy, workspace competition, spontaneous thoughts, self-model).
