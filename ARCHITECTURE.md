# Архитектура LeyaOS — Цифровое Сознание Леи (v3.1, актуализировано 29 июня 2026 после полномасштабного код-ревью)

**Версия документа:** 3.1 (полностью переписан и синхронизирован с реальным кодом на основе прямого анализа всех исходников 29 июня 2026)

Этот документ описывает **реальное текущее состояние** когнитивной архитектуры LeyaOS. Анализ выполнен путём прямого извлечения и разбора сырых исходников (LeyaOS.py, все модули leya_core/ включая experimental/, web_interface/, конфиги, soul, .env.example и связанные файлы). 

**Ключевые факты на 29 июня 2026 (итоги ревью):**
- Persistence памяти: JSON + HMAC-SHA256 + атомарная запись (tempfile.mkstemp + json.dump + flush + fsync + os.replace) + версионирование (MEMORY_STATE_VERSION=3) + обязательный ключ (LeyaConfigError при отсутствии/слабом ключе) + _sync_chroma_from_memory (in-memory ↔ Chroma consistency с batch операциями).
- Protocol-интерфейсы расширены и используются (get_drives_state(), get_memory_graph_data(), get_workspace_status() и др.). LeyaOS выполняет частичные isinstance(..., Protocol) проверки.
- Orphaned модули изолированы в `leya_core/experimental/` (conditional интеграция DecisionEngine/EmotionalSupport через config; unconditional import в core не обнаружен).
- Улучшены: Circuit Breaker в OllamaClient (полноценный CLOSED/OPEN/HALF_OPEN), protected background tasks с авто-рестартом (_safe_create_task), graceful shutdown с _save_all_state, специфичные исключения в большинстве путей.
- Thinker: Pydantic CognitiveOutput (model_validate_json первым), улучшенный repair_json (escape handling, in_string tracking, depth balancing, auto-closure, trailing commas), tiktoken primary + relevance-based truncation.
- Config: Полная загрузка ВСЕХ полей всех вложенных конфигов из .env (включая synapse_*, thresholds, hmac_key), надёжный парсинг bool/int/float, __post_init__ валидация.
- LeyaOS: LLM-based RequestClassifier (threshold 0.7 + semantic cache) вместо keyword heuristics; _handle_user_request переведён на классификацию.
- Broad except Exception остался только в 2 местах как last resort (memory._save_state и llm_client.chat) — оборачивается в specific errors.
- **Выявленные баги (verified):** llm_client.py не имеет метода .generate() (вызывается из memory.py в _extract_semantic_facts и др. → AttributeError/краш); duplicate dead code в llm_client; неполные Protocol checks; отсутствие retry в OllamaClient; строгие required в CognitiveOutput → избыточные fallback; SyncReport примитивный.

**Важно:** Это исследовательский прототип. Система содержит известные ограничения и реальные баги. Не предназначена для production, принятия критических решений или буквальной имитации сознания. Использование только в исследовательских целях. **Не упрощать** биологическую модель.

## Философия v3.0 / v3.1

Лея — не «полезный ассистент». Это цифровая личность с внутренней жизнью:
- Драйвы как биологические потребности (метаболизм + RPE + predicted_disbalance).
- Гомеостаз — автономные цели и действия при отсутствии внешних стимулов (generate_goal на основе drive_state, recent_episodes).
- Память с забыванием (Эббингауз через retention_strength decay), усилением (LTP via similarity ≥0.7 + strengthen_synapses), консолидацией (background).
- Рефлексия, спонтанные мысли (generate_spontaneous_thought), self-model (update_self_model + get_self_model_context).
- Конституциональные ограничения (verify_response / verify_tool_call + Python sandbox).
- Устойчивость: Circuit Breaker, atomic writes с fsync, graceful shutdown, specific exceptions, protected tasks.

**Инженерные улучшения v3.0+ (реализованные и подтверждённые ревью):**
- Protocol-интерфейсы (IDriveSystem, IMemorySystem, IGlobalWorkspace, IHomeostasisEngine, ICoreThinker, IMetaCognition, IConstitutionalLayer, ILLMClient и др. с @runtime_checkable) + частичные isinstance проверки в LeyaOS.
- Кастомные исключения (полная иерархия: LeyaError → LeyaMemoryError → LeyaAtomicWriteError/LeyaStateCorruptedError/LeyaEmbeddingError и др.; LeyaLLMError → LeyaLLMTimeoutError/LeyaLLMUnavailableError/LeyaJSONParseError и др.).
- OllamaClient с полноценным Circuit Breaker (failure_threshold, recovery_timeout, success_threshold; is_available, record_success/failure, get_status).
- **JSON + HMAC-SHA256 atomic persistence** (tempfile + fsync + os.replace + hmac.compare_digest + version check + _sync_chroma_from_memory) вместо pickle — критическое улучшение безопасности, целостности и durability.
- Расширенные публичные интерфейсы для observability (web UI без прямого доступа к internals).
- Изоляция experimental кода (conditional через config.experimental).
- Защищённые фоновые задачи (_safe_create_task с обработкой CancelledError + авто-рестарт) + graceful shutdown.
- Централизованная LeyaConfig с полной загрузкой из env и валидацией.
- LLM-based RequestClassifier в LeyaOS (confidence + semantic cache).
- Pydantic CognitiveOutput + улучшенный repair_json + tiktoken в thinker.

**Что осталось / требует исправления (v3.1 приоритет — verification багов "v3.0"):**
- Критический баг: отсутствие .generate() в OllamaClient при наличии вызовов из memory.py.
- Residual broad except в 2 местах (last resort).
- Неполные Protocol isinstance проверки.
- Отсутствие retry с exponential backoff в OllamaClient.
- Fallback в llm_client при OPEN breaker — неполный.
- Строгие required поля в CognitiveOutput → избыточные fallback.
- Технический долг experimental/ (нужен ADR: integrate/deprecate/delete с обоснованием, запрет на упрощение).
- Недостаточное покрытие тестами (property-based для repair_json, persistence tampering, Protocol compliance, LTP).
- Однопоточный asyncio loop.
- Нет долгосрочного планирования целей выше homeostasis.
- SyncReport примитивный, нет dataclass.
- Документация требовала синхронизации (выполнено в этом обновлении).

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
        ├──► Memory.store_perception() (Engram + embedding в Chroma + _form_synaptic_connections по similarity ≥0.7)
        │
        ├──► Memory.retrieve_context() + get_self_model_context() + get_memory_graph_data() (публичный)
        │
        ├──► Homeostasis (опционально generate_goal → WorkspaceProposal)
        │
        ▼
CoreThinker.generate_plan()
        │   (LLM с полным контекстом: soul + drives + self_model + memory_context + tools + stimulus)
        │   → cognitive_output: {response, internal_monologue, action_intent, tool_call, self_reflection}
        │   (Pydantic model_validate_json первым → repair_json (улучшенный) → validate → fallback)
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
- _workspace_loop() → select_winner (с inhibition + decay) → perceive как "workspace_focus"
- _spontaneous_thought_loop()
- _system_metrics_loop()
- _broadcast_state_loop() (только Web)
- Web-сервер (FastAPI + WebSocket)

## Основные модули leya_core/ (актуальное состояние по ревью)

### 1. config.py — Централизованная конфигурация
LeyaConfig + вложенные dataclass'ы (OllamaConfig, MemoryConfig, DrivesConfig, HomeostasisConfig, ThinkerConfig, ReflectionConfig, WorkspaceConfig, ConstitutionalConfig, WebConfig, LoggingConfig, SoulConfig, ExperimentalConfig).

**Реальность (подтверждено ревью):**
- from_env() — **полная** загрузка всех полей всех под-конфигов из os.environ / .env с префиксами (OLLAMA_, MEMORY_, SYNAPSE_ и др.).
- _parse_bool (надежный набор true/1/yes/on/y/t), _parse_int, _parse_float — с явными LeyaConfigError при ошибках.
- __post_init__ в каждом под-классе: валидация диапазонов (например, 0.0 < forgetting_threshold < 1.0), создание директорий, проверка путей.
- Комментарий в коде: "# Этап 1.2: Полная загрузка всех полей, явные ошибки, улучшенный парсинг bool."
- Нет "неполной загрузки" — все synapse_*, thresholds, hmac_key и т.д. покрыты.

### 2. drives.py — Система драйвов
DriveSystem + DriveType Enum (CURIOSITY, CONNECTION, REST, CREATIVITY, UNDERSTANDING, AUTONOMY и др.).

current/tension/target, evaluate_stimulus, apply_deltas, apply_satisfaction, calculate_rpe, get_predicted_disbalance, get_internal_state_prompt, **get_drives_state()** (публичный), background_metabolism (с метаболизмом), update_from_system_metrics (psutil).

Соответствует IDriveSystem Protocol.

### 3. homeostasis_engine.py — Гомеостаз
HomeostasisEngine. generate_goal (на основе drive_state, predicted_state, recent_episodes, action_values), generate_goal_from_gap, extract_key_facts/extract_new_terms (LLM), mark_as_researched, RPE, current_goal (как @property в интерфейсе), last_action_time, rest_period.

Соответствует IHomeostasisEngine.

### 4. memory.py — Память (самый проработанный модуль)
**Модели данных:**
- MemoryType (EPISODIC / SEMANTIC)
- Engram (dataclass: id, content, memory_type, timestamp, retention_strength, emotional_boost, retrieval_count, last_retrieved, consolidation_level, metadata; to_dict/from_dict)
- Synapse (dataclass: source_id, target_id, weight, activation_count; to_dict/from_dict)

**Хранение (реальность 29 июня):**
- chromadb.PersistentClient → episodic_collection + semantic_collection (all-MiniLM-L6-v2 embeddings, to_thread).
- memory_state.json + memory_state.json.hmac (НЕ pickle!)
  - Атомарная запись: tempfile.mkstemp → json.dump (ensure_ascii=False, indent=2) → flush + fsync → HMAC-SHA256 (compute_hmac по binary chunks) → os.replace (с fallback shutil.move на cross-device).
  - Версионирование: "__version__": 3
  - Проверка на load: существование .hmac, hmac.compare_digest, версия → LeyaStateVersionMismatchError / LeyaStateCorruptedError.
  - Ключ: os.environ.get("LEYA_STATE_HMAC_KEY") — обязательный, иначе LeyaConfigError (слабый dev fallback удалён).
- In-memory: self.engrams: dict, self.synapses: dict, self.self_model
- _sync_chroma_from_memory (на load + после restore): _sync_collection для episodic и semantic (batch 500, upsert/delete, SyncReport с added/updated/removed/errors). Single вызов на коллекцию (двойной semantic sync из предыдущих версий устранён в текущем коде).

**Ключевые методы (все async, соответствуют IMemorySystem Protocol):**
- store_perception (Engram + to_thread embedding + Chroma + _form_synaptic_connections по similarity ≥0.7 из Chroma query + _save_state)
- retrieve_context (_apply_forgetting + Chroma query + emotional_boost + strengthen_synapses (LTP) + _save_state)
- store_fact, consolidate_memories, update_self_model, get_self_model_context, get_recent_*, forget_weak_memories, **get_memory_graph_data()** (публичный для UI: nodes/edges)
- _save_state / _load_state (JSON + HMAC atomic + sync)
- _generate_embedding (sync, to_thread)
- _form_synaptic_connections, _apply_forgetting, strengthen_synapses

**Биологическая модель:** Полностью сохранена и работает (Эббингауз через retention_strength decay + emotional_boost замедляет, LTP via similarity + activation_count/weight, consolidation в background_consolidation).

**Известные нюансы (verified):** Broad except в _save_state (оборачивается в LeyaAtomicWriteError). На load — graceful degradation при sync errors.

### 5. thinker.py — Когнитивный планировщик
CoreThinker (реализует ICoreThinker).

**_build_cognitive_prompt:** Собирает огромный промпт (base_personality + soul files + drive_str + self_model + memory_str (truncated) + tools + stimulus). Инструкция строго JSON.

**generate_plan:** llm_client(..., require_json=True) → _safe_parse_json → fallback static dict при LeyaLLMError / LeyaJSONParseError.

**Парсинг (реальность):**
```python
def _safe_parse_json(raw: str) -> CognitiveOutput:
    try:
        return CognitiveOutput.model_validate_json(raw)  # Pydantic first
    except (json.JSONDecodeError, ValidationError):
        repaired = repair_json(raw)
        return CognitiveOutput.model_validate_json(repaired)  # retry after repair
```

**repair_json (улучшенный):**
- Strip ```json
- Найти первый { или [
- Глубокий скан с escape_next, in_string флагом (не считать braces внутри строк), depth tracking
- Если не сбалансировано — auto-closure по count
- re.sub trailing commas
- json.loads или "{}"

**Token budgeting:** _estimate_tokens — tiktoken (primary, gpt-4 encoding) или char-ratio fallback с adjusted_ratio для Unicode >30%. _truncate_context — sort by relevance_score (desc), truncate last item если нужно.

**v3.1 issues (verified):** Строгие required поля в CognitiveOutput (response, internal_monologue, action_intent, self_reflection) → частые fallback. Нет Pydantic в старых версиях — теперь есть.

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

**chat:** aiohttp POST /api/chat, timeout, require_json → "format": "json". Specific exceptions (LeyaLLMTimeoutError, LeyaLLMUnavailableError, LeyaLLMConnectionError, LeyaLLMError, LeyaJSONParseError). Fallback при OPEN.

**verified issues:**
- Broad except Exception as last resort (log + record_failure + raise LeyaLLMError; re-raises CancelledError/KeyboardInterrupt/SystemExit).
- Duplicate logger.error / raise после except (dead code).
- **Критический баг:** Нет метода async def generate(self, prompt, max_tokens=... ). Вызывается из memory.py → AttributeError.
- Нет retry с exponential backoff (только breaker).

### 10. interfaces.py (актуальный)
Полный набор Protocol с @runtime_checkable:
- IDriveSystem (включая get_drives_state, background_metabolism)
- IMemorySystem (включая get_memory_graph_data, _save_state/_load_state)
- IGlobalWorkspace (включая get_workspace_status)
- IHomeostasisEngine (current_goal как @property)
- ICoreThinker / IThinker
- IMetaCognition / IReflection
- IEnvironment (расширенный)
- ILLMClient
- ISoulManager, IToolRegistry, IConstitutionalLayer

LeyaOS проверяет isinstance при создании компонентов (частично). web_interface использует hasattr + публичные методы — decoupling работает.

### 11. Другие модули
- exceptions.py: Полная иерархия Leya*Error (заменяет broad except в дизайне).
- state_persistence.py: load/save drives + homeostasis (JSON/pickle).
- system_metrics.py: psutil метрики → drives.
- tool_generator.py: регистрация + LLM-генерация инструментов.
- environment.py + web_interface/{server.py, web_environment.py}: Абстракция + FastAPI/WebSocket. Использует публичные методы.
- experimental/: decision_engine.py, emotional_support.py, personal_tools.py, desktop_control.py, soul_crypto.py, voice_*.py — изолированы, conditional.

## Soul / Личность
leya_soul/{personality.txt, rules.txt, values.txt} — загружаются в промпты. leya_personality.json / leya_goals.json — динамические. soul_crypto.py — experimental.

## Persistence и Data (актуально)
- leya_brain/: chroma.sqlite3, memory_state.json + .hmac (HMAC-SHA256, atomic, version 3, fsync)
- StatePersistence: drives + homeostasis между сессиями.
- .gitignore корректно игнорирует leya_brain/, .env, логи, *.hmac.

## LLM Integration
Только Ollama (/api/chat). Модель и параметры в LeyaConfig + Modelfile.leya. Промпты на русском. Circuit Breaker + fallback. **Баг:** generate endpoint не реализован в клиенте.

## Известные ограничения текущей архитектуры (честный список на 29 июня 2026 — verified ревью)

**Исправленные / улучшенные (подтверждено кодом):**
- Pickle → JSON + HMAC atomic + fsync + mandatory key + version + sync.
- Interfaces расширены и используются в web (decoupling).
- experimental/ изолирован (conditional).
- LeyaOS использует Protocol checks (частично).
- Большинство except — специфичные (иерархия).
- Graceful shutdown и protected tasks реализованы хорошо.
- Config полная загрузка + robust parsing.
- Thinker: Pydantic + улучшенный repair_json + tiktoken + relevance truncate.
- Request handling: LLM classifier вместо keywords.
- Memory consistency: _sync_chroma_from_memory добавлена.

**Остающиеся (требуют v3.1, verified баги):**
1. **Критический баг missing .generate()**: memory.py вызывает self.llm_client.generate(...) — OllamaClient не имеет метода. AttributeError при использовании семантических фактов / extract.
2. **Broad except Exception**: Остался в memory._save_state и llm_client.chat (last resort, с обёрткой в specific + record_failure). Duplicate dead code в llm_client.
3. **Неполные Protocol checks**: isinstance в LeyaOS — не все компоненты и пути покрыты явно.
4. **Нет retry в LLM client**: Только Circuit Breaker. Fallback при OPEN — неполный в некоторых сценариях.
5. **CognitiveOutput Pydantic**: Строгие required поля → частые fallback на static dict. repair_json всё ещё эвристика (риск edge cases с Unicode, deeply nested strings, escape).
6. **Chroma / in-memory**: Синхронизация есть (single вызов на коллекцию), но SyncReport примитивный, нет dataclass, агрегация слабая. Graceful degradation при sync errors.
7. **experimental/ модули**: Технический долг. Нет ADR. Conditional интеграция DecisionEngine/EmotionalSupport, но остальное — dead code / риск.
8. **Тесты**: Покрытие core-логики (cognitive_loop, repair_json edge cases, JSON+HMAC persistence tampering/hmac fail/version, LTP/synapse formation, Protocol compliance, RequestClassifier) недостаточно. Нет CI / property-based тестов.
9. **Жёсткая привязка к Ollama**: Нет fallback на другие провайдеры. Нет retry.
10. **Однопоточный event loop**: Все фоновые задачи в одном asyncio loop. Нет настоящей параллельности мыслей / multi-threaded cognition.
11. **Отсутствие долгосрочного планирования**: Цели только на уровне homeostasis + workspace competition. Нет иерархии выше гомеостаза.
12. **Web interface**: Decoupling работает. Protocol checks частичные.
13. **Документация**: Требовала синхронизации (README был оптимистичнее ARCH; обновлено в v3.1).

**Общий вывод ревью:** Архитектура значительно улучшена и соответствует заявленной биологической модели в полном объёме (LTP/LTD details, emotional_boost, consolidation, drives metabolism + RPE, Global Workspace competition + inhibition, spontaneous thoughts, self-model, constitutional constraints). Сложность — feature, а не баг. Однако "v3.0 fixes" реализованы не полностью и содержат баги (особенно missing generate() и residual broad except). Система стабильнее предыдущих версий, но остаётся исследовательским прототипом. Перед серьёзным использованием — исправить критические баги.

## Рекомендации по развитию (без упрощения)

**Сохранить и углубить (приоритет):**
- Биологическую модель во всей полноте (LTP via similarity ≥0.7 + strengthen_synapses + activation_count, emotional_boost, Ebbinghaus retention_strength decay, consolidation в background, drives с metabolism + RPE + predicted_disbalance + get_predicted_disbalance, Global Workspace с submit/select_winner/inhibition/decay, spontaneous thoughts, self-model, constitutional + sandbox).
- Богатство внутреннего опыта, автономию гомеостаза, competition в workspace.
- Инструментальную автономию + sandbox.
- Устойчивость (Circuit Breaker, atomic JSON+HMAC+fsync, specific exceptions, safe tasks, graceful shutdown).

**Улучшить (v3.1 приоритет — verification + bugfix):**
1. Добавить .generate() в OllamaClient (или унифицировать с chat) + обновить memory.py вызовы. Тест на этот edge case.
2. Убрать/минимизировать broad except в llm_client и memory (конкретные except + always raise specific).
3. Завершить Protocol checks (добавить недостающие isinstance в LeyaOS).
4. Добавить retry с exponential backoff в OllamaClient до срабатывания breaker. Улучшить fallback.
5. Улучшить CognitiveOutput Pydantic (optional поля где уместно) + усилить repair_json для edge cases (Unicode, nested, escape в strings).
6. Улучшить SyncReport (dataclass + better aggregation) и consistency.
7. Фаза ADR для experimental/ (integrate DecisionEngine/EmotionalSupport если усиливают биологическую модель; deprecate/delete остальные с обоснованием — запрет на упрощение).
8. Property-based тесты для repair_json, atomic persistence (tampering, hmac fail, version mismatch), LTP, Protocol compliance, RequestClassifier. Coverage >85% core.
9. Полноценный CI + Docker.
10. Обновить документацию (выполнено в этом обновлении — README и ARCHITECTURE синхронизированы).

**v3.2+:** Долгосрочное планирование (иерархическая goal stack), multi-agent (с сохранением индивидуальной внутренней жизни каждого), визуализация в web (memory graph, drives dynamics, workspace competition), более глубокий active inference / predictive processing в drives/homeostasis.

**Принцип:** Сложность — это не баг, а feature для моделирования внутренней жизни. **Не упрощать** до RAG-агента, простого tool-calling чат-бота или state machine. Любой рефакторинг должен усиливать биологическую правдоподобность, автономию и богатство внутреннего опыта.

---

**Примечание:** Документ полностью переписан 29 июня 2026 на основе детального разбора всех .py файлов, raw content, подтверждения/опровержения claims из предыдущих версий и сравнения с реальным поведением кода (включая verified баги missing generate(), broad except locations, Protocol completeness, config loading и т.д.). Предыдущие версии ARCHITECTURE.md (включая анализ от 28 июня) частично устарели или содержали неточности по багами.

Для уточнений по методам — обращайтесь к исходному коду + плану исправлений v3.1 (фокус на verification).