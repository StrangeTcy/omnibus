"""Runtime-owned structured actions; never parse worker prose as a command."""
from dataclasses import dataclass
from pydantic import BaseModel, ConfigDict, Field
from .security import redact

class WriteArtifact(BaseModel):
    model_config = ConfigDict(extra='forbid')
    content: str = Field(max_length=100000)
    kind: str = Field(pattern=r'^(context|response|report)$')

class ArtifactRef(BaseModel):
    id: str

@dataclass(frozen=True)
class Capability:
    id: str
    version: str
    input_schema: type[BaseModel]
    output_schema: type[BaseModel]
    side_effect: str
    permission: str
    timeout_seconds: int
    max_bytes: int
    idempotent: bool

class Registry:
    def __init__(self, store, artifacts):
        self.store, self.artifacts = store, artifacts
        self.descriptors = {'artifact.write': Capability('artifact.write', '1', WriteArtifact, ArtifactRef, 'local_append', 'run_workspace', 5, 100000, False)}

    def execute(self, name, payload, run_id):
        if name not in self.descriptors:
            raise ValueError('Unregistered capability')
        action = self.descriptors[name].input_schema.model_validate(payload)
        if len(action.content.encode()) > self.descriptors[name].max_bytes:
            raise ValueError('Capability byte budget exceeded')
        with self.store.lock:
            run = self.store.get('runs', run_id)
            task = self.store.get('tasks', run['task_id'])
            if run['status'] != 'running':
                raise ValueError('Run is not active')
            calls = run['budget_use'].get('tool_calls', 0)
            if calls >= task['budget']['tool_calls']:
                raise ValueError('Tool-call budget exhausted')
            self.store.update('runs', run_id, {'budget_use': {**run['budget_use'], 'tool_calls': calls+1}})
            self.store.event(run_id, 'tool_invoked', {'capability': name})
            obj = self.artifacts.write(redact(action.content).encode(), kind=action.kind, run_id=run_id, provenance=run_id)
            return ArtifactRef(id=obj['id'])
