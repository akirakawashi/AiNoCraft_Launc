"""Windows child-process environment helpers."""

from __future__ import annotations

import os
from collections.abc import Mapping


_PYTHON_ENV_EXACT = frozenset({"PYTHONHOME", "PYTHONPATH"})
_PYINSTALLER_ENV_PREFIXES = ("PYTHONNET", "_PYI", "PYI_", "PYINSTALLER", "_MEI")


def sanitize_child_env(env: Mapping[str, str]) -> dict[str, str]:
    """Remove frozen-Python internals before starting a child process."""
    clean = dict(env)
    for key in list(clean):
        upper = key.upper()
        if upper in _PYTHON_ENV_EXACT or any(
            upper.startswith(prefix) for prefix in _PYINSTALLER_ENV_PREFIXES
        ):
            clean.pop(key, None)

    for path_key in [key for key in clean if key.upper() == "PATH"]:
        clean[path_key] = os.pathsep.join(
            part for part in clean[path_key].split(os.pathsep) if part and "_MEI" not in part.upper()
        )
    return clean
