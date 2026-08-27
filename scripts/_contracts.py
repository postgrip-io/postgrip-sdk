from __future__ import annotations

import hashlib
from pathlib import Path
import re

PLANES = ("agent", "worker", "service")


def digest_bundle(contracts: Path) -> tuple[str, dict[str, str]]:
    bundle = hashlib.sha256()
    per_plane: dict[str, str] = {}
    for plane in sorted(PLANES):
        path = contracts / f"{plane}-openapi.json"
        body = path.read_bytes()
        per_plane[plane] = hashlib.sha256(body).hexdigest()
        bundle.update(path.name.encode())
        bundle.update(b"\0")
        bundle.update(body)
        bundle.update(b"\0")
    return bundle.hexdigest(), per_plane


def snake(value: str) -> str:
    value = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", value)
    return re.sub(r"[^A-Za-z0-9]+", "_", value).strip("_").lower()
