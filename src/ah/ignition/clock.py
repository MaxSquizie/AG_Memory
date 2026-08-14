from __future__ import annotations

from dataclasses import dataclass
from threading import Event, Lock, RLock, Thread
from time import monotonic, sleep
from typing import Callable

from .engine import IgnitionEngine, TickResult


@dataclass(frozen=True, slots=True)
class ClockStats:
    running: bool
    ticks_executed: int
    last_tick_duration_seconds: float
    last_error: str | None


class IgnitionClock:
    """Background driver for continuous engine ticks.

    IgnitionEngine owns all cognitive tick semantics. This class only supplies the
    wall-clock cadence. If the process is stopped, memory time stops as required by
    the architecture. `tick()` remains usable directly for deterministic tests.
    """

    def __init__(
        self,
        engine: IgnitionEngine,
        interval_seconds: float,
        on_tick: Callable[[TickResult], None] | None = None,
        execution_lock: RLock | None = None,
    ) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be > 0")
        self.engine = engine
        self.interval_seconds = float(interval_seconds)
        self.on_tick = on_tick
        self.execution_lock = execution_lock
        self._stop = Event()
        self._thread: Thread | None = None
        self._state_lock = Lock()
        self._ticks_executed = 0
        self._last_duration = 0.0
        self._last_error: str | None = None
        self._listeners: list[Callable[[TickResult], None]] = []

    @property
    def running(self) -> bool:
        thread = self._thread
        return thread is not None and thread.is_alive() and not self._stop.is_set()

    def set_interval(self, interval_seconds: float) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be > 0")
        with self._state_lock:
            self.interval_seconds = float(interval_seconds)

    def add_listener(self, callback: Callable[[TickResult], None]) -> None:
        with self._state_lock:
            if callback not in self._listeners:
                self._listeners.append(callback)

    def remove_listener(self, callback: Callable[[TickResult], None]) -> None:
        with self._state_lock:
            if callback in self._listeners:
                self._listeners.remove(callback)

    def start(self) -> None:
        if self.running:
            return
        self._stop.clear()
        self._thread = Thread(target=self._run, name="AH-IgnitionClock", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 2.0) -> None:
        self._stop.set()
        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=timeout)
        self._thread = None

    def stats(self) -> ClockStats:
        with self._state_lock:
            return ClockStats(
                running=self.running,
                ticks_executed=self._ticks_executed,
                last_tick_duration_seconds=self._last_duration,
                last_error=self._last_error,
            )

    def _run(self) -> None:
        deadline = monotonic()
        while not self._stop.is_set():
            with self._state_lock:
                interval = self.interval_seconds
            deadline += interval
            started = monotonic()
            try:
                if self.execution_lock is None:
                    result = self.engine.tick()
                else:
                    with self.execution_lock:
                        result = self.engine.tick()
                if self.on_tick is not None:
                    self.on_tick(result)
                with self._state_lock:
                    listeners = tuple(self._listeners)
                for callback in listeners:
                    callback(result)
                error = None
            except Exception as exc:  # keep the clock alive; diagnostics exposes failure
                error = f"{type(exc).__name__}: {exc}"
            duration = monotonic() - started
            with self._state_lock:
                self._ticks_executed += 1
                self._last_duration = duration
                self._last_error = error
            delay = deadline - monotonic()
            if delay > 0:
                self._stop.wait(delay)
            else:
                # We are behind schedule. Do not spin in a catch-up storm; reset the
                # next deadline from now. Cognitive time is tick-count based, not wall
                # time based, so skipped wall-clock slots do not create hidden ticks.
                deadline = monotonic()
