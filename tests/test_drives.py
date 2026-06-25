"""
tests/test_drives.py — Тесты для системы драйвов Леи.
Проверяет: метаболизм, RPE, оценку стимулов, предсказание дисбаланса.
"""
import asyncio
import time
from unittest.mock import MagicMock

import pytest

from leya_core.drives import DriveSystem, DriveType, Drive


class TestDrive:
    """Тесты для модели Drive."""
    
    def test_drive_initialization(self):
        """Проверка инициализации драйва."""
        drive = Drive(type=DriveType.CURIOSITY, current=0.5, target=0.6)
        
        assert drive.type == DriveType.CURIOSITY
        assert drive.current == 0.5
        assert drive.target == 0.6
        assert drive.tension == 0.0
        assert drive.retention_strength == 1.0  # По умолчанию
    
    def test_drive_validation(self):
        """Проверка валидации значений драйва."""
        # Значения должны быть ограничены диапазоном [0.0, 1.0]
        drive = Drive(type=DriveType.CURIOSITY, current=1.5, tension=-0.5)
        
        assert drive.current == 1.0  # Ограничено максимумом
        assert drive.tension == 0.0  # Ограничено минимумом
    
    def test_drive_apply_delta(self):
        """Проверка применения дельты к драйву."""
        drive = Drive(type=DriveType.CURIOSITY, current=0.5, target=0.6)
        
        # Положительная дельта
        drive.apply_delta(0.1)
        assert drive.current == 0.6
        
        # Отрицательная дельта
        drive.apply_delta(-0.2)
        assert drive.current == 0.4
        
        # Ограничение диапазона
        drive.apply_delta(10.0)
        assert drive.current == 1.0
        
        drive.apply_delta(-10.0)
        assert drive.current == 0.0
    
    def test_drive_tension_update(self):
        """Проверка обновления tension на основе метаболизма."""
        drive = Drive(
            type=DriveType.CURIOSITY,
            current=0.3,  # Ниже target
            target=0.6,
            metabolism_rate=0.01
        )
        
        initial_tension = drive.tension
        current_time = time.time() + 3600  # Через 1 час
        
        drive.update_tension(current_time)
        
        # Tension должно увеличиться (дефицит + метаболизм)
        assert drive.tension > initial_tension


class TestDriveSystem:
    """Тесты для DriveSystem."""
    
    def test_drivesystem_initialization(self):
        """Проверка инициализации DriveSystem."""
        system = DriveSystem()
        
        assert len(system.drives) == 6  # Все типы драйвов
        assert DriveType.CURIOSITY in system.drives
        assert DriveType.CONNECTION in system.drives
        assert DriveType.REST in system.drives
        assert DriveType.CREATIVITY in system.drives
        assert DriveType.UNDERSTANDING in system.drives
        assert DriveType.AUTONOMY in system.drives
    
    def test_evaluate_stimulus_greeting(self):
        """Проверка оценки стимула-приветствия."""
        system = DriveSystem()
        
        deltas = asyncio.get_event_loop().run_until_complete(
            system.evaluate_stimulus("Привет, как дела?")
        )
        
        # Приветствие должно удовлетворять CONNECTION
        assert DriveType.CONNECTION in deltas
        assert deltas[DriveType.CONNECTION] > 0
    
    def test_evaluate_stimulus_question(self):
        """Проверка оценки стимула-вопроса."""
        system = DriveSystem()
        
        deltas = asyncio.get_event_loop().run_until_complete(
            system.evaluate_stimulus("Что такое квантовая физика?")
        )
        
        # Вопрос должен удовлетворять CURIOSITY
        assert DriveType.CURIOSITY in deltas
        assert deltas[DriveType.CURIOSITY] > 0
    
    def test_apply_deltas(self):
        """Проверка применения дельт к драйвам."""
        system = DriveSystem()
        
        initial_curiosity = system.drives[DriveType.CURIOSITY].current
        
        system.apply_deltas({DriveType.CURIOSITY: 0.1})
        
        assert system.drives[DriveType.CURIOSITY].current > initial_curiosity
    
    def test_calculate_rpe(self):
        """Проверка расчета RPE (Reward Prediction Error)."""
        system = DriveSystem()
        
        # Первое действие — ожидаемая награда из action_values
        rpe1 = system.calculate_rpe("research:wikipedia_search", 0.8)
        
        # Ожидаемое значение должно быть из action_values (0.7)
        # RPE = actual - expected = 0.8 - 0.7 = 0.1
        assert rpe1 == pytest.approx(0.1, abs=0.01)
        
        # Второе действие с тем же ключом — среднее из истории
        rpe2 = system.calculate_rpe("research:wikipedia_search", 0.6)
        
        # Теперь ожидаемое = среднее из истории = (0.8 + 0.6) / 2 = 0.7
        # RPE = 0.6 - 0.7 = -0.1
        assert rpe2 == pytest.approx(-0.1, abs=0.01)
    
    def test_apply_satisfaction_with_rpe(self):
        """Проверка применения удовлетворения с учетом RPE."""
        system = DriveSystem()
        
        initial_curiosity = system.drives[DriveType.CURIOSITY].current
        
        # Положительный RPE → больше удовлетворения
        system.apply_satisfaction(DriveType.CURIOSITY, 0.1, rpe=0.2)
        
        assert system.drives[DriveType.CURIOSITY].current > initial_curiosity
    
    def test_get_predicted_disbalance(self):
        """Проверка предсказания дисбаланса."""
        system = DriveSystem()
        
        # Устанавливаем высокое tension
        system.drives[DriveType.CURIOSITY].tension = 0.8
        
        predicted = system.get_predicted_disbalance()
        
        # Предсказанное значение должно быть выше текущего (из-за tension)
        assert predicted["CURIOSITY"] > system.drives[DriveType.CURIOSITY].current
    
    def test_get_internal_state_prompt(self):
        """Проверка генерации текстового описания состояния."""
        system = DriveSystem()
        
        prompt = system.get_internal_state_prompt()
        
        assert "CURIOSITY" in prompt
        assert "CONNECTION" in prompt
        assert isinstance(prompt, str)
        assert len(prompt) > 0
    
    def test_save_and_load_state(self):
        """Проверка сохранения и загрузки состояния."""
        system1 = DriveSystem()
        system1.apply_deltas({DriveType.CURIOSITY: 0.2})
        
        state = system1.save_state()
        
        system2 = DriveSystem()
        system2.load_state(state)
        
        assert system2.drives[DriveType.CURIOSITY].current == system1.drives[DriveType.CURIOSITY].current
    
    def test_action_history_limit(self):
        """Проверка ограничения размера истории действий."""
        system = DriveSystem(max_action_history=10)
        
        # Добавляем больше записей, чем лимит
        for i in range(20):
            system.calculate_rpe(f"action_{i}", 0.5)
        
        # История должна быть ограничена
        assert len(system.action_history) == 10