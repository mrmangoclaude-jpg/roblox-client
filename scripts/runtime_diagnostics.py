"""Coalesced private snapshot writer for runtime diagnostics.

Callers must pass a fresh JSON-ready snapshot and relinquish it after submit;
this class deliberately does not deep-copy potentially large diagnostic data.
The worker only calls the private-file writer and never accesses a World, host,
or network object. At most one batch is active and one newer batch is pending.
"""
from __future__ import annotations

from pathlib import Path
import re
import threading
from typing import Any, Callable, Iterable

try:  # optional native validator (scripts/build_native_wire.py); the Python walk below is the reference implementation
    from _wire_native import valid_json as _native_valid_json  # ImportError too for a stale build without it
except ImportError:
    _native_valid_json = None


Batch = tuple[tuple[Path, Any], ...]
Writer = Callable[[Path, Any], None]


def _load_private_writer() -> Writer:
    """Import the existing secure writer only when the worker needs it."""
    from join_allocation import write_private
    return write_private


def _valid_json_value(value: Any, depth: int = 0) -> bool:
    """Reject host/runtime objects before they can cross into the worker."""
    if depth == 0 and _native_valid_json is not None:
        return _native_valid_json(value)
    if depth > 64:
        return False
    if value is None or type(value) in (str, int, float, bool):
        return True
    if type(value) in (list, tuple):
        return all(_valid_json_value(item, depth + 1) for item in value)
    if type(value) is dict:
        return all(type(key) is str and _valid_json_value(item, depth + 1)
                   for key, item in value.items())
    return False


class CoalescedPrivateSnapshotWriter:
    """Write last-status snapshots on one daemon worker.

    `submit(batch)` takes ownership of a batch of at most two `(Path, value)`
    pairs. The caller must not mutate the batch or its values after submission.
    A newer pending batch replaces the prior pending batch; an active batch is
    allowed to finish. `close(flush=True, timeout=2)` rejects new submissions,
    drains the latest pending batch, then waits at most `timeout` seconds and
    returns whether the worker exited. `error_type` exposes only the first
    exception class name, never its message or traceback.
    """

    def __init__(self, writer: Writer | None = None):
        self._writer = writer
        self._condition = threading.Condition()
        self._pending: Batch | None = None
        self._active = False
        self._closing = False
        self._failed = False
        self._error_type: str | None = None
        self._finished = threading.Event()
        self._thread = threading.Thread(
            target=self._run, name="runtime-diagnostics-writer", daemon=True
        )
        self._thread.start()

    @property
    def error_type(self) -> str | None:
        with self._condition:
            return self._error_type

    @property
    def failed(self) -> bool:
        with self._condition:
            return self._failed

    def submit(self, batch: Iterable[tuple[Path, Any]]) -> bool:
        """Queue a fresh snapshot batch without waiting for disk I/O."""
        # Bound to two destinations and take ownership of the outer iterable.
        if type(batch) not in (list, tuple):
            raise ValueError("A diagnostics batch must be a list or tuple")
        entries = tuple(batch)
        if not 1 <= len(entries) <= 2:
            raise ValueError("A diagnostics batch must contain one or two paths")
        normalized: list[tuple[Path, Any]] = []
        for entry in entries:
            if type(entry) not in (tuple, list) or len(entry) != 2:
                raise ValueError("Each diagnostics entry must be a (Path, JSON value) pair")
            path, value = entry
            if not isinstance(path, Path):
                raise ValueError("Diagnostics destinations must be pathlib.Path values")
            normalized.append((path, value))
        owned: Batch = tuple(normalized)
        with self._condition:
            if self._closing or self._failed:
                return False
            self._pending = owned
            self._condition.notify()
            return True

    def close(self, flush: bool = True, timeout: float = 2) -> bool:
        """Stop accepting work; optionally drain the newest queued snapshot."""
        if timeout < 0:
            raise ValueError("timeout must be nonnegative")
        with self._condition:
            self._closing = True
            if not flush:
                self._pending = None
            self._condition.notify_all()
        if threading.current_thread() is self._thread:
            return False
        self._thread.join(timeout)
        return not self._thread.is_alive()

    def _run(self) -> None:
        writer = self._writer
        try:
            while True:
                with self._condition:
                    while self._pending is None and not self._closing:
                        self._condition.wait()
                    if self._pending is None and self._closing:
                        return
                    batch = self._pending
                    self._pending = None
                    self._active = True
                try:
                    assert batch is not None
                    # Validate every nested value before writing any file from
                    # this batch. This traversal stays off the runtime caller.
                    if any(not _valid_json_value(value) for _, value in batch):
                        raise TypeError("Invalid diagnostics value")
                    if writer is None:
                        writer = _load_private_writer()
                    for path, value in batch:
                        writer(path, value)
                except Exception as error:
                    error_name = type(error).__name__
                    # Exception class names are usually built-in identifiers;
                    # constrain the public field even for unusual subclasses.
                    safe_name = error_name if re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,63}", error_name) else "Exception"
                    with self._condition:
                        if self._error_type is None:
                            self._error_type = safe_name
                        self._failed = True
                        self._closing = True
                        self._pending = None
                        self._active = False
                        self._condition.notify_all()
                    return
                with self._condition:
                    self._active = False
                    self._condition.notify_all()
        finally:
            self._finished.set()
