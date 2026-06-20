import asyncio
import os
from typing import List, Dict, Any, Optional
from Core.logger import log
from Core.state import LeyaState
from Core.event_bus import event_bus
from Perception.system_monitor import SystemMonitor
from Core.world_model import WorldModel



class PerceptionManager:
    """Чистый сенсор. НЕ принимает решений о гормонах."""
    
    def __init__(self, state: LeyaState):
        self.state = state
        self.monitor = SystemMonitor()
        self.world_model = WorldModel()
        self.last_known_window = "Unknown"
        self.last_active_file = None
        
        self.file_monitor = None
        try:
            from Perception.file_monitor import FileMonitor
            self.file_monitor = FileMonitor()
            log.info("📁 File Monitor attached")
        except ImportError:
            log.warning("⚠️ FileMonitor not available")
        
        log.info("👁️ Perception Manager initialized (Pure Sensor)")
    
    async def gather(self, budget: float) -> List[Dict[str, Any]]:
        sensory_data = []
        active_window = self.monitor.get_active_window()
        stats = self.monitor.get_system_stats()
        
        if active_window != self.last_known_window and active_window != "Unknown":
            self.last_known_window = active_window
            log.info("👁️ Environment changed", window=active_window)

            window_context = self.world_model.classify_window(active_window)

            sensory_data.append({
                "type": "proprioception",
                "content": f"Влад переключился на окно: '{active_window}'",
                "active_window": active_window,
                "window_category": window_context["category"],
                "window_description": window_context["description"],
                "is_self": window_context["is_self"],
                "importance": 0.8
            })
        
        if self.file_monitor and any(ide in active_window.lower() for ide in ["visual studio", "vs code", "pycharm"]):
            file_path = self._extract_file_from_window(active_window)
            if file_path and file_path != self.last_active_file:
                self.last_active_file = file_path
                self.file_monitor.update_active_file(file_path)
                await asyncio.sleep(0.3)
                
                fc = self.file_monitor.get_context()
                if fc["has_file"]:
                    sensory_data.append({
                        "type": "file_context",
                        "content": f"Влад работает с файлом: {fc['file_name']} ({fc['language']}, {fc['lines']} строк)",
                        "file_path": fc["file_path"],
                        "file_content": fc["content"],
                        "language": fc["language"],
                        "importance": 0.9
                    })
                    await event_bus.publish("file_changed", {
                        "name": fc["file_name"],
                        "language": fc["language"],
                        "path": fc["file_path"]
                    })
        
        sensory_data.append({
            "type": "system_telemetry",
            "cpu": stats["cpu"],
            "ram": stats["ram"],
            "active_window": active_window
        })
        
        return sensory_data
    
    def _extract_file_from_window(self, window_title: str) -> Optional[str]:
        if not self.file_monitor:
            return None
        parts = window_title.split(' - ')
        if len(parts) >= 1:
            potential_file = parts[0].strip()
            if os.path.exists(potential_file):
                return potential_file
            for watch_dir in self.file_monitor.watch_dirs:
                full_path = os.path.join(watch_dir, potential_file)
                if os.path.exists(full_path):
                    return full_path
        return None