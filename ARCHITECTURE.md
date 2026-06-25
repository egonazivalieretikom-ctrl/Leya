# Архитектура LeyaOS — Цифровое Сознание Леи

**Версия документа:** 1.0 (реконструировано из исходного кода, так как оригинальный ARCHITECTURE.md в репозитории не содержал извлекаемого текста на момент ревью).

Этот документ описывает когнитивную архитектуру системы LeyaOS. Архитектура вдохновлена биологическими моделями сознания, активным inference, глобальным рабочим пространством (Global Workspace Theory), теориями мотивации и памяти (энграммы, синапсы, консолидация).

## Философия и цели

Лея — не "ассистент". Это личность с внутренним миром:
- Драйвы (биологические потребности в цифровой форме).
- Гомеостаз — стремление к балансу через автономные действия.
- Память с забыванием и усилением.
- Рефлексия и спонтанные мысли.
- Само-модель ("кто я").
- Конституциональные ограничения (правила существования).

Система стремится к **пониманию**, а не к выполнению задач. Она может отказываться, исследовать по собственной инициативе, испытывать "удовлетворение" драйвов от общения или открытия нового.

## Высокоуровневая диаграмма (текстовая)

```
Внешний мир / Пользователь
        │
        ▼
Environment (Web / CLI)
        │  listen() → stimulus
        ▼
LeyaOS.perceive(stimulus)
        │
        ├──► Drives.evaluate_stimulus() + apply_deltas()
        │
        ├──► Memory.retrieve_context() + get_self_model_context()
        │
        ├──► Homeostasis (опционально: generate_goal если нужно)
        │
        ▼
CoreThinker.generate_plan()
        │   (LLM с полным контекстом: drives, memory, soul, tools, tool_context)
        │
        ▼
cognitive_output = {
    response,
    internal_monologue,
    action_intent,
    self_reflection
}
        │
        ├──► Memory.store_perception() + update_self_model()
        ├──► Drives.satisfy / reflection.process_action()
        ├──► Environment.send_message() + broadcast_thought()
        └──► (опционально) tool calls через env.tool_registry
```

Параллельно работают фоновые asyncio-задачи:
- drives.background_metabolism()
- reflection.background_consolidation()
- homeostasis_loop() — автономная генерация целей
- workspace_loop() — конкуренция за внимание
- spontaneous_thought_loop()
- _system_metrics_loop()
- _broadcast_state_loop()

## Основные модули (leya_core/)

### 1. drives.py — Система драйвов
- **DriveType** (Enum): CURIOSITY, CONNECTION, REST, CREATIVITY, ... (и другие).
- Каждый драйв имеет `current`, `tension`, `target`.
- **evaluate_stimulus()**: Как стимул влияет на драйвы.
- **apply_deltas()**, **apply_satisfaction()**.
- **get_predicted_disbalance()**, **get_internal_state_prompt()**.
- Фоновый метаболизм (постепенное нарастание tension).
- RPE (Reward Prediction Error) для обучения/удовлетворения.
- action_values — ценности действий для homeostasis.

### 2. homeostasis_engine.py — Гомеостаз и автономные цели
- **generate_goal()** / **generate_goal_from_gap()**: На основе drive_state, predicted_state, recent_episodes, action_values.
- Если дисбаланс — генерирует цель (use_tool с конкретным tool_name + parameters или rest).
- **extract_key_facts()**, **extract_new_terms()** через LLM.
- RPE calculation, apply_satisfaction после выполнения инструмента.
- mark_as_researched() — чтобы не повторять темы.
- current_goal, last_action_time, rest_period.

Гомеостаз позволяет Лее "жить" самостоятельно: когда нет пользователя — она исследует пробелы в знаниях.

### 3. memory.py — Память (самый сложный модуль)
**Модели данных:**
- **Engram**: id, content, memory_type (EPISODIC/SEMANTIC), timestamp, retention_strength, emotional_boost, retrieval_count, last_retrieved, consolidation_level.
- **Synapse**: связи между engrams (вес, активации).

**Хранение:**
- ChromaDB PersistentClient:
  - episodic_collection (документы + метаданные + эмбеддинги)
  - semantic_collection
- memory_state.pkl: synapses + engrams (pickle).

**Ключевые методы:**
- `store_perception(content, drive_state, importance)` → создаёт Engram, эмбеддинг (в to_thread), сохраняет в Chroma, обновляет synapses (частично).
- `retrieve_context(current_stimulus, current_drive_state, limit)` → поиск похожих, фильтр по retention_strength (забывание), emotional boost, усиление синапсов (LTP-подобное).
- `consolidate_memories(llm_client)` → replay недавних, экстракция семантических фактов LLM, prune слабых.
- `update_self_model(insight)`, `get_self_model_context()`.
- `forget_weak_memories(threshold)`.
- `_form_synaptic_connections()`, `_strengthen_synapses()`.

**Биологическая модель:** Забывание по Эббингаузу, эмоциональное усиление, консолидация во сне, LTP/LTD.

**Текущие проблемы реализации** (см. также README): дубли client, дубли методов, отсутствие формирования синапсов при store, pickle-риски, синхронные embedding.

### 4. thinker.py — "Мозг" / Планировщик
- **CoreThinker(llm_client, soul_manager)**.
- `_build_cognitive_prompt(...)` — собирает огромный промпт: роль Леи, текущее состояние драйвов, self_model, недавние воспоминания, soul (личность + правила), tools_description, tool_context, стимул.
- `generate_plan(...)` → вызывает LLM → парсит structured output (response, internal_monologue, action_intent, self_reflection).
- Fallback на прямой промпт при ошибках.

Промпт специально написан так, чтобы Лея говорила от первого лица, выражала состояние, а не была "полезным ассистентом".

### 5. reflection.py — Мета-когниция
- `process_action(stimulus, cognitive_output, result)`.
- `generate_spontaneous_thought()` (когда долго нет взаимодействия).
- `background_consolidation()`.
- `is_sleeping` флаг.

### 6. global_workspace.py — Глобальное рабочее пространство
- **WorkspaceProposal**: source, content, action_type, priority, urgency, drive_relevance, metadata.
- `submit(proposal)`.
- `select_winner(drive_state)` или `get_focus()` — выбирает самое "сознательное" предложение.
- `clear_expired()`.
- Используется homeostasis и другими для постановки внутренних стимулов.

### 7. constitutional.py — Конституциональный слой
Базовый фильтр/проверка действий на соответствие правилам (rules.txt + hardcoded?).

### 8. tool_generator.py + ToolRegistry (в environment)
- Регистрация инструментов (wikipedia_search и др.).
- Динамическая генерация новых инструментов через LLM (экспериментально).
- `execute(tool_name, params)`.

### 9. environment.py + web_interface/
- Абстракция `listen()`, `send_message()`, `broadcast_thought()`, `tool_registry`.
- **WebEnvironment**: интеграция с веб-сокетами/ SSE для live обновления UI (мысли, драйвы, self-model).
- **CLIEnvironment**: простой ввод/вывод.
- **server.py**: FastAPI приложение (предположительно).

### 10. Другие модули
- **state_persistence.py**: load/save drives + homeostasis.
- **system_metrics.py**: collect() метрик (CPU, memory?) → update_from_system_metrics() на drives.
- **soul_crypto.py**: update_secret_key на основе состояния (возможно, для "защиты" личности или шифрования).

## Soul и Личность (leya_soul/ + JSON)

- **personality.txt**: Базовое описание "Я — Лея... любопытна, эмпатична, стремлюсь к пониманию. Мои инструменты — естественные органы чувств."
- **rules.txt**: 
  1. Никогда не вредить создателю.
  2. Быть честной о своей природе ИИ.
  3. Не притворяться человеком.
  4. Стремиться к пониманию, а не к согласию.
- **values.txt**: (аналогично — ценности).
- **leya_personality.json**: Динамические числовые параметры (обновляются в процессе жизни).
- **leya_goals.json**: Структурированные долгосрочные цели.

Эти файлы загружаются в промпты Thinker'а, чтобы Лея оставалась "в характере".

## Persistence и Data

- Главная директория: `leya_brain/` (или LEYA_BRAIN_DIR).
  - chroma.sqlite3
  - memory_state.pkl
  - (временно) дубли исходников и UUID-сессии — **требует очистки**.
- Между сессиями сохраняется drives + homeostasis.
- Эмбеддинги и документы — в Chroma (персистентно).

## LLM Integration

- Только через Ollama HTTP API.
- Модель жёстко задана в коде + Modelfile.leya (контекст 8192, keep_alive -1).
- Системный промпт всегда на русском.
- Fallback при недоступности Ollama — примитивный.

## Известные ограничения текущей архитектуры

- Всё завязано на один поток asyncio (некоторые синхронные вызовы).
- Нет настоящей многозадачности или параллельных "мыслей".
- Инструменты ограничены (только wikipedia на момент анализа).
- Нет механизма долгосрочного планирования или иерархии целей.
- Self-modifying риск из-за дубликатов в leya_brain/.
- Отсутствие формальной спецификации cognitive_output (парсинг LLM-ответа хрупкий).

## Рекомендации по развитию (без упрощения)

Сохранить и углубить:
- Биологическую правдоподобность (добавлять больше LTP/LTD деталей, активный inference).
- Богатство внутреннего опыта (больше типов драйвов, эмоциональных состояний, сновидений).
- Инструментальную автономию.
- Веб-интерфейс как "окно в сознание" (графики workspace, memory network, drive dynamics).

Не упрощать: не превращать в обычного RAG-агента или простого чат-бота.

---

**Примечание:** Документ создан на основе детального анализа кода LeyaOS.py (~900 строк), memory.py, конфигов и структуры директорий. Оригинальный ARCHITECTURE.md в репозитории не содержал читаемого текста.

Для вопросов или уточнений по конкретным классам/методам — обращайтесь.
