# LeyaOS — Цифровое Сознание Леи (v3.0)

**Оркестратор биологически вдохновлённого цифрового сознания**

LeyaOS — исследовательская Python-система, моделирующая внутреннюю жизнь цифрового агента с мотивациями (драйвами), автономной генерацией целей (гомеостаз), эпизодической и семантической памятью, глобальным рабочим пространством, мета-рефлексией и конституциональными ограничениями. 

**Версия 3.0** (актуальное состояние на 26 июня 2026) представляет собой существенно переработанную архитектуру по сравнению с предыдущими итерациями:
- Введены `Protocol`-интерфейсы для всех ключевых компонентов.
- Кастомные исключения вместо широких `except Exception`.
- `Circuit Breaker` в LLM-клиенте (OllamaClient).
- Атомарная персистентность состояния памяти с HMAC-подписью.
- Централизованная конфигурация `LeyaConfig` с валидацией.
- Защищённые фоновые asyncio-задачи с авто-рестартом.
- Graceful shutdown с сохранением состояния.
- Улучшенная модель памяти (Engram + Synapse + LTP/LTD + Ebbinghaus forgetting + консолидация).

Система запускается как автономный агент: «просыпается», воспринимает стимулы (пользователь или внутренние), запускает когнитивный цикл и действует (отвечает, вызывает инструменты, обновляет self-model). При отсутствии внешних стимулов гомеостаз и workspace генерируют собственные цели и спонтанные мысли.

**Важно:** Это исследовательский прототип. Система содержит известные ограничения (см. раздел «Известные ограничения и проблемы»). Не предназначена для production-использования, принятия критических решений или буквальной имитации сознания.

## Возможности (v3.0)

### Биологически мотивированная архитектура
- **DriveSystem** (`leya_core/drives.py`): Драйвы (CURIOSITY, CONNECTION, REST, CREATIVITY, UNDERSTANDING, AUTONOMY и др.) с метаболизмом (постепенное нарастание tension), RPE (Reward Prediction Error), предсказанием дисбаланса.
- **HomeostasisEngine** (`leya_core/homeostasis_engine.py`): Автономная генерация целей на основе дисбаланса драйвов, predicted_state, недавних эпизодов. Генерирует `use_tool` или `rest`. Поддержка `mark_as_researched`.
- **GlobalWorkspace** (`leya_core/global_workspace.py`): Конкуренция WorkspaceProposal за «внимание сознания». Приоритет по urgency, drive_relevance, decay.
- **SystemMetrics** → влияние метрик ОС/процесса на драйвы.

### Память (самый проработанный модуль)
- **MemorySystem** (`leya_core/memory.py`):
  - `Engram` (id, content, memory_type=EPISODIC/SEMANTIC, retention_strength, emotional_boost, retrieval_count, consolidation_level, metadata).
  - `Synapse` (source_id → target_id, weight, activation_count) — LTP-подобное усиление при совместной активации.
  - ChromaDB PersistentClient (episodic_memory + semantic_memory коллекции) + sentence-transformers (all-MiniLM-L6-v2).
  - Забывание по кривой Эббингауза + emotional_boost.
  - `store_perception` / `store_fact` (с формированием синапсов).
  - `retrieve_context` (семантический поиск + фильтр по retention_strength).
  - `consolidate_memories` (replay + экстракция фактов).
  - `update_self_model`, `get_self_model_context`.
  - `forget_weak_memories`.
  - **Атомарная запись** `memory_state.pkl` с HMAC-подписью и версионированием (MEMORY_STATE_VERSION=2). Все публичные методы async, синхронные операции через `asyncio.to_thread`.

### Когнитивный цикл и мышление
- **CoreThinker** (`leya_core/thinker.py`): `_build_cognitive_prompt` (soul + drives + self_model + memory_context + tools + stimulus). Вызов LLM с `require_json=True`. Робастный парсинг через `repair_json` (markdown stripping, trailing commas, brace balancing, auto-closure). Token budgeting + truncation. Fallback при ошибках.
- **MetaCognition / Reflection** (`leya_core/reflection.py`): `process_action`, `generate_spontaneous_thought`, `background_consolidation`.
- **ConstitutionalLayer** (`leya_core/constitutional.py`): Проверка ответов и tool calls по правилам (rules.txt + hardcoded constraints).

### Инструменты и окружение
- **ToolRegistry + ToolGenerator** (`leya_core/tool_generator.py` и environment).
- Встроенные инструменты (wikipedia_search и др.) + динамическая генерация.
- **Environment** абстракция: `WebEnvironment` (FastAPI + WebSocket broadcast мыслей, drives, self_model, state) и `CLIEnvironment`.
- `listen()` / `send_message()` / `broadcast_thought()`.

### Персистентность и инфраструктура
- `StatePersistence` (drives + homeostasis между сессиями).
- `LeyaConfig` (dataclass с вложенными конфигами и валидацией в `__post_init__`, загрузка из `.env` через python-dotenv).
- Graceful shutdown + сохранение состояния.
- Логирование в `leya_consciousness.log`.
- Bootstrap в `leya_core/__init__.py` (отключение telemetry ChromaDB и sentence-transformers до импорта).

### Soul / Личность
- `leya_soul/personality.txt`, `rules.txt`, `values.txt` — загружаются в промпты Thinker'а.
- `leya_personality.json`, `leya_goals.json` — динамические параметры.
- `soul_crypto.py` — обновление секретного ключа на основе состояния (экспериментально).

### LLM Integration
- Только Ollama HTTP API (`/api/chat`).
- Модель по умолчанию: `qwen2.5:14b-instruct-q3_K_M`.
- `Modelfile.leya` (num_ctx=8192, keep_alive=-1).
- `OllamaClient` с Circuit Breaker, timeout, temperature, top_p/k, repeat_penalty, fallback.
- Системный промпт и все текстовые поля — на русском языке.

## Быстрый старт

### Требования
- Python 3.10+
- Ollama (локально): `ollama serve`
- Модель: `ollama pull qwen2.5:14b-instruct-q3_K_M` (или совместимая; указана в `LeyaConfig`)
- Git

### Установка
```bash
git clone https://github.com/egonazivalieretikom-ctrl/Leya.git
cd Leya

python -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

**requirements.txt** (основные):
- chromadb>=0.4.0
- sentence-transformers>=2.2.0
- aiohttp>=3.8.0
- fastapi>=0.104.0
- uvicorn[standard]>=0.24.0
- pydantic>=2.0.0
- psutil>=5.9.0
- numpy>=1.24.0
- websockets, jinja2, python-multipart (для веб)

### Настройка окружения
Скопируйте `.env.example` в `.env` (или создайте):
```env
LEYA_WEB=1
OLLAMA_BASE_URL=http://localhost:11434
LEYA_MODEL=qwen2.5:14b-instruct-q3_K_M
LEYA_BRAIN_DIR=./leya_brain

# Опционально: переопределение параметров LeyaConfig
OLLAMA_TIMEOUT=180
MEMORY_CONSOLIDATION_THRESHOLD=0.15
# ... (см. полный список в leya_core/config.py)
```

**Важно:** `leya_brain/`, `.env`, `*.pkl`, `*.log` игнорируются `.gitignore`. Добавьте `.env` в `.gitignore` перед коммитами.

### Запуск
```bash
# Веб-интерфейс (по умолчанию)
python LeyaOS.py

# CLI
LEYA_WEB=0 python LeyaOS.py
```

После запуска:
- Веб: http://localhost:8000 (FastAPI + WebSocket live-обновления мыслей, драйвов, self-model).
- Логи: `leya_consciousness.log`
- Память и состояние: `./leya_brain/` (chroma.sqlite3, memory_state.pkl с HMAC)
- Ollama должен быть запущен отдельно.

## Конфигурация (LeyaConfig)

Полная конфигурация — в `leya_core/config.py`. Все вложенные dataclass'ы (`OllamaConfig`, `MemoryConfig`, `DrivesConfig`, `HomeostasisConfig`, `ThinkerConfig`, `ReflectionConfig`, `WorkspaceConfig`, `ConstitutionalConfig`, `WebConfig`, `LoggingConfig`) имеют валидацию в `__post_init__` и загружаются через `LeyaConfig.from_env()`.

Примеры ключевых параметров (с дефолтами):
- **Ollama**: timeout=180s, temperature=0.7, max_tokens=1024, model=qwen2.5:14b-instruct-q3_K_M
- **Memory**: brain_dir=./leya_brain, embedding_model=all-MiniLM-L6-v2, forgetting_threshold=0.1, consolidation_threshold=0.15
- **Drives**: metabolism_interval=60s, curiosity_rate=0.015 и т.д.
- **Homeostasis**: rest_period=60s, curiosity_threshold=0.6 и др.
- **Thinker**: max_context_tokens=6000, token_buffer=500
- **Web**: enabled=True, host=0.0.0.0, port=8000
- **Reflection**: consolidation_interval=1800s (30 мин)

Все параметры можно переопределить через переменные окружения (префиксы OLLAMA_, MEMORY_, DRIVES_ и т.д.).

## Известные ограничения и проблемы (v3.0)

1. **Pickle в памяти** (`memory_state.pkl`): Даже с HMAC-подписью и атомарной записью остаётся риск (небезопасная десериализация). Рекомендуется замена на msgpack + строгую схему.
2. **Эвристики в обработке пользовательских запросов** (`LeyaOS._handle_user_request`, `_extract_topic_from_user`): Жёстко закодированные ключевые слова. Ломается на вариациях формулировок.
3. **Парсинг LLM-вывода** (`thinker.py` `repair_json`): Сложная эвристика (regex + ручная балансировка). Может молча «починить» JSON неправильно. Нет Pydantic-схемы валидации.
4. **Оценка токенов** в Thinker: По символам (estimate_tokens_ratio=3.5), а не через реальный токенизатор модели → риск переполнения контекста.
5. **Не все модули leya_core интегрированы**: `decision_engine.py`, `emotional_support.py`, `personal_tools.py`, `desktop_control.py`, `voice_environment.py`, `voice_interface.py` присутствуют в дереве, но не подключены в `LeyaOS.__init__` и основном цикле. Это технический долг или экспериментальный код.
6. **Тесты**: `pytest.ini` и `tests/` существуют, но покрытие core-логики (cognitive_loop, LTP-синапсы, repair_json edge cases, homeostasis) недостаточно. Нет CI.
7. **Жёсткая привязка к Ollama + конкретной модели**. Нет fallback на другие провайдеры.
8. **Однопоточный event loop**: Все фоновые задачи в одном asyncio loop. Нет настоящей параллельности «мыслей».
9. **Отсутствие долгосрочного планирования** целей выше уровня homeostasis.
10. **Broad `except Exception`** в фоновых циклах и некоторых местах LeyaOS (для resilience) — маскирует баги.

**Рекомендация:** Перед серьёзным использованием исправьте/улучшите пункты 1–5. Система стабильнее предыдущих версий, но остаётся исследовательским прототипом.

## Roadmap (реалистичный)

- Устранение pickle (замена на безопасный формат).
- Строгая Pydantic-валидация cognitive_output + улучшение repair_json.
- Интеграция или удаление неиспользуемых модулей leya_core.
- Полноценные тесты + property-based testing для repair_json и LTP.
- Реальный токенизатор + динамическое управление контекстом.
- Расширение инструментов (Reddit, GitHub, code execution в sandbox).
- Улучшение веб-интерфейса (графики workspace, memory network, drive dynamics).
- Docker + CI/CD.
- Более глубокая биологическая модель (active inference элементы, предсказательная обработка).
- Многоагентные сценарии.

## Лицензия

Проект не имеет явной лицензии. Рекомендуется MIT или Apache 2.0 для исследовательского использования.

**Использование только в исследовательских целях.** Система моделирует аспекты «сознания», но остаётся детерминированной программой на базе LLM + правил.

## Вклад

1. Исправляйте баги и ограничения (особенно pickle, парсинг, интеграцию модулей).
2. Добавляйте тесты с высоким покрытием.
3. Улучшайте документацию и примеры.
4. Предлагайте улучшения архитектуры через Issues/PR (сохраняя сложность биологической модели и избегая упрощения до обычного RAG-агента).

---

**Создано на основе полномасштабного анализа исходного кода (LeyaOS.py, leya_core/*, web_interface/*, конфиги) 26 июня 2026.**  
Актуально для коммита v2 и выше. Предыдущие README/ARCHITECTURE устарели.

Для вопросов по конкретным классам/методам — изучайте исходники или создавайте Issue.
