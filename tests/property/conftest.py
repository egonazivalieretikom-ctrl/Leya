"""
Настройки hypothesis для property-based тестов.
"""
from hypothesis import settings, HealthCheck

# Увеличиваем таймаут для property-based тестов
# (они могут генерировать тысячи примеров)
settings.register_profile(
    "ci",
    max_examples=100,
    deadline=2000,
    suppress_health_check=[HealthCheck.too_slow],
)

settings.register_profile(
    "dev",
    max_examples=20,
    deadline=500,
)

settings.register_profile(
    " thorough",
    max_examples=500,
    deadline=5000,
    suppress_health_check=[HealthCheck.too_slow, HealthCheck.data_too_large],
)

# По умолчанию используем dev профиль
settings.load_profile("dev")