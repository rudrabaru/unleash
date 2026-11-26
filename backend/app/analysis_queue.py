"""
One worker thread runs the session analyses, one at a time, from a bounded queue.

Before this, every submitted recording became a background task on the server's thread pool and
waited there for the analysis lock: a burst of uploads tied up the pool and stalled every other
request, result polling included. Now a submit reserves one of MAX_QUEUED_ANALYSES slots (the one
running plus those waiting); when none is free it is refused with 503 before the session is claimed,
so the person can simply send it again a little later.

Life cycle: the app's lifespan calls `start()` and `stop()`. The tests, which do not run the
lifespan, call `use_inline()`, which runs each job straight away in the caller's thread.
"""
import logging
import queue
import threading
from typing import Callable, Optional

logger = logging.getLogger("unleash.analysis_queue")

Job = Callable[[], None]


class AnalysisQueue:
    def __init__(self) -> None:
        self._jobs: "queue.Queue[Optional[Job]]" = queue.Queue()
        self._slots: Optional[threading.BoundedSemaphore] = None
        self._thread: Optional[threading.Thread] = None
        self._inline = False

    # --- life cycle -------------------------------------------------------------------------------

    def start(self, capacity: int) -> None:
        if self._thread is not None:
            return
        self._slots = threading.BoundedSemaphore(max(1, capacity))
        self._thread = threading.Thread(target=self._work, name="analysis-worker", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        """Ask the worker to stop after its current job. A waiting job is dropped; its session stays
        PROCESSING and is closed as RETRY by the next start-up."""
        thread = self._thread
        if thread is None:
            return
        self._jobs.put(None)
        thread.join(timeout)
        self._thread = None

    def use_inline(self) -> None:
        """Run every job at once in the caller's thread (tests)."""
        self._inline = True

    @property
    def running(self) -> bool:
        return self._inline or (self._thread is not None and self._thread.is_alive())

    # --- submitting -------------------------------------------------------------------------------

    def reserve(self) -> bool:
        """Take a slot for one job; False when the queue is full or the worker is not running."""
        if self._inline:
            return True
        if not self.running or self._slots is None:
            return False
        return self._slots.acquire(blocking=False)

    def release(self) -> None:
        """Give back a slot that was reserved but will not be used."""
        if not self._inline and self._slots is not None:
            self._slots.release()

    def submit(self, job: Job) -> None:
        """Run `job` on the worker. Call only after a successful `reserve()`; the slot is freed when it ends."""
        if self._inline:
            self._run(job)
            return
        self._jobs.put(job)

    # --- the worker -------------------------------------------------------------------------------

    def _work(self) -> None:
        while True:
            job = self._jobs.get()
            if job is None:
                return
            try:
                self._run(job)
            finally:
                if self._slots is not None:
                    self._slots.release()

    @staticmethod
    def _run(job: Job) -> None:
        try:
            job()
        except Exception:  # noqa: BLE001 - one failed analysis must never stop the worker
            logger.exception("An analysis job failed")


analysis_queue = AnalysisQueue()
