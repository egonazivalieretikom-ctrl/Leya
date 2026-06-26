"""
Тесты для DriveSystem.

Проверяет:
- Инициализацию драйвов с конфигурацией
- Метаболизм (фоновое нарастание tension)
- RPE (Reward Prediction Error)
- apply_satisfaction с RPE-модификатором
- Перекрёстное влияние драйвов
- evaluate_stimulus
- save_state / load_state
"""

from __future__ import annotations

import asyncio

import pytest

from leya_core.drives import DriveSystem, DriveType
from leya_core.exceptions import LeyaDriveNotFoundError


class TestDriveSystemInit:
    """Тесты инициализации DriveSystem."""

    def test_init_with_config(self, test_drives_config):
        """DriveSystem корректно инициализируется с конфигом."""
        ds = DriveSystem(config=test_drives_config)

        assert DriveType.CURIOSITY in ds.drives
        assert DriveType.CONNECTION in ds.drives
        assert DriveType.AUTONOMY in ds.drives
        assert DriveType.REST in ds.drives
        assert DriveType.CREATIVITY in ds.drives
        assert DriveType.UNDERSTANDING in ds.drives
        assert DriveType.INTEGRITY in ds.drives

    def test_init_default_config(self):
        """DriveSystem инициализируется с конфигом по умолчанию."""
        ds = DriveSystem()
        assert len(ds.drives) == 7

    def test_initial_values(self, test_drives_config):
        """Начальные значения драйвов в разумных пределах."""
        ds = DriveSystem(config=test_drives_config)

        for drive in ds.drives.values():
            assert 0.0 <= drive.current <= 1.0
            assert drive.base_growth_rate > 0


class TestDriveSystemMetabolism:
    """Тесты фонового метаболизма."""

    @pytest.mark.asyncio
    async def test_metabolism_increases_tension(self, test_drives_config):
        """Метаболизм увеличивает tension со временем (с учётом cross_influence)."""
        test_drives_config.metabolism_interval = 1
        ds = DriveSystem(config=test_drives_config)

        # Устанавливаем все драйвы в низкое значение, чтобы cross_influence не снижал
        for drive in ds.drives.values():
            drive.current = 0.2  # Низкое значение, чтобы cross_influence был минимальным

        # Запоминаем начальные значения
        initial_values = {dt: d.current for dt, d in ds.drives.items()}

        # Запускаем метаболизм на короткое время
        task = asyncio.create_task(ds.background_metabolism())
        await asyncio.sleep(2.5)
        ds.stop()
        await task

        # Проверяем, что хотя бы некоторые драйвы выросли
        # (cross_influence может снижать некоторые, но base_growth_rate должен увеличивать)
        increased_count = 0
        for dt, drive in ds.drives.items():
            if drive.current > initial_values[dt]:
                increased_count += 1

        # Хотя бы половина драйвов должна вырасти (base_growth_rate > 0)
        assert (
            increased_count >= len(ds.drives) // 2
        ), f"Слишком мало драйвов выросло: {increased_count}/{len(ds.drives)}"

    @pytest.mark.asyncio
    async def test_metabolism_respects_bounds(self, test_drives_config):
        """Метаболизм не выводит tension за пределы [0, 1]."""
        test_drives_config.metabolism_interval = 1
        ds = DriveSystem(config=test_drives_config)

        # Устанавливаем драйвы близко к максимуму
        for drive in ds.drives.values():
            drive.current = 0.99

        task = asyncio.create_task(ds.background_metabolism())
        await asyncio.sleep(2)
        ds.stop()
        await task

        for drive in ds.drives.values():
            assert drive.current <= 1.0
            assert drive.current >= 0.0


class TestDriveSystemRPE:
    """Тесты Reward Prediction Error."""

    def test_rpe_positive(self, test_drives_config):
        """Положительный RPE: награда лучше ожидаемой."""
        ds = DriveSystem(config=test_drives_config)

        # Устанавливаем ожидаемую награду
        ds.action_values["wikipedia_search"] = 0.5

        # Фактическая награда выше ожидаемой
        rpe = ds.calculate_rpe("wikipedia_search", actual_outcome=0.8)

        assert rpe > 0, f"RPE должен быть положительным, получен {rpe}"
        # Ожидаемое значение должно обновиться в сторону фактического
        assert ds.action_values["wikipedia_search"] > 0.5

    def test_rpe_negative(self, test_drives_config):
        """Отрицательный RPE: награда хуже ожидаемой."""
        ds = DriveSystem(config=test_drives_config)
        ds.action_values["wikipedia_search"] = 0.5

        rpe = ds.calculate_rpe("wikipedia_search", actual_outcome=0.2)

        assert rpe < 0, f"RPE должен быть отрицательным, получен {rpe}"
        assert ds.action_values["wikipedia_search"] < 0.5

    def test_rpe_zero(self, test_drives_config):
        """Нулевой RPE: награда как ожидалась."""
        ds = DriveSystem(config=test_drives_config)
        ds.action_values["wikipedia_search"] = 0.5

        rpe = ds.calculate_rpe("wikipedia_search", actual_outcome=0.5)

        assert rpe == 0.0

    def test_rpe_new_action(self, test_drives_config):
        """RPE для нового действия (нет ожидаемого значения)."""
        ds = DriveSystem(config=test_drives_config)

        # По умолчанию ожидаемое значение = 0.5
        rpe = ds.calculate_rpe("new_tool", actual_outcome=0.9)

        assert rpe == 0.4  # 0.9 - 0.5
        assert "new_tool" in ds.action_values


class TestDriveSystemSatisfaction:
    """Тесты применения удовлетворения."""

    def test_apply_satisfaction_reduces_tension(self, test_drives_config):
        """Удовлетворение снижает tension."""
        ds = DriveSystem(config=test_drives_config)
        ds.drives[DriveType.CURIOSITY].current = 0.7

        ds.apply_satisfaction(
            drive_type=DriveType.CURIOSITY,
            base_amount=0.2,
            rpe=0.0,  # Нейтральный RPE
        )

        assert ds.drives[DriveType.CURIOSITY].current < 0.7

    def test_apply_satisfaction_positive_rpe_boosts(self, test_drives_config):
        """Положительный RPE усиливает удовлетворение."""
        ds = DriveSystem(config=test_drives_config)
        ds.drives[DriveType.CURIOSITY].current = 0.7

        # С положительным RPE
        ds.apply_satisfaction(
            drive_type=DriveType.CURIOSITY,
            base_amount=0.2,
            rpe=0.5,
        )
        tension_with_positive_rpe = ds.drives[DriveType.CURIOSITY].current

        # Сбрасываем
        ds.drives[DriveType.CURIOSITY].current = 0.7

        # С отрицательным RPE
        ds.apply_satisfaction(
            drive_type=DriveType.CURIOSITY,
            base_amount=0.2,
            rpe=-0.5,
        )
        tension_with_negative_rpe = ds.drives[DriveType.CURIOSITY].current

        # Положительный RPE должен сильнее снизить tension
        assert tension_with_positive_rpe < tension_with_negative_rpe

    def test_apply_satisfaction_invalid_drive(self, test_drives_config):
        """Применение удовлетворения к несуществующему драйву бросает исключение."""
        ds = DriveSystem(config=test_drives_config)

        with pytest.raises(LeyaDriveNotFoundError):
            ds.apply_satisfaction(
                drive_type="invalid_drive",
                base_amount=0.1,
                rpe=0.0,
            )


class TestDriveSystemStimulus:
    """Тесты оценки стимулов."""

    @pytest.mark.asyncio
    async def test_evaluate_question_stimulus(self, test_drives_config):
        """Вопросительный стимул повышает CURIOSITY."""
        ds = DriveSystem(config=test_drives_config)

        deltas = await ds.evaluate_stimulus("Почему небо синее?")

        assert DriveType.CURIOSITY in deltas
        assert deltas[DriveType.CURIOSITY] > 0

    @pytest.mark.asyncio
    async def test_evaluate_gratitude_stimulus(self, test_drives_config):
        """Благодарность снижает CONNECTION tension."""
        ds = DriveSystem(config=test_drives_config)

        deltas = await ds.evaluate_stimulus("Спасибо, отлично!")

        assert DriveType.CONNECTION in deltas
        assert deltas[DriveType.CONNECTION] < 0

    @pytest.mark.asyncio
    async def test_evaluate_command_stimulus(self, test_drives_config):
        """Команда повышает AUTONOMY tension."""
        ds = DriveSystem(config=test_drives_config)

        deltas = await ds.evaluate_stimulus("Немедленно сделай это!")

        assert DriveType.AUTONOMY in deltas
        assert deltas[DriveType.AUTONOMY] > 0


class TestDriveSystemPersistence:
    """Тесты сохранения и загрузки состояния."""

    def test_save_state(self, test_drives_config):
        """save_state возвращает корректный dict."""
        ds = DriveSystem(config=test_drives_config)
        ds.action_values["tool1"] = 0.7

        state = ds.save_state()

        assert "action_values" in state
        assert "current_drives" in state
        assert state["action_values"]["tool1"] == 0.7

    def test_load_state(self, test_drives_config):
        """load_state восстанавливает состояние."""
        ds = DriveSystem(config=test_drives_config)

        state = {
            "action_values": {"tool1": 0.8},
            "current_drives": {
                "curiosity": 0.6,
                "connection": 0.5,
            },
        }

        ds.load_state(state)

        assert ds.action_values["tool1"] == 0.8
        assert ds.drives[DriveType.CURIOSITY].current == 0.6
        assert ds.drives[DriveType.CONNECTION].current == 0.5


class TestDriveSystemCrossInfluence:
    """Тесты перекрёстного влияния драйвов."""

    def test_cross_influence_matrix(self, test_drives_config):
        """Матрица перекрёстного влияния не пуста."""
        ds = DriveSystem(config=test_drives_config)
        assert len(ds.CROSS_INFLUENCE) > 0

    def test_curiosity_boosts_autonomy(self, test_drives_config):
        """Высокий CURIOSITY положительно влияет на AUTONOMY."""
        ds = DriveSystem(config=test_drives_config)

        # Устанавливаем высокий CURIOSITY
        ds.drives[DriveType.CURIOSITY].current = 0.9

        effect = ds._calculate_cross_influence(DriveType.AUTONOMY)

        # Согласно матрице, (CURIOSITY, AUTONOMY) = 0.15
        assert effect > 0


class TestDriveSystemPredictions:
    """Тесты предсказаний (аллостаз)."""

    def test_predicted_disbalance(self, test_drives_config):
        """get_predicted_disbalance возвращает dict."""
        ds = DriveSystem(config=test_drives_config)
        disbalance = ds.get_predicted_disbalance()

        assert isinstance(disbalance, dict)
        assert len(disbalance) == len(ds.drives)

    def test_internal_state_prompt(self, test_drives_config):
        """get_internal_state_prompt возвращает непустую строку."""
        ds = DriveSystem(config=test_drives_config)
        prompt = ds.get_internal_state_prompt()

        assert isinstance(prompt, str)
        assert len(prompt) > 0
        assert "curiosity" in prompt.lower()
