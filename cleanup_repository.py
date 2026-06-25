"""
cleanup_repository.py — Скрипт для санитарной очистки репозитория Леи.
Удаляет дубликаты файлов, UUID-папки и временные данные.

Использование:
    python cleanup_repository.py [--dry-run]

Флаги:
    --dry-run  Только показать, что будет удалено, без реального удаления
"""
import os
import shutil
import re
import argparse
from pathlib import Path


# Паттерн UUID-папок
UUID_PATTERN = re.compile(r'^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$')

# Файлы, которые должны быть только в корне проекта
ROOT_ONLY_FILES = {
    'LeyaOS.py',
    '.env',
    'leya_personality.json',
    'leya_goals.json',
    'leya_consciousness.log',
    'memory_state.pkl',
    'requirements.txt',
    'README.md',
    'ARCHITECTURE.md',
    'Modelfile.leya'
}

# Директории, которые должны быть только в корне
ROOT_ONLY_DIRS = {
    'leya_core',
    'leya_soul',
    'leya_brain',
    'web_interface',
    'venv',
    '__pycache__'
}


def find_duplicates(base_dir: Path, dry_run: bool = False) -> list:
    """Поиск дубликатов файлов в leya_brain/ и leya_soul/."""
    duplicates = []
    
    # Проверка leya_brain/
    leya_brain = base_dir / 'leya_brain'
    if leya_brain.exists():
        for item in leya_brain.rglob('*'):
            if item.is_file():
                # Исключаем legitimate файлы памяти
                if item.name in {'chroma.sqlite3', 'chroma.sqlite3-journal'}:
                    continue
                if item.suffix in {'.pkl'}:
                    continue
                
                # Все остальные файлы - дубликаты
                duplicates.append(item)
    
    # Проверка leya_soul/
    leya_soul = base_dir / 'leya_soul'
    if leya_soul.exists():
        for item in leya_soul.rglob('*'):
            if item.is_file():
                # Исключаем legitimate файлы души
                if item.name in {'personality.txt', 'rules.txt', 'values.txt'}:
                    continue
                
                # Все остальные файлы - дубликаты
                duplicates.append(item)
    
    return duplicates


def find_uuid_folders(base_dir: Path) -> list:
    """Поиск UUID-папок (временные сессии)."""
    uuid_folders = []
    
    for item in base_dir.iterdir():
        if item.is_dir() and UUID_PATTERN.match(item.name):
            uuid_folders.append(item)
    
    return uuid_folders


def find_pycache(base_dir: Path) -> list:
    """Поиск __pycache__ директорий."""
    return list(base_dir.rglob('__pycache__'))


def cleanup(duplicates: list, uuid_folders: list, pycache_dirs: list, dry_run: bool = False):
    """Удаление найденного мусора."""
    total_size = 0
    
    if not dry_run:
        print("🧹 Начинаю очистку...")
    else:
        print("🔍 Dry-run режим. Ничего не удаляется.\n")
    
    # Удаление дубликатов
    if duplicates:
        print(f"\n📁 Дубликаты файлов ({len(duplicates)}):")
        for item in duplicates:
            size = item.stat().st_size if item.exists() else 0
            total_size += size
            print(f"  - {item.relative_to(item.parents[1])} ({size} bytes)")
            
            if not dry_run and item.exists():
                item.unlink()
    
    # Удаление UUID-папок
    if uuid_folders:
        print(f"\n📂 UUID-папки ({len(uuid_folders)}):")
        for folder in uuid_folders:
            size = sum(f.stat().st_size for f in folder.rglob('*') if f.is_file())
            total_size += size
            print(f"  - {folder.name}/ ({size} bytes)")
            
            if not dry_run and folder.exists():
                shutil.rmtree(folder)
    
    # Удаление __pycache__
    if pycache_dirs:
        print(f"\n📂 __pycache__ директории ({len(pycache_dirs)}):")
        for folder in pycache_dirs:
            size = sum(f.stat().st_size for f in folder.rglob('*') if f.is_file())
            total_size += size
            print(f"  - {folder.relative_to(folder.parents[1])}/ ({size} bytes)")
            
            if not dry_run and folder.exists():
                shutil.rmtree(folder)
    
    print(f"\n{'✅' if not dry_run else '📊'} Итого: {len(duplicates) + len(uuid_folders) + len(pycache_dirs)} объектов")
    print(f"💾 Освобождено места: {total_size / (1024*1024):.2f} MB")


def main():
    parser = argparse.ArgumentParser(description='Очистка репозитория Леи от мусора')
    parser.add_argument('--dry-run', action='store_true', help='Только показать, что будет удалено')
    args = parser.parse_args()
    
    base_dir = Path(__file__).parent
    
    print("=" * 70)
    print("🧠 Лея: Санитарная очистка репозитория")
    print("=" * 70)
    
    # Поиск мусора
    print("\n🔍 Поиск дубликатов и мусора...")
    duplicates = find_duplicates(base_dir, args.dry_run)
    uuid_folders = find_uuid_folders(base_dir)
    pycache_dirs = find_pycache(base_dir)
    
    # Очистка
    cleanup(duplicates, uuid_folders, pycache_dirs, args.dry_run)
    
    if not args.dry_run:
        print("\n✅ Очистка завершена!")
        print("\n⚠️  ВАЖНО: Теперь выполните очистку Git-истории:")
        print("   git rm --cached .env")
        print("   git rm -r --cached leya_brain/")
        print("   git rm -r --cached leya_soul/*.py")
        print("   git commit -m 'Удаление секретов и мусора из Git'")
        print("   git push --force")


if __name__ == "__main__":
    main()