import torch
import torch.nn as nn
import torch.optim as optim
import time
from typing import Dict, List, Optional, Tuple
from Core.logger import log
from Core.state import LeyaState


class BehavioralPolicy(nn.Module):
    """
    Легковесная политика поведения Леи.
    
    Вход: состояние (10 признаков)
    Выход: 4 непрерывных модификатора [-1, 1]
    """
    def __init__(self, state_dim: int = 10, action_dim: int = 4):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(state_dim, 32),
            nn.ReLU(),
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Linear(16, action_dim),
            nn.Tanh()  # Ограничиваем выход [-1, 1]
        )
        self.optimizer = optim.Adam(self.parameters(), lr=0.0005)
        
    def forward(self, state: torch.Tensor) -> torch.Tensor:
        return self.net(state)


class BehavioralRL:
    """
    Система обучения поведению через подкрепление.
    
    Заменяет жёсткие промпты на адаптивную политику,
    которая формируется через опыт взаимодействия.
    """
    
    def __init__(self, state_obj: LeyaState):
        self.state_obj = state_obj
        self.policy = BehavioralPolicy()
        
        # Буфер для онлайн-обучения
        self.last_state: Optional[torch.Tensor] = None
        self.last_action: Optional[torch.Tensor] = None
        self.last_log_prob: Optional[torch.Tensor] = None
        
        # Статистика и обучение
        self.update_counter = 0
        self.update_frequency = 20  # Обновляем каждые 20 взаимодействий
        self.reward_buffer: List[float] = []
        self.interaction_count = 0
        
        # Веса файлов
        self.weights_path = "./leya_rl_policy.pt"
        self._load_weights()
        
        log.info("🎯 Behavioral RL initialized (Online Policy Gradient)")
    
    # ========================================================================
    # СОСТОЯНИЕ И ДЕЙСТВИЕ
    # ========================================================================
    
    def get_state_vector(self) -> torch.Tensor:
        """Преобразует состояние Леи в тензор для политики."""
        s = self.state_obj
        return torch.tensor([
            s.dopamine,
            s.cortisol,
            s.oxytocin,
            s.energy_level,
            getattr(s, 'physical_load', 0.5),
            getattr(s, 'cognitive_load', 0.5),
            getattr(s, 'empathic_resonance', 0.5),
            min(getattr(s, 'error_streak', 0) / 5.0, 1.0),
            s.acetylcholine,
            s.melatonin
        ], dtype=torch.float32).unsqueeze(0)
    
    def select_action(self) -> Dict[str, float]:
        """
        Выбирает модификаторы поведения на основе текущего состояния.
        
        Возвращает:
        - temperature_offset: [-0.3, 0.3]
        - length_factor: [0.5, 2.0]
        - initiative: [0.0, 1.0]
        - formality: [0.0, 1.0]
        """
        state_vec = self.get_state_vector()
        self.last_state = state_vec.clone()
        
        with torch.no_grad():
            action_raw = self.policy(state_vec)
        
        self.last_action = action_raw.clone()
        
        # Маппинг в осмысленные модификаторы
        modifiers = {
            "temperature_offset": float(action_raw[0][0]) * 0.3,
            "length_factor": float((action_raw[0][1] + 1) / 2 * 1.5 + 0.5),
            "initiative": float((action_raw[0][2] + 1) / 2),
            "formality": float((action_raw[0][3] + 1) / 2)
        }
        
        return modifiers
    
    # ========================================================================
    # ОБНОВЛЕНИЕ ПОЛИТИКИ (REINFORCE)
    # ========================================================================
    
    def update_policy(self, reward: float):
        """
        Онлайн-обновление политики через REINFORCE.
        
        reward > 0: поведение укрепляется
        reward < 0: поведение ослабляется
        """
        if self.last_state is None or self.last_action is None:
            return
        
        self.reward_buffer.append(reward)
        self.interaction_count += 1
        
        # Пакетное обновление для стабильности
        if self.interaction_count % self.update_frequency == 0:
            avg_reward = sum(self.reward_buffer) / max(1, len(self.reward_buffer))
            self.reward_buffer.clear()
            self.interaction_count = 0
            
            self._perform_update(avg_reward)
            log.info("🎯 RL Policy updated", avg_reward=f"{avg_reward:.2f}")
    
    def _perform_update(self, reward: float):
        """Шаг градиентного спуска с масштабирующим вознаграждением."""
        if self.last_action is None:
            return
        
        # Простой REINFORCE: градиент = reward * log_prob(action)
        # Для tanh-политики используем MSE как аппроксимацию
        action_pred = self.policy(self.last_state)
        loss = torch.nn.functional.mse_loss(action_pred, self.last_action, reduction='mean')
        
        # Масштабируем градиент вознаграждением
        scaled_loss = loss * reward
        
        self.policy.optimizer.zero_grad()
        scaled_loss.backward()
        torch.nn.utils.clip_grad_norm_(self.policy.parameters(), max_norm=1.0)
        self.policy.optimizer.step()
        
        self.last_state = None
        self.last_action = None
    
    # ========================================================================
    # СОХРАНЕНИЕ / ЗАГРУЗКА
    # ========================================================================
    
    def _load_weights(self):
        import os
        if os.path.exists(self.weights_path):
            try:
                self.policy.load_state_dict(torch.load(self.weights_path, map_location='cpu'))
                log.info("🎯 RL policy loaded", path=self.weights_path)
            except Exception as e:
                log.error("Failed to load RL weights", error=str(e))
    
    def save_weights(self):
        try:
            torch.save(self.policy.state_dict(), self.weights_path)
            log.info("🎯 RL policy saved", path=self.weights_path)
        except Exception as e:
            log.error("Failed to save RL weights", error=str(e))
    
    # ========================================================================
    # УТИЛИТЫ
    # ========================================================================
    
    def get_stats(self) -> Dict:
        return {
            "interactions": self.interaction_count,
            "update_counter": self.update_counter,
            "avg_reward_buffer": sum(self.reward_buffer) / max(1, len(self.reward_buffer)),
            "weights_loaded": True
        }