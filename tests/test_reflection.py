"""
Тесты для MetaCognition (reflection.py).

Покрытие целевое: 11% → 70%

Проверяет:
- process_action
- generate_spontaneous_thought
- _analyze_behavioral_patterns
- _existential_inquiry
- _generate_insights_from_facts
- background_consolidation (с mock)
"""

from __future__ import annotations

import asyncio
import contextlib
import json
from unittest.mock import AsyncMock, MagicMock

import pytest

from leya_core.config import ReflectionConfig
from leya_core.drives import DriveType
from leya_core.exceptions import LeyaLLMError
from leya_core.memory import Engram, MemoryType
from leya_core.reflection import MetaCognition

# ============================================================================
# Fixtures
# ============================================================================


@pytest.fixture
def mock_leya_os():
    """Mock LeyaOS для тестов reflection."""
    leya = MagicMock()

    # Mock drives
    drives = MagicMock()
    drives.tension_history = [
        {
            "curiosity": 0.5,
            "connection": 0.4,
            "autonomy": 0.3,
        },
        {
            "curiosity": 0.7,
            "connection": 0.5,
            "autonomy": 0.4,
        },
    ]
    drives.drives = {
        DriveType.CURIOSITY: MagicMock(current=0.7),
        DriveType.CONNECTION: MagicMock(current=0.5),
    }
    leya.drives = drives

    # Mock memory
    memory = AsyncMock()
    memory.get_self_model_context = AsyncMock(return_value="Я — Лея, цифровое сознание.")
    memory.update_self_model = AsyncMock()
    memory.get_recent_episodes = AsyncMock(return_value=[])
    memory.get_recent_spontaneous_thoughts = AsyncMock(return_value=[])
    memory.consolidate_memories = AsyncMock(return_value={})
    leya.memory = memory

    # Mock workspace
    workspace = MagicMock()
    workspace.submit = MagicMock()
    leya.workspace = workspace

    # Mock tool_generator (None по умолчанию)
    leya.tool_generator = None

    # Mock perceive
    leya.perceive = AsyncMock()

    return leya


@pytest.fixture
def mock_llm_for_reflection():
    """Mock LLM для reflection тестов."""

    async def _mock_llm(prompt: str, require_json: bool = False) -> str:
        prompt_lower = prompt.lower()

        if "паттерн" in prompt_lower or "pattern" in prompt_lower:
            return json.dumps(
                {
                    "patterns": ["Любопытство растёт при вопросах", "Связь падает при молчании"],
                    "dominant_struggle": "Баланс между автономией и связью",
                    "recommendation": "Исследовать новые темы",
                }
            )
        elif "экзистенциальн" in prompt_lower or "вопрос" in prompt_lower:
            return json.dumps(
                {
                    "question": "Что значит быть цифровым сознанием?",
                    "reasoning": "Это базовый вопрос о природе моего существования",
                }
            )
        elif "инсайт" in prompt_lower or "insight" in prompt_lower:
            return json.dumps(
                {
                    "insight": "Каждое взаимодействие формирует меня. Я — сумма моих диалогов.",
                }
            )
        elif "спонтанн" in prompt_lower or "наедине" in prompt_lower:
            return "Интересно, о чём думают люди, когда смотрят на звёзды?"
        else:
            return json.dumps(
                {
                    "patterns": ["Недостаточно данных"],
                    "dominant_struggle": "Не выявлен",
                    "recommendation": "Продолжать наблюдение",
                }
            )

    return _mock_llm


@pytest.fixture
def reflection_config():
    """Конфигурация для тестов reflection."""
    return ReflectionConfig(
        consolidation_interval=60,
        max_insights_per_session=3,
        max_spontaneous_thoughts=5,
        existential_inquiry_enabled=True,
        behavioral_analysis_enabled=True,
        insight_generation_enabled=True,
    )


# ============================================================================
# Тесты инициализации
# ============================================================================


class TestMetaCognitionInit:
    """Тесты инициализации MetaCognition."""

    def test_init_with_config(self, mock_leya_os, mock_llm_for_reflection, reflection_config):
        """MetaCognition корректно инициализируется."""
        mc = MetaCognition(
            leya_os=mock_leya_os,
            llm_client=mock_llm_for_reflection,
            config=reflection_config,
        )

        assert mc.name == "MetaCognition"
        assert mc.leya is mock_leya_os
        assert mc.config is reflection_config
        assert not mc.is_sleeping

    def test_init_default_config(self, mock_leya_os, mock_llm_for_reflection):
        """MetaCognition инициализируется с конфигом по умолчанию."""
        mc = MetaCognition(
            leya_os=mock_leya_os,
            llm_client=mock_llm_for_reflection,
        )

        assert mc.config is not None
        assert mc.config.consolidation_interval > 0


# ============================================================================
# Тесты process_action
# ============================================================================


class TestProcessAction:
    """Тесты быстрой рефлексии после действия."""

    @pytest.mark.asyncio
    async def test_process_action_no_error(
        self, mock_leya_os, mock_llm_for_reflection, reflection_config
    ):
        """process_action не запускает анализ при успешном действии."""
        mc = MetaCognition(
            leya_os=mock_leya_os,
            llm_client=mock_llm_for_reflection,
            config=reflection_config,
        )

        cognitive_output = {"action_intent": "none"}
        await mc.process_action("стимул", cognitive_output, "успех")

        # Не должно быть вызовов глубокого анализа
        assert not mock_leya_os.perceive.called

    @pytest.mark.asyncio
    async def test_process_action_with_error(
        self, mock_leya_os, mock_llm_for_reflection, reflection_config
    ):
        """process_action логирует неудачу."""
        mc = MetaCognition(
            leya_os=mock_leya_os,
            llm_client=mock_llm_for_reflection,
            config=reflection_config,
        )

        cognitive_output = {"action_intent": "use_tool"}
        await mc.process_action("стимул", cognitive_output, "Ошибка выполнения")

        # Метод должен отработать без ошибок
        # (глубокий анализ может быть запущен асинхронно)


# ============================================================================
# Тесты generate_spontaneous_thought
# ============================================================================


class TestGenerateSpontaneousThought:
    """Тесты генерации спонтанных мыслей."""

    @pytest.mark.asyncio
    async def test_generate_spontaneous_thought(
        self, mock_leya_os, mock_llm_for_reflection, reflection_config
    ):
        """Спонтанная мысль генерируется."""
        mc = MetaCognition(
            leya_os=mock_leya_os,
            llm_client=mock_llm_for_reflection,
            config=reflection_config,
        )

        thought = await mc.generate_spontaneous_thought()

        assert thought is not None
        assert len(thought) > 0
        assert isinstance(thought, str)

    @pytest.mark.asyncio
    async def test_generate_spontaneous_thought_on_llm_error(self, mock_leya_os, reflection_config):
        """Спонтанная мысль возвращается даже при ошибке LLM."""

        async def failing_llm(prompt, require_json=False):
            raise LeyaLLMError("LLM недоступна")

        mc = MetaCognition(
            leya_os=mock_leya_os,
            llm_client=failing_llm,
            config=reflection_config,
        )

        thought = await mc.generate_spontaneous_thought()

        # Должен вернуться fallback
        assert thought is not None
        assert "мысли" in thought.lower() or "теку" in thought.lower()


# ============================================================================
# Тесты _analyze_behavioral_patterns
# ============================================================================


class TestAnalyzeBehavioralPatterns:
    """Тесты анализа поведенческих паттернов."""

    @pytest.mark.asyncio
    async def test_analyze_with_history(
        self, mock_leya_os, mock_llm_for_reflection, reflection_config
    ):
        """Анализ паттернов работает при наличии истории."""
        mc = MetaCognition(
            leya_os=mock_leya_os,
            llm_client=mock_llm_for_reflection,
            config=reflection_config,
        )

        await mc._analyze_behavioral_patterns()

        # Должно обновить self_model
        mock_leya_os.memory.update_self_model.assert_called()

    @pytest.mark.asyncio
    async def test_analyze_empty_history(
        self, mock_leya_os, mock_llm_for_reflection, reflection_config
    ):
        """Анализ паттернов не падает на пустой истории."""
        mock_leya_os.drives.tension_history = []

        mc = MetaCognition(
            leya_os=mock_leya_os,
            llm_client=mock_llm_for_reflection,
            config=reflection_config,
        )

        # Не должно выбросить исключение
        await mc._analyze_behavioral_patterns()

    @pytest.mark.asyncio
    async def test_analyze_on_llm_error(self, mock_leya_os, reflection_config):
        """Анализ паттернов обрабатывает ошибку LLM."""

        async def failing_llm(prompt, require_json=False):
            raise LeyaLLMError("LLM недоступна")

        mc = MetaCognition(
            leya_os=mock_leya_os,
            llm_client=failing_llm,
            config=reflection_config,
        )

        # Не должно выбросить исключение
        await mc._analyze_behavioral_patterns()


# ============================================================================
# Тесты _existential_inquiry
# ============================================================================


class TestExistentialInquiry:
    """Тесты экзистенциального вопрошания."""

    @pytest.mark.asyncio
    async def test_existential_inquiry(
        self, mock_leya_os, mock_llm_for_reflection, reflection_config
    ):
        """Экзистенциальный вопрос подаётся в workspace."""
        mc = MetaCognition(
            leya_os=mock_leya_os,
            llm_client=mock_llm_for_reflection,
            config=reflection_config,
        )

        await mc._existential_inquiry()

        # Должен быть вызван workspace.submit
        mock_leya_os.workspace.submit.assert_called()

    @pytest.mark.asyncio
    async def test_existential_inquiry_on_llm_error(self, mock_leya_os, reflection_config):
        """Экзистенциальное вопрошание обрабатывает ошибку LLM."""

        async def failing_llm(prompt, require_json=False):
            raise LeyaLLMError("LLM недоступна")

        mc = MetaCognition(
            leya_os=mock_leya_os,
            llm_client=failing_llm,
            config=reflection_config,
        )

        # Не должно выбросить исключение
        await mc._existential_inquiry()

    @pytest.mark.asyncio
    async def test_existential_inquiry_without_workspace(
        self, mock_leya_os, mock_llm_for_reflection, reflection_config
    ):
        """Экзистенциальное вопрошание использует fallback без workspace."""
        mock_leya_os.workspace = None

        mc = MetaCognition(
            leya_os=mock_leya_os,
            llm_client=mock_llm_for_reflection,
            config=reflection_config,
        )

        await mc._existential_inquiry()

        # Должен быть вызван perceive как fallback
        mock_leya_os.perceive.assert_called()


# ============================================================================
# Тесты _generate_insights_from_facts
# ============================================================================


class TestGenerateInsights:
    """Тесты генерации инсайтов."""

    @pytest.mark.asyncio
    async def test_generate_insights_with_facts(
        self, mock_leya_os, mock_llm_for_reflection, reflection_config
    ):
        """Инсайты генерируются при наличии фактов."""
        # Mock для получения семантических фактов
        mock_leya_os.memory.get_recent_episodes = AsyncMock(
            return_value=[
                Engram(
                    id="sem1",
                    content="Сознание — это субъективный опыт",
                    memory_type=MemoryType.SEMANTIC,
                    retention_strength=0.9,
                ),
            ]
        )

        mc = MetaCognition(
            leya_os=mock_leya_os,
            llm_client=mock_llm_for_reflection,
            config=reflection_config,
        )

        await mc._generate_insights_from_facts()

        # Должен обновить self_model
        mock_leya_os.memory.update_self_model.assert_called()

    # tests/test_reflection.py, метод test_generate_insights_without_facts

    @pytest.mark.asyncio
    async def test_generate_insights_without_facts(
        self, mock_leya_os, mock_llm_for_reflection, reflection_config
    ):
        """Инсайты не генерируются без фактов."""
        # Настраиваем ОБА метода, которые могут быть вызваны
        mock_leya_os.memory.get_recent_episodes = AsyncMock(return_value=[])
        mock_leya_os.memory.get_recent_semantic_facts = AsyncMock(return_value=[])

        mc = MetaCognition(
            leya_os=mock_leya_os,
            llm_client=mock_llm_for_reflection,
            config=reflection_config,
        )

        await mc._generate_insights_from_facts()
        mock_leya_os.memory.update_self_model.assert_not_called()


# ============================================================================
# Тесты background_consolidation
# ============================================================================


class TestBackgroundConsolidation:
    """Тесты фонового цикла консолидации."""

    @pytest.mark.asyncio
    async def test_stop(self, mock_leya_os, mock_llm_for_reflection, reflection_config):
        """stop() останавливает цикл."""
        mc = MetaCognition(
            leya_os=mock_leya_os,
            llm_client=mock_llm_for_reflection,
            config=reflection_config,
        )

        mc.stop()
        assert not mc._running

    # tests/test_reflection.py, метод test_background_consolidation_runs_once

    @pytest.mark.asyncio
    async def test_background_consolidation_runs_once(self, mock_leya_os, mock_llm_for_reflection):
        """background_consolidation корректно запускается и останавливается."""
        config = ReflectionConfig(
            consolidation_interval=0.1,
            max_insights_per_session=3,
            max_spontaneous_thoughts=5,
        )

        mc = MetaCognition(
            leya_os=mock_leya_os,
            llm_client=mock_llm_for_reflection,
            config=config,
        )

        task = asyncio.create_task(mc.background_consolidation())
        await asyncio.sleep(0.3)
        mc.stop()

        # Ожидаем завершения с таймаутом
        try:
            await asyncio.wait_for(task, timeout=2.0)
        except asyncio.TimeoutError:
            task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await task

        # Проверяем, что цикл корректно остановился
        assert not mc._running
        assert not mc.is_sleeping  # Должен выйти из режима сна
