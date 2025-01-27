"""Celery configuration module"""

# Broker settings
broker_url = 'redis://localhost:6379/0'
result_backend = 'redis://localhost:6379/0'
broker_connection_retry_on_startup = True

# Task settings
task_serializer = 'json'
result_serializer = 'json'
accept_content = ['json']
timezone = 'UTC'
enable_utc = True

# Task execution settings
task_acks_late = True  # Tasks are acknowledged after execution
task_reject_on_worker_lost = True  # Tasks are rejected if worker is lost
worker_prefetch_multiplier = 1  # One task at a time per worker

# Task timeouts
task_soft_time_limit = 600  # 10 minutes
task_time_limit = 1200  # 20 minutes

# Pool settings
worker_pool = 'prefork'
worker_concurrency = 2  # Number of worker processes

# Logging
worker_redirect_stdouts = False
worker_redirect_stdouts_level = 'INFO'
