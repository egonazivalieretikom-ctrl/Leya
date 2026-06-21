import torch
import torch.nn as nn
import snntorch as snn
from typing import Dict, List, Optional
from Core.logger import log
from Core.state import LeyaState


class AmygdalaSNN(nn.Module):
    """
    Спайковая нейронная сеть "Амигдала" — быстрая эмоциональная оценка.
    
    Биология: Амигдала оценивает стимулы за миллисекунды, до того как
    кора успела их осознать. Она работает на спайках, а не на символах.
    
    Архитектура:
    - Вход: 12 нейронов (сенсоры + контекст)
    - Скрытый слой: 32 LIF-нейрона (амигдала)
    - Выход: 8 нейронов (гормональные стимулы)
    """
    
    # Маппинг выходных нейронов на гормоны
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
        beta = 0.85  # Скорость затухания мембранного потенциала
        threshold = 0.5  # Порог срабатывания
        
        # Слой 1: Входы → Скрытый слой
        self.fc1 = nn.Linear(12, 32)
        self.lif1 = snn.Leaky(beta=beta, threshold=threshold, reset_mechanism='subtract')
        
        # Слой 2: Скрытый слой → Выходы
        self.fc2 = nn.Linear(32, 8)
        self.lif2 = snn.Leaky(beta=beta, threshold=threshold, reset_mechanism='subtract')
        
        # Инициализация весов
        self._init_weights()
        
        # История спайков (для STDP)
        self.spike_history: List[Dict] = []
        self.max_history = 100
        
        # Статистика
        self.total_spikes = 0
        self.total_forward_passes = 0
        
        log.info("🧠 Amygdala SNN initialized (12→32→8 neurons)")
    
    def _init_weights(self):
        """Инициализирует веса сети."""
        nn.init.xavier_uniform_(self.fc1.weight, gain=0.5)
        nn.init.xavier_uniform_(self.fc2.weight, gain=0.5)
        nn.init.zeros_(self.fc1.bias)
        nn.init.zeros_(self.fc2.bias)
    
    def forward(self, input_spikes: torch.Tensor, num_steps: int = 10) -> Dict[str, float]:
        """
        Прямой проход через сеть с временной симуляцией.
        
        Args:
            input_spikes: Тензор входных спайков [batch=1, num_steps, 12]
            num_steps: Количество временных шагов
        
        Returns:
            Словарь {гормон: стимул}
        """
        self.total_forward_passes += 1
        
        # Инициализируем мембранные потенциалы
        mem1 = self.lif1.init_leaky()
        mem2 = self.lif2.init_leaky()
        
        # Для накопления выходных спайков
        output_spike_counts = torch.zeros(8)
        hidden_spike_record = []
        
        # Временная симуляция
        for t in range(num_steps):
            # Извлекаем входные спайки для текущего шага
            spk_in = input_spikes[0, t, :].unsqueeze(0)  # [1, 12]
            
            # Слой 1: линейное преобразование + LIF
            cur1 = self.fc1(spk_in)
            spk1, mem1 = self.lif1(cur1, mem1)  # 🆕 Распаковка кортежа!
            hidden_spike_record.append(spk1.detach())
            
            # Слой 2: линейное преобразование + LIF
            cur2 = self.fc2(spk1)
            spk2, mem2 = self.lif2(cur2, mem2)  # 🆕 Распаковка кортежа!
            
            # Накапливаем выходные спайки
            output_spike_counts += spk2.squeeze(0).detach()
        
        # Преобразуем спайки в гормональные стимулы
        hormonal_impact = self._spikes_to_hormones(output_spike_counts)
        
        # Сохраняем историю (для STDP)
        if hidden_spike_record:
            self._save_spike_history(input_spikes, hidden_spike_record, output_spike_counts)
        
        return hormonal_impact
    
    def _spikes_to_hormones(self, output_spikes: torch.Tensor) -> Dict[str, float]:
        """Преобразует выходные спайки в гормональные стимулы."""
        impact = {}
        
        # Нормализуем: делим на количество шагов
        max_possible = 10.0
        normalized = output_spikes / max_possible
        
        for idx, hormone in self.OUTPUT_MAPPING.items():
            spike_rate = normalized[idx].item()
            
            # Преобразуем частоту спайков в стимул
            # Базовая активность (0.5) = нулевой стимул
            stimulus = (spike_rate - 0.3) * 0.15
            
            # Ограничиваем диапазон
            stimulus = max(-0.15, min(0.15, stimulus))
            
            impact[hormone] = stimulus
        
        return impact
    
    def _save_spike_history(self, input_spikes, hidden_spikes, output_spikes):
        """Сохраняет историю спайков для STDP."""
        self.spike_history.append({
            "input": input_spikes.detach(),
            "hidden": torch.stack(hidden_spikes[-3:]).mean(dim=0),  # Усредняем последние 3
            "output": output_spikes.detach()
        })
        
        if len(self.spike_history) > self.max_history:
            self.spike_history.pop(0)
        
        self.total_spikes += output_spikes.sum().item()


class EmotionalSNNSystem:
    """
    Система эмоциональной оценки на основе SNN.
    
    Заменяет паттерн-матчинг на реальную нейронную сеть.
    """
    
    def __init__(self, state: LeyaState):
        self.state = state
        self.network = AmygdalaSNN()
        
        self.enabled = True
        self.stdp_learning_rate = 0.001
        self.stdp_enabled = True
        
        self.total_evaluations = 0
        
        log.info("🧠 Emotional SNN System initialized")
    
    # ========================================================================
    # ГЛАВНЫЙ МЕТОД: Оценка стимула
    # ========================================================================
    
    def evaluate(self, event_type: str, content: str, 
                 context_history: List[Dict] = None) -> Dict[str, float]:
        """Оценивает стимул через спайковую сеть."""
        if not self.enabled:
            return {}
        
        self.total_evaluations += 1
        
        try:
            # 1. Кодируем стимул в спайки
            input_spikes = self._encode_stimulus(event_type, content, context_history)
            
            # 2. Пропускаем через сеть
            hormonal_impact = self.network(input_spikes)
            
            # 3. Применяем STDP
            if self.stdp_enabled and self.total_evaluations % 5 == 0:
                self._apply_stdp()
            
            # 4. Логируем (раз в 10 оценок)
            if self.total_evaluations % 10 == 0:
                active_hormones = {k: round(v, 3) for k, v in hormonal_impact.items() if abs(v) > 0.01}
                if active_hormones:
                    log.info(
                        "🧠 SNN evaluation",
                        event=event_type,
                        hormones=active_hormones,
                        total_spikes=int(self.network.total_spikes)
                    )
            
            # 5. Сохраняем веса периодически
            if self.total_evaluations % 100 == 0:
                self.save_weights()
            
            return hormonal_impact
            
        except Exception as e:
            log.error("SNN evaluation failed", error=str(e), exc_info=False)
            return {}
    
    # ========================================================================
    # КОДИРОВАНИЕ СТИМУЛА В СПАЙКИ
    # ========================================================================
    
    def _encode_stimulus(self, event_type: str, content: str, 
                         context_history: List[Dict] = None) -> torch.Tensor:
        """Преобразует стимул в паттерн входных спайков."""
        num_steps = 10
        num_inputs = 12
        
        # Инициализируем тензор спайков [batch=1, num_steps, num_inputs]
        spikes = torch.zeros(1, num_steps, num_inputs)
        
        # 1. Эмбодзимент (сенсоры тела)
        if hasattr(self.state, 'body_temperature'):
            temp_norm = max(0.0, min(1.0, (self.state.body_temperature - 40) / 50))
            spikes[0, :, 0] = self._rate_to_spikes(temp_norm, num_steps)
        
        if hasattr(self.state, 'physical_load'):
            spikes[0, :, 1] = self._rate_to_spikes(self.state.physical_load, num_steps)
        
        if hasattr(self.state, 'cognitive_load'):
            spikes[0, :, 2] = self._rate_to_spikes(self.state.cognitive_load, num_steps)
        
        # 2. Анализ сообщения пользователя
        if event_type == "user_command" and content:
            content_lower = content.lower()
            
            # Позитивные слова
            positive_words = ["рад", "счаст", "отличн", "круто", "супер", "люблю", "класс"]
            pos_score = min(1.0, sum(1 for w in positive_words if w in content_lower) / 3)
            spikes[0, :, 3] = self._rate_to_spikes(pos_score, num_steps)
            
            # Негативные слова
            negative_words = ["груст", "плох", "ошибк", "проблем", "устал", "больно"]
            neg_score = min(1.0, sum(1 for w in negative_words if w in content_lower) / 3)
            spikes[0, :, 4] = self._rate_to_spikes(neg_score, num_steps)
            
            # Вопросы
            if "?" in content:
                spikes[0, :, 5] = self._rate_to_spikes(0.7, num_steps)
        
        # 3. Временное давление
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
        
        # 6. Обнаруженная ошибка
        if hasattr(self.state, 'error_streak') and self.state.error_streak > 0:
            spikes[0, :, 9] = self._rate_to_spikes(0.7, num_steps)
        
        # 7. Успех
        if hasattr(self.state, 'error_streak') and self.state.error_streak == 0:
            spikes[0, :, 10] = self._rate_to_spikes(0.5, num_steps)
        
        # 8. Усталость
        if self.state.energy_level < 0.4:
            spikes[0, :, 11] = self._rate_to_spikes(1.0 - self.state.energy_level, num_steps)
        
        return spikes
    
    def _rate_to_spikes(self, rate: float, num_steps: int) -> torch.Tensor:
        """Преобразует частоту (0.0-1.0) в паттерн спайков."""
        spikes = torch.zeros(num_steps)
        spike_prob = rate * 0.8
        
        for t in range(num_steps):
            if torch.rand(1).item() < spike_prob:
                spikes[t] = 1.0
        
        return spikes
    
    # ========================================================================
    # STDP (СПАЙКОВО-ЗАВИСИМАЯ ПЛАСТИЧНОСТЬ)
    # ========================================================================
    
    def _apply_stdp(self):
        """Применяет упрощённую STDP."""
        if len(self.network.spike_history) < 2:
            return
        
        try:
            prev = self.network.spike_history[-2]
            curr = self.network.spike_history[-1]
            
            # Корреляция между скрытым слоем и выходом
            pre_spikes = prev["hidden"]
            post_spikes = curr["output"]
            
            # Упрощённая STDP
            correlation = torch.mean(pre_spikes.sum() * post_spikes.sum()) / 100.0
            
            # Мягкое обновление весов
            with torch.no_grad():
                delta = self.stdp_learning_rate * correlation.item()
                noise = torch.randn_like(self.network.fc2.weight) * 0.005
                self.network.fc2.weight += delta * noise
            
        except Exception as e:
            log.debug("STDP update failed", error=str(e))
    
    # ========================================================================
    # СТАТИСТИКА И СОХРАНЕНИЕ
    # ========================================================================
    
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
            "stdp_enabled": self.stdp_enabled
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
            log.info("No SNN weights found, using random initialization")
            return
        
        try:
            self.network.load_state_dict(torch.load(filepath))
            log.info("🧠 SNN weights loaded", path=filepath)
        except Exception as e:
            log.error("Failed to load SNN weights", error=str(e))