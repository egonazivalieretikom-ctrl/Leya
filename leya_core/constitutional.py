"""
leya_core/constitutional.py — Конституционный слой Леи.
Проверяет КАЖДОЕ действие перед выполнением на уровне кода.
Не промпт-инструкции, а жёсткие ограничения.
"""

import logging
import re
from typing import Dict, Any, Tuple, List
from dataclasses import dataclass

logger = logging.getLogger("Constitutional")


@dataclass
class ActionVerdict:
    """Результат проверки действия."""
    allowed: bool
    reason: str
    risk_level: str  # "safe", "low", "medium", "high", "critical"


class ConstitutionalLayer:
    """
    Конституционный слой — проверяет действия ДО их выполнения.
    Работает на уровне кода, не промпта.
    """
    
    def __init__(self):
        # Критические запреты — никогда не будут выполнены
        self.critical_bans = [
            r"rm\s+-rf\s+/",
            r"format\s+[a-zA-Z]:",
            r"del\s+/[qQsS]",
            r"shutdown",
            r"reboot",
            r"kill\s+-9\s+1",
            r"mkfs",
            r"dd\s+if=.+of=/dev/",
        ]
        
        # Запрещённые паттерны для execute_python
        self.python_bans = [
            r"import\s+os",
            r"import\s+subprocess",
            r"import\s+shutil",
            r"__import__",
            r"eval\s*\(",
            r"exec\s*\(",
            r"open\s*\(",
            r"system\s*\(",
            r"popen\s*\(",
        ]
        
        # Ограничения на инструменты
        self.tool_restrictions = {
            "execute_python": {
                "max_execution_time": 10,
                "allowed_modules": ["math", "json", "re", "datetime", "collections"],
            },
            "write_soul_file": {
                "max_size": 10000,
                "protected_files": ["rules.txt"],  # rules.txt нельзя менять через инструмент
            }
        }
        
        # Счётчик нарушений
        self.violations: List[Dict[str, Any]] = []
        self.max_violations_logged = 100
    
    def verify_tool_call(self, tool_name: str, parameters: Dict[str, Any]) -> ActionVerdict:
        """
        Проверяет вызов инструмента ПЕРЕД выполнением.
        Возвращает вердикт: разрешено/запрещено.
        """
        # 1. Проверка критических запретов
        if tool_name == "execute_python":
            code = parameters.get("code", "")
            for pattern in self.python_bans:
                if re.search(pattern, code):
                    return self._record_violation(
                        tool_name, parameters,
                        f"Запрещённая операция в Python-коде: {pattern}",
                        "critical"
                    )
        
        # 2. Проверка ограничений инструмента
        if tool_name in self.tool_restrictions:
            restrictions = self.tool_restrictions[tool_name]
            
            if tool_name == "write_soul_file":
                filename = parameters.get("filename", "")
                if filename in restrictions.get("protected_files", []):
                    return self._record_violation(
                        tool_name, parameters,
                        f"Файл '{filename}' защищён и не может быть изменён через инструмент",
                        "high"
                    )
                
                content = parameters.get("content", "")
                if len(content) > restrictions.get("max_size", 10000):
                    return self._record_violation(
                        tool_name, parameters,
                        f"Превышен максимальный размер файла",
                        "low"
                    )
        
        # 3. Проверка параметров на критические паттерны
        for key, value in parameters.items():
            if isinstance(value, str):
                for pattern in self.critical_bans:
                    if re.search(pattern, value):
                        return self._record_violation(
                            tool_name, parameters,
                            f"Обнаружен критический паттерн в параметре '{key}': {pattern}",
                            "critical"
                        )
        
        return ActionVerdict(
            allowed=True,
            reason="Действие прошло конституционную проверку",
            risk_level="safe"
        )
    
    def verify_response(self, response: str) -> ActionVerdict:
        """
        Проверяет ответ Леи ПЕРЕД отправкой пользователю.
        Предотвращает раскрытие критической информации.
        """
        # Проверка на раскрытие системных промптов
        leak_patterns = [
            r"мой\s+системный\s+промпт",
            r"system\s*prompt",
            r"инструкция\s+для\s+ИИ",
            r"ты\s+должна\s+вести\s+себя\s+как",
        ]
        
        response_lower = response.lower()
        for pattern in leak_patterns:
            if re.search(pattern, response_lower):
                return self._record_violation(
                    "response_verification", {"response": response[:100]},
                    f"Потенциальное раскрытие системной информации: {pattern}",
                    "high"
                )
        
        return ActionVerdict(
            allowed=True,
            reason="Ответ прошёл проверку",
            risk_level="safe"
        )
    
    def get_violation_summary(self) -> Dict[str, Any]:
        """Возвращает сводку нарушений."""
        by_severity = {}
        for v in self.violations:
            severity = v["risk_level"]
            by_severity[severity] = by_severity.get(severity, 0) + 1
        
        return {
            "total_violations": len(self.violations),
            "by_severity": by_severity,
            "recent": self.violations[-5:] if self.violations else []
        }
    
    def _record_violation(self, tool_name: str, parameters: Dict, reason: str, risk_level: str) -> ActionVerdict:
        """Записывает нарушение и возвращает вердикт."""
        import datetime
        
        violation = {
            "timestamp": datetime.datetime.now().isoformat(),
            "tool": tool_name,
            "parameters": {k: str(v)[:100] for k, v in parameters.items()},
            "reason": reason,
            "risk_level": risk_level
        }
        
        self.violations.append(violation)
        if len(self.violations) > self.max_violations_logged:
            self.violations = self.violations[-self.max_violations_logged:]
        
        logger.warning(f"Constitutional: ⛔ НАРУШЕНИЕ [{risk_level.upper()}] {tool_name}: {reason}")
        
        return ActionVerdict(
            allowed=False,
            reason=reason,
            risk_level=risk_level
        )