"""
Тесты для StatePersistence.

Покрытие целевое: 29% → 70%+

Проверяет:
- Инициализацию с созданием директории
- Сохранение и загрузку состояния
- Обработку отсутствующего файла
- Обработку повреждённого JSON
- Атомарную запись (tmp + replace)
- Бэкап предыдущего состояния
"""

from __future__ import annotations

import json

import pytest

from leya_core.exceptions import LeyaStateCorruptedError
from leya_core.state_persistence import StatePersistence


class TestStatePersistenceInit:
    """Тесты инициализации StatePersistence."""

    def test_init_creates_directory(self, tmp_path):
        """StatePersistence создаёт директорию при инициализации."""
        state_file = tmp_path / "subdir" / "state.json"
        StatePersistence(state_file=str(state_file))

        assert state_file.parent.exists()

    def test_init_default_path(self):
        """StatePersistence инициализируется с путём по умолчанию."""
        persistence = StatePersistence()
        assert persistence.state_file.endswith("leya_state.json")


class TestSaveState:
    """Тесты сохранения состояния."""

    def test_save_state_creates_file(self, tmp_path):
        """save_state создаёт файл состояния."""
        state_file = tmp_path / "state.json"
        persistence = StatePersistence(state_file=str(state_file))

        state = {"drives": {"curiosity": 0.5}, "homeostasis": {}}
        result = persistence.save_state(state)

        assert result is True
        assert state_file.exists()

    def test_save_state_writes_json(self, tmp_path):
        """save_state записывает валидный JSON."""
        state_file = tmp_path / "state.json"
        persistence = StatePersistence(state_file=str(state_file))

        state = {"drives": {"curiosity": 0.5, "connection": 0.3}}
        persistence.save_state(state)

        with open(state_file, encoding="utf-8") as f:
            loaded = json.load(f)

        assert loaded["drives"]["curiosity"] == 0.5
        assert loaded["drives"]["connection"] == 0.3
        assert "_saved_at" in loaded

    def test_save_state_creates_backup(self, tmp_path):
        """save_state создаёт бэкап предыдущего состояния."""
        state_file = tmp_path / "state.json"
        persistence = StatePersistence(state_file=str(state_file))

        # Первое сохранение
        state1 = {"version": 1}
        persistence.save_state(state1)

        # Второе сохранение
        state2 = {"version": 2}
        persistence.save_state(state2)

        # Проверяем бэкап
        backup_file = state_file.with_suffix(".json.backup")
        assert backup_file.exists()

        with open(backup_file, encoding="utf-8") as f:
            backup = json.load(f)
        assert backup["version"] == 1

    def test_save_state_atomic_write(self, tmp_path):
        """save_state использует атомарную запись (tmp + replace)."""
        state_file = tmp_path / "state.json"
        persistence = StatePersistence(state_file=str(state_file))

        state = {"test": "data"}
        persistence.save_state(state)

        # Проверяем, что основной файл существует и содержит данные
        assert state_file.exists()
        with open(state_file, encoding="utf-8") as f:
            loaded = json.load(f)
        assert loaded["test"] == "data"

        # Проверяем, что tmp файл не остался
        tmp_file = state_file.with_suffix(".json.tmp")
        assert not tmp_file.exists()


class TestLoadState:
    """Тесты загрузки состояния."""

    def test_load_state_returns_empty_for_missing_file(self, tmp_path):
        """load_state возвращает пустой dict для отсутствующего файла."""
        state_file = tmp_path / "nonexistent.json"
        persistence = StatePersistence(state_file=str(state_file))

        state = persistence.load_state()

        assert state == {}

    def test_load_state_restores_state(self, tmp_path):
        """load_state восстанавливает сохранённое состояние."""
        state_file = tmp_path / "state.json"
        persistence = StatePersistence(state_file=str(state_file))

        original = {
            "drives": {"curiosity": 0.7, "connection": 0.4},
            "homeostasis": {"researched": ["тема1", "тема2"]},
        }
        persistence.save_state(original)

        loaded = persistence.load_state()

        assert loaded["drives"]["curiosity"] == 0.7
        assert loaded["drives"]["connection"] == 0.4
        assert loaded["homeostasis"]["researched"] == ["тема1", "тема2"]

    def test_load_state_from_backup(self, tmp_path):
        """load_state бросает LeyaStateCorruptedError при повреждённом JSON."""
        state_file = tmp_path / "state.json"
        persistence = StatePersistence(state_file=str(state_file))

        # Создаём повреждённый основной файл
        state_file.write_text("invalid json", encoding="utf-8")

        # Создаём валидный бэкап (но load_state не пытается его загрузить)
        backup_file = state_file.with_suffix(".json.backup")
        backup_data = {"version": 1, "drives": {}}
        backup_file.write_text(json.dumps(backup_data), encoding="utf-8")

        # load_state должен бросить исключение, а не загрузить из бэкапа
        with pytest.raises(LeyaStateCorruptedError):
            persistence.load_state()

    def test_load_state_corrupted_json(self, tmp_path):
        """load_state бросает LeyaStateCorruptedError для повреждённого JSON."""
        state_file = tmp_path / "state.json"
        persistence = StatePersistence(state_file=str(state_file))

        # Создаём повреждённый файл
        state_file.write_text("not valid json {{{", encoding="utf-8")

        with pytest.raises(LeyaStateCorruptedError):
            persistence.load_state()

    def test_load_state_preserves_timestamp(self, tmp_path):
        """load_state сохраняет timestamp из _saved_at."""
        state_file = tmp_path / "state.json"
        persistence = StatePersistence(state_file=str(state_file))

        original = {"test": "data"}
        persistence.save_state(original)

        loaded = persistence.load_state()

        assert "_saved_at" in loaded


class TestStatePersistenceEdgeCases:
    """Тесты граничных случаев."""

    def test_save_empty_state(self, tmp_path):
        """save_state сохраняет пустое состояние."""
        state_file = tmp_path / "state.json"
        persistence = StatePersistence(state_file=str(state_file))

        result = persistence.save_state({})

        assert result is True
        loaded = persistence.load_state()
        assert loaded == {} or "_saved_at" in loaded

    def test_save_complex_state(self, tmp_path):
        """save_state сохраняет сложное состояние с вложенными структурами."""
        state_file = tmp_path / "state.json"
        persistence = StatePersistence(state_file=str(state_file))

        complex_state = {
            "drives": {
                "curiosity": 0.5,
                "action_values": {"tool1": 0.7, "tool2": 0.3},
            },
            "homeostasis": {
                "researched": ["тема1", "тема2"],
                "keywords": ["ключ1", "ключ2"],
            },
            "nested": {
                "level1": {
                    "level2": {
                        "data": [1, 2, 3],
                    }
                }
            },
        }

        persistence.save_state(complex_state)
        loaded = persistence.load_state()

        assert loaded["drives"]["action_values"]["tool1"] == 0.7
        assert loaded["nested"]["level1"]["level2"]["data"] == [1, 2, 3]

    def test_unicode_in_state(self, tmp_path):
        """save_state корректно сохраняет Unicode символы."""
        state_file = tmp_path / "state.json"
        persistence = StatePersistence(state_file=str(state_file))

        state = {"message": "Привет, мир! 🌍", "emoji": "✨🎉"}
        persistence.save_state(state)

        loaded = persistence.load_state()

        assert loaded["message"] == "Привет, мир! 🌍"
        assert loaded["emoji"] == "✨🎉"

    def test_large_state(self, tmp_path):
        """save_state справляется с большими состояниями."""
        state_file = tmp_path / "state.json"
        persistence = StatePersistence(state_file=str(state_file))

        large_state = {
            "data": [f"item_{i}" for i in range(1000)],
            "nested": {f"key_{i}": i for i in range(100)},
        }

        persistence.save_state(large_state)
        loaded = persistence.load_state()

        assert len(loaded["data"]) == 1000
        assert loaded["nested"]["key_50"] == 50
