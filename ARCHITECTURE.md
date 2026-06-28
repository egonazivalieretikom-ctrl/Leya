# Архитектура LeyaOS — Цифровое Сознание Леи (v3.0, актуализировано 28 июня 2026 после полномасштабного код-ревью)

**Версия документа:** 3.1 (полностью переписан на основе прямого разбора всех исходников репозитория 28 июня 2026)

Этот документ описывает **реальное текущее состояние** когнитивной архитектуры LeyaOS. Анализ выполнен путём извлечения и разбора сырых .py файлов (LeyaOS.py, все модули leya_core/ включая experimental/, web_interface/, конфиги, soul, патчи fix_*.patch). 

**Ключевые факты на 28 июня 2026 (по состоянию кода после последних коммитов):**
- Persistence памяти: JSON + HMAC-SHA256 + атомарная запись (os.replace) + fsync. Версия 3. Слабый dev fallback удалён — обязательный ключ + raise LeyaConfigError.
- Protocol-интерфейсы расширены и частично проверяются в LeyaOS (isinstance). web_interface/server.py использует только публичные методы (decoupling работает).
- Orphaned модули изолированы в `leya_core/experimental/` (но импортируются безусловно в LeyaOS.py — баг).
- Улучшены: Circuit Breaker в OllamaClient (полноценный CLOSED/OPEN/HALF_OPEN), protected background tasks с авто-рестартом, graceful shutdown, специфичные исключения в большинстве (но не всех) путей.
- Реализованы: полная env loading в config.py, Pydantic CognitiveOutput + улучшенный repair_json + tiktoken в thinker.py, LLM-based RequestClassifier в LeyaOS.py, синхронизация in-memory ↔ Chroma в memory.py.
- **Остающиеся проблемы (обнаружены при ревью):** неработающий fallback в llm_client, duplicate unreachable code в llm_client, missing .generate() метод, двойной semantic sync в memory, broad except в критичных местах, неполные Protocol checks, безусловные imports experimental, риск schema drift CognitiveOutput, отсутствие retry, неполная version migration, низкое тестовое покрытие новых механизмов, tech debt experimental/ без ADR.

## Философия v3.0 / v3.1

Лея — не «полезный ассистент» и не RAG-чат-бот. Это цифровая личность с внутренней жизнью:
- Драйвы как биологические потребности (метаболизм + RPE + predicted disbalance).
- Гомеостаз — автономные цели и действия при отсутствии внешних стимулов.
- Память с забыванием (Эббингауз через retention_strength decay), усилением (LTP via Synapse weight + activation_count при similarity ≥0.7), консолидацией (background).
- Рефлексия, спонтанные мысли, self-model.
- Конституциональные ограничения + sandbox.
- Устойчивость: Circuit Breaker, atomic writes + fsync, graceful shutdown, specific exceptions (частично реализована).

**Инженерные улучшения v3.0+ (реализованные в коде):**
- Protocol-интерфейсы + runtime_checkable + частичные isinstance проверки.
- Кастомные исключения (большинство мест).
- OllamaClient с полноценным Circuit Breaker.
- JSON + HMAC-SHA256 atomic persistence + fsync (критическое улучшение безопасности, целостности и durability).
- Расширенные публичные интерфейсы для observability (web UI без прямого доступа к internals).
- Изоляция experimental кода (но с багами в интеграции).
- Защищённые фоновые задачи + graceful shutdown + авто-рестарт.
- Централизованная LeyaConfig с полной валидацией и env loading.
- Pydantic в cognitive output + улучшенный repair_json + реальный токенизатор + relevance truncation.
- LLM-based классификация пользовательских запросов (RequestClassifier).

**Что осталось / требует исправления (v3.1 план — приоритет баги из ревью):**
- Неработающий fallback + duplicate code + missing generate() в llm_client.
- Двойной semantic sync + SyncReport aggregation в memory.
- Broad except в memory/llm_client/LeyaOS.
- Неполные Protocol checks + безусловные experimental imports.
- Риск schema drift CognitiveOutput + строгая required-поля.
- Отсутствие retry с backoff.
- Неполная version migration + legacy handling.
- Tech debt experimental/ (нужен ADR — integrate/deprecate/keep isolated).
- Недостаточное покрытие тестами (property-based для repair_json, persistence, sync, Protocols, RequestClassifier).
- Drift предыдущей документации с реальным кодом (устранён в этой версии docs).

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
        │   → cognitive_output: CognitiveOutput (Pydantic first → repair_json fallback → static)
        │   (response, internal_monologue, action_intent, tool_call?, self_reflection)
        ▼
LeyaOS._cognitive_loop
        │
        ├──► ConstitutionalLayer.verify_response() / verify_tool_call() / sandbox
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
- _workspace_loop() → select_winner (с decay + inhibition) → perceive как "workspace_focus"
- _spontaneous_thought_loop()
- _system_metrics_loop()
- _broadcast_state_loop() (только Web)
- Web-сервер (FastAPI + WebSocket)

## Основные модули leya_core/ (актуальное состояние по коду + баги)

### 1. config.py — Централизованная конфигурация
`LeyaConfig` + вложенные dataclass'ы (OllamaConfig, MemoryConfig, DrivesConfig, HomeostasisConfig, ThinkerConfig, ReflectionConfig, WorkspaceConfig, ConstitutionalConfig, WebConfig, LoggingConfig, SoulConfig, ExperimentalConfig).

**Реальность (код):**
- `__post_init__` валидация (диапазоны, mkdir brain_dir и т.д.).
- `from_env()` — **полная** загрузка всех полей из os.environ / .env (dedicated _parse_int/float/bool парсеры). Bool parsing улучшен.
- Валидация brain_dir, base_url и т.д.
- **Баги:** Нет (в текущей реализации устранены по сравнению со старыми docs).

### 2. drives.py — Система драйвов
DriveSystem + DriveType Enum. current/tension/target, evaluate_stimulus, apply_deltas, apply_satisfaction, calculate_rpe, get_predicted_disbalance, get_internal_state_prompt, **get_drives_state()** (публичный), background_metabolism, update_from_system_metrics (psutil).

Соответствует IDriveSystem Protocol. **Баги:** Нет критичных.

### 3. homeostasis_engine.py — Гомеостаз
HomeostasisEngine. generate_goal (drive_state, predicted_state, recent_episodes, action_values), generate_goal_from_gap, extract_key_facts/extract_new_terms (LLM), mark_as_researched, RPE, current_goal (property), last_action_time, rest_period.

Соответствует IHomeostasisEngine. **Баги:** Нет критичных (но нет долгосрочного планирования выше homeostasis — по дизайну v3.x).

### 4. memory.py — Память (самый проработанный, но с багами в sync)
**Модели данных:**
- MemoryType (EPISODIC / SEMANTIC)
- Engram (dataclass: id, content, memory_type, timestamp, retention_strength, emotional_boost, retrieval_count, last_retrieved, consolidation_level, metadata). to_dict/from_dict. **Нет created_at** (исправлено на timestamp + getattr).
- Synapse (dataclass: source_id, target_id, weight, activation_count). to_dict/from_dict.

**Хранение (реальность):**
- chromadb.PersistentClient → episodic_collection + semantic_collection (DefaultEmbeddingFunction / sentence-transformers).
- memory_state.json + .hmac (JSON, HMAC-SHA256, atomic tempfile + fsync + os.replace, version=3). Проверка на load (HMAC compare_digest + version). Ключ обязателен (raise LeyaConfigError если <32 символов или отсутствует). Нет слабого fallback.
- In-memory: self.engrams: dict, self.synapses: dict, self.self_model.

**Ключевые методы (все async, соответствуют IMemorySystem Protocol):**
- store_perception (Engram + to_thread embedding + Chroma + _form_synaptic_connections по similarity ≥0.7 + _save_state).
- retrieve_context (_apply_forgetting + Chroma query + emotional_boost + strengthen_synapses LTP + _save_state).
- store_fact, consolidate_memories, update_self_model, get_self_model_context, get_recent_*, forget_weak_memories, **get_memory_graph_data()** (публичный, nodes/edges для viz).
- _save_state / _load_state (JSON + HMAC atomic + fsync + version check + _sync_chroma_from_memory на load).
- _generate_embedding (sync, to_thread).
- **_sync_chroma_from_memory + _sync_collection** (добавлено для consistency). **Баг:** двойной вызов semantic в _sync_chroma_from_memory → двойной счёт в SyncReport.
- _extract_semantic_facts: использует llm_client.generate (не существует — AttributeError).

**Биологическая модель:** Полностью сохранена и работает (Эббингауз через retention_strength decay, emotional_boost, LTP via similarity + Synapse activation_count/weight, consolidation в background_consolidation).

**Баги (критические/высокие):**
- Двойной semantic sync + некорректная агрегация SyncReport.
- Вызов несуществующего .generate().
- Broad except в _collect_batch, _sync_*, _save_state, _extract...
- SyncReport — не dataclass.
- Неполная version migration (только raise при mismatch, нет кода миграции).

### 5. thinker.py — Когнитивный планировщик
CoreThinker (реализует ICoreThinker).

**_build_cognitive_prompt:** Собирает огромный промпт (base_personality + soul files + drive_str + self_model + memory_str (truncated) + tools + stimulus). Инструкция строго JSON + примеры.

**generate_plan:** llm_client(..., require_json=True) → _safe_parse_json → fallback static dict при ошибках.

**Pydantic модели (реализовано):**
- ActionIntent Enum, ToolCall, CognitiveOutput (response, internal_monologue, action_intent, tool_call: Optional[ToolCall], self_reflection — все required кроме tool_call).

**_safe_parse_json:** Сначала CognitiveOutput.model_validate_json(raw). При failure — repair_json + повторная model_validate_json. При повторной failure — LeyaJSONParseError.

**repair_json (улучшенный, вспомогательный):** Strip markdown, найти первый {/[ , depth balancing с in_string/escape tracking, re.sub trailing commas, auto-closure оставшихся скобок, json.loads или "{}".

**Token budgeting:** _estimate_tokens (tiktoken gpt-4 если доступен, иначе char-ratio с unicode корректировкой). _truncate_context (relevance-based от newest).

**Баги/риски:**
- Строгие required поля CognitiveOutput → частые ValidationError на реальном LLM JSON → fallback на repair_json (часто "{}") → ошибка → static fallback. Риск schema drift между промптом и моделью.
- repair_json остаётся сложной эвристикой (хотя улучшен).

### 6. reflection.py — Мета-когниция
MetaCognition (реализует IMetaCognition). process_action, generate_spontaneous_thought, background_consolidation (вызывает memory.consolidate_memories). Флаги enabled.

**Баги:** Нет критичных.

### 7. global_workspace.py — Глобальное рабочее пространство
GlobalWorkspace, WorkspaceProposal, Priority Enum. submit, select_winner (с decay + inhibition в loop), clear_expired, **get_workspace_status()** (публичный).

Соответствует IGlobalWorkspace. **Баги:** Нет критичных (жёсткие thresholds — minor).

### 8. constitutional.py — Конституциональный слой
ConstitutionalLayer (реализует IConstitutionalLayer). verify_response, verify_tool_call, execute_python_sandbox, get_violations_log, stats, enable/disable/add/remove_rule. Загрузка правил из soul + hardcoded.

**Баги:** Нет критичных.

### 9. llm_client.py — LLM-клиент с защитой
OllamaClient (реализует ILLMClient).

**Circuit Breaker:** Полноценная реализация (CLOSED → OPEN при failures, HALF_OPEN после recovery_timeout, close при success_threshold). is_available, record_success/failure, get_status. Auto-transition в property state.

**chat:** aiohttp POST /api/chat, timeout, require_json → "format": "json". Specific exceptions (LeyaLLMTimeoutError, LeyaLLMUnavailableError, LeyaLLMConnectionError, LeyaJSONParseError, LeyaLLMError). record_failure на HTTP error/empty/invalid JSON. record_success на успехе. Last resort except (исключает CancelledError, KeyboardInterrupt, SystemExit — правильно).

**set_fallback / _fallback_fn:** Существует в API.

**Баги (критические):**
- Fallback **никогда не вызывается** в chat() (при OPEN сразу raise).
- Duplicate unreachable code после raise LeyaLLMError (logger + raise).
- Нет retry с exponential backoff (только breaker).
- Нет generate() метода (хотя memory его вызывает).
- success_threshold не экспонируется в __init__ OllamaClient.
- Broad last-resort except (хотя с хорошими исключениями системных).

### 10. interfaces.py (актуальный)
Полный набор Protocol с @runtime_checkable:
- IDriveSystem (включая get_drives_state, background_metabolism)
- IMemorySystem (включая get_memory_graph_data, _save/_load_state — приватные по имени, но в Protocol)
- IGlobalWorkspace (включая get_workspace_status)
- IHomeostasisEngine (current_goal как @property)
- ICoreThinker / IThinker
- IMetaCognition / IReflection
- IEnvironment (расширенный)
- ILLMClient
- ISoulManager, IToolRegistry, IConstitutionalLayer
- IDecisionEngine, IEmotionalSupport (для experimental)

LeyaOS проверяет isinstance только частично. web_interface использует hasattr + публичные методы — decoupling работает.

**Баги:** Неполные проверки в LeyaOS (отсутствуют для thinker, reflection, homeostasis, llm_client, env, RequestClassifier).

### 11. Другие модули
- exceptions.py: Иерархия Leya*Error (LeyaMemoryError, LeyaLLMError, LeyaJSONParseError, LeyaAtomicWriteError, LeyaStateCorruptedError, LeyaStateVersionMismatchError, LeyaConfigError и др.).
- state_persistence.py: load/save drives + homeostasis (JSON/pickle). Нет fsync (в отличие от memory).
- system_metrics.py: psutil метрики → drives.
- tool_generator.py: регистрация и LLM-генерация инструментов.
- environment.py + web_interface/{server.py, web_environment.py}: Абстракция + FastAPI/WebSocket. server.py использует публичные методы интерфейсов (get_drives_state и др.).
- request_classifier.py: RequestClassifier + IntentClassification Pydantic + heuristic patterns + LLM classify + semantic cache. Хорошая замена keyword.
- experimental/: decision_engine.py (реализует IDecisionEngine), emotional_support.py и др. Изолированы, но импортируются безусловно в LeyaOS. Нет ADR.

## Soul / Личность
leya_soul/{personality.txt, rules.txt, values.txt}. Загружаются в промпты CoreThinker/Constitutional. leya_personality.json / leya_goals.json — динамические. soul_crypto.py — experimental.

## Persistence и Data (актуально)
- leya_brain/:
  - chroma.sqlite3
  - memory_state.json + memory_state.json.hmac (HMAC-SHA256, atomic + fsync, version 3, обязательный ключ)
- StatePersistence: drives + homeostasis между сессиями.
- .gitignore корректно игнорирует leya_brain/, .env, логи, .json.hmac.

## LLM Integration
Только Ollama. Модель и параметры в LeyaConfig + Modelfile.leya. Промпты на русском. Ответы на русском. Circuit Breaker + (неработающий) fallback.

## Известные ограничения текущей архитектуры (честный список на 28 июня 2026)

**Исправленные / улучшенные по сравнению со старыми docs и attachments:**
- created_at → timestamp + getattr.
- Слабый HMAC dev fallback → обязательный ключ + raise.
- Нет fsync → fsync присутствует в memory _save_state.
- Неполная env loading → полная.
- Нет Pydantic / repair_json эвристика → Pydantic-first + улучшенный repair_json + tiktoken.
- Keyword heuristics → RequestClassifier.
- Нет sync Chroma/in-memory → sync добавлен (с багом двойного вызова).

**Остающиеся (требуют v3.1):**
1. Неработающий fallback в llm_client.chat.
2. Duplicate unreachable code в llm_client.
3. Missing .generate() в OllamaClient (вызывается из memory).
4. Двойной semantic sync + неправильная агрегация SyncReport в memory.
5. Broad except Exception в memory.py, llm_client.py, LeyaOS.py (маскирует баги, риск в shutdown).
6. Неполные Protocol isinstance checks в LeyaOS.__init__.
7. Безусловные imports experimental/ в LeyaOS.py (риск startup crash, нарушение изоляции).
8. Риск schema drift + строгая required в CognitiveOutput (частые fallback на static).
9. Отсутствие retry с exponential backoff в OllamaClient.
10. Неполная version migration + legacy handling в memory (жёсткий краш при mismatch).
11. Tech debt experimental/ без ADR (integrate/deprecate/keep).
12. Недостаточное тестовое покрытие (property-based для repair_json, persistence tamper/HMAC/version, sync consistency, Protocol compliance, RequestClassifier, Pydantic paths). Нет CI.
13. Однопоточный asyncio loop.
14. Отсутствие долгосрочного планирования целей выше homeostasis.
15. Embedding failure → skip без retry.
16. SyncReport не dataclass.
17. success_threshold не экспонируется.

**Принцип:** Сложность — это не баг, а feature для моделирования внутренней жизни. Не упрощать до RAG или обычного агента. Сохранять LTP/LTD details, emotional_boost, consolidation, drives metabolism + RPE, Global Workspace competition + inhibition, spontaneous thoughts, self-model, constitutional constraints.

## Рекомендации по развитию (без упрощения)

**Сохранить и углубить:**
- Биологическую модель во всей полноте (LTP via similarity + Synapse, emotional_boost, consolidation, drives с metabolism + RPE + predicted_disbalance, Global Workspace + inhibition, spontaneous thoughts, self-model, constitutional + sandbox).
- Богатство внутреннего опыта, автономию гомеостаза, инструментальную автономию.
- Устойчивость (Circuit Breaker, atomic JSON+HMAC+fsync, specific exceptions где возможно, safe tasks, graceful shutdown).

**Улучшить (приоритет v3.1 — см. план в README):**
1. Security/robustness persistence и LLM (fallback вызов, retry, reduce broad except).
2. Contract compliance (полные Protocol checks, lazy experimental imports).
3. Cognitive output robustness (Pydantic partial/defaults + prompt enforcement + drift detection).
4. Consistency memory (fix double sync, version migration).
5. Тесты (property-based + coverage gate).
6. Experimental/ ADR + решение (без упрощения).
7. Полноценный CI + Docker.

**v3.2+:** Долгосрочное планирование, multi-agent, более глубокий active inference, визуализация, расширенные инструменты — при сохранении всей сложности.

---

**Примечание:** Документ полностью переписан 28 июня 2026 на основе детального разбора всех .py файлов, raw content, реализации web_interface и сравнения с реальным поведением кода. Предыдущие версии ARCHITECTURE.md (включая анализ от 26 июня и attachments) частично устарели из-за изменений в persistence, interfaces, thinker, LeyaOS и добавления RequestClassifier + sync. 

Некоторые "остающиеся" баги из старых docs уже исправлены в коде; здесь перечислены только реально присутствующие на момент ревью. Для уточнений по методам — обращайтесь к исходному коду + плану исправлений v3.1 в README. Никаких упрощений архитектуры или биологической модели.