"""
leya_core/global_workspace.py — Глобальное рабочее пространство Леи.
Этап 4.4: Полная переработка. Теория Global Workspace, биологическая модель, интеграция config.py.
Согласно ARCHITECTURE.md: WorkspaceProposal, submit, select_winner/get_focus, clear_expired.
"""
import logging
import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Any

logger = logging.getLogger("GlobalWorkspace")


# =================================================================================
# МОДЕЛИ ДАННЫХ
# =================================================================================

class Priority(Enum):
    """Приоритет предложения в глобальном рабочем пространстве."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"
    
    @property
    def weight(self) -> float:
        """Вес приоритета для расчета score."""
        weights = {
            Priority.LOW: 0.3,
            Priority.MEDIUM: 0.6,
            Priority.HIGH: 0.9,
            Priority.CRITICAL: 1.2
        }
        return weights.get(self, 0.5)


@dataclass
class WorkspaceProposal:
    """
    Предложение для глобального рабочего пространства.
    Согласно ARCHITECTURE.md: source, content, action_type, priority, urgency, drive_relevance, metadata.
    """
    source: str  # Источник предложения (homeostasis, drives, memory, external)
    content: str  # Содержание предложения
    action_type: str = "workspace_action"  # Тип действия
    priority: Priority = Priority.MEDIUM  # Приоритет
    urgency: float = 0.5  # Срочность (0.0 - 1.0)
    drive_relevance: float = 0.5  # Релевантность текущим драйвам (0.0 - 1.0)
    metadata: Dict[str, Any] = field(default_factory=dict)  # Дополнительные данные
    
    # Автоматически заполняемые поля
    id: str = field(default_factory=lambda: str(uuid.uuid4()))
    timestamp: float = field(default_factory=time.time)
    ttl: float = 300.0  # Time-to-live в секундах (5 минут по умолчанию)
    activation_count: int = 0  # Количество активаций
    
    def __post_init__(self):
        """Валидация полей."""
        self.content = self.content.strip() if self.content else ""
        self.source = self.source.strip() if self.source else "unknown"
        self.action_type = self.action_type.strip() if self.action_type else "workspace_action"
        
        # Валидация числовых значений
        self.urgency = max(0.0, min(1.0, self.urgency))
        self.drive_relevance = max(0.0, min(1.0, self.drive_relevance))
        self.ttl = max(10.0, min(3600.0, self.ttl))
        
        # Валидация priority
        if not isinstance(self.priority, Priority):
            try:
                self.priority = Priority(self.priority)
            except (ValueError, KeyError):
                logger.warning(f"Некорректный priority: {self.priority}. Сброс в MEDIUM")
                self.priority = Priority.MEDIUM
    
    def is_expired(self, current_time: float = None) -> bool:
        """Проверка, устарело ли предложение."""
        if current_time is None:
            current_time = time.time()
        return (current_time - self.timestamp) > self.ttl
    
    def get_age(self, current_time: float = None) -> float:
        """Получение возраста предложения в секундах."""
        if current_time is None:
            current_time = time.time()
        return current_time - self.timestamp
    
    def calculate_score(self, drive_state: Dict[str, float], current_time: float = None) -> float:
        """
        Расчет score предложения для конкуренции за внимание.
        Биологическая модель: score = priority_weight * urgency * drive_relevance * decay
        
        Args:
            drive_state: Текущее состояние драйвов {drive_name: value}
            current_time: Текущее время (для расчета затухания)
            
        Returns:
            Score (0.0 - ∞)
        """
        if current_time is None:
            current_time = time.time()
        
        # Базовые компоненты
        priority_weight = self.priority.weight
        urgency_factor = self.urgency
        
        # Релевантность драйвам: учитываем максимальное значение драйва
        max_drive = max(drive_state.values()) if drive_state else 0.5
        drive_factor = self.drive_relevance * (0.5 + max_drive * 0.5)
        
        # Затухание со временем (забывание)
        age = self.get_age(current_time)
        decay_factor = max(0.1, 1.0 - (age / self.ttl))
        
        # Финальный score
        score = priority_weight * urgency_factor * drive_factor * decay_factor
        
        # Бонус за повторные активации (LTP-подобный эффект)
        activation_bonus = min(self.activation_count * 0.05, 0.3)
        score += activation_bonus
        
        return max(0.0, score)


# =================================================================================
# ГЛОБАЛЬНОЕ РАБОЧЕЕ ПРОСТРАНСТВО
# =================================================================================

class GlobalWorkspace:
    """
    Глобальное рабочее пространство Леи.
    Согласно ARCHITECTURE.md: submit, select_winner/get_focus, clear_expired.
    Реализует теорию Global Workspace — конкуренцию за внимание сознания.
    """
    
    def __init__(
        self,
        max_proposals: int = 50,
        default_ttl: float = 300.0,
        min_score_threshold: float = 0.1
    ):
        """
        Инициализация GlobalWorkspace.
        
        Args:
            max_proposals: Максимальное количество предложений в workspace
            default_ttl: Time-to-live по умолчанию для новых предложений (секунды)
            min_score_threshold: Минимальный score для выбора победителя
        """
        self.max_proposals = max_proposals
        self.default_ttl = default_ttl
        self.min_score_threshold = min_score_threshold
        
        # Хранилище предложений
        self.proposals: Dict[str, WorkspaceProposal] = {}
        
        # История победителей (для анализа паттернов)
        self.winner_history: List[str] = []
        self.max_history_size = 20
        
        logger.info(f"✅ GlobalWorkspace инициализирован. Max proposals: {max_proposals}, TTL: {default_ttl}s")
    
    # =================================================================================
    # ОТПРАВКА ПРЕДЛОЖЕНИЙ
    # =================================================================================
    
    def submit(self, proposal: WorkspaceProposal) -> bool:
        """
        Отправка предложения в глобальное рабочее пространство.
        Согласно ARCHITECTURE.md: submit(proposal).
        
        Args:
            proposal: Предложение для добавления
            
        Returns:
            True если предложение успешно добавлено
        """
        try:
            # Валидация
            if not proposal.content:
                logger.warning("Пустое содержание предложения. Отклонено.")
                return False
            
            # Установка TTL по умолчанию, если не указан
            if proposal.ttl <= 0:
                proposal.ttl = self.default_ttl
            
            # Проверка дубликатов (по content + source)
            for existing in self.proposals.values():
                if (existing.content == proposal.content and 
                    existing.source == proposal.source and
                    not existing.is_expired()):
                    # Обновляем существующее предложение
                    existing.urgency = max(existing.urgency, proposal.urgency)
                    existing.priority = max(existing.priority, proposal.priority, 
                                          key=lambda p: p.weight)
                    existing.activation_count += 1
                    logger.debug(f"Обновлено существующее предложение: {proposal.id}")
                    return True
            
            # Добавление нового предложения
            self.proposals[proposal.id] = proposal
            
            # Ограничение размера
            if len(self.proposals) > self.max_proposals:
                self._cleanup_oldest()
            
            logger.info(f"✅ Предложение добавлено: {proposal.source} → {proposal.content[:50]}... "
                       f"(priority={proposal.priority.value}, urgency={proposal.urgency:.2f})")
            return True
            
        except Exception as e:
            logger.error(f"Ошибка отправки предложения: {e}", exc_info=True)
            return False
    
    # =================================================================================
    # ВЫБОР ПОБЕДИТЕЛЯ
    # =================================================================================
    
    def select_winner(self, drive_state: Dict[str, float]) -> Optional[WorkspaceProposal]:
        """
        Выбор самого "сознательного" предложения (победителя).
        Согласно ARCHITECTURE.md: select_winner(drive_state).
        
        Args:
            drive_state: Текущее состояние драйвов {drive_name: value}
            
        Returns:
            WorkspaceProposal победителя или None
        """
        try:
            current_time = time.time()
            
            # Очистка устаревших предложений
            self.clear_expired()
            
            if not self.proposals:
                logger.debug("Workspace пуст. Нет победителя.")
                return None
            
            # Расчет score для каждого предложения
            scored_proposals = []
            for proposal in self.proposals.values():
                score = proposal.calculate_score(drive_state, current_time)
                scored_proposals.append((score, proposal))
            
            # Сортировка по score (убывание)
            scored_proposals.sort(key=lambda x: x[0], reverse=True)
            
            # Выбор победителя
            if scored_proposals:
                top_score, winner = scored_proposals[0]
                
                # Проверка минимального порога
                if top_score < self.min_score_threshold:
                    logger.debug(f"Score победителя ({top_score:.3f}) ниже порога "
                               f"({self.min_score_threshold}). Нет сознательного фокуса.")
                    return None
                
                # Обновление статистики победителя
                winner.activation_count += 1
                
                # Запись в историю
                self.winner_history.append(winner.id)
                if len(self.winner_history) > self.max_history_size:
                    self.winner_history = self.winner_history[-self.max_history_size:]
                
                logger.info(f"🏆 Победитель workspace: {winner.source} → {winner.content[:50]}... "
                           f"(score={top_score:.3f}, priority={winner.priority.value})")
                
                return winner
            
            return None
            
        except Exception as e:
            logger.error(f"Ошибка выбора победителя: {e}", exc_info=True)
            return None
    
    async def get_focus(self) -> Optional[WorkspaceProposal]:
        """
        Асинхронная версия получения фокуса внимания.
        Согласно ARCHITECTURE.md: get_focus().
        
        Returns:
            WorkspaceProposal в фокусе или None
        """
        try:
            # Используем пустой drive_state (будет обновлен в select_winner)
            return self.select_winner({})
        except Exception as e:
            logger.error(f"Ошибка get_focus: {e}", exc_info=True)
            return None
    
    # =================================================================================
    # ОЧИСТКА
    # =================================================================================
    
    def clear_expired(self):
        """
        Очистка устаревших предложений.
        Согласно ARCHITECTURE.md: clear_expired().
        """
        try:
            current_time = time.time()
            expired_ids = [
                proposal_id for proposal_id, proposal in self.proposals.items()
                if proposal.is_expired(current_time)
            ]
            
            for proposal_id in expired_ids:
                del self.proposals[proposal_id]
            
            if expired_ids:
                logger.debug(f"Очищено {len(expired_ids)} устаревших предложений")
                
        except Exception as e:
            logger.error(f"Ошибка очистки устаревших предложений: {e}", exc_info=True)
    
    def _cleanup_oldest(self):
        """Очистка самых старых предложений при превышении лимита."""
        try:
            if len(self.proposals) <= self.max_proposals:
                return
            
            # Сортировка по timestamp (возрастание)
            sorted_proposals = sorted(
                self.proposals.items(),
                key=lambda x: x[1].timestamp
            )
            
            # Удаление самых старых
            to_remove = len(self.proposals) - self.max_proposals
            for i in range(to_remove):
                proposal_id = sorted_proposals[i][0]
                del self.proposals[proposal_id]
            
            logger.debug(f"Удалено {to_remove} самых старых предложений")
            
        except Exception as e:
            logger.error(f"Ошибка очистки старых предложений: {e}", exc_info=True)
    
    def clear_all(self):
        """Полная очистка workspace."""
        try:
            count = len(self.proposals)
            self.proposals.clear()
            logger.info(f"Workspace полностью очищен. Удалено {count} предложений")
        except Exception as e:
            logger.error(f"Ошибка полной очистки: {e}", exc_info=True)
    
    # =================================================================================
    # ПОЛУЧЕНИЕ ИНФОРМАЦИИ
    # =================================================================================
    
    def get_all_proposals(self) -> List[WorkspaceProposal]:
        """Получение всех текущих предложений."""
        try:
            self.clear_expired()
            return list(self.proposals.values())
        except Exception as e:
            logger.error(f"Ошибка получения предложений: {e}")
            return []
    
    def get_proposal_by_id(self, proposal_id: str) -> Optional[WorkspaceProposal]:
        """Получение предложения по ID."""
        try:
            proposal = self.proposals.get(proposal_id)
            if proposal and not proposal.is_expired():
                return proposal
            return None
        except Exception as e:
            logger.error(f"Ошибка получения предложения по ID: {e}")
            return None
    
    def get_proposals_by_source(self, source: str) -> List[WorkspaceProposal]:
        """Получение предложений по источнику."""
        try:
            self.clear_expired()
            return [p for p in self.proposals.values() if p.source == source]
        except Exception as e:
            logger.error(f"Ошибка получения предложений по источнику: {e}")
            return []
    
    def get_proposals_by_priority(self, priority: Priority) -> List[WorkspaceProposal]:
        """Получение предложений по приоритету."""
        try:
            self.clear_expired()
            return [p for p in self.proposals.values() if p.priority == priority]
        except Exception as e:
            logger.error(f"Ошибка получения предложений по приоритету: {e}")
            return []
    
    def get_winner_history(self) -> List[str]:
        """Получение истории победителей."""
        return self.winner_history.copy()
    
    # =================================================================================
    # СТАТИСТИКА
    # =================================================================================
    
    def get_stats(self) -> Dict[str, Any]:
        """Получение статистики workspace."""
        try:
            self.clear_expired()
            
            stats = {
                "total_proposals": len(self.proposals),
                "by_priority": {},
                "by_source": {},
                "avg_urgency": 0.0,
                "avg_drive_relevance": 0.0,
                "winner_history_size": len(self.winner_history)
            }
            
            if self.proposals:
                # Подсчет по приоритетам
                for priority in Priority:
                    count = len([p for p in self.proposals.values() if p.priority == priority])
                    stats["by_priority"][priority.value] = count
                
                # Подсчет по источникам
                sources = {}
                for proposal in self.proposals.values():
                    sources[proposal.source] = sources.get(proposal.source, 0) + 1
                stats["by_source"] = sources
                
                # Средние значения
                urgencies = [p.urgency for p in self.proposals.values()]
                relevances = [p.drive_relevance for p in self.proposals.values()]
                stats["avg_urgency"] = sum(urgencies) / len(urgencies) if urgencies else 0.0
                stats["avg_drive_relevance"] = sum(relevances) / len(relevances) if relevances else 0.0
            
            return stats
            
        except Exception as e:
            logger.error(f"Ошибка получения статистики: {e}")
            return {}
    
    def __len__(self) -> int:
        """Количество активных предложений."""
        self.clear_expired()
        return len(self.proposals)
    
    def __repr__(self) -> str:
        """Строковое представление."""
        return f"GlobalWorkspace(proposals={len(self)}, max={self.max_proposals})"