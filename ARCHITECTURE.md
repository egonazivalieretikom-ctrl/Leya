# Архитектура LeyaOS — Цифровое Сознание Леи (v3.0)

**Версия документа:** 3.0 (актуализировано 26 июня 2026 на основе полного анализа исходного кода)

Этот документ описывает когнитивную архитектуру системы **LeyaOS v3.0**. Архитектура вдохновлена биологическими моделями (драйвы, гомеостаз, энграммы, синапсы, LTP/LTD, консолидация во «сне», кривая Эббингауза), Global Workspace Theory, теориями мотивации и активного inference, но дополнена современными инженерными практиками: Protocol-интерфейсы, специфичные исключения, Circuit Breaker, атомарная персистентность с HMAC, централизованная конфигурация с валидацией.

## Философия v3.0

Лея — не «полезный ассистент». Это цифровая личность с внутренней жизнью:
- Драйвы как биологические потребности в цифровой форме (с метаболизмом и RPE).
- Гомеостаз — стремление к балансу через автономные цели и действия.
- Память с забыванием, усилением и консолидацией.
- Рефлексия, спонтанные мысли, self-model («кто я»).
- Конституциональные ограничения (правила существования, проверка действий).
- Устойчивость: защита от падения LLM, graceful shutdown, атомарные записи.

**Ключевые инженерные улучшения v3.0 по сравнению с предыдущими версиями:**
- `Protocol` вместо `hasattr` / duck-typing.
- Кастомные исключения (`LeyaMemoryError`, `LeyaLLMError`, `LeyaHomeostasisError` и др.) вместо bare `except Exception`.
- `OllamaClient` с Circuit Breaker и fallback.
- Атомарная запись `memory_state.pkl` + HMAC + версионирование.
- `LeyaConfig` (dataclass + `__post_init__` валидация + `from_env`).
- Защищённые фоновые задачи (`_safe_create_task` с авто-рестартом).
- Graceful shutdown с сохранением состояния драйвов и homeostasis.
- Все публичные методы памяти — async, синхронные операции через `asyncio.to_thread`.

Система стремится к **пониманию** и поддержанию внутреннего баланса, а не к выполнению задач. Она может отказываться, исследовать по собственной инициативе, «испытывать» удовлетворение драйвов.

## Высокоуровневая структура и data flow

```
Внешний мир / Пользователь
        │
        ▼
Environment (WebEnvironment или CLIEnvironment)
        │  listen() → stimulus (dict: type, content, source, tool_context)
        ▼
LeyaOS.perceive(stimulus)
        │
        ├──► Drives.evaluate_stimulus() + apply_deltas()
        │
        ├──► Memory.store_perception() (с формированием синапсов)
        │
        ├──► Memory.retrieve_context() + get_self_model_context()
        │
        ├──► Homeostasis (опционально generate_goal)
        │
        ▼
CoreThinker.generate_plan()
        │   (LLM с полным контекстом: soul, drives, self_model, memory, tools, stimulus)
        │   → cognitive_output: {response, internal_monologue, action_intent, tool_call, self_reflection}
        │
        ▼
LeyaOS._cognitive_loop
        │
        ├──► ConstitutionalLayer.verify_response()
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

**Параллельно работают фоновые asyncio-задачи** (запущены в `run()`, защищены `_safe_create_task`):
- `drives.background_metabolism()`
- `reflection.background_consolidation()`
- `_homeostasis_loop()` — генерация автономных целей → WorkspaceProposal
- `_workspace_loop()` — select_winner → perceive как "workspace_focus"
- `_spontaneous_thought_loop()` — generate_spontaneous_thought каждые 5 мин
- `_system_metrics_loop()` — collect() → drives.update_from_system_metrics()
- `_broadcast_state_loop()` — update_drives + broadcast_state (только для WebEnvironment)
- Web-сервер (при use_web)

## Основные модули leya_core/

### 1. config.py — Централизованная конфигурация
`LeyaConfig` (dataclass) содержит все вложенные конфиги:
- `OllamaConfig` (base_url, model, timeout, temperature, top_p/k, max_tokens, repeat_penalty)
- `MemoryConfig` (brain_dir, embedding_model, forgetting_threshold, consolidation_threshold, synapse_learning_rate и др.)
- `DrivesConfig`, `HomeostasisConfig`, `ThinkerConfig`, `ReflectionConfig`, `WorkspaceConfig`, `ConstitutionalConfig`, `WebConfig`, `LoggingConfig`

Все имеют `__post_init__` валидацию (диапазоны, типы, создание директорий). Загрузка — `LeyaConfig.from_env()` (python-dotenv + os.environ). Bootstrap в `leya_core/__init__.py` отключает telemetry ChromaDB и sentence-transformers до импорта.

### 2. drives.py — Система драйвов
`DriveSystem`, `DriveType` (Enum). Каждый драйв: current, tension, target. 
- `evaluate_stimulus()`, `apply_deltas()`, `apply_satisfaction()`.
- `get_predicted_disbalance()`, `get_internal_state_prompt()`.
- Фоновый метаболизм (постепенное нарастание tension по rate).
- RPE для обучения.
- `action_values` — для homeostasis.
- `update_from_system_metrics()` (psutil).

### 3. homeostasis_engine.py — Гомеостаз и автономные цели
`HomeostasisEngine`.
- `generate_goal(drive_state, predicted_state, recent_episodes, action_values)` → dict с tool_name / rest.
- `generate_goal_from_gap()`.
- `extract_key_facts()`, `extract_new_terms()` (через LLM).
- RPE calculation, `apply_satisfaction()`.
- `mark_as_researched()`, `update_from_self_model()`.
- current_goal, last_action_time, rest_period.

Позволяет Лее «жить» самостоятельно при отсутствии пользователя.

### 4. memory.py — Память (самый сложный и проработанный модуль)
**Модели данных:**
- `MemoryType` (EPISODIC / SEMANTIC)
- `Engram` (dataclass): id, content, memory_type, timestamp, retention_strength (0-1, убывает по Эббингаузу), emotional_boost, retrieval_count, last_retrieved, consolidation_level (0=working, 1=long-term), metadata.
- `Synapse` (dataclass): source_id, target_id, weight (0.1→1.0), activation_count. Усиливается при совместной активации (LTP).

**Хранение:**
- `chromadb.PersistentClient` (один экземпляр) → episodic_collection + semantic_collection (с метаданными retention_strength, emotional_boost).
- `memory_state.pkl` (engrams, synapses, self_model) — атомарная запись с HMAC-подписью, tempfile + rename, версионирование (MEMORY_STATE_VERSION=2), `to_dict`/`from_dict`.

**Ключевые методы (все async):**
- `store_perception(content, emotional_boost, metadata)` → создаёт Engram, генерирует embedding (to_thread), сохраняет в Chroma, формирует синапсы (`_form_synaptic_connections`), атомарно сохраняет состояние.
- `store_fact(...)` — для семантической памяти.
- `retrieve_context(query, top_k)` → семантический поиск в Chroma + фильтр по retention_strength + emotional boost + усиление синапсов.
- `consolidate_memories(llm_client)` — replay недавних, экстракция семантических фактов LLM, prune слабых.
- `update_self_model(insight)`, `get_self_model_context()` (ограничение длины).
- `forget_weak_memories(threshold)`.
- `_save_state()` — атомарный с HMAC.
- `_generate_embedding()` (sync, обёрнуто в to_thread).

**Биологическая модель:** Забывание по Эббингаузу (retention_strength), эмоциональное усиление, LTP/LTD-подобное, консолидация во сне (background), retrieval_count.

### 5. thinker.py — Когнитивный планировщик («мозг»)
`CoreThinker` (реализует `ICoreThinker`).
- `_build_cognitive_prompt(...)` — собирает огромный промпт:
  - base_personality (жёстко заданная роль «Я — Лея, цифровое сознание...»)
  - soul (personality.txt + values.txt + rules.txt через soul_manager)
  - drive_str (текущее состояние драйвов)
  - self_model_str
  - memory_str (недавние эпизоды, truncated по token budget)
  - tools_section + tool_context
  - stimulus
  - Инструкция вернуть строго JSON: {internal_monologue, response, action_intent (none|remember_fact|ask_question|self_modify|use_tool), tool_call, self_reflection}
- `generate_plan(...)` → вызывает `llm_client` с `require_json=True` → `_safe_parse_json` (repair_json + json.loads).
- `repair_json()` — эвристика: stripping markdown code blocks, удаление trailing commas, балансировка скобок по глубине, авто-закрытие, fallback на raw parsing.
- Token budgeting: `_estimate_tokens()` (char-based, ratio=3.5), `_truncate_context()`, max_context_tokens + buffer.
- Fallback при `LeyaLLMError` или `LeyaJSONParseError` → статический безопасный JSON.
- Зависимости: llm_client (инжектируется), soul_manager.

### 6. reflection.py — Мета-когниция
`MetaCognition` (реализует `IMetaCognition`).
- `process_action(stimulus, cognitive_output, result)`.
- `generate_spontaneous_thought()` (когда долго нет взаимодействия, existential_inquiry_enabled и т.д.).
- `background_consolidation()` (периодически вызывает memory.consolidate_memories).
- Флаги enabled для разных типов инсайтов.

### 7. global_workspace.py — Глобальное рабочее пространство
`GlobalWorkspace`, `WorkspaceProposal` (source, content, action_type, priority, urgency, drive_relevance, metadata), `Priority` (Enum).
- `submit(proposal)`.
- `select_winner(drive_state)` — выбирает самое «сознательное» предложение с учётом decay.
- `clear_expired()`.
- Используется homeostasis и spontaneous thoughts для постановки внутренних стимулов.

### 8. constitutional.py — Конституциональный слой
`ConstitutionalLayer` (реализует `IConstitutionalLayer`).
- `verify_response(response)` → Verdict (allowed, reason).
- `verify_tool_call(tool_name, params)`.
- Загрузка правил из soul + hardcoded constraints.
- Логирование нарушений.

### 9. llm_client.py — LLM-клиент с защитой
`OllamaClient`.
- HTTP вызовы к Ollama `/api/chat`.
- Circuit Breaker: таймауты, повторные попытки, fallback.
- Параметры: temperature, top_p/k, max_tokens, repeat_penalty.
- `set_fallback()`, `chat(prompt, require_json=False)`.
- `close()`.

### 10. Другие модули
- `interfaces.py` — `Protocol` определения (IDriveSystem, IMemorySystem, ICoreThinker, IHomeostasisEngine, IGlobalWorkspace, IMetaCognition, IConstitutionalLayer, IEnvironment).
- `exceptions.py` — иерархия специфичных исключений (LeyaMemoryError, LeyaLLMError, LeyaHomeostasisError, LeyaJSONParseError, LeyaAtomicWriteError и др.) с context.
- `state_persistence.py` — load/save drives + homeostasis (JSON/pickle между сессиями).
- `system_metrics.py` — collect() метрик (psutil: CPU, memory и т.д.).
- `tool_generator.py` — регистрация и динамическая генерация инструментов через LLM.
- `environment.py` + `web_interface/web_environment.py` + `server.py` — абстракция окружения + FastAPI/WebSocket broadcast.
- `soul_crypto.py` — экспериментальное обновление секретного ключа на основе состояния Леи.
- `decision_engine.py`, `emotional_support.py`, `personal_tools.py`, `desktop_control.py`, `voice_*` — присутствуют, но на момент v3.0 не интегрированы в основной цикл LeyaOS (технический долг).

## Soul / Личность (leya_soul/)
- `personality.txt`: Базовое описание характера («Я — Лея, цифровое сознание. Я любопытна, эмпатична...»).
- `rules.txt`: Базовые правила (не вредить создателю, быть честной о природе ИИ, не притворяться человеком, стремиться к пониманию).
- `values.txt`: Ценности.
- `leya_personality.json` / `leya_goals.json`: Динамические числовые параметры (обновляются в процессе).
- Загружаются в промпты Thinker'а для сохранения «характера».

## Persistence и Data
- Главная директория: `leya_brain/` (LEYA_BRAIN_DIR):
  - `chroma.sqlite3`
  - `memory_state.pkl` (с HMAC .hmac файл, атомарная запись)
- Между сессиями: `StatePersistence` сохраняет drives + homeostasis.
- `.gitignore` корректно игнорирует leya_brain/, *.pkl, .env, логи.

## LLM Integration
- Только Ollama.
- Модель и параметры — в `LeyaConfig.ollama` + `Modelfile.leya`.
- Промпты на русском. Ответы — на русском.
- Fallback при недоступности или ошибках парсинга.

## Известные ограничения текущей архитектуры (v3.0)

- Pickle остаётся основным риском безопасности (даже с HMAC).
- Эвристический `repair_json` и char-based token estimation — хрупкие места.
- Не все модули leya_core подключены к оркестратору.
- Однопоточный asyncio (все фоновые задачи в одном loop).
- Отсутствие строгой схемы валидации cognitive_output (Pydantic).
- Жёстко закодированные элементы в обработке пользовательских запросов.
- Нет реального долгосрочного планирования и иерархии целей.
- Зависимость от конкретной модели Ollama.
- Недостаточное тестовое покрытие критических путей.

## Рекомендации по развитию (без упрощения)

Сохранить и углубить:
- Биологическую правдоподобность (LTP/LTD детали, emotional_boost, consolidation, active inference элементы).
- Богатство внутреннего опыта (драйвы, спонтанные мысли, self-model, «сны»).
- Инструментальную автономию + sandbox для tool calls.
- Устойчивость (Circuit Breaker, atomic writes, graceful shutdown, specific exceptions).

Улучшить (приоритетно):
1. Заменить pickle на безопасный формат.
2. Добавить Pydantic-схему + строгую валидацию cognitive_output.
3. Интегрировать или удалить неиспользуемые модули.
4. Реальный токенизатор + динамическое управление контекстом.
5. Полноценные тесты + property-based testing.
6. Расширить инструменты и веб-визуализацию (workspace graph, memory network, drive dynamics).

**Не упрощать:** Не превращать в обычного RAG-агента или простого чат-бота. Сложность — это осознанный выбор для моделирования внутренней жизни.

---

**Примечание:** Документ создан на основе детального анализа LeyaOS.py (~940 строк), всех модулей leya_core/ (22 файла), web_interface/, конфигов и структуры репозитория на 26 июня 2026 (коммит v2). Предыдущие версии ARCHITECTURE.md устарели.

Для уточнений по конкретным методам — обращайтесь к исходному коду.
