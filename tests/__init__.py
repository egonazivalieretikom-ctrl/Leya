"""
tests/ — Unit, integration и property-based тесты для LeyaOS.

Структура:
- unit/          — изолированные тесты отдельных модулей (memory, drives, thinker)
- integration/   — тесты взаимодействия компонентов (LeyaOS, cognitive_loop)
- property/      — property-based тесты (hypothesis) для edge cases
- fake_backend.py — тестовый LLM-бэкенд (FakeLLMBackend)
- conftest.py    — общие fixtures

Запуск:
    pytest tests/                    # все тесты
    pytest tests/unit/               # только unit
    pytest tests/property/           # только property-based
    pytest --cov=leya_core tests/    # с покрытием
"""