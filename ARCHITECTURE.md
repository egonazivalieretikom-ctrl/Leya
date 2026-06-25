# Архитектура LeyaOS — Цифровое Сознание Леи (Версия 2.0)

**Дата обновления:** 25 июня 2026 (на основе полномасштабного код-ревью)  
**Статус:** Актуальная реконструкция + анализ текущей реализации после исправления критических багов.

Этот документ описывает когнитивную архитектуру в её текущем состоянии. Архитектура остаётся глубоко биологически вдохновлённой (Global Workspace Theory, активный inference элементы, теории мотивации, энграммы/синапсы, консолидация во сне, Эббингауз). **Никаких упрощений не производилось.**

## Философия

Лея — не ассистент и не RAG-бот. Это личность с внутренней жизнью:
- Мотивационные драйвы с метаболизмом и reward prediction error.
- Автономный гомеостаз (цели генерируются изнутри).
- Память с забыванием, усилением и консолидацией.
- Рефлексия и спонтанные мысли.
- Само-модель («кто я»).
- Конституциональные ограничения.

Система стремится к **пониманию** через взаимодействие внутреннего мира с внешними стимулами и инструментами.

## Высокоуровневая диаграмма потока данных

```
Внешний стимул (user / homeostasis / workspace)
        │
Environment.listen() → LeyaOS.perceive(stimulus)
        │
├──► Drives.evaluate_stimulus() + apply_deltas() + RPE
│
├──► Memory.retrieve_context() (с фильтром retention_strength + strengthen_synapses)
│
├──► self_model = Memory.get_self_model_context()
│
├──► (опционально) Homeostasis.generate_goal(...) → WorkspaceProposal
│
▼
CoreThinker.generate_plan()
   ├── _build_cognitive_prompt (soul + drives_state + memory_context + self_model + tools + tool_context)
   ├── LLM call (Ollama /api/chat + format=json)
   └── parse → CognitiveOutput dataclass
        (internal_monologue, response, action_intent, self_reflection)
        │
Post-processing
├── Memory.store_perception(...) + _form_synaptic_connections
├── Memory.update_self_model(self_reflection)
├── Drives.satisfy / apply_satisfaction (с RPE)
├── Reflection.process_action(...)
│
Environment.send_message(response) + broadcast_thought(...) + update_drives(...) + ...
        │
Фоновые циклы (asyncio.create_task)
├── drives.background_metabolism()
├── reflection.background_consolidation()
├── _homeostasis_loop() (generate_goal → tool / rest → perceive обратно)
├── _workspace_loop() (select_winner → perceive)
├── _spontaneous_thought_loop()
├── _system_metrics_loop()
└── _broadcast_state_loop()
```

## Основные модули (leya_core/)

### 1. drives.py — Система драйвов
- DriveType Enum + Drive dataclass (current, tension, target, action_values).
- evaluate_stimulus, apply_deltas, apply_satisfaction, calculate_rpe.
- get_predicted_disbalance, get_internal_state_prompt.
- background_metabolism (постепенное нарастание tension по rates из config).
- update_from_system_metrics.

### 2. homeostasis_engine.py — Гомеостаз
- generate_goal / generate_goal_from_gap (на основе drive_state, predicted_state, recent_episodes, action_values).
- extract_key_facts, extract_new_terms (LLM).
- mark_as_researched, add_dynamic_keywords.
- current_goal, last_action_time, rest_period.
- RPE feedback loop после выполнения инструмента.

### 3. memory.py — Память (ядро сложности)
**Модели данных (датаклассы):**
- MemoryType (EPISODIC / SEMANTIC)
- Engram (id, content, memory_type, timestamp, retention_strength, emotional_boost, retrieval_count, last_retrieved, consolidation_level, metadata)
- Synapse (source_id, target_id, weight, activation_count)

**Хранение:**
- chromadb.PersistentClient (один экземпляр в __init__)
  - episodic_collection
  - semantic_collection
- memory_state.pkl (pickle: engrams dict, synapses dict, self_model str) — с планом hardening.

**Ключевые методы (все async где возможно):**
- store_perception → Engram + embedding (to_thread) + _form_synaptic_connections (LTP)
- retrieve_context → semantic search + retention filter + emotional boost + _strengthen_synapses (LTP)
- store_fact (SEMANTIC)
- consolidate_memories (replay + LLM _extract_semantic_facts + _forget_weak_memories)
- update_self_model, get_self_model_context
- get_recent_spontaneous_thoughts, get_recent_episodes (публичный рекомендуется)
- _save_state / _load_state (pickle)

**Биологическая модель:** Забывание по Эббингаузу, эмоциональное усиление, консолидация во сне, LTP/LTD-подобные механизмы.

### 4. thinker.py — Когнитивный планировщик
- CoreThinker(llm_client, soul_manager)
- _load_soul() (из soul_manager или файлов leya_soul/)
- _build_cognitive_prompt (многосекционный промпт на русском)
- generate_plan → LLM (require_json=True) → _parse_json_safely (markdown cleanup + regex + field extraction) → CognitiveOutput dataclass (__post_init__ валидация action_intent)
- _generate_fallback_response

### 5. reflection.py — Мета-когниция
- process_action
- generate_spontaneous_thought
- background_consolidation
- is_sleeping флаг

### 6. global_workspace.py
- WorkspaceProposal (source, content, action_type, priority, urgency, drive_relevance, metadata)
- submit, select_winner, get_focus, clear_expired

### 7. Другие модули
- constitutional.py — правила
- tool_generator.py + ToolRegistry (в environment)
- environment.py + web_environment.py (broadcast hooks)
- state_persistence.py, system_metrics.py, soul_crypto.py
- config.py (полноценные dataclass с __post_init__ валидацией + LeyaConfig.from_env())

## Soul и Личность
- leya_soul/personality.txt, rules.txt, values.txt — загружаются в промпты.
- laya_personality.json, leya_goals.json — динамические параметры.
- broadcast_soul_update для live-обновления в UI.

## Persistence
- leya_brain/ (Chroma + pickle) — **требует строгого .gitignore**
- StatePersistence (JSON/pickle drives + homeostasis)

## LLM Integration
- Только Ollama HTTP API.
- settings.ollama.* (model, base_url, timeout, temperature и т.д.)
- Системный промпт всегда на русском.

## Продвинутый Веб-Интерфейс (технические детали)

WebEnvironment предоставляет полный набор broadcast-методов:
- broadcast_thought(thought_type, content)
- update_drives(drive_state)
- update_self_model(self_model)
- update_memory(memory_info)
- broadcast_state(state)
- broadcast_soul_update(soul_files)
- send_message / handle_user_message

Текущий server.py реализует WebSocket broadcast и REST, но frontend — минималистичный hardcoded HTML.

**Рекомендуемая архитектура продвинутого UI (см. также NEW_README_LeyaOS.md):**
- Отдельные JS-модули для каждого broadcast-типа.
- Реал-тайм визуализация:
  - Drives: Chart.js radar + line history.
  - Workspace: live cards + priority queue.
  - Memory: vis.js force-directed graph (узлы=Engram, рёбра=Synapse с weight).
  - Thoughts: виртуализированный feed с типизацией и timeline.
- State management: подписка на WS + локальный кэш последних N сообщений.
- Интеграция с Memory Explorer: при retrieve_context — подсветка активированных engrams в графе.

Это позволяет полностью отобразить сложность когнитивного цикла в реальном времени.

## Известные ограничения текущей реализации (после ревью)

- Много defensive `hasattr` и широких except (требует Protocol-интерфейсов).
- Прямой доступ к episodic_collection (нужен публичный API).
- Pickle (нужен hardening).
- Отсутствие тестов.
- Базовый UI (не использует все broadcast'ы).
- Потенциальные проблемы с размером промптов и token limit.
- Repo hygiene (leya_brain в git).

## Рекомендации по развитию (без упрощения)

Сохранить и углубить:
- Биологическую правдоподобность (добавлять детали LTP/LTD, predictive processing, более сложные RPE).
- Богатство внутреннего опыта (больше типов драйвов, эмоциональных состояний, многоуровневая консолидация).
- Инструментальную автономию и tool generation.
- **Продвинутый UI** как полноценное «окно в сознание» (графики, графы памяти, визуализация workspace и homeostasis).

Не превращать в обычный чат-бот или упрощённый агент.

---

**Документ создан на основе детального анализа исходного кода (LeyaOS.py ~900+ строк после исправлений, все модули leya_core, web_interface, config).**  
Оригинальный ARCHITECTURE.md в репозитории был пустым/нечитаемым — эта версия заменяет его.

Для вопросов по конкретным классам/методам или генерации диаграмм (Mermaid/PlantUML) — обращайтесь.
