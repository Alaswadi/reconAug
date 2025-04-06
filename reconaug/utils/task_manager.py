import time
import uuid
import threading
from collections import defaultdict

class TaskManager:
    def __init__(self):
        self.tasks = {}
        self.task_lock = threading.Lock()
    
    def create_task(self, domain):
        """Create a new task for domain scanning"""
        task_id = str(uuid.uuid4())
        with self.task_lock:
            self.tasks[task_id] = {
                'domain': domain,
                'status': 'pending',
                'progress': 0,
                'message': 'Initializing...',
                'timestamp': time.time(),
                'complete': False
            }
        return task_id
    
    def update_task(self, task_id, status=None, progress=None, message=None, complete=None):
        """Update task status"""
        with self.task_lock:
            if task_id in self.tasks:
                if status is not None:
                    self.tasks[task_id]['status'] = status
                if progress is not None:
                    self.tasks[task_id]['progress'] = progress
                if message is not None:
                    self.tasks[task_id]['message'] = message
                if complete is not None:
                    self.tasks[task_id]['complete'] = complete
                self.tasks[task_id]['timestamp'] = time.time()
    
    def get_task(self, task_id):
        """Get task status"""
        with self.task_lock:
            return self.tasks.get(task_id, {}).copy()
    
    def clean_old_tasks(self, max_age=3600):
        """Clean up old tasks (older than max_age seconds)"""
        current_time = time.time()
        with self.task_lock:
            for task_id in list(self.tasks.keys()):
                if current_time - self.tasks[task_id]['timestamp'] > max_age:
                    del self.tasks[task_id]

# Create a global task manager instance
task_manager = TaskManager()

# Start a background thread to clean up old tasks
def start_cleanup_thread():
    def cleanup_loop():
        while True:
            task_manager.clean_old_tasks()
            time.sleep(300)  # Clean up every 5 minutes
    
    cleanup_thread = threading.Thread(target=cleanup_loop, daemon=True)
    cleanup_thread.start()

# Start the cleanup thread when the module is imported
start_cleanup_thread()
