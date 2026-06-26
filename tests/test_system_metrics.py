"""
Тесты для SystemMetrics.

Покрытие целевое: 20% → 70%+

Проверяет:
- Сбор метрик с psutil (mock)
- Fallback метрики без psutil
- Модификаторы драйвов на основе метрик
- Обработка батареи
- Обработка ошибок psutil
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from leya_core.system_metrics import SystemMetrics


class TestSystemMetricsInit:
    """Тесты инициализации SystemMetrics."""

    def test_init(self):
        """SystemMetrics инициализируется корректно."""
        metrics = SystemMetrics()
        assert metrics.last_metrics == {}

    def test_init_with_psutil(self):
        """SystemMetrics работает с psutil."""
        with patch("leya_core.system_metrics.PSUTIL_AVAILABLE", True):
            metrics = SystemMetrics()
            assert metrics is not None


class TestCollectMetrics:
    """Тесты сбора метрик."""

    def test_collect_with_psutil(self):
        """collect собирает метрики с psutil."""
        with (
            patch("leya_core.system_metrics.PSUTIL_AVAILABLE", True),
            patch("leya_core.system_metrics.psutil") as mock_psutil,
        ):
            # Настраиваем mock
            mock_psutil.cpu_percent.return_value = 50.0
            mock_psutil.virtual_memory.return_value = MagicMock(percent=60.0)
            mock_psutil.disk_usage.return_value = MagicMock(percent=70.0)
            mock_psutil.disk_io_counters.return_value = MagicMock(
                read_bytes=1000000,
                write_bytes=500000,
            )
            mock_psutil.net_io_counters.return_value = MagicMock(
                bytes_sent=2000000,
                bytes_recv=1000000,
            )
            mock_psutil.sensors_battery.return_value = MagicMock(percent=80)

            metrics = SystemMetrics()
            result = metrics.collect()

            assert "cpu" in result
            assert "ram" in result
            assert "disk" in result
            assert "battery" in result
            assert 0.0 <= result["cpu"] <= 1.0
            assert 0.0 <= result["ram"] <= 1.0

    def test_collect_without_psutil(self):
        """collect возвращает fallback метрики без psutil."""
        with patch("leya_core.system_metrics.PSUTIL_AVAILABLE", False):
            metrics = SystemMetrics()
            result = metrics.collect()

            assert "cpu" in result
            assert "ram" in result
            assert result["cpu"] == 0.5
            assert result["ram"] == 0.5

    def test_collect_handles_psutil_error(self):
        """collect обрабатывает ошибки psutil."""
        with (
            patch("leya_core.system_metrics.PSUTIL_AVAILABLE", True),
            patch("leya_core.system_metrics.psutil") as mock_psutil,
        ):
            mock_psutil.cpu_percent.side_effect = Exception("psutil error")

            metrics = SystemMetrics()
            result = metrics.collect()

            # Должен вернуться fallback
            assert result["cpu"] == 0.5


class TestGetBattery:
    """Тесты получения уровня батареи."""

    def test_get_battery_with_sensor(self):
        """_get_battery возвращает уровень батареи."""
        with patch("leya_core.system_metrics.psutil") as mock_psutil:
            mock_psutil.sensors_battery.return_value = MagicMock(percent=75)

            metrics = SystemMetrics()
            result = metrics._get_battery()

            assert result == 0.75

    def test_get_battery_without_sensor(self):
        """_get_battery возвращает 1.0 если нет батареи."""
        with patch("leya_core.system_metrics.psutil") as mock_psutil:
            mock_psutil.sensors_battery.return_value = None

            metrics = SystemMetrics()
            result = metrics._get_battery()

            assert result == 1.0

    def test_get_battery_handles_error(self):
        """_get_battery обрабатывает ошибки."""
        with patch("leya_core.system_metrics.psutil") as mock_psutil:
            mock_psutil.sensors_battery.side_effect = Exception("No battery sensor")

            metrics = SystemMetrics()
            result = metrics._get_battery()

            assert result == 1.0


class TestFallbackMetrics:
    """Тесты fallback метрик."""

    def test_fallback_metrics_structure(self):
        """_fallback_metrics возвращает корректную структуру."""
        metrics = SystemMetrics()
        result = metrics._fallback_metrics()

        assert "cpu" in result
        assert "ram" in result
        assert "disk" in result
        assert "disk_io" in result
        assert "net_io" in result
        assert "battery" in result

    def test_fallback_metrics_values(self):
        """_fallback_metrics возвращает разумные значения."""
        metrics = SystemMetrics()
        result = metrics._fallback_metrics()

        assert result["cpu"] == 0.5
        assert result["ram"] == 0.5
        assert result["disk"] == 0.5
        assert result["battery"] == 1.0


class TestGetDriveModifiers:
    """Тесты модификаторов драйвов."""

    def test_get_drive_modifiers_high_cpu(self):
        """get_drive_modifiers снижает autonomy при высоком CPU."""
        metrics = SystemMetrics()
        metrics.last_metrics = {
            "cpu": 0.9,  # Высокая загрузка CPU
            "ram": 0.5,
            "disk": 0.5,
            "disk_io": 0.3,
            "net_io": 0.2,
            "battery": 1.0,
        }

        modifiers = metrics.get_drive_modifiers()

        assert modifiers["autonomy"] < 0  # Должно быть отрицательным

    def test_get_drive_modifiers_low_cpu(self):
        """get_drive_modifiers повышает autonomy при низком CPU."""
        metrics = SystemMetrics()
        metrics.last_metrics = {
            "cpu": 0.2,  # Низкая загрузка CPU
            "ram": 0.5,
            "disk": 0.5,
            "disk_io": 0.3,
            "net_io": 0.2,
            "battery": 1.0,
        }

        modifiers = metrics.get_drive_modifiers()

        assert modifiers["autonomy"] > 0  # Должно быть положительным

    def test_get_drive_modifiers_high_ram(self):
        """get_drive_modifiers снижает integrity при высоком RAM."""
        metrics = SystemMetrics()
        metrics.last_metrics = {
            "cpu": 0.5,
            "ram": 0.9,  # Высокое использование RAM
            "disk": 0.5,
            "disk_io": 0.3,
            "net_io": 0.2,
            "battery": 1.0,
        }

        modifiers = metrics.get_drive_modifiers()

        assert modifiers["integrity"] < 0

    def test_get_drive_modifiers_high_disk_io(self):
        """get_drive_modifiers повышает curiosity при высоком disk_io."""
        metrics = SystemMetrics()
        metrics.last_metrics = {
            "cpu": 0.5,
            "ram": 0.5,
            "disk": 0.5,
            "disk_io": 0.7,  # Высокий disk I/O
            "net_io": 0.2,
            "battery": 1.0,
        }

        modifiers = metrics.get_drive_modifiers()

        assert modifiers["curiosity"] > 0

    def test_get_drive_modifiers_high_net_io(self):
        """get_drive_modifiers повышает connection при высоком net_io."""
        metrics = SystemMetrics()
        metrics.last_metrics = {
            "cpu": 0.5,
            "ram": 0.5,
            "disk": 0.5,
            "disk_io": 0.3,
            "net_io": 0.5,  # Высокий network I/O
            "battery": 1.0,
        }

        modifiers = metrics.get_drive_modifiers()

        assert modifiers["connection"] > 0

    def test_get_drive_modifiers_low_battery(self):
        """get_drive_modifiers снижает все драйвы при низкой батарее."""
        metrics = SystemMetrics()
        metrics.last_metrics = {
            "cpu": 0.5,
            "ram": 0.5,
            "disk": 0.5,
            "disk_io": 0.3,
            "net_io": 0.2,
            "battery": 0.1,  # Низкий заряд батареи
        }

        modifiers = metrics.get_drive_modifiers()

        # Все драйвы должны быть снижены
        assert all(v <= 0 for v in modifiers.values())

    def test_get_drive_modifiers_collects_if_empty(self):
        """get_drive_modifiers собирает метрики если last_metrics пуст."""
        with patch("leya_core.system_metrics.PSUTIL_AVAILABLE", False):
            metrics = SystemMetrics()
            metrics.last_metrics = {}

            modifiers = metrics.get_drive_modifiers()

            # Должны быть использованы fallback метрики
            assert isinstance(modifiers, dict)
            assert "curiosity" in modifiers
