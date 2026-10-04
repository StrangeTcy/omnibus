from typing import Literal
from pydantic import BaseModel, Field, ConfigDict

class Payload(BaseModel):
    model_config = ConfigDict(extra="forbid")

class Budget(Payload):
    seconds: float = Field(default=60, gt=0, le=600)
    turns: int = Field(default=1, ge=1, le=1)
    tool_calls: int = Field(default=4, ge=1, le=20)
    retries: int = Field(default=0, ge=0, le=2)

class Submission(Payload):
    text: str = Field(min_length=1, max_length=16000)
    route: Literal["auto", "answer", "task", "investigation", "project"] = "auto"
    project_id: str | None = None
    source: str = Field(default="api", max_length=40)
    execution_mode: Literal['read_only', 'workspace_write'] = 'read_only'
    authorize_workspace_write: bool = False
    fixture: Literal['sales-summary'] | None = None
    budget: Budget = Field(default_factory=Budget)

class Memory(Payload):
    kind: Literal["preference", "fact", "commitment", "inventory", "project_state", "hypothesis"]
    subject: str = Field(min_length=1, max_length=200)
    predicate: str = Field(min_length=1, max_length=200)
    value: str = Field(min_length=1, max_length=4000)
    scope: str = Field(default="personal", max_length=200)
    provenance: list[str] = Field(default_factory=lambda: ["explicit user entry"], max_length=20)
    confidence: float = Field(default=1, ge=0, le=1)
    basis: str = Field(default="user supplied", max_length=1000)
    validity: str = Field(default="current", max_length=200)
    supersedes: str | None = None
    sensitivity: Literal["ordinary", "sensitive"] = "ordinary"
    status: Literal["active", "superseded"] = "active"

class ProjectChange(Payload):
    status: Literal["active", "paused", "archived"] | None = None
    note: str | None = Field(default=None, max_length=4000)
    item: str | None = Field(default=None, min_length=1, max_length=500)
    complete: str | None = None
    next_action: str | None = Field(default=None, max_length=1000)
