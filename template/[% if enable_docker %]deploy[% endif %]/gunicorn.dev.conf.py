"""Connect Gunicorn's development reloader to Uvicorn's graceful shutdown."""

import os
import signal

from gunicorn.workers.base import Worker


def worker_int(worker: Worker) -> None:
    """Stop the async server when Gunicorn's reload thread requests an exit."""
    os.kill(worker.pid, signal.SIGTERM)
