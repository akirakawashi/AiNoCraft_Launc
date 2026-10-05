"""Publish a launcher release and stable manifest to S3-compatible storage."""

from __future__ import annotations

import argparse
import mimetypes
import os
from pathlib import Path
from urllib.parse import urlparse

from minio import Minio


DEFAULT_BUCKET = "launcher"
DEFAULT_RELEASE_PREFIX = "releases"
DEFAULT_STABLE_MANIFEST_PATH = "stable/manifest.json"


def build_parser() -> argparse.ArgumentParser:
    """Create the CLI parser."""
    parser = argparse.ArgumentParser(prog="publish_release")
    parser.add_argument("--endpoint", default=os.environ.get("S3_STORAGE_ENDPOINT", ""))
    parser.add_argument("--access-key", default=os.environ.get("S3_STORAGE_ACCESS_KEY", ""))
    parser.add_argument("--secret-key", default=os.environ.get("S3_STORAGE_SECRET_KEY", ""))
    parser.add_argument("--secure", default=os.environ.get("S3_STORAGE_SECURE", ""))
    parser.add_argument("--bucket", default=os.environ.get("LAUNCHER_BUCKET_NAME", DEFAULT_BUCKET))
    parser.add_argument("--release-dir", type=Path, required=True)
    parser.add_argument("--release-prefix", default=DEFAULT_RELEASE_PREFIX)
    parser.add_argument("--manifest", type=Path, required=True)
    parser.add_argument("--stable-manifest-path", default=DEFAULT_STABLE_MANIFEST_PATH)
    return parser


def main(argv: list[str] | None = None) -> int:
    """Upload release files first and stable manifest last."""
    args = build_parser().parse_args(argv)
    endpoint, secure = resolve_endpoint(args.endpoint, args.secure)
    validate_required("S3 endpoint", endpoint)
    validate_required("S3 access key", args.access_key)
    validate_required("S3 secret key", args.secret_key)

    release_dir = args.release_dir.expanduser().resolve()
    manifest_file = args.manifest.expanduser().resolve()
    if not release_dir.is_dir():
        raise FileNotFoundError(f"release directory was not found: {release_dir}")
    if not manifest_file.is_file():
        raise FileNotFoundError(f"manifest file was not found: {manifest_file}")

    client = Minio(endpoint, access_key=args.access_key, secret_key=args.secret_key, secure=secure)
    if not client.bucket_exists(args.bucket):
        raise RuntimeError(f"S3 bucket does not exist: {args.bucket}. Start backend once to initialize buckets.")

    release_prefix = normalize_object_path(args.release_prefix)
    stable_manifest_path = normalize_object_path(args.stable_manifest_path)

    for path in sorted(release_dir.rglob("*")):
        if not path.is_file():
            continue
        rel_path = path.relative_to(release_dir).as_posix()
        object_name = f"{release_prefix}/{rel_path}"
        upload_file(client, args.bucket, object_name, path)

    upload_file(client, args.bucket, stable_manifest_path, manifest_file, content_type="application/json")
    print(f"published manifest: s3://{args.bucket}/{stable_manifest_path}")
    return 0


def upload_file(
    client: Minio,
    bucket: str,
    object_name: str,
    path: Path,
    *,
    content_type: str | None = None,
) -> None:
    """Upload one file to S3-compatible storage."""
    resolved_content_type = content_type or guess_content_type(path)
    client.fput_object(bucket, object_name, str(path), content_type=resolved_content_type)
    print(f"uploaded: s3://{bucket}/{object_name}")


def resolve_endpoint(raw_endpoint: str, raw_secure: str) -> tuple[str, bool]:
    """Convert env-style endpoint settings into MinIO client arguments."""
    endpoint = raw_endpoint.strip().rstrip("/")
    if not endpoint:
        return "", parse_bool(raw_secure, default=True)

    parsed = urlparse(endpoint)
    if parsed.scheme in {"http", "https"}:
        if parsed.path not in {"", "/"}:
            raise ValueError("S3_STORAGE_ENDPOINT must not include a URL path")
        secure = parsed.scheme == "https"
        if raw_secure.strip():
            secure = parse_bool(raw_secure, default=secure)
        return parsed.netloc, secure

    return endpoint, parse_bool(raw_secure, default=True)


def normalize_object_path(value: str) -> str:
    """Normalize an S3 object path."""
    normalized = value.strip().strip("/").replace("\\", "/")
    if not normalized:
        raise ValueError("S3 object path cannot be empty")
    return normalized


def guess_content_type(path: Path) -> str:
    """Guess an upload content type."""
    if path.suffix.lower() == ".exe":
        return "application/octet-stream"
    return mimetypes.guess_type(path.name)[0] or "application/octet-stream"


def parse_bool(value: str, *, default: bool) -> bool:
    """Parse bool-like environment values."""
    cleaned = value.strip().lower()
    if not cleaned:
        return default
    return cleaned in {"1", "true", "yes", "on"}


def validate_required(label: str, value: str) -> None:
    """Fail when a required setting is empty."""
    if not value.strip():
        raise ValueError(f"{label} is required")


if __name__ == "__main__":
    raise SystemExit(main())
