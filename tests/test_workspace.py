"""
Тесты для GlobalWorkspace.

Покрытие целевое: 46% → 70%

Проверяет:
- WorkspaceProposal
- submit
- select_winner (конкуренция proposals)
- clear_expired
- compute_score
"""

from __future__ import annotations

import time

import pytest

from leya_core.config import WorkspaceConfig
from leya_core.exceptions import LeyaWorkspaceError
from leya_core.global_workspace import GlobalWorkspace, Priority, WorkspaceProposal

# ============================================================================
# Тесты WorkspaceProposal
# ============================================================================


class TestWorkspaceProposal:
    """Тесты модели WorkspaceProposal."""

    def test_proposal_creation(self):
        """Proposal корректно создаётся."""
        proposal = WorkspaceProposal(
            source="user",
            content="Тестовое предложение",
            action_type="question",
            priority=Priority.MEDIUM,
            urgency=0.5,
            drive_relevance=0.5,
        )

        assert proposal.source == "user"
        assert proposal.content == "Тестовое предложение"
        assert proposal.priority == Priority.MEDIUM

    def test_compute_score(self):
        """compute_score вычисляет score."""
        proposal = WorkspaceProposal(
            source="user",
            content="Тест",
            priority=Priority.HIGH,
            urgency=0.8,
            drive_relevance=0.7,
        )

        score = proposal.compute_score({})

        assert isinstance(score, float)
        assert score > 0

    def test_compute_score_priority_weight(self):
        """Высокий приоритет даёт больший score."""
        low = WorkspaceProposal(source="user", content="Тест", priority=Priority.LOW)
        high = WorkspaceProposal(source="user", content="Тест", priority=Priority.CRITICAL)

        assert high.compute_score({}) > low.compute_score({})

    def test_compute_score_age_decay(self):
        """Старые proposals имеют меньший score."""
        old = WorkspaceProposal(
            source="user",
            content="Тест",
            priority=Priority.HIGH,
            timestamp=time.time() - 500,  # 500 секунд назад
        )
        new = WorkspaceProposal(
            source="user",
            content="Тест",
            priority=Priority.HIGH,
            timestamp=time.time(),
        )

        assert new.compute_score({}) > old.compute_score({})


# ============================================================================
# Тесты GlobalWorkspace
# ============================================================================


class TestGlobalWorkspace:
    """Тесты глобального рабочего пространства."""

    def test_init_with_config(self, test_workspace_config):
        """GlobalWorkspace корректно инициализируется."""
        ws = GlobalWorkspace(config=test_workspace_config)

        assert ws.config is test_workspace_config
        assert len(ws.proposals) == 0

    def test_init_default_config(self):
        """GlobalWorkspace инициализируется с конфигом по умолчанию."""
        ws = GlobalWorkspace()

        assert ws.config is not None

    def test_submit_proposal(self, test_workspace_config):
        """submit добавляет proposal."""
        ws = GlobalWorkspace(config=test_workspace_config)

        proposal = WorkspaceProposal(
            source="user",
            content="Тест",
            priority=Priority.MEDIUM,
        )
        ws.submit(proposal)

        assert len(ws.proposals) == 1
        assert ws.total_submissions == 1

    def test_submit_invalid_proposal(self, test_workspace_config):
        """submit бросает LeyaWorkspaceError для невалидного proposal."""
        ws = GlobalWorkspace(config=test_workspace_config)

        with pytest.raises(LeyaWorkspaceError):
            ws.submit("not a proposal")

    def test_submit_empty_content(self, test_workspace_config):
        """submit бросает LeyaWorkspaceError для пустого контента."""
        ws = GlobalWorkspace(config=test_workspace_config)

        proposal = WorkspaceProposal(source="user", content="")

        with pytest.raises(LeyaWorkspaceError):
            ws.submit(proposal)

    def test_select_winner(self, test_workspace_config):
        """select_winner выбирает proposal с наивысшим score."""
        ws = GlobalWorkspace(config=test_workspace_config)

        low = WorkspaceProposal(
            source="user",
            content="Низкий",
            priority=Priority.LOW,
            urgency=0.2,
        )
        high = WorkspaceProposal(
            source="user",
            content="Высокий",
            priority=Priority.CRITICAL,
            urgency=0.9,
        )

        ws.submit(low)
        ws.submit(high)

        winner = ws.select_winner({})

        assert winner is not None
        assert winner.content == "Высокий"

    def test_select_winner_empty(self, test_workspace_config):
        """select_winner возвращает None при пустом workspace."""
        ws = GlobalWorkspace(config=test_workspace_config)

        winner = ws.select_winner({})
        assert winner is None

    def test_select_winner_moves_to_history(self, test_workspace_config):
        """select_winner перемещает победителя в историю."""
        ws = GlobalWorkspace(config=test_workspace_config)

        proposal = WorkspaceProposal(
            source="user",
            content="Тест",
            priority=Priority.HIGH,
        )
        ws.submit(proposal)

        winner = ws.select_winner({})

        assert len(ws.proposals) == 0
        assert len(ws.history) == 1
        assert ws.total_selections == 1

    def test_clear_expired(self, test_workspace_config):
        """clear_expired удаляет устаревшие proposals."""
        ws = GlobalWorkspace(config=test_workspace_config)

        old = WorkspaceProposal(
            source="user",
            content="Старый",
            timestamp=time.time() - 1000,  # 1000 секунд назад
        )
        new = WorkspaceProposal(
            source="user",
            content="Новый",
            timestamp=time.time(),
        )

        ws.submit(old)
        ws.submit(new)

        ws.clear_expired(max_age=500)

        assert len(ws.proposals) == 1
        assert ws.proposals[0].content == "Новый"

    def test_get_status(self, test_workspace_config):
        """get_status возвращает статус."""
        ws = GlobalWorkspace(config=test_workspace_config)

        proposal = WorkspaceProposal(
            source="user",
            content="Тест",
            priority=Priority.HIGH,
        )
        ws.submit(proposal)

        status = ws.get_status()

        assert "proposals_count" in status
        assert "history_count" in status
        assert "total_submissions" in status
        assert status["proposals_count"] == 1

    def test_force_submit(self, test_workspace_config):
        """force_submit создаёт и подаёт proposal."""
        ws = GlobalWorkspace(config=test_workspace_config)

        proposal = ws.force_submit(
            source="test",
            content="Принудительное предложение",
            priority=Priority.HIGH,
        )

        assert len(ws.proposals) == 1
        assert proposal.content == "Принудительное предложение"

    def test_get_recent_history(self, test_workspace_config):
        """get_recent_history возвращает историю."""
        ws = GlobalWorkspace(config=test_workspace_config)

        for i in range(5):
            proposal = WorkspaceProposal(
                source="user",
                content=f"Тест {i}",
                priority=Priority.MEDIUM,
            )
            ws.submit(proposal)
            ws.select_winner({})

        history = ws.get_recent_history(limit=3)

        assert len(history) == 3
        assert "source" in history[0]
        assert "content" in history[0]

    # tests/test_workspace.py, метод test_max_proposals_limit

    def test_max_proposals_limit(self):
        """Workspace ограничивает количество proposals."""
        config = WorkspaceConfig(max_proposals=10)  # Минимум 10 согласно __post_init__
        ws = GlobalWorkspace(config=config)

        for i in range(15):  # Больше 10
            proposal = WorkspaceProposal(
                source="user",
                content=f"Тест {i}",
                priority=Priority.MEDIUM,
            )
            ws.submit(proposal)

        assert len(ws.proposals) <= 10
