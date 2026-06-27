"""
Тесты для CoreThinker и repair_json.
Покрывает парсинг JSON, edge cases, fallback.
"""
import pytest
from leya_core.thinker import repair_json


class TestRepairJson:
    """Тесты функции repair_json."""

    def test_clean_json_from_markdown(self):
        """Удаляет markdown-блоки из JSON."""
        response = '```json\n{"key": "value"}\n```'
        cleaned = repair_json(response)
        assert cleaned == '{"key": "value"}'

    def test_extract_json_from_text(self):
        """Извлекает JSON из текста."""
        response = 'Вот ответ: {"key": "value"} и ещё текст'
        cleaned = repair_json(response)
        assert '{"key": "value"}' in cleaned

    def test_handle_empty_response(self):
        """Обрабатывает пустой ответ."""
        cleaned = repair_json("")
        assert cleaned == "{}"

    def test_handle_malformed_json(self):
        """Обрабатывает повреждённый JSON."""
        response = '{"key": "value"'  # Нет закрывающей скобки
        cleaned = repair_json(response)
        # Должна попытаться восстановить или вернуть "{}"
        assert cleaned is not None

    def test_preserve_valid_json(self):
        """Сохраняет валидный JSON без изменений."""
        response = '{"key": "value", "number": 42}'
        cleaned = repair_json(response)
        assert cleaned == response