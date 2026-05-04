"""Build helper for launcher release."""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
VERSION_JSON = ROOT / "version.json"
SPEC_FILE = ROOT / "launcher.spec"


def read_version_from_json(path: Path = VERSION_JSON) -> str:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8-sig"))
    version = str(data.get("version", "")).strip()
    if not version:
        raise ValueError(f"{path} must contain non-empty 'version'")
    if not re.fullmatch(r"\d+(?:\.\d+)*", version):
        raise ValueError(f"Unsupported version format: {version!r}")
    return version


def build_exe() -> None:
    version = read_version_from_json()
    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(SPEC_FILE)]
    print(f"Version: {version}")
    print("Running:", " ".join(cmd))
    subprocess.run(cmd, cwd=str(ROOT), check=True)
    print(f"Build complete. Version: {version}")


def main() -> int:
    if len(sys.argv) != 2 or sys.argv[1] != "build_exe":
        print("Usage: python _build_helper.py build_exe")
        return 1

    build_exe()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
