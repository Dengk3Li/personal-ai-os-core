from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_file(root: Path, relative: str) -> Path:
    candidate = Path(relative)
    if candidate.is_absolute() or ".." in candidate.parts:
        raise ValueError("asset path is outside root")
    resolved_root = root.resolve()
    resolved = (resolved_root / candidate).resolve()
    try:
        resolved.relative_to(resolved_root)
    except ValueError as error:
        raise ValueError("asset path is outside root") from error
    if not resolved.is_file() or resolved.is_symlink():
        raise ValueError(f"asset is not a regular file: {relative}")
    return resolved


def freeze_assets(root: Path, relative_paths: list[str]) -> dict[str, Any]:
    files = {relative: _sha256(_safe_file(root, relative)) for relative in sorted(relative_paths)}
    return {"schema_version": "personal-ai-os.freeze.v1", "files": files}


def verify_freeze(root: Path, manifest: dict[str, Any]) -> dict[str, Any]:
    missing: list[str] = []
    drifted: list[str] = []
    for relative, expected in sorted(manifest.get("files", {}).items()):
        try:
            current = _sha256(_safe_file(root, relative))
        except ValueError:
            missing.append(relative)
            continue
        if current != expected:
            drifted.append(relative)
    return {
        "status": "PASS" if not missing and not drifted else "BLOCKED",
        "missing": missing,
        "drifted": drifted,
    }
