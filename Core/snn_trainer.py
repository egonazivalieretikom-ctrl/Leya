import torch
import torch.nn as nn
from typing import List, Dict, Tuple
from Core.logger import log
from Cognition.llm_client import LLMClient


class SNNTrainer:
    """
    Тренер для SNN.
    
    Использует LLM как учителя для генерации размеченных данных,
    затем обучает SNN через backpropagation.
    """
    
    def __init__(self, snn_network):
        self.snn = snn_network
        self.llm = LLMClient(model="ollama/qwen2.5:14b")
        
        # Датасет: (входные спайки, ожидаемые гормоны)
        self.dataset: List[Tuple[torch.Tensor, Dict[str, float]]] = []
        
        # Функция потерь
        self.criterion = nn.MSELoss()
        
        # Оптимизатор
        self.optimizer = torch.optim.Adam(self.snn.parameters(), lr=0.001)
        
        log.info("🎓 SNN Trainer initialized")
    
    # ========================================================================
    # ГЕНЕРАЦИЯ ДАННЫХ С ПОМОЩЬЮ LLM
    # ========================================================================
    
    async def generate_training_data(self, num_samples: int = 50):
        """
        Генерирует размеченные данные с помощью LLM.
        
        LLM выступает как "учитель", генерируя правильные гормональные
        стимулы для разных ситуаций.
        """
        log.info(f"🎓 Generating {num_samples} training samples with LLM...")
        
        scenarios = [
            "Радостное сообщение от собеседника",
            "Грустное сообщение от собеседника",
            "Угроза или опасность",
            "Социальное взаимодействие (приветствие)",
            "Новая, неожиданная ситуация",
            "Успех в задаче",
            "Ошибка или неудача",
            "Одиночество",
            "Любопытство и интерес",
            "Усталость",
        ]
        
        for i, scenario in enumerate(scenarios * (num_samples // len(scenarios) + 1)):
            if i >= num_samples:
                break
            
            # Просим LLM сгенерировать правильные гормоны
            hormones = await self._llm_generate_hormones(scenario)
            
            if hormones:
                # Кодируем сценарий в входные спайки
                input_spikes = self._encode_scenario(scenario)
                
                # Добавляем в датасет
                self.dataset.append((input_spikes, hormones))
                
                log.debug(f"🎓 Sample {i+1}: {scenario} → {hormones}")
        
        log.info(f"✅ Generated {len(self.dataset)} training samples")
    
    async def _llm_generate_hormones(self, scenario: str) -> Dict[str, float]:
        """
        LLM генерирует правильные гормональные стимулы для сценария.
        """
        prompt = (
            f"Сценарий: {scenario}\n\n"
            "Ты — эксперт по нейробиологии. Определи, какие гормоны должны "
            "активироваться в этой ситуации и с какой интенсивностью.\n\n"
            "Гормоны:\n"
            "- dopamine (дофамин): награда, удовольствие, мотивация\n"
            "- serotonin (серотонин): настроение, благополучие\n"
            "- cortisol (кортизол): стресс, угроза\n"
            "- oxytocin (окситоцин): социальная связь, доверие\n"
            "- acetylcholine (ацетилхолин): внимание, обучение\n"
            "- norepinephrine (норадреналин): возбуждение, бдительность\n"
            "- endorphins (эндорфины): удовольствие, обезболивание\n"
            "- gaba (ГАМК): торможение, спокойствие\n\n"
            "Ответь JSON (без markdown):\n"
            '{"dopamine": <число от -0.2 до 0.2>, "serotonin": ..., ...}\n\n'
            "Положительные значения = активация, отрицательные = подавление."
        )
        
        try:
            response = await self.llm.chat(
                [
                    {"role": "system", "content": "Ты — эксперт по нейробиологии. Только русский, только JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=300
            )
            
            if not response:
                return None
            
            # Извлекаем JSON
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if not json_match:
                return None
            
            import json
            hormones = json.loads(json_match.group())
            
            # Валидация
            valid_hormones = ["dopamine", "serotonin", "cortisol", "oxytocin", 
                             "acetylcholine", "norepinephrine", "endorphins", "gaba"]
            
            for h in valid_hormones:
                if h not in hormones:
                    hormones[h] = 0.0
                else:
                    hormones[h] = max(-0.2, min(0.2, float(hormones[h])))
            
            return hormones
            
        except Exception as e:
            log.error("LLM hormone generation failed", error=str(e))
            return None
    
    def _encode_scenario(self, scenario: str) -> torch.Tensor:
        """
        Кодирует сценарий в входные спайки.
        
        Это упрощённое кодирование — в реальности нужно использовать
        более сложные методы (например, word embeddings).
        """
        num_steps = 10
        num_inputs = 12
        
        spikes = torch.zeros(1, num_steps, num_inputs)
        
        # Простое кодирование на основе ключевых слов
        scenario_lower = scenario.lower()
        
        # Эмбодзимент (базовые значения)
        spikes[0, :, 0] = 0.3  # Температура
        spikes[0, :, 1] = 0.3  # Физическая нагрузка
        spikes[0, :, 2] = 0.3  # Когнитивная нагрузка
        
        # Ключевые слова → входные нейроны
        if "радост" in scenario_lower or "успех" in scenario_lower:
            spikes[0, :, 3] = 0.8  # Позитивные слова
        elif "груст" in scenario_lower or "ошибк" in scenario_lower:
            spikes[0, :, 9] = 0.8  # Негативные слова
        
        if "угроз" in scenario_lower or "опасн" in scenario_lower:
            spikes[0, :, 6] = 0.8  # Временное давление
        
        if "социаль" in scenario_lower or "привет" in scenario_lower:
            spikes[0, :, 8] = 0.8  # Социальное присутствие
        
        if "нов" in scenario_lower or "неожид" in scenario_lower:
            spikes[0, :, 7] = 0.8  # Новизна
        
        if "любопыт" in scenario_lower or "интерес" in scenario_lower:
            spikes[0, :, 7] = 0.7  # Новизна + внимание
        
        if "устал" in scenario_lower:
            spikes[0, :, 11] = 0.8  # Усталость
        
        return spikes
    
    # ========================================================================
    # ОБУЧЕНИЕ SNN
    # ========================================================================
    
    def train(self, epochs: int = 100, batch_size: int = 10):
        """
        Обучает SNN на сгенерированных данных.
        
        Использует простую backpropagation (не BPTT),
        потому что snntorch не поддерживает BPTT из коробки.
        """
        if not self.dataset:
            log.error("❌ No training data available")
            return
        
        log.info(f"🎓 Training SNN for {epochs} epochs...")
        
        for epoch in range(epochs):
            total_loss = 0.0
            
            # Перемешиваем данные
            import random
            random.shuffle(self.dataset)
            
            # Обучаем батчами
            for i in range(0, len(self.dataset), batch_size):
                batch = self.dataset[i:i+batch_size]
                
                # Обнуляем градиенты
                self.optimizer.zero_grad()
                
                batch_loss = 0.0
                
                for input_spikes, target_hormones in batch:
                    # Прямой проход
                    output_hormones = self.snn(input_spikes)
                    
                    # Преобразуем target в тензор
                    target_tensor = torch.tensor([
                        target_hormones.get("dopamine", 0.0),
                        target_hormones.get("serotonin", 0.0),
                        target_hormones.get("cortisol", 0.0),
                        target_hormones.get("oxytocin", 0.0),
                        target_hormones.get("acetylcholine", 0.0),
                        target_hormones.get("norepinephrine", 0.0),
                        target_hormones.get("endorphins", 0.0),
                        target_hormones.get("gaba", 0.0),
                    ], dtype=torch.float32)
                    
                    # Преобразуем output в тензор
                    output_tensor = torch.tensor([
                        output_hormones.get("dopamine", 0.0),
                        output_hormones.get("serotonin", 0.0),
                        output_hormones.get("cortisol", 0.0),
                        output_hormones.get("oxytocin", 0.0),
                        output_hormones.get("acetylcholine", 0.0),
                        output_hormones.get("norepinephrine", 0.0),
                        output_hormones.get("endorphins", 0.0),
                        output_hormones.get("gaba", 0.0),
                    ], dtype=torch.float32)
                    
                    # Вычисляем loss
                    loss = self.criterion(output_tensor, target_tensor)
                    batch_loss += loss.item()
                    
                    # Backward pass
                    loss.backward()
                
                # Обновляем веса
                self.optimizer.step()
                
                total_loss += batch_loss / len(batch)
            
            avg_loss = total_loss / (len(self.dataset) // batch_size + 1)
            
            if (epoch + 1) % 10 == 0:
                log.info(f"🎓 Epoch {epoch+1}/{epochs}, Loss: {avg_loss:.4f}")
        
        log.info("✅ SNN training complete")
    
    def save_dataset(self, filepath: str = "./snn_training_data.json"):
        """Сохраняет датасет в файл."""
        import json
        
        data = []
        for input_spikes, hormones in self.dataset:
            data.append({
                "input_spikes": input_spikes.tolist(),
                "hormones": hormones
            })
        
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        
        log.info(f"📚 Dataset saved to {filepath}")
    
    def load_dataset(self, filepath: str = "./snn_training_data.json"):
        """Загружает датасет из файла."""
        import json
        
        if not os.path.exists(filepath):
            log.warning(f"Dataset file not found: {filepath}")
            return
        
        with open(filepath, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        self.dataset = []
        for item in data:
            input_spikes = torch.tensor(item["input_spikes"])
            hormones = item["hormones"]
            self.dataset.append((input_spikes, hormones))
        
        log.info(f"📚 Loaded {len(self.dataset)} samples from {filepath}")

    async def _llm_generate_hormones(self, scenario: str) -> Dict[str, float]:
        """LLM генерирует правильные гормональные стимулы для сценария."""
        log.info(f"🎓 Requesting LLM for scenario: {scenario[:50]}...")
    
        prompt = (
            f"Сценарий: {scenario}\n\n"
            "Ты — эксперт по нейробиологии. Определи, какие гормоны должны "
            "активироваться в этой ситуации и с какой интенсивностью.\n\n"
            "Гормоны:\n"
            "- dopamine (дофамин): награда, удовольствие, мотивация\n"
            "- serotonin (серотонин): настроение, благополучие\n"
            "- cortisol (кортизол): стресс, угроза\n"
            "- oxytocin (окситоцин): социальная связь, доверие\n"
            "- acetylcholine (ацетилхолин): внимание, обучение\n"
            "- norepinephrine (норадреналин): возбуждение, бдительность\n"
            "- endorphins (эндорфины): удовольствие, обезболивание\n"
            "- gaba (ГАМК): торможение, спокойствие\n\n"
            "Ответь JSON (без markdown):\n"
            '{"dopamine": <число от -0.2 до 0.2>, "serotonin": ..., ...}\n\n'
            "Положительные значения = активация, отрицательные = подавление."
        )
    
        try:
            log.debug(f"🎓 Sending prompt to LLM (length={len(prompt)})")
        
            response = await self.llm.chat(
                [
                    {"role": "system", "content": "Ты — эксперт по нейробиологии. Только русский, только JSON."},
                    {"role": "user", "content": prompt}
                ],
                temperature=0.3,
                max_tokens=300
            )
        
            if not response:
                log.warning(f"🎓 LLM returned empty response for scenario: {scenario[:50]}")
                return None
        
            log.debug(f"🎓 LLM response received (length={len(response)})")
        
            # Извлекаем JSON
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if not json_match:
                log.warning(f"🎓 No JSON found in LLM response: {response[:100]}")
                return None
        
            import json
            hormones = json.loads(json_match.group())
        
            log.info(f"🎓 Generated hormones for '{scenario[:30]}...': {hormones}")
        
            # Валидация
            valid_hormones = ["dopamine", "serotonin", "cortisol", "oxytocin", 
                             "acetylcholine", "norepinephrine", "endorphins", "gaba"]
        
            for h in valid_hormones:
                if h not in hormones:
                    hormones[h] = 0.0
                else:
                    hormones[h] = max(-0.2, min(0.2, float(hormones[h])))
        
            return hormones
        
        except Exception as e:
            log.error(f"🎓 LLM hormone generation failed for scenario: {scenario[:50]}", 
                      error=str(e), exc_info=True)
            return None