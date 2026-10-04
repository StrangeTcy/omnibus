import os
from pathlib import Path
from dataclasses import dataclass
from platformdirs import user_data_path

@dataclass
class Config:
    root: Path
    worker: str = "mock"

    @classmethod
    def load(cls):
        worker = os.environ.get("PAR_WORKER", "mock")
        if worker not in {"mock", "codex"}:
            raise ValueError("PAR_WORKER must be mock or codex")
        return cls(Path(os.environ.get("PAR_DATA_ROOT", user_data_path("personal-agent-runtime"))).expanduser().resolve(), worker)
