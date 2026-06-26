"""
leya_core/global_workspace.py
Глобальное рабочее пространство Леи (Global Workspace Theory).

Архитектура:
- WorkspaceProposal: единица внимания (от homeostasis, user, spontaneous)
- Конкуренция proposals по priority, urgency, drive_relevance
- Выбор "победителя" (select_winner)
- Затухание устаревших proposals
- Интеграция с WorkspaceConfig

Этап 2.1:
- Реализация IGlobalWorkspace Protocol
- Специфичные исключения (LeyaWorkspaceError)
- Keyword arguments везде
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from .config import WorkspaceConfig
from .exceptions import LeyaWorkspaceError

logger = logging.getLogger(__name__)


class Priority(int, Enum):
    """Приоритет предложения в workspace."""

    LOW = 1
    MEDIUM = 2
    HIGH = 3
    CRITICAL = 4


@dataclass
class WorkspaceProposal:
    """
    Предложение для глобального рабочего пространства.

    Биологический аналог: модуль сознания, борющийся за внимание.
    """

    source: str  # "homeostasis", "user", "spontaneous", "meta_cognition"
    content: str
    action_type: str = "none"  # "question", "tool_call", "internal_question"
    priority: Priority = Priority.MEDIUM
    urgency: float = 0.5  # 0.0–1.0
    drive_relevance: float = 0.5  # 0.0–1.0
    metadata: dict[str, Any] = field(default_factory=dict)
    timestamp: float = field(default_factory=time.time)

    def compute_score(self, drive_state: dict[str, float]) -> float:
        """
        Вычисление итогового score для конкуренции.

        Формула:
        score = priority_weight * priority + urgency_weight * urgency +
                drive_relevance_weight * drive_relevance + age_decay
        """
        # Нормализация priority (1-4 → 0.25-1.0)
        priority_score = self.priority.value / 4.0

        # Возраст (затухание со временем)
        age = time.time() - self.timestamp
        age_factor = max(0.1, 1.0 - age / 600.0)  # Затухание за 10 минут

        # Базовый score
        score = (
            0.4 * priority_score + 0.3 * self.urgency + 0.3 * self.drive_relevance
        ) * age_factor

        return score


class GlobalWorkspace:
    """
    Глобальное рабочее пространство Леи.

    Биологическая модель: Global Workspace Theory (Baars).
    Модули сознания конкурируют за внимание, победитель попадает в фокус.
    """

    def __init__(self, config: WorkspaceConfig | None = None) -> None:
        self.config = config or WorkspaceConfig()

        self.proposals: list[WorkspaceProposal] = []
        self.history: list[WorkspaceProposal] = []
        self.current_focus: WorkspaceProposal | None = None

        # Статистика
        self.total_submissions = 0
        self.total_selections = 0

        logger.info(
            f"GlobalWorkspace инициализирован: " f"max_proposals={self.config.max_proposals}"
        )

    def submit(self, proposal: WorkspaceProposal) -> None:
        """
        Подать предложение в workspace.

        Raises:
            LeyaWorkspaceError: если proposal невалиден
        """
        if not isinstance(proposal, WorkspaceProposal):
            raise LeyaWorkspaceError(
                "proposal должен быть экземпляром WorkspaceProposal",
                context={"type": type(proposal).__name__},
            )

        if not proposal.content:
            raise LeyaWorkspaceError(
                "proposal.content не может быть пустым",
                context={"source": proposal.source},
            )

        self.proposals.append(proposal)
        self.total_submissions += 1

        # Ограничение размера
        if len(self.proposals) > self.config.max_proposals:
            self._prune_proposals()

        logger.debug(
            f"GlobalWorkspace: Предложение от {proposal.source} "
            f"(priority={proposal.priority.name}, urgency={proposal.urgency:.2f})"
        )

    def _prune_proposals(self) -> None:
        """Удаление наименее релевантных proposals."""
        # Сортировка по score (предварительная оценка без drive_state)
        self.proposals.sort(
            key=lambda p: p.compute_score({}),
            reverse=True,
        )
        removed = self.proposals[self.config.max_proposals :]
        self.proposals = self.proposals[: self.config.max_proposals]

        if removed:
            logger.debug(f"GlobalWorkspace: Удалено {len(removed)} устаревших proposals")

    def select_winner(self, drive_state: dict[str, float]) -> WorkspaceProposal | None:
        """
        Выбрать победителя среди proposals.

        Args:
            drive_state: Текущее состояние драйвов для учёта relevance

        Returns:
            WorkspaceProposal-победитель или None
        """
        if not self.proposals:
            return None

        # Удаление устаревших
        self.clear_expired()

        if not self.proposals:
            return None

        # Вычисление score для каждого
        scored = [(p, p.compute_score(drive_state)) for p in self.proposals]
        scored.sort(key=lambda x: x[1], reverse=True)

        winner, score = scored[0]

        # Перемещение в историю
        self.proposals.remove(winner)
        self.history.append(winner)
        self.total_selections += 1

        # Ограничение истории
        if len(self.history) > self.config.max_history:
            self.history = self.history[-self.config.max_history :]

        self.current_focus = winner

        logger.info(
            f"GlobalWorkspace: Победитель — {winner.source} "
            f"(score={score:.3f}, content={winner.content[:50]}...)"
        )

        return winner

    def clear_expired(self, max_age: float | None = None) -> None:
        """Удаление устаревших proposals."""
        if max_age is None:
            max_age = self.config.proposal_decay_start + self.config.proposal_decay_duration

        current_time = time.time()
        original_count = len(self.proposals)

        self.proposals = [p for p in self.proposals if (current_time - p.timestamp) < max_age]

        removed_count = original_count - len(self.proposals)
        if removed_count > 0:
            logger.debug(f"GlobalWorkspace: Удалено {removed_count} устаревших proposals")

    def get_focus(self) -> WorkspaceProposal | None:
        """Получить текущий фокус внимания."""
        return self.current_focus

    def get_workspace_status(self) -> dict:
        """
        Возвращает полное состояние workspace: все proposals + текущий focus.
        Публичный API для UI.

        Returns:
            {
                "proposals": list[dict],
                "focus": dict | None,
                "total": int,
            }
        """
        import time

        proposals_data = []
        for i, p in enumerate(self.proposals):
            proposals_data.append(
                {
                    "id": i,
                    "source": p.source,
                    "content": p.content,
                    "action_type": p.action_type,
                    "priority": p.priority.name if hasattr(p.priority, "name") else str(p.priority),
                    "urgency": p.urgency,
                    "drive_relevance": p.drive_relevance,
                    "timestamp": p.timestamp,
                    "age_seconds": time.time() - p.timestamp,
                }
            )

        focus = self.get_focus()
        focus_data = None
        if focus:
            focus_data = {
                "source": focus.source,
                "content": focus.content,
                "action_type": focus.action_type,
                "priority": (
                    focus.priority.name if hasattr(focus.priority, "name") else str(focus.priority)
                ),
                "urgency": focus.urgency,
                "drive_relevance": focus.drive_relevance,
            }

        return {
            "proposals": proposals_data,
            "focus": focus_data,
            "total": len(proposals_data),
        }

    def get_status(self) -> dict[str, Any]:
        """Получить статус workspace для диагностики."""
        return {
            "proposals_count": len(self.proposals),
            "history_count": len(self.history),
            "current_focus": (
                {
                    "source": self.current_focus.source,
                    "content": self.current_focus.content[:100],
                    "action_type": self.current_focus.action_type,
                }
                if self.current_focus
                else None
            ),
            "total_submissions": self.total_submissions,
            "total_selections": self.total_selections,
        }

    def force_submit(
        self,
        source: str,
        content: str,
        action_type: str = "none",
        priority: Priority = Priority.HIGH,
        urgency: float = 0.8,
        drive_relevance: float = 0.8,
    ) -> WorkspaceProposal:
        """Принудительная подача proposal (для тестирования)."""
        proposal = WorkspaceProposal(
            source=source,
            content=content,
            action_type=action_type,
            priority=priority,
            urgency=urgency,
            drive_relevance=drive_relevance,
        )
        self.submit(proposal)
        return proposal

    def get_recent_history(self, limit: int = 10) -> list[dict[str, Any]]:
        """Получить недавнюю историю proposals."""
        return [
            {
                "source": p.source,
                "content": p.content[:100],
                "action_type": p.action_type,
                "priority": p.priority.name,
                "timestamp": p.timestamp,
            }
            for p in self.history[-limit:]
        ]
