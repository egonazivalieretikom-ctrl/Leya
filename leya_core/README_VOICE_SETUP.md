# Готовый голосовой режим для LeyaOS (Персональный ИИ)

## Что ты получаешь
- Голосовой ввод (микрофон)
- Голосовой вывод (озвучивание ответов)
- Автоматическое понимание, обращены ли слова именно к Лее (без "Лея," в начале)
- Полная совместимость с существующим кодом LeyaOS

## Файлы, которые нужно скачать и положить

Скачай эти два файла и положи их в свою папку проекта:

1. `leya_core/voice_interface.py`
2. `leya_core/voice_environment.py`

(Они уже лежат в папке artifacts/leya_core/)

## Самая простая установка (3 шага)

### Шаг 1: Установи зависимости
Открой PowerShell или Командную строку и выполни:

```powershell
pip install faster-whisper pyttsx3 sounddevice numpy soundfile
```

### Шаг 2: Добавь импорт в LeyaOS.py

Открой файл `LeyaOS.py`

Найди строку:
```python
from leya_core.environment import CLIEnvironment
```

**Сразу после неё** вставь:
```python
from leya_core.voice_environment import VoiceEnvironment
```

### Шаг 3: Включи голосовой режим

В том же файле `LeyaOS.py` найди метод `__init__` и замени блок создания окружения.

**Найди этот код:**
```python
        if use_web:
            self.env = WebEnvironment(leya_os=self)
            logger.info("Используется веб-интерфейс")
        else:
            self.env = CLIEnvironment(leya_os=self)
            logger.info("Используется CLI-интерфейс")
```

**Замени его на:**
```python
        if use_web:
            self.env = WebEnvironment(leya_os=self)
            logger.info("Используется веб-интерфейс")
        else:
            self.env = VoiceEnvironment(leya_os=self, use_voice=True)
            logger.info("Используется голосовой интерфейс (персональный режим)")
```

### Шаг 4: Запуск

Запусти программу с параметром `use_web=False`:

```python
LeyaOS(use_web=False)
```

Или если запускаешь файл напрямую, добавь в конец файла:

```python
if __name__ == "__main__":
    asyncio.run(LeyaOS(use_web=False).run())
```

## Готово!

Теперь Лея будет:
- Слушать тебя через микрофон
- Понимать, когда ты обращаешься именно к ней
- Отвечать голосом
- Игнорировать речь, если ты разговариваешь с кем-то другим

## Дополнительно (опционально)

Если хочешь, чтобы Лея постоянно слушала в фоне (always-on), в методе `run()` после создания `background_tasks` добавь:

```python
        if isinstance(self.env, VoiceEnvironment):
            background_tasks.append(
                asyncio.create_task(self.env.run_voice_loop(), name="voice_listener")
            )
```

## Важные замечания

- Работает только при `use_web=False`
- Для лучшего качества речи можно позже поменять модель в `VoiceInterface` (stt_model_size="small")
- Все инструменты (поиск, выполнение кода и т.д.) продолжают работать как раньше

Если что-то не заработает — пришли лог, я помогу исправить.