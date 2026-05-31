from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel

from dich_truyen_agent.paths import temp_sibling_path

ModelT = TypeVar("ModelT", bound=BaseModel)


def load_yaml_model(path: Path, model_type: type[ModelT]) -> ModelT:
    with path.open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream)
    return model_type.model_validate(data)


def atomic_write_yaml(path: Path, model: ModelT) -> None:
    validated = type(model).model_validate(model.model_dump(mode="json"))
    serialized = yaml.safe_dump(
        validated.model_dump(mode="json"),
        allow_unicode=True,
        sort_keys=False,
    )
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = temp_sibling_path(path)
    with temp_path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(serialized)
        stream.flush()
        os.fsync(stream.fileno())
    load_yaml_model(temp_path, type(model))
    os.replace(temp_path, path)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def find_orphan_temp_files(workspace_root: Path) -> list[Path]:
    return sorted(
        path
        for path in workspace_root.rglob(".*.tmp")
        if path.is_file()
    )
