import torch
import torch.nn as nn
import snntorch as snn
from typing import Dict, List, Optional
from Core.logger import log
from Core.state import LeyaState


def safe_round(x, ndigits=3):
    """Безопасный round для чисел и тензоров PyTorch"""
    if torch.is_tensor(x):
        val = x.item() if x.numel() == 1 else x.mean().item()
        return round(val, ndigits)
    return round(x, ndigits)


class SpecializedAmygdalaSNN(nn.Module):
    """
    Специализированная амигдала с разными слоями для разных типов стимулов.
    
    Архитектура:
    - Входной слой: 12 нейронов (сенсоры + контекст)
    - 4 специализированных слоя по 8 нейронов:
      * Угроза → кортизол + норадреналин
      * Награда → дофамин + эндорфины
      * Социальный сигнал → окситоцин
      * Новизна → ацетилхолин
    - Выходной слой: 32 → 8 (конкатенация специализированных слоёв)
    """
    
    OUTPUT_MAPPING = {
        0: "dopamine",
        1: "serotonin",
        2: "cortisol",
        3: "oxytocin",
        4: "acetylcholine",
        5: "norepinephrine",
        6: "endorphins",
        7: "gaba"
    }
    
    def __init__(self):
        super().__init__()
        
        # Параметры LIF-нейронов
        beta = 0.85
        threshold = 0.5
        
        # Входной слой: 12 → 32
        self.fc_input = nn.Linear(12, 32)
        self.lif_input = snn.Leaky(beta=beta, threshold=threshold, reset_mechanism='subtract')
        
        # Специализированные слои: 32 → 8 каждый
        # Угроза → кортизол + норадреналин
        self.fc_threat = nn.Linear(32, 8)
        self.lif_threat = snn.Leaky(beta=beta, threshold=threshold, reset_mechanism='subtract')
        
        # Награда → дофамин + эндорфины
        self.fc_reward = nn.Linear(32, 8)
        self.lif_reward = snn.Leaky(beta=beta, threshold=threshold, reset_mechanism='subtract')
        
        # Социальный сигнал → окситоцин
        self.fc_social = nn.Linear(32, 8)
        self.lif_social = snn.Leaky(beta=beta, threshold=threshold, reset_mechanism='subtract')
        
        # Новизна → ацетилхолин
        self.fc_novelty = nn.Linear(32, 8)
        self.lif_novelty = snn.Leaky(beta=beta, threshold=threshold, reset_mechanism='subtract')
        
        # Выходной слой: 32 → 8 (конкатенация специализированных слоёв)
        self.fc_output = nn.Linear(32, 8)
        self.lif_output = snn.Leaky(beta=beta, threshold=threshold, reset_mechanism='subtract')
        
        # Инициализация весов
        self._init_weights()
        
        # История спайков (для STDP)
        self.spike_history: List[Dict] = []
        self.max_history = 100
        
        # Статистика
        self.total_spikes = 0
        self.total_forward_passes = 0
        
        log.info("🧠 Specialized Amygdala SNN initialized (4 specialized layers + concatenation)")
    
    def _init_weights(self):
        """Инициализирует веса сети с биологически правдоподобными значениями."""
        with torch.no_grad():
            # Инициализируем все веса малыми случайными значениями
            nn.init.xavier_uniform_(self.fc_input.weight, gain=0.3)
            nn.init.xavier_uniform_(self.fc_output.weight, gain=0.3)
            nn.init.zeros_(self.fc_input.bias)
            nn.init.zeros_(self.fc_output.bias)
            
            # Усиливаем специализированные связи
            # Угроза → кортизол (индекс 2) + норадреналин (индекс 5)
            self.fc_threat.weight[2, :] *= 2.0
            self.fc_threat.weight[5, :] *= 2.0
            
            # Награда → дофамин (индекс 0) + эндорфины (индекс 6)
            self.fc_reward.weight[0, :] *= 2.0
            self.fc_reward.weight[6, :] *= 2.0
            
            # Социальный сигнал → окситоцин (индекс 3)
            self.fc_social.weight[3, :] *= 2.0
            
            # Новизна → ацетилхолин (индекс 4)
            self.fc_novelty.weight[4, :] *= 2.0
    
    def forward(self, input_spikes: torch.Tensor, num_steps: int = 10) -> Dict[str, float]:
        """Прямой проход через сеть с временной симуляцией."""
        self.total_forward_passes += 1
        
        # Инициализируем мембранные потенциалы
        mem_input = self.lif_input.init_leaky()
        mem_threat = self.lif_threat.init_leaky()
        mem_reward = self.lif_reward.init_leaky()
        mem_social = self.lif_social.init_leaky()
        mem_novelty = self.lif_novelty.init_leaky()
        mem_output = self.lif_output.init_leaky()
        
        # Для накопления выходных спайков
        output_spike_counts = torch.zeros(8)
        specialized_spikes = {
            "threat": torch.zeros(8),
            "reward": torch.zeros(8),
            "social": torch.zeros(8),
            "novelty": torch.zeros(8)
        }
        
        # Временная симуляция
        for t in range(num_steps):
            # Извлекаем входные спайки для текущего шага
            spk_in = input_spikes[0, t, :].unsqueeze(0)  # [1, 12]
            
            # Входной слой
            cur_input = self.fc_input(spk_in)
            spk_input, mem_input = self.lif_input(cur_input, mem_input)
            
            # Специализированные слои
            # Угроза
            cur_threat = self.fc_threat(spk_input)
            spk_threat, mem_threat = self.lif_threat(cur_threat, mem_threat)
            specialized_spikes["threat"] += spk_threat.squeeze(0).detach()
            
            # Награда
            cur_reward = self.fc_reward(spk_input)
            spk_reward, mem_reward = self.lif_reward(cur_reward, mem_reward)
            specialized_spikes["reward"] += spk_reward.squeeze(0).detach()
            
            # Социальный сигнал
            cur_social = self.fc_social(spk_input)
            spk_social, mem_social = self.lif_social(cur_social, mem_social)
            specialized_spikes["social"] += spk_social.squeeze(0).detach()
            
            # Новизна
            cur_novelty = self.fc_novelty(spk_input)
            spk_novelty, mem_novelty = self.lif_novelty(cur_novelty, mem_novelty)
            specialized_spikes["novelty"] += spk_novelty.squeeze(0).detach()
            
            # Конкатенация специализированных слоёв (создаёт [1, 32])
            combined = torch.cat([spk_threat, spk_reward, spk_social, spk_novelty], dim=1)
            
            # Выходной слой
            cur_output = self.fc_output(combined)
            spk_output, mem_output = self.lif_output(cur_output, mem_output)
            
            # Накапливаем выходные спайки
            output_spike_counts += spk_output.squeeze(0).detach()
        
        # Преобразуем спайки в гормональные стимулы
        hormonal_impact = self._spikes_to_hormones(output_spike_counts)
        
        # Сохраняем историю (для STDP)
        self._save_spike_history(input_spikes, output_spike_counts)
        
        return hormonal_impact
    
    def _spikes_to_hormones(self, output_spikes: torch.Tensor) -> Dict[str, float]:
        """Преобразует выходные спайки в гормональные стимулы."""
        impact = {}
        max_possible = 10.0
        normalized = output_spikes / max_possible
        
        for idx, hormone in self.OUTPUT_MAPPING.items():
            spike_rate = normalized[idx].item()
            stimulus = (spike_rate - 0.3) * 0.15
            stimulus = max(-0.15, min(0.15, stimulus))
            impact[hormone] = float(stimulus)
        
        return impact
    
    def _save_spike_history(self, input_spikes, output_spikes):
        """Сохраняет историю спайков для STDP."""
        self.spike_history.append({
            "input": input_spikes.detach(),
            "output": output_spikes.detach()
        })
        
        if len(self.spike_history) > self.max_history:
            self.spike_history.pop(0)
        
        self.total_spikes += output_spikes.sum().item()


class EmotionalSNNSystem:
    """Система эмоциональной оценки на основе специализированной SNN."""
    
    def __init__(self, state: LeyaState):
        self.state = state
        self.network = SpecializedAmygdalaSNN()
        
        self.enabled = True
        self.stdp_learning_rate = 0.001
        self.stdp_enabled = True
        
        self.total_evaluations = 0
        
        log.info("🧠 Emotional SNN System initialized (specialized architecture)")
    
    def evaluate(self, event_type: str, content: str, 
                 context_history: List[Dict] = None) -> Dict[str, float]:
        """Оценивает стимул через SNN."""
        if not self.enabled:
            return {}
        
        self.total_evaluations += 1
        
        try:
            # Кодируем стимул в спайки
            input_spikes = self._encode_stimulus(event_type, content, context_history)
            
            # Пропускаем через сеть
            hormonal_impact = self.network(input_spikes)
            
            # Применяем STDP
            if self.stdp_enabled and self.total_evaluations % 5 == 0:
                self._apply_stdp()
            
            # Логируем с использованием safe_round
            active_hormones = {
                k: safe_round(v, 3) 
                for k, v in hormonal_impact.items() 
                if abs(v) > 0.01
            }
            
            if active_hormones:
                log.info(f"🧠 SNN evaluation: event={event_type}, hormones={active_hormones}, spikes={self.network.total_spikes}")
            
            # Сохраняем веса периодически
            if self.total_evaluations % 100 == 0:
                self.save_weights()
            
            return hormonal_impact
            
        except Exception as e:
            log.error("SNN evaluation failed", error=str(e))
            return {}
    
    def _encode_stimulus(self, event_type: str, content: str, 
                         context_history: List[Dict] = None) -> torch.Tensor:
        """Преобразует стимул в паттерн входных спайков."""
        num_steps = 10
        num_inputs = 12
        
        spikes = torch.zeros(1, num_steps, num_inputs)
        
        # 1. Эмбодзимент
        if hasattr(self.state, 'body_temperature'):
            temp_norm = max(0.0, min(1.0, (self.state.body_temperature - 40) / 50))
            spikes[0, :, 0] = self._rate_to_spikes(temp_norm, num_steps)
        
        if hasattr(self.state, 'physical_load'):
            spikes[0, :, 1] = self._rate_to_spikes(self.state.physical_load, num_steps)
        
        if hasattr(self.state, 'cognitive_load'):
            spikes[0, :, 2] = self._rate_to_spikes(self.state.cognitive_load, num_steps)
        
        # 2. Анализ сообщения
        if event_type == "user_command" and content:
            content_lower = content.lower()
            
            # Позитивные слова (награда)
            positive_words = ["рад", "счаст", "отличн", "круто", "супер", "люблю", "класс"]
            pos_score = min(1.0, sum(1 for w in positive_words if w in content_lower) / 3)
            spikes[0, :, 3] = self._rate_to_spikes(pos_score, num_steps)
            
            # Негативные слова (угроза)
            negative_words = ["груст", "плох", "ошибк", "проблем", "устал", "больно"]
            neg_score = min(1.0, sum(1 for w in negative_words if w in content_lower) / 3)
            spikes[0, :, 9] = self._rate_to_spikes(neg_score, num_steps)
            
            # Вопросы (новизна)
            if "?" in content:
                spikes[0, :, 7] = self._rate_to_spikes(0.7, num_steps)
        
        # 3. Временное давление (угроза)
        if hasattr(self.state, 'cortisol') and self.state.cortisol > 0.6:
            spikes[0, :, 6] = self._rate_to_spikes(0.8, num_steps)
        
        # 4. Новизна
        if context_history and len(context_history) > 0:
            last_event = context_history[-1]
            if last_event.get("type") != event_type:
                spikes[0, :, 7] = self._rate_to_spikes(0.6, num_steps)
        
        # 5. Социальное присутствие
        if event_type == "user_command":
            spikes[0, :, 8] = self._rate_to_spikes(0.8, num_steps)
        
        # 6. Обнаруженная ошибка (угроза)
        if hasattr(self.state, 'error_streak') and self.state.error_streak > 0:
            spikes[0, :, 9] = self._rate_to_spikes(0.7, num_steps)
        
        # 7. Успех (награда)
        if hasattr(self.state, 'error_streak') and self.state.error_streak == 0:
            spikes[0, :, 10] = self._rate_to_spikes(0.5, num_steps)
        
        # 8. Усталость (угроза)
        if self.state.energy_level < 0.4:
            spikes[0, :, 11] = self._rate_to_spikes(1.0 - self.state.energy_level, num_steps)
        
        return spikes
    
    def _rate_to_spikes(self, rate: float, num_steps: int) -> torch.Tensor:
        """Преобразует частоту в паттерн спайков."""
        spikes = torch.zeros(num_steps)
        spike_prob = rate * 0.8
        
        for t in range(num_steps):
            if torch.rand(1).item() < spike_prob:
                spikes[t] = 1.0
        
        return spikes
    
    def _apply_stdp(self):
        """Упрощённый STDP."""
        if len(self.network.spike_history) < 2:
            return
        
        try:
            prev = self.network.spike_history[-2]
            curr = self.network.spike_history[-1]
            
            with torch.no_grad():
                correlation = torch.mean(prev["output"] * curr["output"])
                delta = self.stdp_learning_rate * correlation.item()
                noise = torch.randn_like(self.network.fc_output.weight) * 0.005
                self.network.fc_output.weight += delta * noise
            
        except Exception as e:
            log.debug("STDP update failed", error=str(e))
    
    def get_stats(self) -> Dict:
        """Возвращает статистику работы сети."""
        return {
            "total_evaluations": self.total_evaluations,
            "total_spikes": int(self.network.total_spikes),
            "total_forward_passes": self.network.total_forward_passes,
            "avg_spikes_per_pass": (
                self.network.total_spikes / max(1, self.network.total_forward_passes)
            ),
            "history_size": len(self.network.spike_history),
            "enabled": self.enabled,
            "stdp_enabled": self.stdp_enabled,
            "architecture": "specialized"
        }
    
    def save_weights(self, filepath: str = "./leya_snn_weights.pt"):
        """Сохраняет веса сети."""
        try:
            torch.save(self.network.state_dict(), filepath)
            log.info("🧠 SNN weights saved", path=filepath)
        except Exception as e:
            log.error("Failed to save SNN weights", error=str(e))
    
    def load_weights(self, filepath: str = "./leya_snn_weights.pt"):
        """Загружает веса сети."""
        import os
        if not os.path.exists(filepath):
            log.info("No SNN weights found, using biological initialization")
            return
        
        try:
            self.network.load_state_dict(torch.load(filepath))
            log.info("🧠 SNN weights loaded", path=filepath)
        except Exception as e:
            log.error("Failed to load SNN weights", error=str(e))