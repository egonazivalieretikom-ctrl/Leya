"""
leya_core/global_workspace.py — Глобальное рабочее пространство.
Модель Baars/Dehaene: модули соревнуются за "внимание" сознания.
Только победитель попадает в сознательный поток (internal_monologue).
"""

import logging
import time
import json
from typing import Dict, Any, Optional, List
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

logger = logging.getLogger("GlobalWorkspace")


class Priority(Enum):
    CRITICAL = 5    # Угроза существованию
    HIGH = 4        # Сильная потребность
    MEDIUM = 3      # Обычная потребность
    LOW = 2         # Слабая потребность
    BACKGROUND = 1  # Фоновый процесс


@dataclass
class WorkspaceProposal:
    """Предложение от модуля в глобальное рабочее пространство."""
    source: str
    content: str
    action_type: str
    priority: Priority
    urgency: float = 0.5
    drive_relevance: float = 0.0
    timestamp: float = field(default_factory=time.time)
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def compute_score(self, drive_state: Dict[str, float]) -> float:
        """Вычисляет итоговый счёт предложения."""
        base_score = self.priority.value / 5.0
        urgency_modifier = self.urgency
        drive_modifier = self.drive_relevance
        
        score = (base_score * 0.4) + (urgency_modifier * 0.3) + (drive_modifier * 0.3)
        
        # Штраф за устаревание
        age = time.time() - self.timestamp
        if age > 60:
            decay = max(0.5, 1.0 - (age - 60) / 300)
            score *= decay
        
        return score


class GlobalWorkspace:
    """Центральный арбитр сознания."""
    
    def __init__(self):
        self.proposals: List[WorkspaceProposal] = []
        self.max_proposals = 50
        self.history: List[Dict[str, Any]] = []
        self.max_history = 100
    
    def submit(self, proposal: WorkspaceProposal):
        """Модуль подаёт предложение."""
        self.proposals.append(proposal)
        
        if len(self.proposals) > self.max_proposals:
            self.proposals.sort(key=lambda p: p.compute_score({}), reverse=True)
            self.proposals = self.proposals[:self.max_proposals]
        
        logger.debug(f"GlobalWorkspace: Предложение от {proposal.source} (priority: {proposal.priority.name})")
    
    def select_winner(self, drive_state: Dict[str, float]) -> Optional[WorkspaceProposal]:
        """Выбирает победителя — предложение с наивысшим счётом."""
        if not self.proposals:
            return None
        
        scored = [(p.compute_score(drive_state), p) for p in self.proposals]
        scored.sort(key=lambda x: x[0], reverse=True)
        
        winner_score, winner = scored[0]
        self.proposals.remove(winner)
        
        self.history.append({
            "source": winner.source,
            "content": winner.content[:200],
            "action_type": winner.action_type,
            "score": round(winner_score, 3),
            "timestamp": datetime.now().isoformat()
        })
        
        if len(self.history) > self.max_history:
            self.history = self.history[-self.max_history:]
        
        logger.info(f"GlobalWorkspace: 🏆 Победитель — {winner.source} (score: {winner_score:.2f}, action: {winner.action_type})")
        
        return winner
    
    def get_status(self) -> Dict[str, Any]:
        """Текущий статус рабочего пространства."""
        return {
            "pending": len(self.proposals),
            "top_proposals": [
                {
                    "source": p.source,
                    "content": p.content[:100],
                    "priority": p.priority.name,
                    "score": round(p.compute_score({}), 3)
                }
                for p in sorted(self.proposals, key=lambda p: p.compute_score({}), reverse=True)[:5]
            ],
            "recent_winners": self.history[-5:]
        }
    
    def clear_expired(self, max_age: float = 300.0):
        """Удаляет устаревшие предложения."""
        now = time.time()
        before = len(self.proposals)
        self.proposals = [p for p in self.proposals if now - p.timestamp < max_age]
        removed = before - len(self.proposals)
        if removed > 0:
            logger.debug(f"GlobalWorkspace: Удалено {removed} устаревших предложений")