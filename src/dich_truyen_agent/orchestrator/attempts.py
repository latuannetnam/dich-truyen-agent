from __future__ import annotations

import json
from pathlib import Path

from dich_truyen_agent.storage import atomic_write_text


class AttemptJournal:
    """Durably tracks per-run attempt counts for chapters and profile repair before launches."""

    def __init__(self, path: Path | str) -> None:
        self.path = Path(path).resolve()

    def _load(self) -> dict[str, dict[str, int]]:
        if not self.path.is_file():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data.get("records", {})
        except Exception:
            return {}

    def _save(self, records: dict[str, dict[str, int]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "schema_version": 1,
            "records": records,
        }
        atomic_write_text(self.path, json.dumps(payload, indent=2))

    def get_attempts(self, run_id: str, item_id: int | str) -> int:
        records = self._load()
        return records.get(run_id, {}).get(str(item_id), 0)

    def reserve(self, run_id: str, item_id: int | str, limit: int = 3) -> int:
        """Reserve and atomically record the next attempt for an item in a run.

        Raises RuntimeError if the attempt limit has already been reached.
        """
        records = self._load()
        run_records = records.setdefault(run_id, {})
        current = run_records.get(str(item_id), 0)

        if current >= limit:
            raise RuntimeError(f"attempt limit {limit} reached for {item_id} in run {run_id}")

        next_attempt = current + 1
        run_records[str(item_id)] = next_attempt
        self._save(records)
        return next_attempt

    def clear_run(self, run_id: str) -> None:
        records = self._load()
        if run_id in records:
            del records[run_id]
            self._save(records)
