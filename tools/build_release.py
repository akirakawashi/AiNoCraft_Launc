"""Build the launcher executable and bootstrapper manifest."""

from __future__ import annotations

import argparse
import hashlib
import json
import shutil
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
APP_NAME = "AiNoCraftLauncher"
EXE_NAME = f"{APP_NAME}.exe"
DEFAULT_RELEASE_DIR = ROOT / "release" / APP_NAME
DEFAULT_MANIFEST_FILE = ROOT / "release" / "manifest.json"
BUILD_METADATA_FILE = ROOT / "build_metadata.json"


@dataclass(frozen=True)
class ReleaseFile:
    """File metadata stored in the bootstrapper manifest."""

    path: str
    size: int
    sha256: str
    executable: bool

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "path": self.path,
            "size": self.size,
            "sha256": self.sha256,
        }
        if self.executable:
            payload["executable"] = True
        return payload


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(prog="build_release")
    parser.add_argument("--version", required=True, help="Launcher release version stored in manifest.")
    parser.add_argument("--base-url", required=True, help="Public URL prefix for release files.")
    parser.add_argument("--channel", default="stable", help="Launcher update channel.")
    parser.add_argument("--entrypoint", default=EXE_NAME, help="Entrypoint path inside the release directory.")
    parser.add_argument("--release-dir", type=Path, default=DEFAULT_RELEASE_DIR, help="Output release directory.")
    parser.add_argument("--manifest", type=Path, default=DEFAULT_MANIFEST_FILE, help="Output manifest file.")
    parser.add_argument("--skip-pyinstaller", action="store_true", help="Use an existing dist executable.")
    return parser


def main(argv: list[str] | None = None) -> int:
    """Build the executable, copy it to release/, and write manifest.json."""
    args = build_parser().parse_args(argv)
    release_dir = args.release_dir.expanduser().resolve()
    manifest_file = args.manifest.expanduser().resolve()

    write_build_metadata(args.version)

    if not args.skip_pyinstaller:
        run_pyinstaller()

    prepare_release_dir(release_dir)
    copy_executable(release_dir)
    manifest = build_manifest(
        release_dir=release_dir,
        version=args.version,
        channel=args.channel,
        entrypoint=args.entrypoint,
        base_url=args.base_url,
    )
    write_manifest(manifest, manifest_file)

    print(f"release dir: {release_dir}")
    print(f"manifest: {manifest_file}")
    print(f"version: {args.version}")
    return 0


def run_pyinstaller() -> None:
    """Build AiNoCraftLauncher.exe with PyInstaller."""
    spec_file = ROOT / "launcher.spec"
    if not spec_file.exists():
        raise FileNotFoundError(f"PyInstaller spec was not found: {spec_file}")

    cmd = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean", str(spec_file)]
    subprocess.run(cmd, cwd=str(ROOT), check=True)


def write_build_metadata(version: str) -> None:
    """Write metadata bundled into the PyInstaller executable."""
    BUILD_METADATA_FILE.write_text(
        json.dumps(
            {
                "version": version,
                "generated_at": datetime.now(timezone.utc).isoformat(),
            },
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def prepare_release_dir(release_dir: Path) -> None:
    """Recreate the clean release directory under repo release/."""
    allowed_root = (ROOT / "release").resolve()
    if not is_relative_to(release_dir, allowed_root):
        raise ValueError(f"release directory must stay under {allowed_root}: {release_dir}")

    shutil.rmtree(release_dir, ignore_errors=True)
    release_dir.mkdir(parents=True, exist_ok=True)


def copy_executable(release_dir: Path) -> None:
    """Copy the built executable into the release directory."""
    source = ROOT / "dist" / EXE_NAME
    if not source.exists():
        raise FileNotFoundError(f"built executable was not found: {source}")

    shutil.copy2(source, release_dir / EXE_NAME)


def build_manifest(
    *,
    release_dir: Path,
    version: str,
    channel: str,
    entrypoint: str,
    base_url: str,
) -> dict[str, object]:
    """Build a schema-1 bootstrapper manifest."""
    files = tuple(build_release_file(path, release_dir) for path in sorted(release_dir.rglob("*")) if path.is_file())
    if not files:
        raise ValueError(f"release directory contains no files: {release_dir}")

    return {
        "schema": 1,
        "app": APP_NAME,
        "channel": channel,
        "version": version,
        "entrypoint": entrypoint.replace("\\", "/"),
        "files": [file.to_dict() for file in files],
        "delete": [],
        "base_url": ensure_url_dir(base_url),
        "prune": True,
        "metadata": {
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "file_count": len(files),
        },
    }


def build_release_file(path: Path, release_dir: Path) -> ReleaseFile:
    """Build manifest metadata for one release file."""
    rel_path = path.relative_to(release_dir).as_posix()
    return ReleaseFile(
        path=rel_path,
        size=path.stat().st_size,
        sha256=sha256_file(path),
        executable=path.suffix.lower() == ".exe",
    )


def write_manifest(manifest: dict[str, object], manifest_file: Path) -> None:
    """Write manifest JSON with stable formatting."""
    manifest_file.parent.mkdir(parents=True, exist_ok=True)
    manifest_file.write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def sha256_file(path: Path) -> str:
    """Return a file SHA-256 digest."""
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_url_dir(url: str) -> str:
    """Return URL with a trailing slash."""
    stripped = url.strip()
    return stripped if stripped.endswith("/") else stripped + "/"


def is_relative_to(path: Path, root: Path) -> bool:
    """Backport Path.is_relative_to for older Python habits."""
    try:
        path.resolve().relative_to(root.resolve())
    except ValueError:
        return False
    return True


if __name__ == "__main__":
    raise SystemExit(main())
