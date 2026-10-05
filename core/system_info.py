"""Host system capabilities used for settings bounds."""

from __future__ import annotations

import ctypes
import os
from functools import lru_cache

from config import RAM_DEFAULT_GB, RAM_MIN_GB


_FALLBACK_TOTAL_RAM_GB = 16
_RAM_HEADROOM_GB = 2
_RAM_HARD_CAP_GB = 32


@lru_cache(maxsize=1)
def total_ram_gb() -> int:
    """Return the machine's total physical RAM in whole gigabytes."""
    try:
        if os.name == "nt":

            class _MemoryStatusEx(ctypes.Structure):
                _fields_ = [
                    ("dwLength", ctypes.c_uint32),
                    ("dwMemoryLoad", ctypes.c_uint32),
                    ("ullTotalPhys", ctypes.c_uint64),
                    ("ullAvailPhys", ctypes.c_uint64),
                    ("ullTotalPageFile", ctypes.c_uint64),
                    ("ullAvailPageFile", ctypes.c_uint64),
                    ("ullTotalVirtual", ctypes.c_uint64),
                    ("ullAvailVirtual", ctypes.c_uint64),
                    ("ullAvailExtendedVirtual", ctypes.c_uint64),
                ]

            status = _MemoryStatusEx()
            status.dwLength = ctypes.sizeof(_MemoryStatusEx)
            if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
                return max(1, round(status.ullTotalPhys / 1_073_741_824))
        else:
            pages = os.sysconf("SC_PHYS_PAGES")
            page_size = os.sysconf("SC_PAGE_SIZE")
            return max(1, round(pages * page_size / 1_073_741_824))
    except Exception:
        pass
    return _FALLBACK_TOTAL_RAM_GB


def ram_limits() -> dict[str, int]:
    """Return per-machine RAM slider bounds and the recommended default."""
    total = total_ram_gb()
    ram_max = min(_RAM_HARD_CAP_GB, max(RAM_MIN_GB + 2, total - _RAM_HEADROOM_GB))
    ram_default = min(ram_max, max(RAM_MIN_GB, RAM_DEFAULT_GB))
    return {
        "ram_min_gb": RAM_MIN_GB,
        "ram_max_gb": ram_max,
        "ram_default_gb": ram_default,
        "total_ram_gb": total,
    }
