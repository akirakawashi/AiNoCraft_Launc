"""Shared streaming HTTP download support."""

from __future__ import annotations

import hashlib
import time
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Event


@dataclass(frozen=True, slots=True)
class DownloadProgress:
    downloaded_bytes: int
    total_bytes: int
    speed_bytes_per_sec: float

    @property
    def percent(self) -> float:
        return self.downloaded_bytes / self.total_bytes * 100 if self.total_bytes else 0.0


@dataclass(frozen=True, slots=True)
class DownloadResult:
    downloaded_bytes: int
    total_bytes: int
    sha256: str
    cancelled: bool


def _content_length(headers: object) -> int:
    try:
        value = headers.get("content-length", 0)  # type: ignore[attr-defined]
        return max(int(value or 0), 0)
    except (AttributeError, TypeError, ValueError):
        return 0


def download_to_file(
    url: str,
    destination: Path,
    *,
    user_agent: str,
    timeout: float,
    chunk_size: int,
    progress_interval: float,
    on_progress: Callable[[DownloadProgress], None] | None = None,
    cancel_event: Event | None = None,
    max_bytes: int | None = None,
) -> DownloadResult:
    """Stream an HTTP response to disk and return transfer metadata.

    ``max_bytes`` is enforced both against Content-Length and against bytes
    actually received, because the header may be absent or dishonest.
    """
    if max_bytes is not None and max_bytes <= 0:
        raise ValueError("Лимит размера загрузки должен быть положительным")
    destination.parent.mkdir(parents=True, exist_ok=True)
    request = urllib.request.Request(url, headers={"User-Agent": user_agent})
    downloaded = 0
    total_bytes = 0
    hasher = hashlib.sha256()

    with urllib.request.urlopen(request, timeout=timeout) as response:
        total_bytes = _content_length(response.headers)
        if max_bytes is not None and total_bytes > max_bytes:
            raise ValueError(
                f"Размер загрузки превышает допустимый лимит ({max_bytes} байт)"
            )
        if on_progress:
            on_progress(DownloadProgress(0, total_bytes, 0.0))

        last_bytes = 0
        last_time = time.monotonic()
        with destination.open("wb") as file:
            while not (cancel_event and cancel_event.is_set()):
                chunk = response.read(chunk_size)
                if not chunk:
                    break
                if max_bytes is not None and downloaded + len(chunk) > max_bytes:
                    raise ValueError(
                        f"Размер загрузки превышает допустимый лимит ({max_bytes} байт)"
                    )
                file.write(chunk)
                hasher.update(chunk)
                downloaded += len(chunk)

                now = time.monotonic()
                elapsed = now - last_time
                if on_progress and elapsed > 0 and elapsed >= progress_interval:
                    on_progress(
                        DownloadProgress(
                            downloaded,
                            total_bytes,
                            (downloaded - last_bytes) / elapsed,
                        )
                    )
                    last_time = now
                    last_bytes = downloaded

    return DownloadResult(
        downloaded_bytes=downloaded,
        total_bytes=total_bytes,
        sha256=hasher.hexdigest(),
        cancelled=bool(cancel_event and cancel_event.is_set()),
    )
