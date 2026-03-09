"""Gunicorn configuration for messenger service."""

from multiprocessing import cpu_count

bind = "0.0.0.0:8000"
workers = cpu_count() * 2 + 1
worker_class = "uvicorn.workers.UvicornWorker"

timeout = 120
graceful_timeout = 30
keepalive = 5

accesslog = "-"
errorlog = "-"
loglevel = "info"
