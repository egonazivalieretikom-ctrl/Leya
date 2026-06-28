"""
Интеграционный smoke test для LeyaOS.

Проверяет полный цикл: perceive → plan → act → reflect
с mock LLM и mock ChromaDB.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))
import LeyaOS as leya_module
LeyaOS = leya_module.LeyaOS


class TestIntegrationSmoke:
    """Интеграционные smoke-тесты."""

    @pytest.mark.asyncio
    async def test_leya_os_initialization(self, test_leya_config):
        """LeyaOS корректно инициализируется."""
        with patch("leya_core.memory.chromadb.PersistentClient") as mock_chroma:
            mock_chroma.return_value = MagicMock()

            leya = LeyaOS(config=test_leya_config, use_web=False)

            assert leya.name == "Лея"
            assert leya.state == "initializing"
            assert leya.memory is not None
            assert leya.drives is not None
            assert leya.thinker is not None

    @pytest.mark.asyncio
    async def test_perceive_cycle(self, test_leya_config):
        """Полный цикл perceive работает."""
        with patch("leya_core.memory.chromadb.PersistentClient") as mock_chroma:
            mock_chroma.return_value = MagicMock()

            # Mock для env
            with patch("LeyaOS.CLIEnvironment") as mock_env_class:
                mock_env = MagicMock()
                mock_env.tool_registry = MagicMock()
                mock_env.tool_registry.get_all_descriptions.return_value = ""
                mock_env.send_message = AsyncMock()
                mock_env.broadcast_thought = AsyncMock()
                mock_env_class.return_value = mock_env

                leya = LeyaOS(config=test_leya_config, use_web=False)
                leya.env = mock_env

                # Выполняем perceive
                await leya.perceive(
                    {
                        "type": "user_message",
                        "content": "Привет, Лея!",
                        "source": "test",
                    }
                )

                # Проверяем, что сообщение было отправлено
                mock_env.send_message.assert_called()

    @pytest.mark.asyncio
    async def test_protocol_checks_pass(self, test_leya_config):
        """Все Protocol-проверки проходят при инициализации."""
        with patch("leya_core.memory.chromadb.PersistentClient") as mock_chroma:
            mock_chroma.return_value = MagicMock()

            # Не должно бросить TypeError
            leya = LeyaOS(config=test_leya_config, use_web=False)

            from leya_core.interfaces import (
                IConstitutionalLayer,
                IDriveSystem,
                IGlobalWorkspace,
                IHomeostasisEngine,
                IMemorySystem,
            )

            assert isinstance(leya.memory, IMemorySystem)
            assert isinstance(leya.drives, IDriveSystem)
            assert isinstance(leya.workspace, IGlobalWorkspace)
            assert isinstance(leya.homeostasis, IHomeostasisEngine)
            assert isinstance(leya.constitutional, IConstitutionalLayer)

    @pytest.mark.asyncio
    async def test_shutdown_saves_state(self, test_leya_config, tmp_path):
        """Shutdown сохраняет состояние."""
        with patch("leya_core.memory.chromadb.PersistentClient") as mock_chroma:
            mock_chroma.return_value = MagicMock()

            with patch("LeyaOS.StatePersistence") as mock_persistence_class:
                mock_persistence = MagicMock()
                mock_persistence.save_state = MagicMock()
                mock_persistence.load_state = MagicMock(return_value=None)
                mock_persistence_class.return_value = mock_persistence

                leya = LeyaOS(config=test_leya_config, use_web=False)
                leya.persistence = mock_persistence
                leya.running = True

                await leya.shutdown()

                mock_persistence.save_state.assert_called()
                assert leya.state == "sleeping"
