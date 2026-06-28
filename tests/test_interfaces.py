"""
Тесты Protocol-совместимости модулей.

Проверяет, что все модули реализуют свои Protocol-интерфейсы.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from leya_core.constitutional import ConstitutionalLayer
from leya_core.drives import DriveSystem
from leya_core.global_workspace import GlobalWorkspace
from leya_core.homeostasis_engine import HomeostasisEngine
from leya_core.interfaces import (
    IConstitutionalLayer,
    IDriveSystem,
    IGlobalWorkspace,
    IHomeostasisEngine,
    IMemorySystem,
    IMetaCognition,
)
from leya_core.memory import MemorySystem
from leya_core.reflection import MetaCognition
from leya_core.thinker import CoreThinker


class TestProtocolCompliance:
    """Тесты соответствия Protocol-интерфейсам."""

    def test_memory_system_implements_protocol(self, tmp_path):
        from leya_core.config import MemoryConfig
        from leya_core.memory import MemorySystem
        from leya_core.interfaces import IMemorySystem
    
        config = MemoryConfig(brain_dir=str(tmp_path / "brain"))
        memory = MemorySystem(config=config)
        assert isinstance(memory, IMemorySystem)

    def test_drive_system_implements_protocol(self, test_drives_config):
        """DriveSystem реализует IDriveSystem."""
        ds = DriveSystem(config=test_drives_config)
        assert isinstance(ds, IDriveSystem)

    def test_homeostasis_implements_protocol(self, test_homeostasis_config):
        """HomeostasisEngine реализует IHomeostasisEngine."""
        he = HomeostasisEngine(config=test_homeostasis_config)
        assert isinstance(he, IHomeostasisEngine)

    def test_workspace_implements_protocol(self, test_workspace_config):
        """GlobalWorkspace реализует IGlobalWorkspace."""
        ws = GlobalWorkspace(config=test_workspace_config)
        assert isinstance(ws, IGlobalWorkspace)

    def test_constitutional_implements_protocol(self, test_constitutional_config):
        """ConstitutionalLayer реализует IConstitutionalLayer."""
        cl = ConstitutionalLayer(config=test_constitutional_config)
        assert isinstance(cl, IConstitutionalLayer)

    def test_thinker_implements_protocol(self, test_thinker_config, mock_llm_client):
        """CoreThinker реализует ICoreThinker."""
        from leya_core.interfaces import ICoreThinker

        thinker = CoreThinker(
            llm_client=mock_llm_client,
            config=test_thinker_config,
        )
        assert isinstance(thinker, ICoreThinker)

    def test_reflection_implements_protocol(self, test_reflection_config, mock_llm_client):
        """MetaCognition реализует IMetaCognition."""
        mock_leya = MagicMock()
        reflection = MetaCognition(
            leya_os=mock_leya,
            llm_client=mock_llm_client,
            config=test_reflection_config,
        )
        assert isinstance(reflection, IMetaCognition)
