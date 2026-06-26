"""
voice_environment.py (ИСПРАВЛЕННАЯ ВЕРСИЯ - Phase 2)
"""

import logging

from leya_core.environment import Environment, Tool
from leya_core.personal_tools import (
    PERSONAL_TOOLS_DESCRIPTION,
    get_latest_news,
    open_browser_tab,
    send_personal_message,
)
from leya_core.voice_interface import VoiceInterface

logger = logging.getLogger("LeyaOS.VoiceEnvironment")


class VoiceEnvironment(Environment):

    def __init__(self, leya_os=None, use_voice: bool = True):
        super().__init__(leya_os=leya_os)

        self.use_voice = use_voice
        self.voice = None

        if self.use_voice:
            try:
                self.voice = VoiceInterface(stt_model_size="base", tts_rate=175)
                logger.info("VoiceInterface подключён к VoiceEnvironment.")
            except Exception as e:
                logger.error(f"Не удалось загрузить VoiceInterface: {e}")
                self.use_voice = False

        self._register_personal_tools()

    def _register_personal_tools(self):
        """Правильная регистрация инструментов"""
        if not hasattr(self, "tool_registry") or self.tool_registry is None:
            return

        # open_browser_tab
        tool1 = Tool(
            name="open_browser_tab",
            description=PERSONAL_TOOLS_DESCRIPTION["open_browser_tab"]["description"],
            parameters=PERSONAL_TOOLS_DESCRIPTION["open_browser_tab"]["parameters"],
            handler=open_browser_tab,
        )
        self.tool_registry.register(tool1)

        # send_personal_message
        tool2 = Tool(
            name="send_personal_message",
            description=PERSONAL_TOOLS_DESCRIPTION["send_personal_message"]["description"],
            parameters=PERSONAL_TOOLS_DESCRIPTION["send_personal_message"]["parameters"],
            handler=send_personal_message,
        )
        self.tool_registry.register(tool2)

        # get_latest_news
        tool3 = Tool(
            name="get_latest_news",
            description=PERSONAL_TOOLS_DESCRIPTION["get_latest_news"]["description"],
            parameters=PERSONAL_TOOLS_DESCRIPTION["get_latest_news"]["parameters"],
            handler=get_latest_news,
        )
        self.tool_registry.register(tool3)

        logger.info("Зарегистрированы персональные инструменты Phase 2")

    async def listen(self) -> str | None:
        if self.use_voice and self.voice:
            try:
                transcript = await self.voice.listen_once()
                if self.voice.is_addressed_to_me(transcript):
                    return transcript
                return None
            except Exception as e:
                logger.error(f"Ошибка голосового ввода: {e}")
                return None
        else:
            try:
                text = input("Ты: ").strip()
                return text if text else None
            except EOFError:
                return None

    def send_message(self, message: str):
        print(f"Лея: {message}")
        if self.use_voice and self.voice:
            try:
                self.voice.speak(message)
            except Exception as e:
                logger.error(f"Ошибка TTS: {e}")

    async def run_voice_loop(self):
        if not (self.use_voice and self.voice):
            return

        async def handle_transcript(text: str):
            if self.voice.is_addressed_to_me(text):
                if self.leya_os:
                    await self.leya_os.perceive({"type": "voice", "content": text})

        await self.voice.start_always_listening(handle_transcript)
