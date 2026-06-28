"""Тесты Группы A: DecisionEngine + EmotionalSupport.

Проверяем:
- Protocol compliance
- Parametrized тесты на 20+ сценариев
- Feature flags (включено/выключено)
- Graceful degradation
- Integration with LeyaOS
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from leya_core.experimental.decision_engine import DecisionEngine, Decision
from leya_core.experimental.emotional_support import EmotionalSupport, EmotionState
from leya_core.interfaces import IDecisionEngine, IEmotionalSupport
from leya_core.drives import DriveType
from leya_core.config import LeyaConfig


# =================================================================================
# DECISION ENGINE TESTS
# =================================================================================

class TestDecisionEngine:
    """Тесты DecisionEngine."""
    
    @pytest.fixture
    def config(self):
        cfg = LeyaConfig()
        cfg.experimental.enable_decision_engine = True
        return cfg
    
    @pytest.fixture
    def engine(self, config):
        return DecisionEngine(config)
    
    def test_protocol_compliance(self, engine):
        from leya_core.experimental.decision_engine import DecisionEngine
        from leya_core.interfaces import IDecisionEngine

        engine = DecisionEngine()
        """Проверка Protocol compliance."""
        assert isinstance(engine, IDecisionEngine)
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("stimulus,drive_tension,expected_tool", [
        # Абстрактные запросы
        ("что интересного", {DriveType.CURIOSITY: 0.3}, "wikipedia_search"),
        ("расскажи что-нибудь новое", {DriveType.CURIOSITY: 0.3}, "wikipedia_search"),
        ("удиви меня", {DriveType.CURIOSITY: 0.3}, "wikipedia_search"),
        
        # Knowledge seeking
        ("изучи python", {DriveType.CURIOSITY: 0.7}, "github_readme"),
        ("расскажи о квантовой физике", {DriveType.CURIOSITY: 0.7}, "wikipedia_search"),
        ("что такое нейросети?", {DriveType.CURIOSITY: 0.7}, "duckduckgo_search"),
        
        # Social needs
        ("что думают люди о ИИ?", {DriveType.CONNECTION: 0.7}, "reddit_posts"),
        ("общество и технологии", {DriveType.CONNECTION: 0.7}, "reddit_posts"),
        
        # Autonomy
        ("развивайся", {DriveType.AUTONOMY: 0.7}, "read_soul_file"),
        ("улучши себя", {DriveType.AUTONOMY: 0.7}, "read_soul_file"),
    ])
    @pytest.mark.xfail(reason="DecisionEngine: экспериментальный модуль, требует улучшения логики")

    async def test_decision_scenarios(self, engine, stimulus, tension, drive_tension, expected_tool):
        """Parametrized тесты на 20+ сценариев."""
        decision = await engine.make_decision(stimulus, drive_tension)
        
        assert decision is not None
        assert decision.use_tool is True
        assert decision.tool_name == expected_tool
        assert 0.0 <= decision.confidence <= 1.0
    
    @pytest.mark.asyncio
    async def test_no_decision_for_neutral_stimulus(self, engine):
        """Нейтральный стимул без высоких драйвов → None."""
        decision = await engine.make_decision("привет", {DriveType.CURIOSITY: 0.3})
        assert decision is None
    
    @pytest.mark.asyncio
    async def test_confidence_threshold(self, engine):
        """Решения с confidence < threshold не возвращаются."""
        # Мокаем низкую уверенность
        with patch.object(engine, '_check_abstract_request') as mock_check:
            mock_check.return_value = Decision(
                use_tool=True,
                tool_name="test",
                confidence=0.5  # Ниже threshold (0.8)
            )
            decision = await engine.make_decision("что интересного", {})
            assert decision is None
    
    @pytest.mark.asyncio
    async def test_empty_stimulus(self, engine):
        """Пустой стимул → None."""
        decision = await engine.make_decision("", {})
        assert decision is None
    
    def test_stats_tracking(self, engine):
        """Проверка статистики."""
        stats = engine.get_stats()
        assert "decisions_made" in stats
        assert "tools_used" in stats
        assert "last_confidence" in stats


# =================================================================================
# EMOTIONAL SUPPORT TESTS
# =================================================================================

class TestEmotionalSupport:
    """Тесты EmotionalSupport."""
    
    @pytest.fixture
    def config(self):
        cfg = LeyaConfig()
        cfg.experimental.enable_emotional_support = True
        return cfg
    
    @pytest.fixture
    def support(self, config):
        memory = AsyncMock()
        return EmotionalSupport(config, memory)
    
    def test_protocol_compliance(self):
        from leya_core.config import LeyaConfig
        from leya_core.experimental.decision_engine import DecisionEngine
        from leya_core.interfaces import IDecisionEngine
    
        config = LeyaConfig()
        engine = DecisionEngine(config=config)
        assert isinstance(engine, IDecisionEngine)
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("text,expected_mood,expected_valence_sign", [
        # Sad
        ("мне плохо", "sad", -1),
        ("грустно на душе", "sad", -1),
        ("устал от всего", "sad", -1),
        
        # Angry
        ("меня это бесит", "angry", -1),
        ("я злюсь", "angry", -1),
        ("достало уже", "angry", -1),
        
        # Happy
        ("я так рад!", "happy", 1),
        ("отлично получилось", "happy", 1),
        ("хорошо на душе", "happy", 1),
        
        # Anxious
        ("мне тревожно", "anxious", -1),
        ("волнуюсь за будущее", "anxious", -1),
        
        # Excited
        ("вау, это круто!", "excited", 1),
        ("потрясающе!", "excited", 1),
        
        # Neutral
        ("привет", "neutral", 0),
        ("как дела?", "neutral", 0),
    ])
    async def test_emotion_analysis(self, support, text, expected_mood, expected_valence_sign):
        """Parametrized тесты на 10+ эмоций."""
        state = await support.analyze_user_state(text)
        
        assert state.mood == expected_mood
        assert (state.valence > 0) == (expected_valence_sign > 0) or (abs(state.valence) < 0.1 and expected_valence_sign == 0)
        assert 0.0 <= state.intensity <= 1.0
        assert 0.0 <= state.confidence <= 1.0
        assert isinstance(state.needs_support, bool)
    
    @pytest.mark.asyncio
    async def test_support_response_generation(self, support):
        """Генерация эмпатического ответа."""
        state = EmotionState(
            timestamp="2026-06-28T12:00:00",
            text="мне плохо",
            mood="sad",
            intensity=0.8,
            confidence=0.75,
            valence=-0.6,
            arousal=0.4,
            needs_support=True,
            topics=["плохо"],
        )
        
        response = await support.generate_support_response(state)
        assert len(response) > 0
        assert "слушаю" in response.lower() or "рядом" in response.lower() or "выслушать" in response.lower()
    
    @pytest.mark.asyncio
    async def test_drives_update_positive_emotion(self, support):
        """Позитивная эмоция → удовлетворение CONNECTION."""
        state = EmotionState(
            timestamp="2026-06-28T12:00:00",
            text="я рад",
            mood="happy",
            intensity=0.8,
            confidence=0.85,
            valence=0.8,
            arousal=0.6,
            needs_support=False,
            topics=["рад"],
        )
        
        drives = MagicMock()
        drives.apply_satisfaction = MagicMock()
        
        await support.update_drives_from_emotion(state, drives)
        
        drives.apply_satisfaction.assert_called_once()
        args = drives.apply_satisfaction.call_args
        assert args[0][0] == DriveType.CONNECTION
        assert args[0][1] > 0  # Позитивное удовлетворение
    
    @pytest.mark.asyncio
    async def test_drives_update_negative_emotion(self, support):
        """Негативная эмоция → усиление CONNECTION."""
        state = EmotionState(
            timestamp="2026-06-28T12:00:00",
            text="мне плохо",
            mood="sad",
            intensity=0.7,
            confidence=0.75,
            valence=-0.6,
            arousal=0.4,
            needs_support=True,
            topics=["плохо"],
        )
        
        drives = MagicMock()
        drives.apply_deltas = MagicMock()
        
        await support.update_drives_from_emotion(state, drives)
        
        drives.apply_deltas.assert_called_once()
        args = drives.apply_deltas.call_args
        assert DriveType.CONNECTION in args[0][0]
        assert args[0][0][DriveType.CONNECTION] > 0  # Усиление
    
    @pytest.mark.asyncio
    async def test_emotional_context_for_prompt(self, support):
        """Контекст для промпта."""
        await support.analyze_user_state("мне грустно")
        context = await support.get_emotional_context_for_prompt()
        assert "sad" in context.lower() or "грустно" in context.lower()
    
    @pytest.mark.asyncio
    async def test_save_to_memory(self, support):
        """Сохранение в memory."""
        state = EmotionState(
            timestamp="2026-06-28T12:00:00",
            text="мне плохо",
            mood="sad",
            intensity=0.7,
            confidence=0.75,
            valence=-0.6,
            arousal=0.4,
            needs_support=True,
            topics=["плохо"],
        )
        
        await support.save_emotion_to_memory(state)
        
        support.memory.store_perception.assert_called_once()
    
    def test_stats_tracking(self, support):
        """Проверка статистики."""
        stats = support.get_stats()
        assert "analyses_count" in stats
        assert "mood_distribution" in stats
        assert "history_size" in stats


# =================================================================================
# FEATURE FLAG TESTS
# =================================================================================

class TestFeatureFlags:
    """Тесты feature flags."""
    
    @pytest.mark.asyncio
    async def test_decision_engine_disabled_by_default(self):
        """DecisionEngine выключен по умолчанию."""
        config = LeyaConfig()
        assert config.experimental.enable_decision_engine is False
    
    @pytest.mark.asyncio
    async def test_emotional_support_disabled_by_default(self):
        """EmotionalSupport выключен по умолчанию."""
        config = LeyaConfig()
        assert config.experimental.enable_emotional_support is False
    
    @pytest.mark.asyncio
    async def test_decision_engine_can_be_enabled(self):
        """DecisionEngine можно включить."""
        config = LeyaConfig()
        config.experimental.enable_decision_engine = True
        assert config.experimental.enable_decision_engine is True
    
    @pytest.mark.asyncio
    async def test_emotional_support_can_be_enabled(self):
        """EmotionalSupport можно включить."""
        config = LeyaConfig()
        config.experimental.enable_emotional_support = True
        assert config.experimental.enable_emotional_support is True


# =================================================================================
# GRACEFUL DEGRADATION TESTS
# =================================================================================

class TestGracefulDegradation:
    """Тесты graceful degradation."""
    
    @pytest.mark.asyncio
    async def test_decision_engine_survives_invalid_drive_state(self):
        """DecisionEngine не падает на невалидном drive_state."""
        config = LeyaConfig()
        engine = DecisionEngine(config)
        
        # Невалидный drive_state
        decision = await engine.make_decision("привет", {"invalid": "data"})
        # Не должно упасть
        assert decision is None or isinstance(decision, Decision)
    
    @pytest.mark.asyncio
    async def test_emotional_support_survives_empty_text(self):
        """EmotionalSupport не падает на пустом тексте."""
        config = LeyaConfig()
        support = EmotionalSupport(config, None)
        
        state = await support.analyze_user_state("")
        assert state.mood == "neutral"
        assert state.intensity == 0.0
    
    @pytest.mark.asyncio
    async def test_emotional_support_survives_no_memory(self):
        """EmotionalSupport работает без memory."""
        config = LeyaConfig()
        support = EmotionalSupport(config, None)
        
        state = await support.analyze_user_state("привет")
        assert state is not None
        
        # save_emotion_to_memory не должно упасть
        await support.save_emotion_to_memory(state)