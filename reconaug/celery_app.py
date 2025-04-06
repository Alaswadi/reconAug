from celery import Celery

# Create Celery app
celery = Celery(
    'reconaug',
    broker='redis://redis:6379/0',
    backend='redis://redis:6379/0',
    include=['reconaug.tasks']
)

# Configure Celery
celery.conf.update(
    task_serializer='json',
    accept_content=['json'],
    result_serializer='json',
    timezone='UTC',
    enable_utc=True,
    worker_prefetch_multiplier=1,
    task_acks_late=True,
    task_track_started=True,
    task_time_limit=3600,  # 1 hour
    task_soft_time_limit=3540,  # 59 minutes
)

def create_celery_app(app=None):
    """Create and configure Celery app with Flask context"""
    if app:
        # Use Flask application context
        class ContextTask(celery.Task):
            def __call__(self, *args, **kwargs):
                with app.app_context():
                    return self.run(*args, **kwargs)
        
        celery.Task = ContextTask
    
    return celery
