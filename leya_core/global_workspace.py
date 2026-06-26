"""
leya_core/global_workspace.py
Глобальное рабочее пространство Леи — механизм внимания.

Архитектура:
- WorkspaceProposal: предложение от homeostasis, spontaneous thoughts, user
- Конкуренция предложений по priority, urgency, drive_relevance
- Затухание предложений со временем (proposal_decay)
- История предложений для диагностики и UI
- Выбор "победителя" (focus) для подачи в когнитивный цикл

Биологическая модель:
- Global Workspace Theory (Baars): конкуренция за внимание
- Предложения "борются" за попадание в фокус сознания
- Затухание: если предложение не выбрано, его актуальность падает

Этап 1.3:
- Интеграция с WorkspaceConfig
- Специфичные исключения (LeyaWorkspaceError)
- Затухание предложений
- История для UI
- Метрики для диагностики
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Dict, List, Optional

from .config import WorkspaceConfig
from .exceptions import LeyaWorkspaceError

logger = logging.getLogger(__name__)


class Priority(str, Enum):
    """Приоритет предложения в workspace."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"

    @property
    def weight(self) -> float:
        """Числовой вес для вычисления score."""
        weights = {
            Priority.LOW: 0.2,
            Priority.MEDIUM: 0.4,
            Priority.HIGH: 0.7,
            Priority.CRITICAL: 1.0,
        }
        return weights[self]


@dataclass
class WorkspaceProposal:
    """
    Предложение для попадания в фокус внимания.
    
    Биологическая модель:
    - source: источник (homeostasis, spontaneous, user, meta_cognition)
    - content: содержание предложения
    - action_type: тип действия (tool_name, internal_question, none)
    - priority: базовый приоритет
    - urgency: срочность (0.0–1.0)
    - drive_relevance: релевантность драйвам (0.0–1.0)
    - metadata: дополнительная информация
    
    Score вычисляется динамически с учётом затухания.
    """
    source: str
    content: str
    action_type: str = "none"
    priority: Priority = Priority.MEDIUM
    urgency: float = 0.5
    drive_relevance: float = 0.5
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # Внутренние поля (не инициализируются пользователем)
    created_at: float = field(default_factory=time.time)
    last_accessed: float = field(default_factory=time.time)
    access_count: int = 0
    _score_cache: Optional[float] = field(default=None, repr=False)
    _score_cache_time: float = field(default=0.0, repr=False)

    def compute_score(
        self,
        drive_state: Dict[str, float],
        config: Optional[WorkspaceConfig] = None,
    ) -> float:
        """
        Вычисление score предложения с учётом затухания.
        
        Формула:
        score = (priority_weight * 0.4 + urgency * 0.3 + drive_relevance * 0.3) * decay_factor
        
        где decay_factor = max(0.1, 1.0 - (age - decay_start) / decay_duration)
        
        Args:
            drive_state: Текущее состояние драйвов (для будущей адаптации)
            config: Конфигурация workspace (для параметров затухания)
            
        Returns:
            Score (0.0–1.0)
        """
        # Кэширование на 1 секунду
        current_time = time.time()
        if (
            self._score_cache is not None
            and current_time - self._score_cache_time < 1.0
        ):
            return self._score_cache

        # Базовый score
        base_score = (
            self.priority.weight * 0.4
            + self.urgency * 0.3
            + self.drive_relevance * 0.3
        )

        # Затухание
        config = config or WorkspaceConfig()
        age = current_time - self.created_at
        
        if age < config.proposal_decay_start:
            decay_factor = 1.0
        else:
            decay_duration = config.proposal_decay_duration
            decay_factor = max(0.1, 1.0 - (age - config.proposal_decay_start) / decay_duration)

        # Финальный score
        score = base_score * decay_factor
        score = max(0.0, min(1.0, score))

        # Кэширование
        self._score_cache = score
        self._score_cache_time = current_time

        return score

    def mark_accessed(self) -> None:
        """Пометить предложение как доступное (для статистики)."""
        self.last_accessed = time.time()
        self.access_count += 1
        # Сброс кэша
        self._score_cache = None

    def is_expired(self, max_age: float = 3600.0) -> bool:
        """
        Проверка, истекло ли предложение.
        
        Args:
            max_age: Максимальный возраст в секундах (по умолчанию 1 час)
            
        Returns:
            True, если предложение старше max_age
        """
        return (time.time() - self.created_at) > max_age

    def to_dict(self) -> Dict[str, Any]:
        """Сериализация для UI/диагностики."""
        return {
            "source": self.source,
            "content": self.content,
            "action_type": self.action_type,
            "priority": self.priority.value,
            "urgency": self.urgency,
            "drive_relevance": self.drive_relevance,
            "metadata": self.metadata,
            "created_at": self.created_at,
            "age_seconds": time.time() - self.created_at,
            "access_count": self.access_count,
        }


class GlobalWorkspace:
    """
    Глобальное рабочее пространство — механизм внимания Леи.
    
    Биологическая модель (Global Workspace Theory):
    - Множество модулей (homeostasis, reflection, user) подают предложения
    - Предложения конкурируют за попадание в фокус внимания
    - "Победитель" становится содержанием сознания (подаётся в когнитивный цикл)
    - Непобедившие предложения затухают со временем
    
    Архитектура:
    - proposals: текущий список активных предложений
    - history: история всех предложений (для UI/диагностики)
    - focus: текущий "победитель" (последнее выбранное предложение)
    """

    def __init__(self, config: Optional[WorkspaceConfig] = None) -> None:
        """
        Инициализация workspace.
        
        Args:
            config: Конфигурация workspace (лимиты, параметры затухания)
        """
        self.config = config or WorkspaceConfig()
        
        self.proposals: List[WorkspaceProposal] = []
        self.history: List[WorkspaceProposal] = []
        self.focus: Optional[WorkspaceProposal] = None
        
        # Статистика
        self._total_submissions = 0
        self._total_selections = 0

        logger.info(
            f"GlobalWorkspace инициализирован: "
            f"max_proposals={self.config.max_proposals}, "
            f"decay_start={self.config.proposal_decay_start}с"
        )

    def submit(self, proposal: WorkspaceProposal) -> None:
        """
        Подача предложения в workspace.
        
        Args:
            proposal: Предложение для конкуренции
            
        Raises:
            LeyaWorkspaceError: если proposal невалиден
        """
        # Валидация
        if not isinstance(proposal, WorkspaceProposal):
            raise LeyaWorkspaceError(
                "proposal должен быть экземпляром WorkspaceProposal",
                context={"type": type(proposal).__name__},
            )

        if not proposal.content or not proposal.content.strip():
            raise LeyaWorkspaceError(
                "proposal.content не может быть пустым",
                context={"source": proposal.source},
            )

        # Добавление в список
        self.proposals.append(proposal)
        self._total_submissions += 1

        # Ограничение размера списка
        if len(self.proposals) > self.config.max_proposals:
            # Сортировка по score и обрезка
            self.proposals.sort(
                key=lambda p: p.compute_score({}, self.config),
                reverse=True,
            )
            removed = self.proposals[self.config.max_proposals:]
            self.proposals = self.proposals[:self.config.max_proposals]
            
            # Добавление удалённых в историю
            for p in removed:
                self.history.append(p)
            
            logger.debug(
                f"GlobalWorkspace: Удалено {len(removed)} предложений "
                f"(превышен лимит {self.config.max_proposals})"
            )

        # Ограничение истории
        if len(self.history) > self.config.max_history:
            self.history = self.history[-self.config.max_history:]

        logger.debug(
            f"GlobalWorkspace: Предложение от {proposal.source} "
            f"(priority={proposal.priority.value}, urgency={proposal.urgency:.2f})"
        )

    def select_winner(
        self,
        drive_state: Dict[str, float],
        min_score: float = 0.3,
    ) -> Optional[WorkspaceProposal]:
        """
        Выбор "победителя" — предложения с наибольшим score.
        
        Алгоритм:
        1. Удаление истёкших предложений
        2. Вычисление score для каждого предложения
        3. Выбор предложения с максимальным score
        4. Если score < min_score, возвращаем None
        
        Args:
            drive_state: Текущее состояние драйвов (для адаптации score)
            min_score: Минимальный порог score для выбора
            
        Returns:
            WorkspaceProposal-победитель или None
        """
        # Удаление истёкших
        self.clear_expired()

        if not self.proposals:
            return None

        # Вычисление score для всех
        scored_proposals = [
            (p, p.compute_score(drive_state, self.config))
            for p in self.proposals
        ]

        # Сортировка по score
        scored_proposals.sort(key=lambda x: x[1], reverse=True)

        # Выбор победителя
        winner, winner_score = scored_proposals[0]

        if winner_score < min_score:
            logger.debug(
                f"GlobalWorkspace: Победитель не выбран "
                f"(max_score={winner_score:.3f} < min_score={min_score})"
            )
            return None

        # Обновление focus
        self.focus = winner
        winner.mark_accessed()
        self._total_selections += 1

        # Удаление победителя из списка (он уже в фокусе)
        self.proposals.remove(winner)

        logger.info(
            f"GlobalWorkspace: Победитель — {winner.source} "
            f"(score={winner_score:.3f}, content={winner.content[:50]}...)"
        )

        return winner

    def get_focus(self) -> Optional[WorkspaceProposal]:
        """
        Получение текущего фокуса внимания.
        
        Returns:
            Текущий WorkspaceProposal-фокус или None
        """
        return self.focus

    def clear_expired(self, max_age: Optional[float] = None) -> int:
        """
        Удаление истёкших предложений.
        
        Args:
            max_age: Максимальный возраст в секундах (по умолчанию из config)
            
        Returns:
            Количество удалённых предложений
        """
        max_age = max_age or self.config.proposal_decay_duration * 2  # 2x decay_duration

        initial_count = len(self.proposals)
        expired = [p for p in self.proposals if p.is_expired(max_age)]
        
        for p in expired:
            self.proposals.remove(p)
            self.history.append(p)

        removed_count = initial_count - len(self.proposals)
        
        if removed_count > 0:
            logger.debug(f"GlobalWorkspace: Удалено {removed_count} истёкших предложений")

        # Ограничение истории
        if len(self.history) > self.config.max_history:
            self.history = self.history[-self.config.max_history:]

        return removed_count

    def get_proposals(
        self,
        include_expired: bool = False,
        limit: Optional[int] = None,
    ) -> List[WorkspaceProposal]:
        """
        Получение списка предложений.
        
        Args:
            include_expired: Включать ли истёкшие предложения
            limit: Максимальное количество (по умолчанию все)
            
        Returns:
            Список WorkspaceProposal, отсортированный по score
        """
        proposals = self.proposals.copy()

        if not include_expired:
            proposals = [p for p in proposals if not p.is_expired()]

        # Сортировка по score
        proposals.sort(
            key=lambda p: p.compute_score({}, self.config),
            reverse=True,
        )

        if limit:
            proposals = proposals[:limit]

        return proposals

    def get_history(self, limit: int = 50) -> List[WorkspaceProposal]:
        """
        Получение истории предложений.
        
        Args:
            limit: Максимальное количество (по умолчанию 50)
            
        Returns:
            Список последних WorkspaceProposal из истории
        """
        return self.history[-limit:]

    def get_stats(self) -> Dict[str, Any]:
        """
        Получение статистики workspace для диагностики.
        
        Returns:
            Dict с метриками
        """
        active_count = len([p for p in self.proposals if not p.is_expired()])
        expired_count = len(self.proposals) - active_count

        # Средний score
        if self.proposals:
            scores = [p.compute_score({}, self.config) for p in self.proposals]
            avg_score = sum(scores) / len(scores)
            max_score = max(scores)
        else:
            avg_score = 0.0
            max_score = 0.0

        return {
            "active_proposals": active_count,
            "expired_proposals": expired_count,
            "total_proposals": len(self.proposals),
            "history_size": len(self.history),
            "total_submissions": self._total_submissions,
            "total_selections": self._total_selections,
            "avg_score": avg_score,
            "max_score": max_score,
            "current_focus": self.focus.to_dict() if self.focus else None,
        }

    def clear(self) -> None:
        """Полная очистка workspace (для отладки/сброса)."""
        cleared_count = len(self.proposals)
        self.proposals.clear()
        self.focus = None
        
        logger.info(f"GlobalWorkspace: Очищено {cleared_count} предложений")

    def force_submit(
        self,
        source: str,
        content: str,
        priority: Priority = Priority.CRITICAL,
        urgency: float = 1.0,
        drive_relevance: float = 1.0,
        action_type: str = "none",
        metadata: Optional[Dict[str, Any]] = None,
    ) -> WorkspaceProposal:
        """
        Принудительная подача предложения с высоким приоритетом (для тестов).
        
        Args:
            source: Источник предложения
            content: Содержание
            priority: Приоритет (по умолчанию CRITICAL)
            urgency: Срочность (по умолчанию 1.0)
            drive_relevance: Релевантность драйвам (по умолчанию 1.0)
            action_type: Тип действия
            metadata: Дополнительные данные
            
        Returns:
            Созданное WorkspaceProposal
        """
        proposal = WorkspaceProposal(
            source=source,
            content=content,
            action_type=action_type,
            priority=priority,
            urgency=urgency,
            drive_relevance=drive_relevance,
            metadata=metadata or {},
        )
        
        self.submit(proposal)
        
        logger.warning(
            f"GlobalWorkspace: Принудительная подача от {source} "
            f"(priority={priority.value}, urgency={urgency:.2f})"
        )
        
        return proposal