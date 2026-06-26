"""
voice_interface.py
Модуль для голосового ввода/вывода в персональном LeyaOS.
Фаза 1 плана: базовый голосовой интерфейс + естественное обращение.

Зависимости (установить локально):
pip install faster-whisper pyttsx3 sounddevice numpy

Для production рекомендуется:
- faster-whisper (локальный Whisper)
- Локальная TTS (Piper TTS, Coqui TTS или Bark)
- sounddevice для записи аудио

Этот модуль — скелет. Интеграция с LeyaOS происходит через VoiceEnvironment (будет добавлено позже).
"""

import asyncio
import logging
import os
import tempfile
from collections.abc import Awaitable, Callable

import numpy as np
import pyttsx3
import sounddevice as sd
from faster_whisper import WhisperModel

logger = logging.getLogger("LeyaOS.VoiceInterface")


class VoiceInterface:
    """
    Класс для голосового взаимодействия.
    Поддерживает:
    - Запись аудио по нажатию (push-to-talk) или always-on (с обнаружением речи).
    - Локальное распознавание речи (STT).
    - Синтез речи (TTS).
    - Базовое определение, обращено ли к системе (простая эвристика + контекст).
    """

    def __init__(
        self,
        stt_model_size: str = "base",  # tiny, base, small, medium, large
        tts_rate: int = 180,
        sample_rate: int = 16000,
        channels: int = 1,
    ):
        self.sample_rate = sample_rate
        self.channels = channels
        self.is_listening = False
        self.audio_buffer = []

        # STT - локальный Whisper
        logger.info("Загрузка Whisper модели...")
        self.stt_model = WhisperModel(stt_model_size, device="cpu", compute_type="int8")
        logger.info("Whisper загружен.")

        # TTS - pyttsx3 (простой кросс-платформенный)
        self.tts_engine = pyttsx3.init()
        self.tts_engine.setProperty("rate", tts_rate)
        # Можно настроить голос: self.tts_engine.setProperty('voice', 'ru') если доступен русский голос

        # Callback для обработки распознанного текста
        self.on_transcript: Callable[[str], Awaitable[None]] | None = None

        logger.info("VoiceInterface инициализирован (персональный режим).")

    async def record_audio(self, duration: float = 5.0) -> np.ndarray:
        """Простая запись аудио (push-to-talk стиль)."""
        logger.info(f"Запись аудио {duration} сек...")
        audio = sd.rec(
            int(duration * self.sample_rate),
            samplerate=self.sample_rate,
            channels=self.channels,
            dtype="float32",
        )
        sd.wait()
        return audio.flatten()

    async def transcribe(self, audio: np.ndarray) -> str:
        """Распознавание речи с помощью Whisper."""
        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
            import soundfile as sf

            sf.write(tmp.name, audio, self.sample_rate)
            tmp_path = tmp.name

        try:
            segments, info = self.stt_model.transcribe(tmp_path, language="ru")
            text = " ".join([seg.text for seg in segments]).strip()
            logger.info(f"Распознано: {text}")
            return text
        finally:
            if os.path.exists(tmp_path):
                os.unlink(tmp_path)

    def speak(self, text: str):
        """Синтез речи (синхронно, для простоты)."""
        if not text:
            return
        logger.info(f"Говорю: {text[:100]}...")
        self.tts_engine.say(text)
        self.tts_engine.runAndWait()

    async def listen_once(self) -> str:
        """Одноразовое прослушивание (push-to-talk)."""
        audio = await self.record_audio(duration=6.0)
        transcript = await self.transcribe(audio)
        return transcript

    async def start_always_listening(
        self,
        on_transcript: Callable[[str], Awaitable[None]],
        silence_threshold: float = 0.01,
        min_speech_duration: float = 1.5,
    ):
        """
        Простая always-on прослушка с обнаружением речи (VAD-like).
        Для настоящего VAD рекомендуется использовать webrtcvad или Silero VAD.
        """
        self.on_transcript = on_transcript
        self.is_listening = True
        logger.info("Запущен always-on listening режим (персональный).")

        # Простая реализация: периодическая запись + проверка энергии
        while self.is_listening:
            try:
                audio = await self.record_audio(duration=3.0)
                energy = np.mean(np.abs(audio))

                if energy > silence_threshold:
                    # Есть речь — распознаём
                    transcript = await self.transcribe(audio)
                    if transcript and len(transcript) > 3:
                        if self.on_transcript:
                            await self.on_transcript(transcript)
                await asyncio.sleep(0.5)
            except Exception as e:
                logger.error(f"Ошибка в always_listening: {e}")
                await asyncio.sleep(1)

    def stop_listening(self):
        self.is_listening = False
        logger.info("Always-on listening остановлен.")

    def is_addressed_to_me(self, text: str, last_messages: list[str] = None) -> bool:
        """
        Простая эвристика определения, обращено ли к системе.
        В персональном сценарии можно сильно улучшить:
        - Анализ предыдущих реплик
        - Голосовая биометрия (кто говорит)
        - Контекст диалога
        """
        text_lower = text.lower().strip()

        # Если есть явные обращения — точно к ней
        if any(word in text_lower for word in ["лея", "леечка", "эй лея"]):
            return True

        # Если короткий запрос или продолжение разговора — вероятно к ней
        if len(text.split()) < 8 and last_messages:
            return True

        # Иначе — не к ней (разговор с кем-то другим)
        return False


# Пример использования (для теста)
async def example_usage():
    vi = VoiceInterface(stt_model_size="base")

    print("Говорите... (нажмите Enter для остановки)")
    # В реальном коде — интеграция с LeyaOS.perceive()

    async def handle_transcript(text: str):
        print(f"Получено: {text}")
        if vi.is_addressed_to_me(text):
            print("Обращение ко мне!")
            vi.speak("Поняла. Что нужно сделать?")
        else:
            print("Обращение не ко мне, игнорирую.")

    # Запуск always-on (в отдельной задаче)
    # asyncio.create_task(vi.start_always_listening(handle_transcript))

    # Или push-to-talk
    while True:
        input("Нажмите Enter для записи (или 'q' для выхода): ")
        cmd = input().strip().lower()
        if cmd == "q":
            break
        transcript = await vi.listen_once()
        await handle_transcript(transcript)


if __name__ == "__main__":
    asyncio.run(example_usage())
