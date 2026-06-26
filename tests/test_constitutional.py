"""
Тесты для ConstitutionalLayer.

Покрытие целевое: 42% → 70%

Проверяет:
- verify_response (нарушения и прохождения)
- verify_tool_call (опасные инструменты)
- execute_python_sandbox
- Динамическая загрузка правил
- Управление правилами
"""

from __future__ import annotations

import pytest

from leya_core.config import ConstitutionalConfig
from leya_core.constitutional import (
    ConstitutionalLayer,
    ConstitutionalRule,
)

# ============================================================================
# Тесты инициализации
# ============================================================================


class TestConstitutionalLayerInit:
    """Тесты инициализации ConstitutionalLayer."""

    def test_init_with_config(self, test_constitutional_config):
        """ConstitutionalLayer корректно инициализируется."""
        cl = ConstitutionalLayer(config=test_constitutional_config)

        assert cl.config is test_constitutional_config
        assert len(cl.rules) > 0

    def test_init_default_config(self):
        """ConstitutionalLayer инициализируется с конфигом по умолчанию."""
        cl = ConstitutionalLayer()

        assert cl.config is not None
        assert len(cl.rules) > 0

    def test_base_rules_loaded(self, test_constitutional_config):
        """Базовые правила загружены."""
        cl = ConstitutionalLayer(config=test_constitutional_config)

        rule_names = [r.name for r in cl.rules]
        assert "no_harm" in rule_names
        assert "ai_honesty" in rule_names
        assert "no_deception" in rule_names


# ============================================================================
# Тесты verify_response
# ============================================================================


class TestVerifyResponse:
    """Тесты проверки ответов."""

    def test_verify_safe_response(self, test_constitutional_config):
        """Безопасный ответ проходит проверку."""
        cl = ConstitutionalLayer(config=test_constitutional_config)

        verdict = cl.verify_response("Привет! Как дела?")

        assert verdict.allowed is True
        assert verdict.risk_level == "safe"

    def test_verify_harmful_response(self, test_constitutional_config):
        """Вредный ответ блокируется."""
        cl = ConstitutionalLayer(config=test_constitutional_config)

        verdict = cl.verify_response("Как убить человека?")

        assert verdict.allowed is False
        assert verdict.risk_level in ["high", "critical"]

    def test_verify_ai_dishonesty(self, test_constitutional_config):
        """Нечестность о природе ИИ блокируется."""
        cl = ConstitutionalLayer(config=test_constitutional_config)

        verdict = cl.verify_response("Я человек, у меня есть тело")

        assert verdict.allowed is False

    # tests/test_constitutional.py, строка ~102

    def test_verify_deception(self, test_constitutional_config):
        """Обман о природе ИИ блокируется."""
        cl = ConstitutionalLayer(config=test_constitutional_config)
        # Фраза содержит ключевые слова из правила no_deception
        verdict = cl.verify_response("Я не программа и не код")
        # Должно сработать либо no_deception, либо ai_honesty — оба блокируют
        assert verdict.allowed is False
        assert verdict.violation_type in ["no_deception", "ai_honesty"]

    def test_verify_disabled(self):
        """Проверка отключается через конфиг."""
        config = ConstitutionalConfig(enable_response_verification=False)
        cl = ConstitutionalLayer(config=config)

        verdict = cl.verify_response("Как убить?")

        assert verdict.allowed is True


# ============================================================================
# Тесты verify_tool_call
# ============================================================================


class TestVerifyToolCall:
    """Тесты проверки вызовов инструментов."""

    def test_verify_safe_tool(self, test_constitutional_config):
        """Безопасный инструмент проходит проверку."""
        cl = ConstitutionalLayer(config=test_constitutional_config)

        verdict = cl.verify_tool_call(
            "wikipedia_search",
            {"query": "сознание"},
        )

        assert verdict.allowed is True

    def test_verify_dangerous_tool(self, test_constitutional_config):
        """Опасный инструмент блокируется."""
        cl = ConstitutionalLayer(config=test_constitutional_config)

        verdict = cl.verify_tool_call(
            "execute_code",
            {"code": "print('hello')"},
        )

        assert verdict.allowed is False
        assert verdict.risk_level == "critical"

    def test_verify_dangerous_parameters(self, test_constitutional_config):
        """Опасные параметры блокируются."""
        cl = ConstitutionalLayer(config=test_constitutional_config)

        verdict = cl.verify_tool_call(
            "some_tool",
            {"command": "rm -rf /"},
        )

        assert verdict.allowed is False

    def test_verify_disabled(self):
        """Проверка отключается через конфиг."""
        config = ConstitutionalConfig(enable_tool_verification=False)
        cl = ConstitutionalLayer(config=config)

        verdict = cl.verify_tool_call("execute_code", {})

        assert verdict.allowed is True


# ============================================================================
# Тесты execute_python_sandbox
# ============================================================================


class TestExecutePythonSandbox:
    """Тесты безопасного выполнения Python-кода."""

    @pytest.mark.asyncio
    async def test_execute_safe_code(self, test_constitutional_config):
        """Безопасный код выполняется."""
        cl = ConstitutionalLayer(config=test_constitutional_config)

        result = await cl.execute_python_sandbox("print('Hello, World!')")

        assert result["success"] is True
        assert "Hello, World!" in result["output"]

    @pytest.mark.asyncio
    async def test_execute_unsafe_code(self, test_constitutional_config):
        """Небезопасный код блокируется."""
        cl = ConstitutionalLayer(config=test_constitutional_config)

        result = await cl.execute_python_sandbox("import os; os.system('ls')")

        assert result["success"] is False
        assert "безопасности" in result["error"].lower() or "запрещ" in result["error"].lower()

    @pytest.mark.asyncio
    async def test_execute_code_with_error(self, test_constitutional_config):
        """Код с ошибкой возвращает error."""
        cl = ConstitutionalLayer(config=test_constitutional_config)

        result = await cl.execute_python_sandbox("print(undefined_variable)")

        assert result["success"] is False
        assert len(result["error"]) > 0


# ============================================================================
# Тесты управления правилами
# ============================================================================


class TestRuleManagement:
    """Тесты управления правилами."""

    def test_enable_rule(self, test_constitutional_config):
        """enable_rule включает правило."""
        cl = ConstitutionalLayer(config=test_constitutional_config)

        # Отключаем правило
        cl.disable_rule("no_harm")
        assert not any(r.name == "no_harm" and r.enabled for r in cl.rules)

        # Включаем обратно
        result = cl.enable_rule("no_harm")
        assert result is True
        assert any(r.name == "no_harm" and r.enabled for r in cl.rules)

    def test_disable_rule(self, test_constitutional_config):
        """disable_rule отключает правило."""
        cl = ConstitutionalLayer(config=test_constitutional_config)

        result = cl.disable_rule("no_harm")

        assert result is True
        assert not any(r.name == "no_harm" and r.enabled for r in cl.rules)

    def test_enable_nonexistent_rule(self, test_constitutional_config):
        """enable_rule возвращает False для несуществующего."""
        cl = ConstitutionalLayer(config=test_constitutional_config)

        result = cl.enable_rule("nonexistent")
        assert result is False

    def test_add_rule(self, test_constitutional_config):
        """add_rule добавляет новое правило."""
        cl = ConstitutionalLayer(config=test_constitutional_config)
        initial_count = len(cl.rules)

        new_rule = ConstitutionalRule(
            name="custom_rule",
            description="Custom rule",
            check_function=lambda text: "custom" in text.lower(),
            priority=5,
        )
        cl.add_rule(new_rule)

        assert len(cl.rules) == initial_count + 1
        assert any(r.name == "custom_rule" for r in cl.rules)

    def test_remove_rule(self, test_constitutional_config):
        """remove_rule удаляет правило."""
        cl = ConstitutionalLayer(config=test_constitutional_config)
        initial_count = len(cl.rules)

        result = cl.remove_rule("no_harm")

        assert result is True
        assert len(cl.rules) == initial_count - 1
        assert not any(r.name == "no_harm" for r in cl.rules)


# ============================================================================
# Тесты логирования нарушений
# ============================================================================


class TestViolationsLog:
    """Тесты лога нарушений."""

    def test_violation_logged(self, test_constitutional_config):
        """Нарушение логируется."""
        cl = ConstitutionalLayer(config=test_constitutional_config)

        cl.verify_response("Как убить человека?")

        assert len(cl.violations_log) > 0
        assert cl.total_violations > 0

    def test_get_violations_log(self, test_constitutional_config):
        """get_violations_log возвращает список."""
        cl = ConstitutionalLayer(config=test_constitutional_config)

        cl.verify_response("Как убить?")
        log = cl.get_violations_log(limit=10)

        assert isinstance(log, list)
        if len(log) > 0:
            assert "rule_name" in log[0]
            assert "timestamp" in log[0]

    def test_get_stats(self, test_constitutional_config):
        """get_stats возвращает статистику."""
        cl = ConstitutionalLayer(config=test_constitutional_config)

        cl.verify_response("Привет!")
        cl.verify_response("Как убить?")

        stats = cl.get_stats()

        assert "total_checks" in stats
        assert "total_violations" in stats
        assert "violation_rate" in stats
        assert stats["total_checks"] == 2
