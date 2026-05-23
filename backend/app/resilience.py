"""Shared resilience primitives — circuit breaker with exponential backoff.

Ported from URA Chatbot's resilience module. Each external dependency
(Qdrant, LLM, Sunbird) gets its own named breaker so one slow service
cannot exhaust the request pool via thundering-herd.

State machine: CLOSED → OPEN → HALF_OPEN → CLOSED (on success) or → OPEN (on failure)
"""

from __future__ import annotations

import logging
import threading
import time
from enum import Enum

logger = logging.getLogger("musawo.resilience")


class CircuitState(Enum):
    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half_open"


class CircuitBreaker:
    """Thread-safe circuit breaker with exponential back-off.

    - CLOSED: requests flow normally; consecutive failures tracked.
    - OPEN: requests rejected immediately; waits *reset_timeout*
      (doubles on each HALF_OPEN→OPEN trip, capped at *max_timeout*).
    - HALF_OPEN: one test request allowed; success → CLOSED, failure → OPEN.
    """

    def __init__(
        self,
        name: str = "breaker",
        failure_threshold: int = 3,
        reset_timeout: float = 10.0,
        max_timeout: float = 300.0,
    ) -> None:
        self.name = name
        self.failure_threshold = failure_threshold
        self._base_timeout = reset_timeout
        self._max_timeout = max_timeout
        self._failures = 0
        self._state = CircuitState.CLOSED
        self._opened_at: float = 0.0
        self._current_timeout = reset_timeout
        self._lock = threading.Lock()

    @property
    def state(self) -> CircuitState:
        with self._lock:
            if (
                self._state == CircuitState.OPEN
                and time.monotonic() - self._opened_at >= self._current_timeout
            ):
                self._state = CircuitState.HALF_OPEN
                logger.info("Circuit breaker %s → HALF_OPEN (testing)", self.name)
            return self._state

    @property
    def is_open(self) -> bool:
        """Legacy property for backward compatibility."""
        return self.state == CircuitState.OPEN

    def allow_request(self) -> bool:
        """Return True if the request should proceed."""
        s = self.state
        return s in (CircuitState.CLOSED, CircuitState.HALF_OPEN)

    def record_success(self) -> None:
        """Call after a successful operation."""
        with self._lock:
            if self._state in (CircuitState.HALF_OPEN, CircuitState.OPEN):
                logger.info("Circuit breaker %s → CLOSED (recovered)", self.name)
            self._failures = 0
            self._state = CircuitState.CLOSED
            self._current_timeout = self._base_timeout

    def record_failure(self) -> None:
        """Call after a failed operation."""
        with self._lock:
            self._failures += 1
            was_half_open = self._state == CircuitState.HALF_OPEN
            if self._failures >= self.failure_threshold or was_half_open:
                self._state = CircuitState.OPEN
                self._opened_at = time.monotonic()
                # Exponential backoff only from HALF_OPEN→OPEN (not first trip)
                if was_half_open:
                    self._current_timeout = min(
                        self._current_timeout * 2, self._max_timeout
                    )
                logger.warning(
                    "Circuit breaker %s → OPEN (failures=%d, backoff=%.0fs)",
                    self.name,
                    self._failures,
                    self._current_timeout,
                )
