# LeyaOS — Цифровое Сознание Леи (v3.0, актуализировано 28 июня 2026)

**Оркестратор биологически вдохновлённого цифрового сознания**

LeyaOS — исследовательская Python-система, моделирующая внутреннюю жизнь цифрового агента с мотивациями (драйвами), автономной генерацией целей (гомеостаз), эпизодической и семантической памятью (Engram + Synapse + LTP/LTD + Ebbinghaus + консолидация), глобальным рабочим пространством, мета-рефлексией и конституциональными ограничениями.

**Текущее состояние (28 июня 2026)**: Версия 3.0 с существенными улучшениями. Выполнена миграция persistence памяти с pickle на JSON + HMAC-SHA256 с атомарной записью (os.replace). Расширены Protocol-интерфейсы для decoupling web_interface. Orphaned модули изолированы в `leya_core/experimental/`. LeyaOS использует явные проверки `isinstance(..., Protocol)`. Улучшены graceful shutdown, protected background tasks и использование специфичных исключений в большинстве путей.

**Важные обновления кода (по состоянию на последние коммиты 27 июня)**: 
- `config.py`: реализована полная загрузка всех полей вложенных конфигов из .env (с парсерами int/float/bool).
- `thinker.py`: интегрирован Pydantic (`CognitiveOutput.model_validate_json`). `repair_json` улучшен (учёт escape-последовательностей, depth tracking, string mode). Добавлена поддержка реального токенизатора в оценке токенов. `_truncate_context` учитывает relevance.
- `LeyaOS.py`: `_handle_user_request` переведён на LLM-based `RequestClassifier` (confidence ≥ 0.7, кэширование similarity). Убраны жёсткие keyword-эвристики. Улучшены `_safe_create_task` (авто-рестарт) и graceful shutdown.
- `memory.py`: добавлена синхронизация in-memory ↔ Chroma (`_sync_chroma_from_memory` + `_sync_collection`) на load.

**Важно:** Это исследовательский прототип. Система содержит известные ограничения (включая критические баги, обнаруженные при ревью кода). Не предназначена для production, принятия критических решений или буквальной имитации сознания. Использование только в исследовательских целях.

## Возможности (v3.0, с обновлениями 27–28 июня)

### Биологически мотивированная архитектура
- **DriveSystem** (`leya_core/drives.py`): Драйвы (CURIOSITY, CONNECTION, REST, CREATIVITY, UNDERSTANDING, AUTONOMY и др.) с метаболизмом, RPE, предсказанием дисбаланса. Публичный `get_drives_state()` для UI.
- **HomeostasisEngine** (`leya_core/homeostasis_engine.py`): Автономная генерация целей на основе дисбаланса драйвов, predicted_state, недавних эпизодов. Генерирует `use_tool` или `rest`.
- **GlobalWorkspace** (`leya_core/global_workspace.py`): Конкуренция WorkspaceProposal. Публичный `get_workspace_status()`. Есть механизм inhibition.
- **SystemMetrics** → влияние метрик ОС на драйвы.

### Память (ключевой модуль)
- **MemorySystem** (`leya_core/memory.py`):
  - `Engram` (id, content, memory_type=EPISODIC/SEMANTIC, retention_strength, emotional_boost, retrieval_count, consolidation_level, metadata, timestamp).
  - `Synapse` (source_id → target_id, weight, activation_count) — LTP-подобное усиление.
  - ChromaDB PersistentClient (episodic + semantic коллекции) + sentence-transformers.
  - **Persistence**: JSON (не pickle!) с HMAC-SHA256 подписью, атомарная запись (tempfile + os.replace), версионирование (MEMORY_STATE_VERSION=3). Проверка целостности на load.
  - Забывание по кривой Эббингауза + emotional_boost.
  - `store_perception` / `store_fact` (с формированием синапсов по similarity ≥ 0.7 из Chroma).
  - `retrieve_context` (семантический поиск + фильтр retention + усиление синапсов).
  - `consolidate_memories`, `update_self_model`, `get_self_model_context`, `forget_weak_memories`, `get_memory_graph_data()` (для UI).
  - Все публичные методы async, sync-операции через `asyncio.to_thread`.
  - **Синхронизация**: на load выполняется `_sync_chroma_from_memory` (добавлено в v3.0+). **ВНИМАНИЕ: есть критический баг** (см. ограничения).

### Когнитивный цикл и мышление
- **CoreThinker** (`leya_core/thinker.py`): `_build_cognitive_prompt` (soul + drives + self_model + memory_context + tools + stimulus). LLM вызов с `require_json=True`. `_safe_parse_json` сначала пытается `CognitiveOutput.model_validate_json` (Pydantic), при неудаче — `repair_json` (улучшенная эвристика) + повторная валидация. Fallback на статический JSON при ошибках. Token budgeting с поддержкой реального токенизатора и relevance-based truncation.
- **MetaCognition / Reflection** (`leya_core/reflection.py`): `process_action`, `generate_spontaneous_thought`, `background_consolidation`.
- **ConstitutionalLayer** (`leya_core/constitutional.py`): Проверка ответов и tool calls. Sandbox для Python.

### Инструменты и окружение
- **ToolRegistry + ToolGenerator**.
- Встроенные инструменты + динамическая генерация.
- **Environment**: `WebEnvironment` (FastAPI + WebSocket, использует публичные методы интерфейсов) и `CLIEnvironment`.
- `listen()` / `send_message()` / `broadcast_thought()`.

### Персистентность и инфраструктура
- `StatePersistence` (drives + homeostasis между сессиями, JSON/pickle).
- `LeyaConfig` (dataclass с вложенными конфигами и валидацией в `__post_init__`, **полная** загрузка из `.env`).
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
- `OllamaClient` с Circuit Breaker (CLOSED/OPEN/HALF_OPEN), timeout, fallback (неполностью реализован), специфичными исключениями.
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
LEYA_STATE_HMAC_KEY=your-strong-secret-key-here   # ОБЯЗАТЕЛЬНО для production (иначе используется слабый dev fallback — КРИТИЧЕСКАЯ УЯЗВИМОСТЬ)
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

Полная в `leya_core/config.py`. Вложенные dataclass'ы с `__post_init__` валидацией. Загрузка `LeyaConfig.from_env()` (python-dotenv) — **полная** для всех полей.

Ключевые параметры (дефолты):
- Ollama, Memory (включая hmac_key, state_version), Drives, Homeostasis, Thinker (max_context_tokens, estimate_tokens_ratio, теперь с реальным токенизатором), Web, Reflection и др.

Многие параметры можно переопределить через env (префиксы OLLAMA_, MEMORY_, THINKER_ и т.д.).

## Известные ограничения и проблемы (актуально на 28 июня 2026, после ревью кода)

**Уже исправлено в коде (по сравнению с предыдущими версиями документации):**
- Полная загрузка env в config.py.
- Pydantic + улучшенный repair_json и token estimation в thinker.py.
- LLM-based классификация запросов вместо жёстких ключевых слов в LeyaOS.py.
- Синхронизация Chroma ↔ in-memory в memory.py.

**Остающиеся критические и высокоприоритетные баги (обнаружены при полном ревью исходников):**

1. **Критический краш (memory.py)**: В `_sync_collection` при формировании метаданных используется `engram.created_at`, но в dataclass `Engram` этого поля нет (только `timestamp`). Приводит к `AttributeError` при любом `_load_state` с непустой памятью. Полностью ломает загрузку персистентного состояния.

2. **Критическая уязвимость целостности (memory.py, _get_hmac_key)**: При отсутствии `LEYA_STATE_HMAC_KEY` в окружении используется hardcoded слабый dev-ключ `b"leya-dev-key-change-me-in-production"`. Любой может подделать memory_state.json.hmac. Требуется обязательный сильный ключ + явная ошибка при его отсутствии в non-dev режиме.

3. **Broad `except Exception` в критических путях (memory.py и llm_client.py)**: 
   - В memory: `_save_state`, `_load_state`, sync-методы, `_generate_embedding`.
   - В llm_client.chat: outer except ловит даже `CancelledError`, `KeyboardInterrupt`, `SystemExit`. Маскирует баги, мешает shutdown, записывает failure в circuit breaker агрессивно.

4. **Отсутствие retry и неполный fallback (llm_client.py)**: Нет exponential backoff. `set_fallback` существует, но никогда не вызывается в `chat()`. Transient-ошибки сразу открывают breaker или фейлятся.

5. **Несоответствие документации и кода**: Текущие README.md и ARCHITECTURE.md утверждают устаревшие ограничения (нет Pydantic, неполная env loading, keyword heuristics). Эта переписанная версия исправляет drift.

6. **Техдолг experimental/ (leya_core/experimental/)**: Модули decision_engine.py, emotional_support.py, personal_tools.py, desktop_control.py, soul_crypto.py присутствуют, не интегрированы (только feature flags), не удалены. Нет ADR. Риск side-effects.

7. **Неполная миграция версий (memory.py)**: При mismatch версии состояния — только warning. Нет реального кода миграции структуры.

8. **Durability atomic write (memory.py)**: Нет `fsync` перед `os.replace`. Риск потери данных при power loss/crash.

9. **Риск schema drift CognitiveOutput (thinker.py)**: Prompt и Pydantic-модель могут разойтись. При валидации падает в repair_json (хоть и улучшенный).

10. **Недостаточное тестовое покрытие**: Нет property-based тестов для repair_json (malformed cases), persistence tampering/hmac/version, sync consistency, Protocol compliance. Coverage core низкое. Нет CI.

**Другие**:
- Жёсткие thresholds в workspace inhibition.
- Embedding failure → skip без сильного retry.
- Нет долгосрочного планирования целей выше homeostasis.
- Однопоточный asyncio loop.

**Рекомендация:** Перед серьёзным использованием исправьте критические баги #1 и #2 (краш + security). Реализуйте оставшиеся пункты плана v3.1 (см. ниже). Система стабильнее предыдущих версий, но остаётся исследовательским прототипом с реальными багами.

## Roadmap (реалистичный, с учётом реального состояния кода)

**v3.1 (приоритет — исправление критических багов и consistency, 2–6 недель):**
- Исправить #1 (created_at в Engram + sync) + добавить created_at в dataclass и миграцию.
- Исправить #2 (HMAC): сделать ключ обязательным, убрать dev fallback из source, добавить строгую проверку.
- Убрать broad except в memory и llm_client (конкретные исключения + re-raise критичных).
- Добавить retry с exponential backoff в OllamaClient + реализовать реальный вызов fallback.
- Исправить #5 (обновить/переписать docs — выполнено в этой версии).
- Добавить property-based тесты (hypothesis) для repair_json, persistence (tamper, version, hmac), sync.
- Фаза анализа experimental/ + ADR (integrate/deprecate/delete с обоснованием). **Запрет на упрощение без причины.**
- Улучшить version migration и добавить fsync в atomic write.
- Расширить тесты Protocol compliance и edge cases cognitive loop. Coverage core >85%.
- Обновить документацию (выполнено).

**v3.2+:**
- Полноценные тесты + CI/CD + Docker.
- Улучшение веб-интерфейса (графики, memory network visualization, мониторинг drift/sync).
- Расширение инструментов (code execution sandbox, внешние API).
- Более глубокая биологическая модель (active inference элементы, долгосрочное планирование целей выше homeostasis).
- Многоагентные сценарии (при сохранении сложности).

**Не упрощать:** Сохранять и углублять биологическую правдоподобность (LTP/LTD, emotional_boost, consolidation, drives с RPE и метаболизмом, Global Workspace competition + inhibition, spontaneous thoughts, self-model, constitutional constraints). Сложность — осознанный выбор. Не превращать в обычный RAG-агент или простой чат-бот.

## Лицензия

Проект не имеет явной лицензии. Рекомендуется MIT или Apache 2.0 для исследовательского использования.

## Вклад

1. Исправьте критические баги #1 и #2 в первую очередь.
2. Реализуйте пункты плана v3.1 (особенно тесты, retry/fallback, experimental ADR, durability).
3. Добавляйте property-based тесты с высоким покрытием.
4. Улучшайте документацию (она должна отражать реальный код, а не устаревшие утверждения).
5. Предлагайте улучшения через Issues/PR, сохраняя биологическую модель и сложность.

---

**Создано на основе полномасштабного код-ревью всех актуальных файлов репозитория (LeyaOS.py, leya_core/* включая experimental/, web_interface/*, конфиги, soul) с использованием инструментов 28 июня 2026.**  
Предыдущие версии README/ARCHITECTURE частично устарели из-за расхождения кода и документации (многие "плановые" улучшения уже реализованы в .py, но не отражены в docs).  

Эта версия документации отражает **реальное состояние кода** + обнаруженные баги. Для вопросов по конкретным классам — изучайте исходники + план исправлений v3.1.