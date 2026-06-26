# run_tests.ps1
Write-Host "🧪 Запуск тестов..." -ForegroundColor Cyan
pytest tests/ --cov=leya_core --cov-report=term-missing -v
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "`n🔍 Линтинг..." -ForegroundColor Cyan
ruff check leya_core/ LeyaOS.py tests/
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "`n🎨 Форматирование..." -ForegroundColor Cyan
black --check leya_core/ LeyaOS.py tests/
if ($LASTEXITCODE -ne 0) { exit 1 }

Write-Host "`n✅ Все проверки пройдены!" -ForegroundColor Green