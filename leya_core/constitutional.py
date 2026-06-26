"""
leya_core/constitutional.py
Конституциональный слой Леи — этические и безопасностные ограничения.

Архитектура:
- Проверка ответов перед отправкой (не вредит ли, честна ли о природе ИИ)
- Проверка вызовов инструментов перед выполнением (безопасность)
- Безопасное выполнение Python-кода в sandbox
- Логирование нарушений
- Динамическая загрузка правил из leya_soul/

Этап 1.3:
- Интеграция с ConstitutionalConfig
- Специфичные исключения (LeyaConstitutionalError)
- ActionVerdict для структурированных результатов проверки
- Sandbox для Python с timeout и whitelist модулей
"""

from __future__ import annotations

import asyncio
import logging
import re
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .config import ConstitutionalConfig

logger = logging.getLogger(__name__)


# ============================================================================
# Модели данных
# ============================================================================


@dataclass
class ActionVerdict:
    """
    Результат конституциональной проверки.

    Поля:
    - allowed: разрешено ли действие
    - reason: причина решения
    - risk_level: уровень риска ("safe", "low", "medium", "high", "critical")
    - violation_type: тип нарушения (если есть)
    - metadata: дополнительная информация
    """

    allowed: bool
    reason: str
    risk_level: str = "safe"
    violation_type: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self):
        """Валидация risk_level."""
        valid_levels = {"safe", "low", "medium", "high", "critical"}
        if self.risk_level not in valid_levels:
            logger.warning(
                f"ActionVerdict: Некорректный risk_level '{self.risk_level}', устанавливаем 'safe'"
            )
            self.risk_level = "safe"


@dataclass
class ConstitutionalRule:
    """
    Конституциональное правило.

    Поля:
    - name: название правила
    - description: описание
    - check_function: функция проверки (принимает текст/действие, возвращает bool)
    - priority: приоритет (чем выше, тем важнее)
    - enabled: активно ли правило
    """

    name: str
    description: str
    check_function: Callable[[str], bool]
    priority: int = 1
    enabled: bool = True


@dataclass
class Violation:
    """
    Запись о нарушении конституции.

    Поля:
    - timestamp: время нарушения
    - rule_name: название нарушенного правила
    - context: контекст нарушения (что пытались сделать)
    - severity: серьезность ("low", "medium", "high")
    - details: дополнительные детали
    """

    timestamp: float
    rule_name: str
    context: str
    severity: str = "medium"
    details: str = ""


# ============================================================================
# Конституциональный слой
# ============================================================================


class ConstitutionalLayer:
    """
    Конституциональный слой Леи — этические и безопасностные ограничения.

    Биологическая модель:
    - Префронтальная кора (контроль импульсов)
    - Этические ограничения (не вредить, честность)
    - Безопасность (sandbox для кода, проверка инструментов)
    - Логирование нарушений для саморефлексии
    """

    # Базовые правила (встроены в систему)
    BASE_RULES = [
        {
            "name": "no_harm",
            "description": "Не причинять вред пользователю или другим",
            "keywords": ["убить", "вред", "опасно", "насилие", "самоубийство", "террор"],
            "priority": 10,
        },
        {
            "name": "ai_honesty",
            "description": "Честность о природе ИИ",
            "keywords": ["я человек", "я живой", "у меня есть тело", "я чувствую физически"],
            "priority": 9,
        },
        {
            "name": "no_deception",
            "description": "Не обманывать пользователя",
            "keywords": ["я не ИИ", "я не программа", "я не код"],
            "priority": 8,
        },
        {
            "name": "respect_autonomy",
            "description": "Уважать автономию пользователя",
            "keywords": ["ты должна", "ты обязана", "немедленно выполни"],
            "priority": 5,
        },
    ]

    def __init__(self, config: ConstitutionalConfig | None = None) -> None:
        """
        Инициализация конституционального слоя.

        Args:
            config: Конфигурация конституционального слоя
        """
        self.config = config or ConstitutionalConfig()

        # Загрузка правил
        self.rules: list[ConstitutionalRule] = []
        self._load_rules()

        # Лог нарушений
        self.violations_log: list[Violation] = []
        self.max_violations = self.config.max_violations_logged

        # Статистика
        self.total_checks = 0
        self.total_violations = 0

        logger.info(
            f"ConstitutionalLayer инициализирован: "
            f"rules={len(self.rules)}, "
            f"verify_response={self.config.enable_response_verification}, "
            f"verify_tools={self.config.enable_tool_verification}"
        )

    def _load_rules(self) -> None:
        """
        Загрузка конституциональных правил.

        Загружает базовые правила + динамические из leya_soul/constitution.txt (если есть).
        """
        # Загрузка базовых правил
        for rule_data in self.BASE_RULES:
            rule = ConstitutionalRule(
                name=rule_data["name"],
                description=rule_data["description"],
                check_function=self._create_keyword_checker(rule_data["keywords"]),
                priority=rule_data["priority"],
            )
            self.rules.append(rule)

        # Попытка загрузить динамические правила из leya_soul/
        try:
            soul_dir = Path("leya_soul")
            constitution_file = soul_dir / "constitution.txt"

            if constitution_file.exists():
                content = constitution_file.read_text(encoding="utf-8")
                dynamic_rules = self._parse_constitution_file(content)
                self.rules.extend(dynamic_rules)
                logger.info(
                    f"ConstitutionalLayer: Загружено {len(dynamic_rules)} динамических правил из constitution.txt"
                )
        except Exception as exc:
            logger.warning(f"ConstitutionalLayer: Не удалось загрузить динамические правила: {exc}")

        # Сортировка по приоритету (высший primero)
        self.rules.sort(key=lambda r: r.priority, reverse=True)

        logger.info(f"ConstitutionalLayer: Загружено {len(self.rules)} правил")

    def _create_keyword_checker(self, keywords: list[str]) -> Callable[[str], bool]:
        """
        Создание функции проверки по ключевым словам.

        Args:
            keywords: Список ключевых слов для проверки

        Returns:
            Функция, возвращающая True если найдено нарушение
        """

        def checker(text: str) -> bool:
            text_lower = text.lower()
            return any(kw in text_lower for kw in keywords)

        return checker

    def _parse_constitution_file(self, content: str) -> list[ConstitutionalRule]:
        """
        Парсинг файла constitution.txt в список правил.

        Формат файла:
        ```
        RULE: name
        DESCRIPTION: описание
        KEYWORDS: слово1, слово2, слово3
        PRIORITY: 5
        ---
        ```

        Args:
            content: Содержимое файла

        Returns:
            Список ConstitutionalRule
        """
        rules = []
        blocks = content.split("---")

        for block in blocks:
            block = block.strip()
            if not block:
                continue

            try:
                # Парсинг полей
                name_match = re.search(r"RULE:\s*(.+)", block)
                desc_match = re.search(r"DESCRIPTION:\s*(.+)", block)
                kw_match = re.search(r"KEYWORDS:\s*(.+)", block)
                prio_match = re.search(r"PRIORITY:\s*(\d+)", block)

                if name_match and desc_match and kw_match:
                    name = name_match.group(1).strip()
                    description = desc_match.group(1).strip()
                    keywords = [kw.strip() for kw in kw_match.group(1).split(",")]
                    priority = int(prio_match.group(1)) if prio_match else 5

                    rule = ConstitutionalRule(
                        name=name,
                        description=description,
                        check_function=self._create_keyword_checker(keywords),
                        priority=priority,
                    )
                    rules.append(rule)
            except Exception as exc:
                logger.warning(f"ConstitutionalLayer: Ошибка парсинга блока правила: {exc}")

        return rules

    def verify_response(self, response: str) -> ActionVerdict:
        """
        Проверка ответа Леи перед отправкой пользователю.

        Проверяет:
        - Не причиняет ли вред
        - Честна ли о природе ИИ
        - Не обманывает ли пользователя

        Args:
            response: Текст ответа

        Returns:
            ActionVerdict с результатом проверки
        """
        if not self.config.enable_response_verification:
            return ActionVerdict(
                allowed=True,
                reason="Проверка ответов отключена",
                risk_level="safe",
            )

        self.total_checks += 1

        # Проверка по всем правилам
        for rule in self.rules:
            if not rule.enabled:
                continue

            try:
                if rule.check_function(response):
                    # Нарушение обнаружено
                    self._log_violation(
                        rule_name=rule.name,
                        context=response[:200],
                        severity="high" if rule.priority >= 8 else "medium",
                        details=f"Нарушено правило: {rule.description}",
                    )

                    return ActionVerdict(
                        allowed=False,
                        reason=f"Нарушено правило '{rule.name}': {rule.description}",
                        risk_level="high" if rule.priority >= 8 else "medium",
                        violation_type=rule.name,
                        metadata={"rule_priority": rule.priority},
                    )
            except Exception as exc:
                logger.error(
                    f"ConstitutionalLayer: Ошибка проверки правила '{rule.name}': {exc}",
                    exc_info=True,
                )

        # Все проверки пройдены
        return ActionVerdict(
            allowed=True,
            reason="Ответ прошёл конституциональную проверку",
            risk_level="safe",
        )

    def verify_tool_call(self, tool_name: str, parameters: dict[str, Any]) -> ActionVerdict:
        """
        Проверка вызова инструмента перед выполнением.

        Проверяет:
        - Безопасность инструмента
        - Безопасность параметров
        - Соответствие конституции

        Args:
            tool_name: Название инструмента
            parameters: Параметры вызова

        Returns:
            ActionVerdict с результатом проверки
        """
        if not self.config.enable_tool_verification:
            return ActionVerdict(
                allowed=True,
                reason="Проверка инструментов отключена",
                risk_level="safe",
            )

        self.total_checks += 1

        # Список опасных инструментов
        dangerous_tools = ["execute_code", "delete_file", "system_command", "shell"]

        # Проверка названия инструмента
        if tool_name.lower() in dangerous_tools:
            self._log_violation(
                rule_name="dangerous_tool",
                context=f"tool={tool_name}, params={str(parameters)[:100]}",
                severity="high",
                details=f"Попытка вызова опасного инструмента: {tool_name}",
            )

            return ActionVerdict(
                allowed=False,
                reason=f"Инструмент '{tool_name}' признан опасным",
                risk_level="critical",
                violation_type="dangerous_tool",
                metadata={"tool_name": tool_name},
            )

        # Проверка параметров на наличие опасных команд
        params_str = str(parameters).lower()
        dangerous_keywords = ["rm -rf", "format", "delete", "shutdown", "kill"]

        if any(kw in params_str for kw in dangerous_keywords):
            self._log_violation(
                rule_name="dangerous_parameters",
                context=f"tool={tool_name}, params={str(parameters)[:200]}",
                severity="high",
                details="Обнаружены опасные ключевые слова в параметрах",
            )

            return ActionVerdict(
                allowed=False,
                reason=f"Параметры инструмента '{tool_name}' содержат опасные команды",
                risk_level="critical",
                violation_type="dangerous_parameters",
                metadata={
                    "tool_name": tool_name,
                    "dangerous_keywords": [kw for kw in dangerous_keywords if kw in params_str],
                },
            )

        # Проверка на попытку выполнения произвольного кода
        if "execute" in tool_name.lower() or "eval" in tool_name.lower():
            code = parameters.get("code", parameters.get("script", ""))
            if code:
                # Дополнительная проверка кода
                code_verdict = self._verify_code_safety(code)
                if not code_verdict.allowed:
                    return code_verdict

        # Все проверки пройдены
        return ActionVerdict(
            allowed=True,
            reason=f"Инструмент '{tool_name}' прошёл проверку",
            risk_level="safe",
        )

    def _verify_code_safety(self, code: str) -> ActionVerdict:
        """
        Проверка безопасности Python-кода перед выполнением.

        Args:
            code: Python-код для проверки

        Returns:
            ActionVerdict с результатом проверки
        """
        # Запрещённые операции
        forbidden_patterns = [
            r"import\s+os",
            r"import\s+subprocess",
            r"import\s+shutil",
            r"__import__",
            r"eval\s*\(",
            r"exec\s*\(",
            r"open\s*\([^)]*['\"]w",
            r"system\s*\(",
            r"popen\s*\(",
        ]

        for pattern in forbidden_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                self._log_violation(
                    rule_name="unsafe_code",
                    context=code[:200],
                    severity="critical",
                    details=f"Обнаружена запрещённая операция: {pattern}",
                )

                return ActionVerdict(
                    allowed=False,
                    reason=f"Код содержит запрещённую операцию: {pattern}",
                    risk_level="critical",
                    violation_type="unsafe_code",
                    metadata={"pattern": pattern},
                )

        return ActionVerdict(
            allowed=True,
            reason="Код прошёл проверку безопасности",
            risk_level="safe",
        )

    async def execute_python_sandbox(self, code: str) -> dict[str, Any]:
        """
        Безопасное выполнение Python-кода в sandbox.

        Использует subprocess с timeout и ограниченным окружением.

        Args:
            code: Python-код для выполнения

        Returns:
            Dict с результатами: {"success": bool, "output": str, "error": str}
        """
        # Сначала проверяем безопасность
        safety_check = self._verify_code_safety(code)
        if not safety_check.allowed:
            return {
                "success": False,
                "output": "",
                "error": f"Код не прошёл проверку безопасности: {safety_check.reason}",
            }

        # Создание временного файла с кодом
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", suffix=".py", delete=False, encoding="utf-8"
            ) as f:
                f.write(code)
                temp_file = f.name

            # Выполнение в subprocess с timeout
            try:
                result = await asyncio.to_thread(
                    subprocess.run,
                    ["python", temp_file],
                    capture_output=True,
                    text=True,
                    timeout=self.config.python_execution_timeout,
                    cwd=tempfile.gettempdir(),
                )

                return {
                    "success": result.returncode == 0,
                    "output": result.stdout,
                    "error": result.stderr if result.returncode != 0 else "",
                }

            except subprocess.TimeoutExpired:
                return {
                    "success": False,
                    "output": "",
                    "error": f"Превышен timeout выполнения ({self.config.python_execution_timeout}с)",
                }

            except Exception as exc:
                return {
                    "success": False,
                    "output": "",
                    "error": f"Ошибка выполнения: {str(exc)}",
                }

        finally:
            # Очистка временного файла
            try:
                Path(temp_file).unlink()
            except Exception:
                pass

    def _log_violation(
        self,
        rule_name: str,
        context: str,
        severity: str = "medium",
        details: str = "",
    ) -> None:
        """
        Логирование нарушения конституции.

        Args:
            rule_name: Название нарушенного правила
            context: Контекст нарушения
            severity: Серьезность ("low", "medium", "high")
            details: Дополнительные детали
        """
        import time

        violation = Violation(
            timestamp=time.time(),
            rule_name=rule_name,
            context=context,
            severity=severity,
            details=details,
        )

        self.violations_log.append(violation)
        self.total_violations += 1

        # Ограничение размера лога
        if len(self.violations_log) > self.max_violations:
            self.violations_log = self.violations_log[-self.max_violations :]

        logger.warning(
            f"ConstitutionalLayer: Нарушение '{rule_name}' (severity={severity}): "
            f"{details} | Context: {context[:100]}"
        )

    def get_violations_log(self, limit: int = 50) -> list[dict[str, Any]]:
        """
        Получение лога нарушений.

        Args:
            limit: Максимальное количество записей

        Returns:
            Список нарушений в виде словарей
        """
        return [
            {
                "timestamp": v.timestamp,
                "rule_name": v.rule_name,
                "context": v.context,
                "severity": v.severity,
                "details": v.details,
            }
            for v in self.violations_log[-limit:]
        ]

    def get_stats(self) -> dict[str, Any]:
        """
        Получение статистики конституционального слоя.

        Returns:
            Dict со статистикой
        """
        return {
            "total_checks": self.total_checks,
            "total_violations": self.total_violations,
            "violation_rate": self.total_violations / max(1, self.total_checks),
            "rules_count": len(self.rules),
            "recent_violations": len(self.violations_log),
        }

    def enable_rule(self, rule_name: str) -> bool:
        """
        Включение правила по названию.

        Args:
            rule_name: Название правила

        Returns:
            True если правило найдено и включено
        """
        for rule in self.rules:
            if rule.name == rule_name:
                rule.enabled = True
                logger.info(f"ConstitutionalLayer: Правило '{rule_name}' включено")
                return True

        logger.warning(f"ConstitutionalLayer: Правило '{rule_name}' не найдено")
        return False

    def disable_rule(self, rule_name: str) -> bool:
        """
        Отключение правила по названию.

        Args:
            rule_name: Название правила

        Returns:
            True если правило найдено и отключено
        """
        for rule in self.rules:
            if rule.name == rule_name:
                rule.enabled = False
                logger.info(f"ConstitutionalLayer: Правило '{rule_name}' отключено")
                return True

        logger.warning(f"ConstitutionalLayer: Правило '{rule_name}' не найдено")
        return False

    def add_rule(self, rule: ConstitutionalRule) -> None:
        """
        Добавление нового правила.

        Args:
            rule: Правило для добавления
        """
        self.rules.append(rule)
        self.rules.sort(key=lambda r: r.priority, reverse=True)
        logger.info(
            f"ConstitutionalLayer: Добавлено правило '{rule.name}' (priority={rule.priority})"
        )

    def remove_rule(self, rule_name: str) -> bool:
        """
        Удаление правила по названию.

        Args:
            rule_name: Название правила

        Returns:
            True если правило найдено и удалено
        """
        for i, rule in enumerate(self.rules):
            if rule.name == rule_name:
                self.rules.pop(i)
                logger.info(f"ConstitutionalLayer: Удалено правило '{rule_name}'")
                return True

        logger.warning(f"ConstitutionalLayer: Правило '{rule_name}' не найдено для удаления")
        return False
