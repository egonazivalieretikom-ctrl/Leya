# Архитектура LeyaOS — Цифровое Сознание Леи (v3.0, актуализировано 28 июня 2026)

**Версия документа:** 3.1 (полностью переписан на основе полномасштабного код-ревью всех файлов репозитория 28 июня 2026 с использованием прямого анализа исходников)

Этот документ описывает **реальное текущее состояние** когнитивной архитектуры LeyaOS. Анализ выполнен путём прямого извлечения и разбора сырых исходников (LeyaOS.py, все модули leya_core/ включая experimental/, web_interface/, конфиги, soul, патчи).

**Ключевые факты на 28 июня 2026 (по состоянию кода):**
- Persistence памяти мигрировала с pickle на **JSON + HMAC-SHA256 + атомарная запись** (os.replace). Версия 3.
- Protocol-интерфейсы расширены (`get_drives_state()`, `get_memory_graph_data()`, `get_workspace_status()` и др.) и реально используются в web_interface/server.py (decoupling работает, прямого доступа к internals нет).
- Orphaned модули изолированы в `leya_core/experimental/` (не загрязняют core, но требуют решения + ADR).
- LeyaOS выполняет `isinstance(..., Protocol)` проверки при инициализации.
- Улучшены: Circuit Breaker в OllamaClient, protected background tasks с авто-рестартом, graceful shutdown.
- **Реальные улучшения в коде (уже реализованы, в отличие от устаревших утверждений в предыдущих docs):**
  - `config.py`: **полная** загрузка всех полей подконфигов из .env (с _parse_int, _parse_float, _parse_bool).
  - `thinker.py`: интегрирован Pydantic (`CognitiveOutput.model_validate_json` в `_safe_parse_json`). `repair_json` улучшен (учёт escape, depth, string mode). Поддержка реального токенизатора в `_estimate_tokens`. Relevance-based truncation.
  - `LeyaOS.py`: `_handle_user_request` использует LLM `RequestClassifier` (confidence threshold, similarity cache). Убраны жёсткие keyword heuristics.
  - `memory.py`: добавлена `_sync_chroma_from_memory` + `_sync_collection` для consistency in-memory ↔ Chroma на load.
- **Остающиеся проблемы (обнаружены при ревью):** критический AttributeError в sync (created_at), слабый HMAC dev fallback, broad except в memory и llm_client (в т.ч. CancelledError), отсутствие retry + неработающий fallback в llm, неполная version migration, отсутствие fsync в atomic write, tech debt experimental, низкое покрытие тестами новых механизмов, drift между предыдущими docs и кодом.

## Философия v3.0 / v3.1

Лея — не «полезный ассистент». Это цифровая личность с внутренней жизнью:
- Драйвы как биологические потребности (метаболизм + RPE).
- Гомеостаз — автономные цели и действия при отсутствии внешних стимулов.
- Память с забыванием (Эббингауз), усилением (LTP), консолидацией.
- Рефлексия, спонтанные мысли, self-model.
- Конституциональные ограничения.
- Устойчивость: Circuit Breaker, atomic writes, graceful shutdown, specific exceptions.

**Инженерные улучшения v3.0+ (реализованные в коде):**
- Protocol-интерфейсы + runtime_checkable + isinstance проверки.
- Кастомные исключения (большинство мест).
- OllamaClient с полноценным Circuit Breaker (CLOSED/OPEN/HALF_OPEN).
- **JSON + HMAC-SHA256 atomic persistence** вместо pickle (критическое улучшение безопасности и целостности).
- Расширенные интерфейсы для observability (web UI без прямого доступа).
- Изоляция experimental кода.
- Защищённые фоновые задачи + graceful shutdown + авто-рестарт.
- Централизованная LeyaConfig с **полной** валидацией и env loading.
- Pydantic в cognitive output + улучшенный repair_json + реальный токенизатор.
- LLM-based классификация пользовательских запросов.

**Что осталось / требует исправления (v3.1 план, приоритет — баги, обнаруженные ревью):**
- Критический краш в memory sync (engram.created_at).
- Слабый HMAC dev fallback + отсутствие обязательного ключа.
- Broad except Exception в memory.py и llm_client.py (включая опасные для shutdown).
- Отсутствие retry с backoff и неработающий fallback в OllamaClient.
- Неполная version migration и durability atomic write (нет fsync).
- Tech debt experimental/ (нужен ADR).
- Недостаточное покрытие тестами (property-based для repair_json, persistence tampering, sync, Protocols).
- Риск schema drift между prompt и CognitiveOutput Pydantic моделью.
- Drift предыдущей документации с реальным кодом (исправлено в этой версии docs).

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
        │   (Pydantic model_validate_json первым; при ошибке — улучшенный repair_json + повторная валидация; fallback static)
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

**Параллельно (в одном asyncio loop, защищены _safe_create_task с авто-рестартом):**
- drives.background_metabolism()
- reflection.background_consolidation()
- _homeostasis_loop() → generate_goal → submit в workspace
- _workspace_loop() → select_winner (с inhibition) → perceive как "workspace_focus"
- _spontaneous_thought_loop()
- _system_metrics_loop()
- _broadcast_state_loop() (только Web)
- Web-сервер (FastAPI + WebSocket)

## Основные модули leya_core/ (актуальное состояние по коду)

### 1. config.py — Централизованная конфигурация
`LeyaConfig` + вложенные dataclass'ы (OllamaConfig, MemoryConfig, DrivesConfig, HomeostasisConfig, ThinkerConfig, ReflectionConfig, WorkspaceConfig, ConstitutionalConfig, WebConfig, LoggingConfig, SoulConfig, ExperimentalConfig).

**Реальность (код):**
- `__post_init__` валидация (диапазоны, создание директорий).
- `from_env()` — **полная** загрузка всех полей из os.environ / .env (с dedicated парсерами). Нет "частичной" проблемы.
- Валидация brain_dir, base_url и т.д.
- ExperimentalConfig содержит флаги для orphaned модулей.

### 2. drives.py — Система драйвов
DriveSystem + DriveType Enum. current/tension/target, evaluate_stimulus, apply_deltas, apply_satisfaction, calculate_rpe, get_predicted_disbalance, get_internal_state_prompt, **get_drives_state()** (публичный для UI), background_metabolism, update_from_system_metrics (psutil).

Соответствует IDriveSystem Protocol.

### 3. homeostasis_engine.py — Гомеостаз
HomeostasisEngine. generate_goal (drive_state, predicted_state, recent_episodes, action_values), generate_goal_from_gap, extract_key_facts/extract_new_terms (LLM), mark_as_researched, RPE, current_goal (property), last_action_time, rest_period.

Соответствует IHomeostasisEngine.

### 4. memory.py — Память (самый проработанный и изменённый модуль)
**Модели данных (актуальные):**
- MemoryType (EPISODIC / SEMANTIC)
- Engram (dataclass: id, content, memory_type, timestamp, retention_strength, emotional_boost, retrieval_count, last_retrieved, consolidation_level, metadata). **Отсутствует created_at** (причина критического бага #1).
- Synapse (dataclass с to_dict/from_dict)

**Хранение (реальность):**
- chromadb.PersistentClient → episodic_collection + semantic_collection
- **memory_state.json + memory_state.json.hmac** (НЕ pickle!)
  - Атомарная запись: tempfile.mkstemp → json.dump → HMAC-SHA256 (hmac.compare_digest) → os.replace
  - Версионирование: MEMORY_STATE_VERSION = 3
  - Проверка на load: существование .hmac, compare_digest, версия
  - Ключ: env LEYA_STATE_HMAC_KEY или **слабый dev fallback** (критическая уязвимость)
- In-memory: self.engrams, self.synapses, self.self_model
- **Синхронизация**: `_sync_chroma_from_memory` (группировка по типу, `_sync_collection` с upsert/delete батчами). **Содержит баг**: обращение к несуществующему `engram.created_at`.

**Ключевые методы (все async, соответствуют IMemorySystem Protocol):**
- store_perception, retrieve_context, store_fact, consolidate_memories, update_self_model, get_self_model_context, get_recent_*, forget_weak_memories, **get_memory_graph_data()** (публичный)
- _save_state / _load_state (JSON + HMAC atomic)
- _generate_embedding (sync, to_thread)
- `_sync_chroma_from_memory` и `_sync_collection` (добавлены для consistency)

**Биологическая модель:** Полностью сохранена (Эббингауз через retention_strength, emotional_boost, LTP via similarity ≥0.7, consolidation в background).

### 5. thinker.py — Когнитивный планировщик
CoreThinker (реализует ICoreThinker).

**_build_cognitive_prompt:** Собирает огромный промпт (base_personality + soul files + drive_str + self_model + memory_str (truncated с relevance) + tools + stimulus). Инструкция строго JSON.

**generate_plan:** llm_client(..., require_json=True) → _safe_parse_json → fallback static dict при ошибках.

**_safe_parse_json:** 
- Сначала `CognitiveOutput.model_validate_json(raw)` (Pydantic).
- При неудаче: `repair_json(raw)` → `model_validate_json(repaired)`.
- При неудаче: raise LeyaJSONParseError с контекстом.

**repair_json (улучшенная эвристика):** Strip markdown, найти первый {/[ , depth tracking с учётом in_string и escape, re.sub trailing commas, count-based auto-closure, json.loads или "{}".

**Token budgeting:** `_estimate_tokens` — приоритет реальному токенизатору, fallback char-ratio с unicode adjustment. `_truncate_context` — сортировка по relevance_score, обрезка с "...".

**v3.1 план:** Устранить риск schema drift (вынести CognitiveOutput в interfaces), добавить property-based тесты repair_json.

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

**chat:** aiohttp POST /api/chat, timeout, require_json → "format": "json". Specific exceptions (LeyaLLMTimeoutError и др.). **Broad except Exception** как last resort (ловит CancelledError и т.п.). **Нет retry.** Fallback не вызывается в chat().

**v3.1 план:** Добавить retry с exponential backoff до breaker. Реализовать вызов fallback. Убрать broad except.

### 10. interfaces.py (актуальный)
Полный набор Protocol с @runtime_checkable:
- IDriveSystem (включая get_drives_state)
- IMemorySystem (включая get_memory_graph_data async, _save/_load_state)
- IGlobalWorkspace (включая get_workspace_status)
- IHomeostasisEngine (current_goal как @property)
- ICoreThinker / IThinker
- IMetaCognition / IReflection
- IEnvironment (расширенный)
- ILLMClient
- ISoulManager, IToolRegistry, IConstitutionalLayer

LeyaOS проверяет isinstance при создании компонентов. web_interface использует публичные методы.

### 11. Другие модули
- exceptions.py: Иерархия Leya*Error.
- state_persistence.py: load/save drives + homeostasis (JSON/pickle).
- system_metrics.py: psutil метрики.
- tool_generator.py: регистрация и LLM-генерация инструментов.
- environment.py + web_interface/{server.py, web_environment.py}: Абстракция + FastAPI/WebSocket.
- experimental/: decision_engine.py, emotional_support.py, personal_tools.py, desktop_control.py, soul_crypto.py + __init__.py, config.py (изолированы, не интегрированы).

## Soul / Личность
leya_soul/{personality.txt, rules.txt, values.txt}. Загружаются в промпты. leya_personality.json / leya_goals.json — динамические.

## Persistence и Data (актуально)
- leya_brain/:
  - chroma.sqlite3
  - memory_state.json + memory_state.json.hmac (HMAC-SHA256, atomic, version 3)
- StatePersistence: drives + homeostasis между сессиями.
- .gitignore корректно игнорирует leya_brain/, .env, логи, .json.hmac.

## LLM Integration
Только Ollama. Модель и параметры в LeyaConfig + Modelfile.leya. Промпты на русском. Ответы на русском. Circuit Breaker + (неполный) fallback.

## Известные ограничения текущей архитектуры (честный список на 28 июня 2026 после ревью)

**Уже исправлено / улучшено по сравнению с предыдущими версиями документации:**
- Полная env loading в config.
- Pydantic в thinker + улучшенный repair_json + реальный токенизатор.
- LLM classifier вместо keyword heuristics в LeyaOS.
- Синхронизация Chroma/in-memory в memory.
- Улучшенные shutdown и protected tasks.

**Остающиеся (требуют v3.1, приоритет — критические):**
1. Критический AttributeError в memory sync (engram.created_at не существует в Engram).
2. Слабый hardcoded HMAC dev fallback (security / integrity).
3. Broad except Exception в memory.py и llm_client.py (в т.ч. перехват CancelledError).
4. Нет retry с backoff + fallback не вызывается в llm_client.chat.
5. Неполная version migration + отсутствие fsync в atomic write.
6. Experimental модули без ADR и решения.
7. Недостаточное тестовое покрытие (особенно property-based для repair_json, persistence tampering, sync logic, Protocol checks).
8. Риск schema drift prompt ↔ CognitiveOutput Pydantic.
9. Drift предыдущей документации с реальным кодом (исправлено здесь).
10. Жёсткие thresholds, embedding skip handling, отсутствие долгосрочного планирования.

## Рекомендации по развитию (без упрощения)

**Сохранить и углубить:**
- Биологическую модель во всей полноте (LTP details, emotional_boost, consolidation, drives metabolism + RPE, Global Workspace competition + inhibition, spontaneous thoughts, self-model, constitutional constraints).
- Богатство внутреннего опыта и автономию.
- Инструментальную автономию + sandbox.
- Устойчивость (Circuit Breaker, atomic JSON+HMAC, specific exceptions где возможно, safe tasks, graceful shutdown).

**Улучшить (приоритет v3.1 — см. план выше):**
1. Критические баги #1 и #2 (краш + security).
2. Убрать оставшиеся broad except + добавить retry + реализовать fallback.
3. Добавить fsync и version migration.
4. Property-based тесты + CI + coverage >85% core.
5. Experimental analysis + ADR (не просто удалить).
6. Устранить schema drift (вынести модель в interfaces).
7. Обновлённая документация (выполнено в этой версии).

**v3.2+:** Долгосрочное планирование, multi-agent, более глубокий active inference, визуализация в web, мониторинг consistency.

**Принцип:** Сложность — это не баг, а feature для моделирования внутренней жизни. Не упрощать до RAG или обычного агента. Любой рефакторинг только для исправления багов/надёжности, с сохранением биологической правдоподобности.

---

**Примечание:** Документ полностью переписан 28 июня 2026 на основе детального разбора всех .py файлов, raw content, web_interface реализации, сравнения с реальным поведением кода и обнаруженных багов. Предыдущие версии ARCHITECTURE.md (включая анализ от 26–28 июня) содержали устаревшие утверждения, не соответствующие текущему состоянию кода.

Для уточнений по методам — обращайтесь к исходному коду + плану исправлений v3.1.