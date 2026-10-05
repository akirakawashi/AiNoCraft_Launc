"""Shared launcher state enums."""

from __future__ import annotations

from enum import StrEnum


class DownloadState(StrEnum):
    IDLE = "idle"
    DOWNLOADING = "downloading"
    EXTRACTING = "extracting"
    DONE = "done"
    ERROR = "error"
    CANCELLED = "cancelled"


class UpdateState(StrEnum):
    IDLE = "idle"
    CHECKING = "checking"
    AVAILABLE = "available"
    UP_TO_DATE = "up_to_date"
    DOWNLOADING = "downloading"
    APPLYING = "applying"
    DONE = "done"
    ERROR = "error"
    DISABLED = "disabled"
