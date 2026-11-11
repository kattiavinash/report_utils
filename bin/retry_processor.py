"""Simple randomized retry result and JSON append helper."""

from __future__ import annotations

import json
import os
import random
import tempfile
from pathlib import Path
from typing import Any

import constants


def append_json_record(path: Path, collection: str, record: dict[str, Any]) -> None:
    """Append one record to a JSON collection using an atomic file replacement."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        with path.open(encoding="utf-8") as source:
            payload = json.load(source)
        if not isinstance(payload, dict) or not isinstance(payload.get(collection), list):
            raise ValueError(f"{path} must contain a '{collection}' list")
    else:
        payload = {collection: []}

    payload[collection].append(record)
    temporary_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=path.parent,
            prefix=f".{path.name}.",
            suffix=".tmp",
            delete=False,
        ) as temporary_file:
            temporary_path = Path(temporary_file.name)
            json.dump(payload, temporary_file, indent=2)
            temporary_file.write("\n")
            temporary_file.flush()
            os.fsync(temporary_file.fileno())
        os.replace(temporary_path, path)
    finally:
        if temporary_path is not None and temporary_path.exists():
            temporary_path.unlink()


class DummyRetryProcessor:
    """Return one simulated status from the existing supported status values."""

    def __init__(self, seed: int | None = None) -> None:
        """Allow deterministic tests while keeping normal outcomes random."""
        self.random = random.Random(seed)

    def retry_job(self) -> str:
        """Return a randomly selected retry status without other side effects."""
        return self.random.choice(constants.DUMMY_RETRY_STATUSES)
