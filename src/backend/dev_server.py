#!/usr/bin/env python3
"""
Development server with auto-reload functionality using watchdog.
"""

import os
import sys
import time
import subprocess
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

class AppReloader(FileSystemEventHandler):
    def __init__(self):
        self.process = None
        self.restart_app()
    
    def on_modified(self, event):
        if event.is_directory:
            return
        
        if event.src_path.endswith('.py'):
            print(f"Detected change in {event.src_path}")
            self.restart_app()
    
    def restart_app(self):
        if self.process:
            print("Stopping application...")
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()
        
        print("Starting application...")
        self.process = subprocess.Popen([sys.executable, "app.py"])
    
    def stop(self):
        if self.process:
            self.process.terminate()

def main():
    # Watch the current directory
    watch_path = Path(__file__).parent
    
    event_handler = AppReloader()
    observer = Observer()
    observer.schedule(event_handler, str(watch_path), recursive=True)
    observer.start()
    
    print(f"Watching {watch_path} for changes...")
    print("Press Ctrl+C to stop")
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("Stopping...")
        event_handler.stop()
        observer.stop()
    
    observer.join()

if __name__ == "__main__":
    main()
