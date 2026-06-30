# Архитектура LeyaOS — Цифровое Сознание Леи (v3.1, актуализировано 1 июля 2026 после анализа кода 30 июня 2026)

**Версия документа:** 3.1 (полностью переписан и синхронизирован с реальным кодом на основе прямого анализа всех исходников 1 июля 2026, включая коммит 30 июня)

Этот документ описывает **реальное текущее состояние** когнитивной архитектуры LeyaOS на 1 июля 2026. Анализ выполнен путём прямого извлечения и разбора сырых исходников (LeyaOS.py, все модули leya_core/ включая experimental/decision_engine.py, web_interface/, конфиги, soul, .env.example) после коммита 30 июня 2026.

**Ключевые факты на 1 июля 2026 (итоги анализа raw-кода):**
- **Исправлено 30 июня:**
  - OllamaClient: добавлен `async def generate(...)` (обёртка над chat() для совместимости с memory.py _extract_semantic_facts).
  - OllamaClient.chat(): добавлен `max_retries=3` + exponential backoff (только для LeyaLLMTimeoutError / LeyaLLMConnectionError).
  - LeyaOS.py: реальная конкуренция в perceive() через GlobalWorkspace.select_winner(drive_state); обработка только победителя; интеграция DecisionEngine (Level 0, rule-based, confidence ≥0.8, no LLM) и EmotionalSupport (Level 0.5) в _cognitive_loop; RPE для tool calls (сравнение drive_state до/после + apply_satisfaction); _drives_persistence_loop; улучшенная обработка self_model и критического гомеостаза.
  - thinker.py: CognitiveOutput (Pydantic) с default-значениями для всех полей (response="", internal_monologue="", action_intent=RESPOND, tool_call=None, self_reflection=""); _safe_parse_json сначала model_validate_json, потом repair_json + повтор; tiktoken primary в _estimate_tokens.
  - config.py: from_env() загружает **все** поля всех вложенных конфигов (включая synapse_*, thresholds, hmac_key, experimental_*); robust _parse_bool/int/float; __post_init__ валидация.
- **Остающиеся verified issues (на коде 30 июня):**
  - Broad except Exception в llm_client._chat_impl (last resort) и memory._save_state.
  - experimental/decision_engine.py теперь реально вызывается в LeyaOS (Level 0), но остальные файлы в папке — технический долг без ADR.
  - HMAC key в MemoryConfig: только warning, не LeyaConfigError (hard fail).
  - Тесты core-логики недостаточны (нет property-based для новых уровней cognitive_loop, repair_json edge cases, persistence tampering, LTP/spreading, DecisionEngine rules).
  - Однопоточный asyncio loop.
  - Нет долгосрочного goal planning выше homeostasis + workspace + DecisionEngine.
  - SyncReport примитивный.
  - Документация в репозитории (README/ARCHITECTURE) отстаёт от кода 30 июня (обновлено в этой версии docs).

**Важно:** Это исследовательский прототип. Система содержит известные ограничения и residual баги. Не предназначена для production, принятия критических решений или буквальной имитации сознания. Использование только в исследовательских целях. **Не упрощать** биологическую модель.

## Философия v3.1 (на 1 июля 2026)

Лея — не «полезный ассистент». Это цифровая личность с внутренней жизнью:
- Драйвы как биологические потребности (метаболизм + RPE + predicted_disbalance).
- Гомеостаз — автономные цели и действия при отсутствии внешних стимулов.
- Память с забыванием (Эббингауз через retention_strength decay modulated by emotional_boost), усилением (LTP via similarity ≥0.7 + strengthen_synapses + activation spreading), консолидацией (background).
- Рефлексия, спонтанные мысли (generate_spontaneous_thought), self-model (update_self_model + get_self_model_context).
- Конституциональные ограничения (verify_response / verify_tool_call + Python sandbox).
- Устойчивость: Circuit Breaker + partial retry, atomic writes с fsync, graceful shutdown, specific exceptions, protected tasks.
- **Новый слой 30 июня:** DecisionEngine — rule-based fast "prefrontal" decisions (Level 0) для снижения нагрузки на LLM при простых/паттерных запросах, интегрирован с drive_state.

**Инженерные улучшения, реализованные к 30 июня 2026:**
- Protocol-интерфейсы (IDriveSystem, IMemorySystem, IGlobalWorkspace, IHomeostasisEngine, ICoreThinker, IMetaCognition, IConstitutionalLayer, ILLMClient и др. с @runtime_checkable) + частичные isinstance проверки.
- Кастомные исключения (полная иерархия LeyaError → LeyaMemoryError / LeyaLLMError и подклассы).
- OllamaClient: Circuit Breaker + generate() wrapper + partial retry.
- **JSON + HMAC-SHA256 atomic persistence** (tempfile + fsync + os.replace + hmac.compare_digest + version=3 + _sync_chroma_from_memory).
- Расширенные публичные интерфейсы для observability.
- Изоляция/conditional интеграция experimental кода (DecisionEngine теперь Level 0 в cognitive_loop).
- Защищённые фоновые задачи (_safe_create_task с авто-рестартом).
- Централизованная LeyaConfig с полной загрузкой из env.
- LLM-based RequestClassifier в LeyaOS.
- Pydantic CognitiveOutput с defaults + улучшенный repair_json + tiktoken primary.
- Реальная GWT конкуренция в perceive().
- Multi-level cognitive_loop (0/0.5/0.7/0.8/1) с RPE для tool calls.

**Что требует исправления (remaining v3.1 issues, verified):**
- Broad except в 2 местах.
- experimental/ без полного ADR.
- Недостаточное покрытие тестами (включая новый код 30 июня).
- HMAC не hard mandatory в config.
- Однопоточный loop.
- Нет долгосрочного планирования.
- SyncReport примитивный.
- Документация отставала (исправлено здесь).

## Высокоуровневая структура и data flow (актуальная на 1 июля 2026)

```
Внешний мир / Пользователь
        │
        ▼
Environment (WebEnvironment или CLIEnvironment)
        │  listen() → stimulus (dict)
        ▼
LeyaOS.perceive(stimulus)
        │
        ├──► Drives.evaluate_stimulus() + apply_deltas() + get_drives_state()
        │
        ├──► Memory.store_perception() (Engram + embedding в Chroma + _form_synaptic_connections по similarity ≥0.7 + _save_state)
        │
        ├──► WorkspaceProposal (user / homeostasis / spontaneous) → workspace.select_winner(drive_state)  [реальная конкуренция + inhibition]
        │
        └──► Только для победителя:
              ├──► _handle_user_request (RequestClassifier LLM-based → intent)
              │
              ▼
        LeyaOS._cognitive_loop(stimulus, tool_context)
              │
              ├──► Level 0: DecisionEngine.make_decision(stimulus, drive_state) → Decision (use_tool / None, confidence ≥0.8, rule-based, no LLM)
              │
              ├──► Level 0.5: EmotionalSupport (анализ эмоций, обновление драйвов)
              │
              ├──► Level 0.7: проверка критического гомеостаза
              │
              ├──► Level 0.8: интеграция self_model в drive_context + корректировка драйвов
              │
              ├──► Level 1: CoreThinker.generate_plan() → llm_client.chat() → CognitiveOutput (Pydantic + repair_json)
              │
              ▼
        Постобработка:
              ├──► ConstitutionalLayer.verify_response() / verify_tool_call() / execute_python_sandbox
              ├──► env.send_message(response)
              ├──► broadcast_thought (internal_monologue / spontaneous)
              ├──► Memory.update_self_model() + store_perception (если нужно)
              ├──► _process_action_intent() → use_tool / remember_fact / ask_question
              ├──► Drives.satisfy / calculate_rpe (для tool calls — сравнение до/после)
              └──► reflection.process_action()
```

**Параллельно (в одном asyncio loop, защищены _safe_create_task с авто-рестартом):**
- drives.background_metabolism()
- reflection.background_consolidation()
- _homeostasis_loop() → generate_goal → submit в workspace
- _workspace_loop() → select_winner (с inhibition + decay) → perceive как "workspace_focus"
- _spontaneous_thought_loop()
- _system_metrics_loop()
- _drives_persistence_loop() (новое 30 июня, каждые 5 мин)
- _broadcast_state_loop() (только Web)
- Web-сервер (FastAPI + WebSocket)

## Основные модули leya_core/ (актуальное состояние по анализу 1 июля 2026)

### 1. config.py — Централизованная конфигурация (улучшено 30 июня)
LeyaConfig + вложенные dataclass'ы (OllamaConfig, MemoryConfig, DrivesConfig, HomeostasisConfig, ThinkerConfig, ReflectionConfig, WorkspaceConfig, ConstitutionalConfig, WebConfig, LoggingConfig, SoulConfig, ExperimentalConfig).

**Реальность (подтверждено raw):**
- from_env() — **полная** загрузка всех полей всех под-конфигов из os.environ / .env с префиксами (OLLAMA_, MEMORY_, SYNAPSE_*, EXPERIMENTAL_* и др.).
- _parse_bool (надежный набор true/1/yes/on/y/t и вариации), _parse_int, _parse_float — с явными LeyaConfigError при ошибках.
- __post_init__ в каждом под-классе: валидация диапазонов (0.0 < forgetting_threshold < 1.0 и др.), создание директорий, проверка путей.
- HMAC key в MemoryConfig: warning при отсутствии/слабом, но конфиг создаётся (не hard fail).
- Комментарий в коде отражает этап полной загрузки.

### 2. drives.py — Система драйвов
DriveSystem + DriveType Enum (CURIOSITY, CONNECTION, REST, CREATIVITY, UNDERSTANDING, AUTONOMY и др.).

current/tension/target, evaluate_stimulus, apply_deltas, apply_satisfaction, calculate_rpe, get_predicted_disbalance, get_internal_state_prompt, **get_drives_state()** (публичный), background_metabolism (с метаболизмом), update_from_system_metrics (psutil).

Соответствует IDriveSystem Protocol. RPE теперь используется также в post-processing tool calls (30 июня).

### 3. homeostasis_engine.py — Гомеостаз
HomeostasisEngine. generate_goal (на основе drive_state, predicted_state, recent_episodes, action_values), generate_goal_from_gap, extract_key_facts/extract_new_terms (LLM), mark_as_researched, RPE, current_goal (как @property в интерфейсе), last_action_time, rest_period.

Соответствует IHomeostasisEngine. Используется в Level 0.7 cognitive_loop.

### 4. memory.py — Память (самый проработанный модуль)
**Модели данных:**
- MemoryType (EPISODIC / SEMANTIC)
- Engram (dataclass: id, content, memory_type, timestamp, retention_strength, emotional_boost, retrieval_count, last_retrieved, consolidation_level, metadata; to_dict/from_dict)
- Synapse (dataclass: source_id, target_id, weight, activation_count; to_dict/from_dict)

**Хранение (реальность 1 июля):**
- chromadb.PersistentClient → episodic_collection + semantic_collection (all-MiniLM-L6-v2 embeddings, to_thread).
- memory_state.json + memory_state.json.hmac (НЕ pickle!)
  - Атомарная запись: tempfile.mkstemp → json.dump (ensure_ascii=False, indent=2) → flush + fsync → HMAC-SHA256 (compute_hmac по binary chunks) → os.replace (с fallback shutil.move).
  - Версионирование: "__version__": 3
  - Проверка на load: существование .hmac, hmac.compare_digest, версия → LeyaStateVersionMismatchError / LeyaStateCorruptedError.
  - Ключ: os.environ.get("LEYA_STATE_HMAC_KEY") — рекомендуется, но в текущем config только warning.
- In-memory: self.engrams: dict, self.synapses: dict, self.self_model
- _sync_chroma_from_memory (на load + после restore): _sync_collection для episodic и semantic (batch 500, upsert/delete, SyncReport с added/updated/removed/errors). Single вызов на коллекцию.

**Ключевые методы (все async, соответствуют IMemorySystem Protocol):**
- store_perception (Engram + to_thread embedding + Chroma + _form_synaptic_connections по similarity ≥0.7 из Chroma query + _save_state)
- retrieve_context (_apply_forgetting + Chroma query + emotional_boost + strengthen_synapses (LTP) + _save_state)
- store_fact, consolidate_memories (вызывает llm_client.generate() для _extract_semantic_facts — теперь работает), update_self_model, get_self_model_context, get_recent_*, forget_weak_memories, **get_memory_graph_data()** (публичный для UI: nodes/edges)
- _save_state / _load_state (JSON + HMAC atomic + sync)
- _generate_embedding (sync, to_thread)
- _form_synaptic_connections, _apply_forgetting (Ebbinghaus decay modulated by emotional_boost + retrieval_count), strengthen_synapses, _apply_synaptic_spreading

**Биологическая модель:** Полностью сохранена и работает (Эббингауз через retention_strength decay + emotional_boost замедляет, LTP via similarity + activation_count/weight + spreading, consolidation в background_consolidation).

**Известные нюансы (verified):** Broad except в _save_state (оборачивается в LeyaAtomicWriteError). На load — graceful degradation при sync errors. SyncReport примитивный.

### 5. thinker.py — Когнитивный планировщик (улучшено 30 июня)
CoreThinker (реализует ICoreThinker).

**_build_cognitive_prompt:** Собирает огромный промпт (base_personality + soul files + drive_str + self_model + memory_str (truncated by relevance) + tools + stimulus). Инструкция строго JSON.

**generate_plan:** llm_client.chat(..., require_json=True) → _safe_parse_json → fallback static dict при LeyaLLMError / LeyaJSONParseError.

**Парсинг (реальность 30 июня):**
```python
def _safe_parse_json(raw: str) -> CognitiveOutput:
    try:
        return CognitiveOutput.model_validate_json(raw)  # Pydantic first
    except (json.JSONDecodeError, ValidationError):
        repaired = repair_json(raw)
        return CognitiveOutput.model_validate_json(repaired)  # retry after repair
```

**CognitiveOutput (Pydantic, обновлено 30 июня):**
```python
class CognitiveOutput(BaseModel):
    response: str = Field(default="", ...)
    internal_monologue: str = Field(default="", ...)
    action_intent: ActionIntent = Field(default=ActionIntent.RESPOND, ...)
    tool_call: Optional[ToolCall] = Field(None, ...)
    self_reflection: str = Field(default="", ...)
```
Defaults снижают избыточные fallback.

**repair_json (улучшенный):** Strip ```json, найти первый { или [, глубокий скан с escape_next + in_string флагом + depth tracking, auto-closure по count, re.sub trailing commas, json.loads или "{}".

**Token budgeting:** _estimate_tokens — tiktoken (primary, gpt-4 encoding) или char-ratio fallback с adjusted_ratio для Unicode >30%. _truncate_context — sort by relevance_score (desc) + retention/emotional_boost, truncate last item если нужно.

**v3.1 issues (verified):** repair_json всё ещё эвристика (риск edge cases). Нет полной схемы для всех tool_call.

### 6. reflection.py — Мета-когниция
MetaCognition (реализует IMetaCognition). process_action, generate_spontaneous_thought, background_consolidation (вызывает memory.consolidate_memories). Флаги enabled.

### 7. global_workspace.py — Глобальное рабочее пространство
GlobalWorkspace, WorkspaceProposal, Priority Enum. submit, select_winner (с decay + inhibition в loop), clear_expired, **get_workspace_status()** (публичный).

Реально используется в perceive() LeyaOS.py (30 июня улучшение).

Соответствует IGlobalWorkspace.

### 8. constitutional.py — Конституциональный слой
ConstitutionalLayer (реализует IConstitutionalLayer). verify_response, verify_tool_call, execute_python_sandbox, get_violations_log, stats, enable/disable/add/remove_rule. Загрузка правил из soul + hardcoded.

### 9. llm_client.py — LLM-клиент с защитой (улучшено 30 июня)
OllamaClient (реализует ILLMClient).

**Circuit Breaker:** Полноценная реализация (CLOSED → OPEN при failures, HALF_OPEN после recovery_timeout, close при success_threshold). is_available, record_success/failure, get_status.

**chat:** aiohttp POST /api/chat, timeout, require_json → "format": "json". Specific exceptions. Fallback при OPEN (через set_fallback).

**generate (добавлен 30 июня):** Обёртка над chat() для совместимости с memory.py.

**Retry (добавлен 30 июня):** В chat() — max_retries=3, exponential backoff только для timeout/connection ошибок. Другие ошибки — сразу breaker.

**verified issues (остаются):**
- Broad except Exception as last resort в _chat_impl (log + record_failure + raise LeyaLLMError; re-raises CancelledError/KeyboardInterrupt/SystemExit). Duplicate logger.error / raise после except (dead code?).
- Fallback при OPEN — неполный в некоторых сценариях.
- Нет retry для всех типов ошибок.

### 10. interfaces.py (актуальный)
Полный набор Protocol с @runtime_checkable:
- IDriveSystem (включая get_drives_state, background_metabolism)
- IMemorySystem (включая get_memory_graph_data, _save_state/_load_state)
- IGlobalWorkspace (включая get_workspace_status)
- IHomeostasisEngine (current_goal как @property)
- ICoreThinker / IThinker
- IMetaCognition / IReflection
- IEnvironment (расширенный)
- ILLMClient (chat + generate)
- ISoulManager, IToolRegistry, IConstitutionalLayer
- IDecisionEngine, IEmotionalSupport (новые для experimental)

LeyaOS проверяет isinstance при создании компонентов (частично). web_interface использует hasattr + публичные методы — decoupling работает.

### 11. experimental/decision_engine.py (интегрирован 30 июня, но debt)
**Purpose:** Deterministic fast decision-making layer (“prefrontal cortex”). Rule-based, no LLM.

**Key Classes:**
- Decision (dataclass: use_tool, tool_name, tool_parameters, reasoning, confidence [0,1] normalized).
- DecisionEngine (implements IDecisionEngine): make_decision(stimulus, drive_state) → Decision или None (если confidence < threshold).

**Integration:** Level 0 в _cognitive_loop LeyaOS.py. Если confidence ≥ decision_engine_confidence_threshold (default 0.8 из ExperimentalConfig) и совпадает pattern (interesting requests, knowledge-seeking Wikipedia/GitHub/DuckDuckGo, social Reddit, autonomy read_soul_file) — возвращает tool decision. Иначе None → переход на LLM levels.

**Status:** Активно используется. Не dead code. Остальные файлы в experimental/ (emotional_support.py и др.) — conditional через config, но без полного ADR.

### 12. Другие модули
- exceptions.py: Полная иерархия Leya*Error.
- state_persistence.py: load/save drives + homeostasis (JSON/pickle).
- system_metrics.py: psutil метрики → drives.
- tool_generator.py: регистрация + LLM-генерация инструментов.
- environment.py + web_interface/{server.py, web_environment.py}: Абстракция + FastAPI/WebSocket. Использует публичные методы.
- experimental/ остальные: изолированы/conditional, technical debt.

## Soul / Личность
leya_soul/{personality.txt, rules.txt, values.txt} — загружаются в промпты. leya_personality.json / leya_goals.json — динамические. soul_crypto.py — experimental.

## Persistence и Data (актуально 1 июля)
- leya_brain/: chroma.sqlite3, memory_state.json + .hmac (HMAC-SHA256, atomic, version 3, fsync, _sync_chroma_from_memory).
- StatePersistence: drives + homeostasis между сессиями.
- .gitignore корректно игнорирует leya_brain/, .env, логи, *.hmac.

## LLM Integration (актуально 1 июля)
Только Ollama (/api/chat). Модель и параметры в LeyaConfig + Modelfile. Промпты на русском. Circuit Breaker + partial retry + generate() wrapper. Broad except last resort. Fallback при OPEN.

## Известные ограничения текущей архитектуры (честный список на 1 июля 2026 — verified ревью raw-кода)

**Исправленные / улучшенные (подтверждено кодом 30 июня):**
- Pickle → JSON + HMAC atomic + fsync + version + sync.
- Interfaces расширены (включая IDecisionEngine) и используются.
- experimental/ частично интегрирован (DecisionEngine как Level 0).
- LeyaOS использует Protocol checks (частично) + реальную GWT.
- Большинство except — специфичные (иерархия).
- Graceful shutdown и protected tasks реализованы.
- Config полная загрузка + robust parsing.
- Thinker: Pydantic defaults + улучшенный repair_json + tiktoken primary + relevance truncate.
- Request handling: LLM classifier + multi-level cognitive_loop.
- LLM client: generate() + partial retry + Circuit Breaker.
- Memory consistency: _sync_chroma_from_memory.

**Остающиеся (требуют v3.1, verified баги/долг):**
1. **Broad except Exception**: Остался в llm_client._chat_impl и memory._save_state (last resort). Duplicate dead code в llm_client.
2. **experimental/ модули**: DecisionEngine интегрирован, но без ADR. Остальные файлы — dead code / риск. Требуется фаза археологии + integrate/deprecate/delete.
3. **HMAC key**: Только warning в config, не hard fail. Риск integrity в dev-режиме.
4. **Тесты**: Покрытие core-логики (новые уровни cognitive_loop, repair_json edge cases Unicode/nested/escape, JSON+HMAC tampering, LTP/spreading, Protocol, DecisionEngine rules, RequestClassifier) недостаточно. Нет CI / property-based.
5. **Однопоточный event loop**: Все фоновые задачи в одном asyncio. Нет настоящей параллельности.
6. **Отсутствие долгосрочного планирования**: Цели только homeostasis + workspace + DecisionEngine. Нет иерархии выше.
7. **SyncReport**: Примитивный, нет dataclass, агрегация слабая.
8. **CognitiveOutput / repair_json**: Defaults помогают, но repair_json — эвристика (риск edge cases). Нет полной схемы для tool_call.
9. **Retry LLM**: Только частичный (timeout/connection). Нет для других ошибок.
10. **Жёсткая привязка к Ollama**: Нет fallback на другие провайдеры.
11. **Web interface**: Decoupling работает. Protocol checks частичные.
12. **Документация**: Отставала от кода 30 июня (исправлено в этой версии).

**Общий вывод анализа (1 июля 2026):** Архитектура значительно улучшена 30 июня и соответствует заявленной биологической модели в полном объёме (LTP/LTD details с spreading, emotional_boost, consolidation, drives metabolism + RPE + predicted_disbalance, Global Workspace competition + inhibition, spontaneous thoughts, self-model, constitutional constraints, DecisionEngine как rule-based fast layer). Сложность — deliberate feature для моделирования внутренней жизни. Однако residual issues v3.0 (broad except, tests, experimental debt, HMAC, single loop, long-term goals) частично остаются. Система стабильнее, но остаётся исследовательским прототипом. Перед серьёзным использованием — завершить remaining v3.1.

## Рекомендации по развитию (без упрощения)

**Сохранить и углубить (приоритет):**
- Биологическую модель во всей полноте (LTP via similarity ≥0.7 + strengthen + spreading, emotional_boost modulating decay, consolidation, drives metabolism + RPE + predicted_disbalance, Global Workspace submit/select_winner/inhibition/decay, spontaneous thoughts, self-model, constitutional + sandbox, DecisionEngine rule-based fast prefrontal).
- Богатство внутреннего опыта, автономию гомеостаза, competition в workspace, multi-level cognitive_loop.
- Инструментальную автономию + sandbox.
- Устойчивость (Circuit Breaker + partial retry, atomic JSON+HMAC+fsync, specific exceptions, safe tasks, graceful shutdown).

**Улучшить (v3.1 приоритет — verification + bugfix remaining):**
1. Убрать/минимизировать broad except в llm_client и memory (конкретные except + always raise specific).
2. Завершить ADR для experimental/ (integrate DecisionEngine/EmotionalSupport если усиливают; deprecate/delete остальные с обоснованием — запрет на упрощение).
3. Property-based тесты для repair_json, atomic persistence (tampering, hmac fail, version), LTP/spreading, cognitive_loop уровней 0-1, Protocol compliance, DecisionEngine rules, RequestClassifier. Coverage >85% core. CI.
4. Сделать HMAC key жёстко обязательным (LeyaConfigError при слабом/отсутствующем, min 32 chars).
5. Улучшить SyncReport (dataclass + aggregation) и consistency.
6. Усилить repair_json для edge cases + рассмотреть optional поля в CognitiveOutput.
7. Расширить retry в OllamaClient.
8. Завершить Protocol checks в LeyaOS.
9. Добавить тесты на изменения 30 июня.
10. Обновить документацию (выполнено в этой версии).

**v3.2+:** Долгосрочное планирование (иерархическая goal stack), multi-agent (с сохранением индивидуальной внутренней жизни), визуализация в web (memory graph, drives dynamics, workspace competition live), более глубокий active inference / predictive processing в drives/homeostasis, расширение DecisionEngine patterns и tool integration.

**Принцип:** Сложность — это не баг, а feature для моделирования внутренней жизни. **Не упрощать** до RAG-агента, простого tool-calling чат-бота или state machine. Любой рефакторинг должен усиливать биологическую правдоподобность, автономию и богатство внутреннего опыта. Запрет на упрощение без веской причины, подтверждённой анализом влияния на drives, memory LTP/LTD, homeostasis, workspace, spontaneous thoughts и self-model.

---

**Примечание:** Документ полностью переписан 1 июля 2026 на основе детального разбора всех .py файлов, raw content после коммита 30 июня 2026, подтверждения/опровержения claims из предыдущих версий и сравнения с реальным поведением кода (включая verified fixes generate()/retry/GWT/DecisionEngine/Pydantic defaults/config completeness и remaining issues broad except/experimental debt/HMAC/tests/single loop). 

Предыдущие версии ARCHITECTURE.md (включая анализ 29 июня) частично устарели. Эта версия синхронизирована с текущим состоянием.

Для уточнений по методам — обращайтесь к исходному коду + этой документации + плану исправлений v3.1 (фокус на verification remaining issues + preserve biological fidelity).
