from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol
from pydantic import BaseModel, Field
from ..schemas import Budget

@dataclass(frozen=True)
class Descriptor:
    id: str
    version: str = '1'
    modalities: tuple[str, ...] = ('text',)
    operations: tuple[str, ...] = ('answer', 'plan')
    resumable: bool = False

@dataclass
class Invocation:
    goal: str
    constraints: list[str]
    criteria: list[str]
    context: dict
    attachments: list[dict]
    workspace: Path
    budget: Budget
    thread_id: str | None = None
    resume_turn_id: str | None = None
    execution_mode: str = 'read_only'

class Result(BaseModel):
    response: str = Field(max_length=100000)
    thread_id: str | None = None
    output_paths: list[str] = Field(default_factory=list)
    usage: dict = Field(default_factory=dict)

class Worker(Protocol):
    descriptor: Descriptor
    async def run(self, invocation: Invocation) -> Result: ...

class WorkerFailure(RuntimeError):
    """Safe diagnostic only: never store arbitrary SDK/provider exception text."""
    def __init__(self, kind, message):
        self.kind = kind
        super().__init__(message)
