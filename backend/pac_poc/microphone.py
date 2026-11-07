from __future__ import annotations

from queue import Empty, Full, Queue
from threading import Lock


class AudioBackpressure(RuntimeError):
    """The live audio consumer fell behind; the session must stop explicitly."""


class MicrophoneFrameBuffer:
    """Bounded in-memory buffer that discards queued audio when closed."""

    def __init__(self, *, max_frames: int) -> None:
        if max_frames < 1:
            raise ValueError("max_frames must be positive")
        self._queue: Queue[bytes] = Queue(maxsize=max_frames)
        self._lock = Lock()
        self._closed = False

    @property
    def closed(self) -> bool:
        with self._lock:
            return self._closed

    @property
    def queued_frames(self) -> int:
        return self._queue.qsize()

    def offer(self, frame: bytes) -> None:
        if not frame:
            raise ValueError("microphone frame cannot be empty")
        with self._lock:
            if self._closed:
                raise RuntimeError("microphone buffer is closed")
            try:
                self._queue.put_nowait(frame)
            except Full as exc:
                self._closed = True
                self._discard_queued_frames()
                raise AudioBackpressure("microphone frame queue is full") from exc

    def take(self, timeout: float) -> bytes:
        return self._queue.get(timeout=timeout)

    def take_nowait(self) -> bytes:
        return self._queue.get_nowait()

    def close(self) -> None:
        with self._lock:
            self._closed = True
            self._discard_queued_frames()

    def _discard_queued_frames(self) -> None:
        while True:
            try:
                self._queue.get_nowait()
            except Empty:
                return
