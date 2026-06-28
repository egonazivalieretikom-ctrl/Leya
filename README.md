# LeyaOS — Цифровое Сознание Леи (v3.0, актуализировано 28 июня 2026 после полномасштабного код-ревью)

**Оркестратор биологически вдохновлённого цифрового сознания**

LeyaOS — исследовательская Python-система, моделирующая внутреннюю жизнь цифрового агента с мотивациями (драйвами), автономной генерацией целей (гомеостаз), эпизодической и семантической памятью (Engram + Synapse + LTP/LTD + Ebbinghaus + консолидация), глобальным рабочим пространством, мета-рефлексией и конституциональными ограничениями.

**Текущее состояние (28 июня 2026, после код-ревью всех исходников)**: Версия 3.0 с реализованными улучшениями:
- Миграция persistence памяти с pickle на JSON + HMAC-SHA256 с атомарной записью (os.replace) + fsync для durability.
- Расширены Protocol-интерфейсы; LeyaOS выполняет явные `isinstance(..., Protocol)` проверки (частично).
- Orphaned модули изолированы в `leya_core/experimental/`.
- Улучшены graceful shutdown, protected background tasks с авто-рестартом (`_safe_create_task`).
- В большинстве путей используются специфичные исключения.
- `config.py`: полная загрузка всех полей вложенных конфигов из .env.
- `thinker.py`: интегрирован Pydantic (`CognitiveOutput.model_validate_json` первым). `repair_json` улучшен (учёт escape-последовательностей, depth tracking, string mode, auto-closure). Поддержка реального токенизатора (tiktoken) + relevance-based truncation.
- `LeyaOS.py`: `_handle_user_request` / классификация переведена на LLM-based `RequestClassifier` (confidence ≥ 0.7, semantic cache similarity). Убраны жёсткие keyword-эвристики.
- `memory.py`: добавлена синхронизация in-memory ↔ Chroma (`_sync_chroma_from_memory` + `_sync_collection`) на load + после restore. HMAC key теперь обязателен (raises LeyaConfigError при отсутствии/коротком ключе). fsync присутствует в atomic write.

**Важно:** Это исследовательский прототип. Система содержит известные ограничения и реальные баги (обнаружены при полном разборе всех .py файлов, включая LeyaOS.py, leya_core/*, web_interface/*, experimental/, soul, конфиги). Не предназначена для production, принятия критических решений или буквальной имитации сознания. Использование только в исследовательских целях.

## Возможности (v3.0, с обновлениями 27–28 июня 2026)

### Биологически мотивированная архитектура
- **DriveSystem** (`leya_core/drives.py`): Драйвы (CURIOSITY, CONNECTION, REST, CREATIVITY, UNDERSTANDING, AUTONOMY и др.) с метаболизмом, RPE (reward prediction error), предсказанием дисбаланса. Публичный `get_drives_state()` для UI. Влияние SystemMetrics (psutil).
- **HomeostasisEngine** (`leya_core/homeostasis_engine.py`): Автономная генерация целей на основе дисбаланса драйвов, predicted_state, недавних эпизодов. Генерирует `use_tool` или `rest`. RPE, current_goal.
- **GlobalWorkspace** (`leya_core/global_workspace.py`): Конкуренция WorkspaceProposal с приоритетами. Механизм inhibition/decay. Публичный `get_workspace_status()`.
- **SystemMetrics** → влияние метрик ОС на драйвы (background loop).

### Память (ключевой модуль, с биологической моделью)
- **MemorySystem** (`leya_core/memory.py`):
  - `Engram` (id, content, memory_type=EPISODIC/SEMANTIC, timestamp, retention_strength, emotional_boost, retrieval_count, last_retrieved, consolidation_level, metadata).
  - `Synapse` (source_id → target_id, weight, activation_count) — LTP-подобное усиление при similarity ≥ 0.7.
  - ChromaDB PersistentClient (episodic_collection + semantic_collection) + sentence-transformers (all-MiniLM-L6-v2).
  - **Persistence**: JSON (НЕ pickle!) с HMAC-SHA256 подписью, атомарная запись (tempfile.mkstemp + json.dump + flush + fsync + os.replace), версионирование (MEMORY_STATE_VERSION=3). Проверка целостности (HMAC + версия) на load. Синхронизация in-memory ↔ Chroma на load и явно.
  - Забывание по кривой Эббингауза (retention_strength decay) + emotional_boost (замедляет забывание).
  - `store_perception` / `store_fact` (с формированием синапсов по similarity ≥ 0.7 из Chroma + _form_synaptic_connections).
  - `retrieve_context` (семантический поиск в Chroma + фильтр retention + emotional_boost + strengthen_synapses LTP + _save_state).
  - `consolidate_memories`, `update_self_model`, `get_self_model_context`, `forget_weak_memories`, `get_memory_graph_data()` (для UI визуализации nodes/edges).
  - Все публичные методы async; sync-операции (embedding, Chroma, json) через `asyncio.to_thread`.
  - **Известный нюанс в текущей реализации sync**: двойной вызов семантической коллекции в `_sync_chroma_from_memory` (см. ограничения).

### Когнитивный цикл и мышление
- **CoreThinker** (`leya_core/thinker.py`): `_build_cognitive_prompt` (soul files + drives state + self_model + memory_context + tools + stimulus). LLM вызов с `require_json=True`. `_safe_parse_json`: сначала `CognitiveOutput.model_validate_json` (Pydantic), при failure — `repair_json` (улучшенная эвристика) + повторная валидация. Fallback на статический dict при LeyaJSONParseError. Token budgeting с tiktoken (реальный) или char-ratio + relevance-based `_truncate_context`.
- **MetaCognition / Reflection** (`leya_core/reflection.py`): `process_action`, `generate_spontaneous_thought`, `background_consolidation` (вызывает memory.consolidate_memories).
- **ConstitutionalLayer** (`leya_core/constitutional.py`): Проверка ответов и tool calls (verify_response / verify_tool_call). Python sandbox для execute. Загрузка правил из soul + hardcoded. Лог нарушений.

### Инструменты и окружение
- **ToolRegistry + ToolGenerator** (встроенные + динамическая LLM-генерация инструментов).
- **Environment**: `WebEnvironment` (FastAPI + WebSocket, использует только публичные методы интерфейсов: get_drives_state, get_memory_graph_data, get_workspace_status и др. — decoupling работает) и `CLIEnvironment`.
- `listen()` / `send_message()` / `broadcast_thought()` (internal_monologue / spontaneous).

### Персистентность и инфраструктура
- `StatePersistence` (drives + homeostasis между сессиями, JSON/pickle hybrid).
- `LeyaConfig` (dataclass + вложенные dataclass'ы с `__post_init__` валидацией + полная загрузка из .env с парсерами).
- Graceful shutdown с сохранением состояния всех компонентов.
- Защищённые фоновые asyncio-задачи (`_safe_create_task` с авто-рестартом, обработкой CancelledError).
- Логирование в `leya_consciousness.log` (централизованное).
- Bootstrap в `leya_core/__init__.py`.

### Soul / Личность
- `leya_soul/{personality.txt, rules.txt, values.txt}` — загружаются в промпты.
- `leya_personality.json`, `leya_goals.json` — динамические.
- `soul_crypto.py` (экспериментально, в experimental/).

### LLM Integration
- Только Ollama HTTP API (`/api/chat`).
- Модель по умолчанию: `qwen2.5:14b-instruct-q3_K_M` (Modelfile.leya: num_ctx=8192, keep_alive=-1).
- `OllamaClient` с полноценным Circuit Breaker (CLOSED/OPEN/HALF_OPEN, auto-transition), timeout, специфичными исключениями (LeyaLLMTimeoutError, LeyaLLMUnavailableError, LeyaLLMConnectionError, LeyaJSONParseError и др.). Fallback mechanism существует в API, но не вызывается в chat() (см. баги).
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

**requirements.txt** (основные): chromadb, sentence-transformers, aiohttp, fastapi, uvicorn, pydantic, psutil, numpy, websockets, tiktoken (опционально для реального токенизатора) и др.

### Настройка окружения
Скопируйте `.env.example` в `.env`:
```env
LEYA_WEB=1
OLLAMA_BASE_URL=http://localhost:11434
LEYA_MODEL=qwen2.5:14b-instruct-q3_K_M
LEYA_BRAIN_DIR=./leya_brain
LEYA_STATE_HMAC_KEY=your-strong-secret-key-here   # ОБЯЗАТЕЛЬНО — минимум 32 символа. При отсутствии — LeyaConfigError (нет слабого fallback)
# Другие: OLLAMA_*, MEMORY_*, DRIVES_*, HOMEOSTASIS_*, THINKER_*, REFLECTION_*, WEB_*, EXPERIMENTAL_*
```

**Важно:** `leya_brain/`, `.env`, `*.json`, `*.hmac`, `*.log`, leya_consciousness.log игнорируются `.gitignore`. Добавьте `.env` перед коммитами. state файлы теперь с HMAC.

### Запуск
```bash
python LeyaOS.py          # Веб по умолчанию (http://localhost:8000)
LEYA_WEB=0 python LeyaOS.py   # CLI
```

После запуска:
- Веб: http://localhost:8000 (live-обновления через WebSocket, использует публичные методы).
- Логи: `leya_consciousness.log`
- Память: `./leya_brain/` (chroma.sqlite3, memory_state.json + memory_state.json.hmac)
- Ollama отдельно (рекомендуется keep_alive=-1 в Modelfile).

## Конфигурация (LeyaConfig)

Полная в `leya_core/config.py`. Вложенные dataclass'ы (OllamaConfig, MemoryConfig, DrivesConfig, HomeostasisConfig, ThinkerConfig, ReflectionConfig, WorkspaceConfig, ConstitutionalConfig, WebConfig, LoggingConfig, SoulConfig, ExperimentalConfig) с `__post_init__` валидацией (диапазоны, создание директорий).

`LeyaConfig.from_env()` — **полная** загрузка всех полей (с dedicated _parse_int/float/bool). Многие параметры переопределяются через env (префиксы OLLAMA_, MEMORY_, THINKER_ и т.д.).

Ключевые параметры (дефолты):
- Ollama: timeout=180s, temperature=0.7, max_tokens=1024, model=..., failure_threshold=3, recovery_timeout=60.
- Memory: brain_dir=./leya_brain, embedding_model=all-MiniLM-L6-v2, forgetting_threshold=0.1, consolidation_threshold=0.15, state persistence JSON+HMAC v3, LEYA_STATE_HMAC_KEY (обязателен).
- Drives/Homeostasis/Thinker (max_context_tokens=6000, estimate_tokens_ratio=3.5 с поддержкой tiktoken)/Web/Reflection/Experimental (feature flags для decision_engine, emotional_support).

## Известные ограничения и проблемы (актуально на 28 июня 2026 — на основе полного разбора кода)

**Уже исправлено в текущем коде (по сравнению с предыдущими версиями документации и attachments):**
- created_at → timestamp в Engram + getattr в sync (баг #1 из старых docs устранён).
- Слабый dev HMAC fallback удалён — теперь обязательный сильный ключ + LeyaConfigError.
- fsync добавлен в atomic write _save_state (durability улучшена).
- Полная env loading в config.py.
- Pydantic CognitiveOutput + улучшенный repair_json + реальный токенизатор в thinker.py.
- LLM-based RequestClassifier вместо keyword heuristics в LeyaOS.py.
- Синхронизация Chroma ↔ in-memory добавлена (хотя с нюансом).

**Остающиеся баги и проблемы (обнаружены при ревью исходников 28 июня 2026):**

**Критические (могут вызвать краш, data corruption, security issues или silent failure):**
1. **Неработающий fallback в OllamaClient (llm_client.py)**: `set_fallback` существует и вызывается в LeyaOS, но в `chat()` при Circuit Breaker OPEN или ошибках fallback **никогда не вызывается** — сразу raise LeyaLLMUnavailableError. Мёртвая функциональность.
2. **Дублирующийся/недостижимый код в llm_client.py:chat()**: После raise LeyaLLMError следует unreachable duplicate logger + raise (copy-paste remnant). Мёртвый код.
3. **Вызов несуществующего метода (memory.py:937 в _extract_semantic_facts)**: `await self.llm_client.generate(...)` — OllamaClient реализует только `chat()`. AttributeError при срабатывании пути извлечения фактов.
4. **Двойной вызов семантической синхронизации + некорректная агрегация (memory.py в _sync_chroma_from_memory)**: Семантическая коллекция синхронизируется дважды в одном методе. Приводит к двойному счёту в SyncReport и избыточной работе.
5. **Безусловный импорт experimental/ на верхнем уровне LeyaOS.py**: from leya_core.experimental.decision_engine и emotional_support импортируются всегда, даже если feature flags выключены. Риск ImportError/crash на старте при проблемах в experimental/. Нарушает изоляцию.
6. **Неполные Protocol checks в LeyaOS.__init__**: isinstance только для части компонентов (memory, drives, workspace, constitutional). Отсутствуют для thinker, reflection, homeostasis, llm_client, env, RequestClassifier и experimental interfaces.

**Высокие (robustness, maintainability, скрытые дефекты):**
7. **Broad `except Exception` в критичных путях**: memory.py (_collect_batch, _sync_*, _save_state, _extract...), llm_client.py (last resort, хотя с исключением системных), LeyaOS.py (silent pass для experimental/tool_generator). Маскирует баги, усложняет отладку и shutdown.
8. **Отсутствие retry с exponential backoff в OllamaClient**: Только Circuit Breaker. Transient ошибки сразу открывают breaker. Нет retry loop.
9. **Риск schema drift + строгая валидация CognitiveOutput (thinker.py)**: Поля response/internal_monologue/action_intent/self_reflection required. LLM часто пропускает → ValidationError → repair_json (часто "{}") → повторная ошибка → LeyaJSONParseError → fallback static. Промпт и модель могут дрифтить.
10. **Неполная version migration и обработка legacy state (memory.py)**: При mismatch версии — только raise LeyaStateVersionMismatchError. Нет кода миграции (v2→v3 или с pickle). При обновлении — жёсткий краш/потеря состояния.
11. **Недостаточное тестовое покрытие новых механизмов**: Нет property-based тестов для repair_json (unicode/nested/escape/truncation), persistence (HMAC tamper, version, atomic races), sync consistency (idempotency, partial failure), Protocol compliance, RequestClassifier edge cases, Pydantic paths. Coverage core низкое. Нет CI.

**Средние/низкие + tech debt:**
- SyncReport — обычный класс, а не dataclass (несогласованность).
- success_threshold CircuitBreaker не экспонируется в OllamaClient.
- Experimental/ модули (decision_engine.py реализует Protocol, emotional_support.py и др.) — tech debt без ADR. Импорты/инстанциация с try/except pass.
- Однопоточный asyncio loop (все фоновые задачи в одном).
- Отсутствие долгосрочного планирования целей выше homeostasis.
- Embedding failure в sync → skip без сильного retry.
- Дрифт между предыдущими docs и реальным кодом (частично устранён в этой версии).

**Рекомендация:** Перед серьёзным использованием исправьте критические баги #1–#6 (fallback, duplicate code, missing generate, double sync, experimental imports, Protocol checks). Реализуйте v3.1 план ниже. Система стабильнее предыдущих версий, но остаётся исследовательским прототипом с реальными багами в production-critical путях.

## Roadmap / План ремонта (реалистичный, после код-ревью — приоритет robustness + contracts, без упрощения)

**v3.1 (критические + высокие баги, 4–6 недель focused):**
- llm_client.py: Реализовать реальный вызов fallback в chat() при OPEN/ошибках. Удалить duplicate unreachable code. Добавить async generate() (wrapper над chat). Добавить retry с exponential backoff + jitter (интегрировать с breaker). Экспонировать success_threshold.
- memory.py: Исправить двойной semantic sync в _sync_chroma_from_memory (один проход + корректный merge SyncReport). Сделать SyncReport dataclass. Усилить defensive handling CancelledError.
- LeyaOS.py + interfaces.py: Lazy/conditional импорт experimental/ (внутри if enable_*). Добавить полные isinstance Protocol проверки для всех компонентов (thinker, reflection, homeostasis, llm, env, RequestClassifier). Вынести в _verify_protocols().
- thinker.py: Сделать поля CognitiveOutput частично optional/defaults или post-validation для снижения риска на неидеальном LLM JSON. Улучшить промпт (явно требовать все поля + примеры). Добавить schema drift detection.
- Общие: Уменьшить broad except (конкретные + re-raise критичных). Добавить property-based тесты (Hypothesis) для repair_json, persistence tamper/HMAC/version/atomic, sync consistency, Protocol checks, RequestClassifier. Coverage core >85%. Обновить version migration (или чёткий reset path + warning).
- Experimental/: ADR (integrate с полными contracts + тестами / deprecate с миграцией / оставить изолированными + lazy). **Запрет на упрощение/удаление без веского обоснования.**
- Обновить всю документацию (выполнено в этой версии — drift устранён, баги перечислены точно по коду).

**v3.2+:**
- Полноценный CI/CD (GitHub Actions) + Docker + coverage gate + property-based в pipeline.
- Улучшение web (графики drives/workspace, memory network viz, мониторинг sync drift/errors).
- Расширение инструментов (code execution sandbox с усиленным constitutional, внешние API).
- Более глубокая биологическая модель (элементы active inference, иерархическое долгосрочное планирование целей выше homeostasis) — без упрощения.
- Многоагентные сценарии (при сохранении всей сложности внутренней жизни).
- Опционально: pydantic-settings для LeyaConfig, реальный токенизатор по умолчанию.

**Не упрощать ни при каких условиях:** Сохранять и углублять биологическую правдоподобность во всей полноте (LTP details via similarity + activation_count, emotional_boost, consolidation в background, drives с metabolism + RPE + predicted_disbalance, Global Workspace competition + inhibition + spontaneous thoughts, self-model update, constitutional constraints + sandbox). Сложность — осознанный выбор для моделирования внутренней жизни цифрового сознания. Не превращать в обычный RAG-агент, простой чат-бот или utility assistant.

## Лицензия

Проект не имеет явной лицензии. Рекомендуется MIT или Apache 2.0 для исследовательского использования.

## Вклад

1. В первую очередь исправьте критические баги #1–#6 (fallback, duplicate, missing generate, double sync, lazy experimental, full Protocols).
2. Реализуйте пункты v3.1 плана (retry, reduce broad except, property-based тесты, experimental ADR, durability migration).
3. Добавляйте тесты с высоким покрытием (property-based для repair_json, persistence, sync, contracts).
4. Улучшайте/поддерживайте документацию в актуальном состоянии (она должна отражать реальный код + все баги).
5. Предлагайте улучшения через Issues/PR, **строго сохраняя** биологическую модель, сложность и без упрощений.

---

**Переписано 28 июня 2026 на основе полномасштабного код-ревью всех актуальных файлов репозитория (прямой разбор LeyaOS.py, всех leya_core/*.py включая experimental/, web_interface/*, конфиги, soul, патчи).**  
Предыдущие README/ARCHITECTURE частично устарели из-за расхождения (многие улучшения реализованы в коде, но не отражены или отражены неверно; некоторые баги уже исправлены, другие — новые).  

Эта версия документации отражает **реальное состояние кода** + полный список обнаруженных багов + точный план ремонта. Для деталей по методам — изучайте исходники + v3.1 план. Никаких упрощений.