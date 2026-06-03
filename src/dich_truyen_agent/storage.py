from __future__ import annotations

import hashlib
import os
from pathlib import Path
from typing import TypeVar

import yaml
from pydantic import BaseModel

from dich_truyen_agent.paths import temp_sibling_path

import time

ModelT = TypeVar("ModelT", bound=BaseModel)


def _replace_with_retry(src: Path | str, dst: Path | str, max_retries: int = 10, delay: float = 0.1) -> None:
    for i in range(max_retries):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if i == max_retries - 1:
                raise
            time.sleep(delay)


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
    _replace_with_retry(temp_path, path)


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = temp_sibling_path(path)
    with temp_path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(text)
        stream.flush()
        os.fsync(stream.fileno())
    _replace_with_retry(temp_path, path)


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
