import os
import time
from pathlib import Path
from typing import Optional, Dict
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler
from Core.logger import log

class FileMonitor:
    """
    Отслеживает изменения в файлах, которые открывает Владислав.
    Читает содержимое и анализирует код.
    """
    
    def __init__(self, watch_dirs: list = None):
        self.watch_dirs = watch_dirs or [
            "F:\\LeyaOS",  # Твой проект
            # Можно добавить другие рабочие директории
        ]
        self.current_file: Optional[str] = None
        self.file_content: str = ""
        self.last_modified: float = 0
        self.observer = Observer()
        
        # Запускаем наблюдателей для каждой директории
        for dir_path in self.watch_dirs:
            if os.path.exists(dir_path):
                handler = CodeFileHandler(self)
                self.observer.schedule(handler, dir_path, recursive=True)
        
        self.observer.start()
        log.info("📁 File Monitor started", watch_dirs=self.watch_dirs)
    
    def update_active_file(self, file_path: str):
        """Обновляет текущий активный файл"""
        if file_path != self.current_file:
            self.current_file = file_path
            self._read_file()
            log.info("📄 Active file changed", file=file_path)
    
    def _read_file(self):
        """Читает содержимое файла"""
        if not self.current_file or not os.path.exists(self.current_file):
            return
        
        try:
            with open(self.current_file, 'r', encoding='utf-8') as f:
                content = f.read()
                
            # Ограничиваем размер (не больше 10KB для анализа)
            if len(content) > 10000:
                content = content[:10000] + "\n... [файл обрезан] ..."
            
            self.file_content = content
            self.last_modified = time.time()
        except Exception as e:
            log.error("Failed to read file", error=str(e), file=self.current_file)
    
    def get_context(self) -> Dict:
        """Возвращает контекст текущего файла для LLM"""
        if not self.current_file:
            return {"has_file": False}
        
        return {
            "has_file": True,
            "file_path": self.current_file,
            "file_name": os.path.basename(self.current_file),
            "content": self.file_content,
            "language": self._detect_language(),
            "lines": len(self.file_content.split('\n'))
        }
    
    def _detect_language(self) -> str:
        """Определяет язык программирования по расширению"""
        if not self.current_file:
            return "unknown"
        
        ext = os.path.splitext(self.current_file)[1].lower()
        lang_map = {
            '.py': 'Python',
            '.js': 'JavaScript',
            '.ts': 'TypeScript',
            '.html': 'HTML',
            '.css': 'CSS',
            '.json': 'JSON',
            '.md': 'Markdown',
            '.txt': 'Text',
        }
        return lang_map.get(ext, 'Unknown')
    
    def stop(self):
        self.observer.stop()
        self.observer.join()


class CodeFileHandler(FileSystemEventHandler):
    """Обработчик изменений файлов"""
    
    def __init__(self, monitor: FileMonitor):
        self.monitor = monitor
    
    def on_modified(self, event):
        if event.is_directory:
            return
        
        # Реагируем только на кодовые файлы
        if any(event.src_path.endswith(ext) for ext in ['.py', '.js', '.ts', '.html', '.css', '.json', '.md']):
            if event.src_path == self.monitor.current_file:
                self.monitor._read_file()
                log.debug("📝 File content updated", file=event.src_path)