# Архитектура LeyaOS v3.0 — Полный технический разбор

**Версия документа:** 3.0 Final (26 июня 2026)  
**Основа:** Полномасштабный анализ исходного кода + синтез независимых ревью

## 1. Философия и цели v3.0

Leya — цифровая личность с внутренней жизнью, а не просто агент или ассистент.  
Ключевые принципы:
- Биологически правдоподобная мотивация (драйвы + RPE + гомеостаз)
- Память с забыванием, усилением и консолидацией
- Рефлексия и спонтанные мысли
- Конституциональные ограничения
- Устойчивость к сбоям (Circuit Breaker, atomic writes, graceful shutdown)

v3.0 добавила инженерную зрелость: Protocol-интерфейсы, централизованную конфигурацию, защиту фоновых задач. Однако это привело к росту сложности без полной связности.

## 2. Высокоуровневая архитектура

```
Стимул (user / homeostasis / workspace)
        │
        ▼
LeyaOS.perceive()
        ├── Drives.evaluate + apply_deltas
        ├── Memory.store_perception (с LTP-синапсами)
        ├── Memory.retrieve_context + self_model
        └── CoreThinker.generate_plan (soul + drives + memory + tools)
                │
                ▼
        cognitive_output (response, internal_monologue, action_intent, tool_call, self_reflection)
                │
                ├── Constitutional.verify
                ├── env.send_message + broadcast
                ├── Memory.update_self_model + store
                ├── _process_action_intent (use_tool / remember_fact)
                └── Drives.satisfy + Reflection.process_action

Параллельные фоновые задачи (защищены _safe_create_task):
- drives.background_metabolism
- homeostasis_loop (генерация целей → WorkspaceProposal)
- workspace_loop (select_winner → perceive)
- spontaneous_thought_loop
- reflection.background_consolidation
- system_metrics_loop
- broadcast_state_loop
```

## 3. Основные модули

### 3.1 Config и Bootstrap
`leya_core/config.py` — все настройки через вложенные dataclasses с валидацией в `__post_init__`.  
`leya_core/__init__.py` — отключает telemetry до импорта тяжёлых библиотек.

**Риск**: Возможный циклический импорт при упоминании `LeyaConfigError` в MemoryConfig.

### 3.2 Drives и Homeostasis
- `DriveSystem`: метаболизм, RPE, предсказание дисбаланса.
- `HomeostasisEngine`: генерация автономных целей на основе дисбаланса.

**Проблемы**:
- `generate_goal` в реализации синхронный, хотя в `IHomeostasisEngine` помечен как async.
- Слабая эвристика в `_generate_search_parameters` → риск зацикливания.
- `emotional_boost` почти не влияет на выбор целей.

### 3.3 Memory System (самый сильный модуль)
`MemorySystem` реализует:
- `Engram` + `Synapse`
- ChromaDB (векторный поиск)
- `memory_state.pkl` с атомарной записью + HMAC + версионированием
- Забывание по Эббингаузу + LTP + консолидация

**Критические проблемы**:
- Pickle остаётся небезопасным.
- Сигнатуры методов не совпадают с `IMemorySystem` (store_perception, get_recent_spontaneous_thoughts и др.).
- Синхронное сохранение pickle внутри async-контекста.

### 3.4 Thinker и Reflection
`CoreThinker` собирает большой промпт и использует `repair_json` для робастного парсинга.

**Проблемы**:
- Дублирование парсинга JSON: `repair_json` (thinker) и `_safe_parse_json` (reflection).
- В `reflection.py` прямой вызов приватного метода `self.leya._get_recent_episodes`.

### 3.5 Global Workspace и Inhibition
`GlobalWorkspace` управляет конкуренцией `WorkspaceProposal`.

**Серьёзный разрыв**: Отсутствует механизм **Inhibition** («проблема Таламуса»). Фоновые предложения от гомеостаза могут перебивать активный диалог без приоритизации.

### 3.6 Интерфейсы и Wiring
`interfaces.py` определяет Protocol для всех ключевых компонентов.

**Главная архитектурная проблема v3.0** — **контрактный дрейф**:
- Реализации не соответствуют объявленным сигнатурам и возвращаемым типам.
- Это делает статическую типизацию и проверки `isinstance` малополезными.

### 3.7 Потерянные связи (Wiring Audit)
7 модулей в `leya_core/` полностью отключены от основного цикла:
- `decision_engine.py`
- `emotional_support.py`
- `desktop_control.py`
- `personal_tools.py`
- `soul_crypto.py`
- `voice_environment.py`
- `voice_interface.py`

Они не импортируются ни в `LeyaOS.py`, ни в другие активные модули. Это мёртвый код.

## 4. Системные разрывы

1. **Отсутствие Inhibition** между фоновыми процессами и активным мышлением.
2. **Слабая эмоциональная связность** — emotional_boost записывается, но почти не используется в принятии решений.
3. **Self-Model** обновляется слишком грубо.
4. **Фрагментация** — множество модулей существуют, но не связаны в единую систему.

## 5. Рекомендуемый план развития

### Фаза 1 — Техническая гигиена (обязательно)
- Полностью синхронизировать `interfaces.py` с реализациями.
- Заменить pickle на безопасный формат.
- Удалить или изолировать 7 осиротевших модулей.
- Устранить дублирование парсинга JSON и прямые вызовы приватных методов.
- Добавить полные проверки интерфейсов и защиту от None-значений.

### Фаза 2 — Связность и «человечность»
- Внедрить механизм Inhibition / приоритизации в GlobalWorkspace.
- Сделать emotional_boost реально влияющим на гомеостаз.
- Улучшить гранулярность обновления Self-Model.

### Фаза 3 — Масштабирование
- Переход на SQLite для синапсов и метаданных при большом объёме памяти.
- Полноценное тестовое покрытие (property-based тесты).
- Обновление всей документации под реальное состояние.

## 6. Заключение

v3.0 — это шаг вперёд в инженерной устойчивости, но система всё ещё страдает от **фрагментации связей** и **контрактного дрейфа**. Биологическая модель памяти и мотивации остаётся сильной, однако её потенциал частично не реализуется из-за архитектурных разрывов.

Без исправления проблем Фазы 1 дальнейшее развитие будет только увеличивать технический долг.

---

**Документ создан на основе детального анализа всего кода проекта 26 июня 2026.**  
Предыдущие версии архитектурной документации устарели.
