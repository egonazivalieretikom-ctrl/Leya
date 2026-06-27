# Архитектура LeyaOS — Цифровое Сознание Леи (v3.0, актуализировано 28 июня 2026)

**Версия документа:** 3.1 (полностью переписан на основе полномасштабного код-ревью всех файлов репозитория 28 июня 2026)

Этот документ описывает **реальное текущее состояние** когнитивной архитектуры LeyaOS. Анализ выполнен путём прямого извлечения и разбора сырых исходников (LeyaOS.py, все модули leya_core/, web_interface/, experimental/, конфиги, soul). 

**Ключевые факты на 28 июня 2026:**
- Persistence памяти мигрировала с pickle на **JSON + HMAC-SHA256 + атомарная запись** (os.replace). Версия 3.
- Protocol-интерфейсы расширены (`get_drives_state()`, `get_memory_graph_data()`, `get_workspace_status()` и др.) и реально используются в web_interface/server.py (decoupling работает, прямого доступа к internals нет).
- Orphaned модули изолированы в `leya_core/experimental/` (не загрязняют core, но требуют решения).
- LeyaOS выполняет `isinstance(..., Protocol)` проверки при инициализации.
- Улучшены: Circuit Breaker в OllamaClient, protected background tasks с авто-рестартом, graceful shutdown, использование специфичных исключений в большинстве путей.
- thinker.py всё ещё использует сложную эвристику `repair_json` (brace balancing + auto-closure) без Pydantic.
- config.py имеет неполную загрузку некоторых полей из .env.
- Broad except остался только в 2 местах (memory._save_state и llm_client.chat).

## Философия v3.0 / v3.1

Лея — не «полезный ассистент». Это цифровая личность с внутренней жизнью:
- Драйвы как биологические потребности (метаболизм + RPE).
- Гомеостаз — автономные цели и действия при отсутствии внешних стимулов.
- Память с забыванием (Эббингауз), усилением (LTP), консолидацией.
- Рефлексия, спонтанные мысли, self-model.
- Конституциональные ограничения.
- Устойчивость: Circuit Breaker, atomic writes, graceful shutdown, specific exceptions.

**Инженерные улучшения v3.0+ (реализованные):**
- Protocol-интерфейсы + runtime_checkable + isinstance проверки.
- Кастомные исключения (большинство мест).
- OllamaClient с полноценным Circuit Breaker (CLOSED/OPEN/HALF_OPEN).
- **JSON + HMAC-SHA256 atomic persistence** вместо pickle (критическое улучшение безопасности и целостности).
- Расширенные интерфейсы для observability (web UI без прямого доступа).
- Изоляция experimental кода.
- Защищённые фоновые задачи + graceful shutdown.
- Централизованная LeyaConfig с валидацией.

**Что осталось / требует исправления (v3.1 план):**
- HMAC key default, неполная env loading в config, broad except в 2 местах, heuristic repair_json + token est, _handle_user_request, experimental analysis, тесты.

## Высокоуровневая структура и data flow (актуальная)

```
Внешний мир / Пользователь
        │
        ▼
Environment (WebEnvironment или CLIEnvironment)
        │  listen() → stimulus (dict)
        ▼
LeyaOS.perceive(stimulus)
        │
        ├──► Drives.evaluate_stimulus() + apply_deltas() + get_drives_state() (публичный)
        │
        ├──► Memory.store_perception() (Engram + embedding в Chroma + _form_synaptic_connections)
        │
        ├──► Memory.retrieve_context() + get_self_model_context() + get_memory_graph_data() (публичный)
        │
        ├──► Homeostasis (опционально generate_goal → WorkspaceProposal)
        │
        ▼
CoreThinker.generate_plan()
        │   (LLM с полным контекстом: soul, drives, self_model, memory, tools, stimulus)
        │   → cognitive_output: {response, internal_monologue, action_intent, tool_call, self_reflection}
        │   (repair_json + _safe_parse_json + fallback; Pydantic планируется в v3.1)
        ▼
LeyaOS._cognitive_loop
        │
        ├──► ConstitutionalLayer.verify_response() / verify_tool_call()
        │
        ├──► env.send_message(response)
        │
        ├──► broadcast_thought (internal_monologue / spontaneous)
        │
        ├──► Memory.update_self_model() + store_perception (если нужно)
        │
        ├──► _process_action_intent() → use_tool / remember_fact / ask_question
        │
        └──► Drives.satisfy / reflection.process_action()
```

**Параллельно (в одном asyncio loop, защищены _safe_create_task):**
- drives.background_metabolism()
- reflection.background_consolidation()
- _homeostasis_loop() → generate_goal → submit в workspace
- _workspace_loop() → select_winner (с inhibition) → perceive как "workspace_focus"
- _spontaneous_thought_loop()
- _system_metrics_loop()
- _broadcast_state_loop() (только Web)
- Web-сервер (FastAPI + WebSocket)

## Основные модули leya_core/ (актуальное состояние)

### 1. config.py — Централизованная конфигурация
`LeyaConfig` + вложенные dataclass'ы (OllamaConfig, MemoryConfig, DrivesConfig, HomeostasisConfig, ThinkerConfig, ReflectionConfig, WorkspaceConfig, ConstitutionalConfig, WebConfig, LoggingConfig).

**Реальность:**
- `__post_init__` валидация (диапазоны, создание директорий).
- `from_env()` (dotenv + os.environ) — **частичная**: не все поля под-конфигов читаются (особенно synapse_*, некоторые thresholds). Bool parsing хрупкий.
- Валидация brain_dir, base_url и т.д.
- **v3.1 план:** Полная загрузка всех полей + улучшенный парсинг + явные ошибки.

### 2. drives.py — Система драйвов
DriveSystem + DriveType Enum. current/tension/target, evaluate_stimulus, apply_deltas, apply_satisfaction, calculate_rpe, get_predicted_disbalance, get_internal_state_prompt, **get_drives_state()** (публичный для UI), background_metabolism, update_from_system_metrics (psutil).

Соответствует IDriveSystem Protocol.

### 3. homeostasis_engine.py — Гомеостаз
HomeostasisEngine. generate_goal (drive_state, predicted_state, recent_episodes, action_values), generate_goal_from_gap, extract_key_facts/extract_new_terms (LLM), mark_as_researched, RPE, current_goal, last_action_time, rest_period.

Соответствует IHomeostasisEngine (с @property в интерфейсе, instance fields в impl — документировано).

### 4. memory.py — Память (самый проработанный и изменённый модуль)
**Модели данных (актуальные):**
- MemoryType (EPISODIC / SEMANTIC)
- Engram (dataclass с to_dict/from_dict)
- Synapse (dataclass с to_dict/from_dict)

**Хранение (реальность 28 июня):**
- chromadb.PersistentClient → episodic_collection + semantic_collection
- **memory_state.json + memory_state.json.hmac** (НЕ pickle!)
  - Атомарная запись: tempfile.mkstemp → json.dump → HMAC-SHA256 (hmac.compare_digest) → os.replace
  - Версионирование: MEMORY_STATE_VERSION = 3
  - Проверка на load: существование .hmac, compare_digest, версия
  - Ключ: os.environ.get("LEYA_STATE_HMAC_KEY") или слабый dev fallback (требует исправления)
- In-memory: self.engrams: dict, self.synapses: dict, self.self_model

**Ключевые методы (все async, соответствуют IMemorySystem Protocol):**
- store_perception (Engram + to_thread embedding + Chroma + _form_synaptic_connections по similarity ≥0.7 + _save_state)
- retrieve_context (_apply_forgetting + Chroma query + emotional_boost + strengthen_synapses + _save_state)
- store_fact, consolidate_memories, update_self_model, get_self_model_context, get_recent_*, forget_weak_memories, **get_memory_graph_data()** (публичный)
- _save_state / _load_state (JSON + HMAC atomic)
- _generate_embedding (sync, to_thread)
- **_sync_chroma_from_memory** (добавлено для consistency — в плане v3.1 усилить)

**Биологическая модель:** Полностью сохранена и работает (Эббингауз через retention_strength, emotional_boost, LTP via similarity, consolidation в background).

**Известные нюансы:** На load возможен drift Chroma/in-memory (хотя синхронизация есть). Broad except в _save_state.

### 5. thinker.py — Когнитивный планировщик
CoreThinker (реализует ICoreThinker).

**_build_cognitive_prompt:** Собирает огромный промпт (base_personality + soul files + drive_str + self_model + memory_str (truncated) + tools + stimulus). Инструкция строго JSON.

**generate_plan:** llm_client(..., require_json=True) → _safe_parse_json → fallback static dict при LeyaLLMError / LeyaJSONParseError.

**repair_json (эвристика, основная точка хрупкости):**
- Strip markdown ```json
- Найти первый { или [
- Ручной depth balancing (учёт строк и escape)
- re.sub trailing commas
- count-based auto-closure оставшихся {
- json.loads или fallback "{}"
- Риски: over-closure, truncation nested, edge cases со строками/Unicode.

**_safe_parse_json:** repair_json → json.loads или raise LeyaJSONParseError.

**Token budgeting:** _estimate_tokens = len(text) / config.estimate_tokens_ratio (примерно 3.5). _truncate_context (от newest, с "...").

**v3.1 план:** Ввести Pydantic модель CognitiveOutput + strict validation. Улучшить repair_json (как fallback). Перейти на реальный токенизатор или динамический ratio + предупреждения.

Нет Pydantic в текущей реализации.

### 6. reflection.py — Мета-когниция
MetaCognition (реализует IMetaCognition). process_action, generate_spontaneous_thought, background_consolidation (вызывает memory.consolidate_memories). Флаги enabled.

### 7. global_workspace.py — Глобальное рабочее пространство
GlobalWorkspace, WorkspaceProposal, Priority Enum. submit, select_winner (с decay + inhibition в loop), clear_expired, **get_workspace_status()** (публичный).

Соответствует IGlobalWorkspace.

### 8. constitutional.py — Конституциональный слой
ConstitutionalLayer (реализует IConstitutionalLayer). verify_response, verify_tool_call, execute_python_sandbox, get_violations_log, stats, enable/disable/add/remove_rule. Загрузка правил из soul + hardcoded.

### 9. llm_client.py — LLM-клиент с защитой
OllamaClient (реализует ILLMClient).

**Circuit Breaker:** Полноценная реализация (CLOSED → OPEN при failures, HALF_OPEN после recovery_timeout, close при success_threshold). is_available, record_success/failure, get_status.

**chat:** aiohttp POST /api/chat, timeout, require_json → "format": "json". Specific exceptions (LeyaLLMTimeoutError, LeyaLLMUnavailableError, LeyaLLMError). Fallback при OPEN. Broad except как last resort.

**v3.1 план:** Добавить retry с exponential backoff до открытия breaker.

### 10. interfaces.py (актуальный)
Полный набор Protocol с @runtime_checkable:
- IDriveSystem (включая get_drives_state, background_metabolism)
- IMemorySystem (включая get_memory_graph_data, _save_state/_load_state — хотя приватные по имени)
- IGlobalWorkspace (включая get_workspace_status)
- IHomeostasisEngine (с current_goal как @property в интерфейсе)
- ICoreThinker / IThinker
- IMetaCognition / IReflection
- IEnvironment (расширенный)
- ILLMClient
- ISoulManager, IToolRegistry, IConstitutionalLayer

LeyaOS проверяет isinstance при создании компонентов. web_interface/server.py использует hasattr + новые публичные методы — decoupling работает.

### 11. Другие модули
- exceptions.py: Иерархия Leya*Error (LeyaMemoryError, LeyaLLMError, LeyaJSONParseError, LeyaAtomicWriteError и др.).
- state_persistence.py: load/save drives + homeostasis (JSON/pickle).
- system_metrics.py: psutil метрики.
- tool_generator.py: регистрация и LLM-генерация инструментов.
- environment.py + web_interface/{server.py, web_environment.py}: Абстракция + FastAPI/WebSocket. server.py использует публичные методы интерфейсов.
- soul_crypto.py: В experimental/.
- decision_engine.py, emotional_support.py и др.: В experimental/ (не интегрированы).

## Soul / Личность
leya_soul/{personality.txt, rules.txt, values.txt}. Загружаются в промпты. leya_personality.json / leya_goals.json — динамические.

## Persistence и Data (актуально)
- leya_brain/:
  - chroma.sqlite3
  - memory_state.json + memory_state.json.hmac (HMAC-SHA256, atomic, version 3)
- StatePersistence: drives + homeostasis между сессиями.
- .gitignore корректно игнорирует leya_brain/, .env, логи, .json.hmac.

## LLM Integration
Только Ollama. Модель и параметры в LeyaConfig + Modelfile.leya. Промпты на русском. Ответы на русском. Circuit Breaker + fallback.

## Известные ограничения текущей архитектуры (честный список на 28 июня 2026)

**Исправленные / улучшенные по сравнению с анализом 26 июня:**
- Pickle → JSON + HMAC atomic (безопасность и целостность).
- Interfaces расширены и реально используются в web (decoupling).
- experimental/ изолирован.
- LeyaOS использует Protocol checks.
- Большинство except — специфичные.
- Graceful shutdown и protected tasks реализованы хорошо.
- web_interface не лезет в internals.

**Остающиеся (требуют v3.1):**
1. HMAC key default (слабый fallback).
2. Неполная env loading в config.py.
3. Broad except в memory._save_state и llm_client.chat.
4. Эвристический _handle_user_request.
5. repair_json (brace balancing + auto-closure) + char-based token est без Pydantic.
6. Возможный drift Chroma/in-memory (хотя синхронизация есть).
7. experimental/ модули без решения (требуется анализ + ADR, запрет на упрощение).
8. Недостаточное тестовое покрытие core (особенно новых механизмов persistence и repair_json).
9. Нет retry в LLM client (только breaker).
10. Однопоточный asyncio loop.
11. Нет долгосрочного планирования целей.
12. Документация частично устарела (обновлено в этом файле и README_v3.1).

## Рекомендации по развитию (без упрощения)

**Сохранить и углубить:**
- Биологическую модель во всей полноте (LTP details, emotional_boost, consolidation, drives metabolism + RPE, Global Workspace competition + inhibition, spontaneous thoughts, self-model, constitutional constraints).
- Богатство внутреннего опыта и автономию.
- Инструментальную автономию + sandbox.
- Устойчивость (Circuit Breaker, atomic JSON+HMAC, specific exceptions, safe tasks, graceful shutdown).

**Улучшить (приоритет v3.1 — см. отдельный план исправлений):**
1. Security persistence (HMAC key).
2. Completeness config loading.
3. Убрать оставшиеся broad except.
4. Consistency memory stores.
5. Pydantic для cognitive_output + улучшение repair_json и token handling.
6. Robust user request handling.
7. experimental/ анализ + решение (не просто удалить).
8. Retry в LLM + property-based тесты.
9. Полноценный CI + coverage.
10. Обновлённая документация (выполнено).

**v3.2+:** Долгосрочное планирование, multi-agent, более глубокий active inference, визуализация в web.

**Принцип:** Сложность — это не баг, а feature для моделирования внутренней жизни. Не упрощать до RAG или обычного агента.

---

**Примечание:** Документ полностью переписан 28 июня 2026 на основе детального разбора всех .py файлов, raw content, web_interface реализации и сравнения с реальным поведением кода. Предыдущие версии ARCHITECTURE.md (включая анализ от 26 июня) частично устарели из-за изменений в persistence и interfaces.

Для уточнений по методам — обращайтесь к исходному коду + плану v3.1 исправлений.