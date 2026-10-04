"""Validated, portable Intellectual Life records. No model dependency."""
from datetime import datetime, timezone, date
from typing import Literal
from pydantic import Field, field_validator, model_validator
from .schemas import Payload

class Evidence(Payload):
    kind: Literal['observed', 'extracted', 'user', 'deterministic', 'model', 'heuristic']
    description: str = Field(min_length=1, max_length=2000)
    node_id: str | None = None
    locator: str | None = Field(default=None, max_length=500)
    sha256: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')

class Node(Payload):
    node_type: Literal['resource', 'concept', 'unit'] = 'resource'
    title: str = Field(min_length=1, max_length=500)
    kind: str = Field(default='book', min_length=1, max_length=60)
    creators: list[str] = Field(default_factory=list, max_length=30)
    url: str | None = Field(default=None, max_length=2000)
    published: str | None = Field(default=None, pattern=r'^\d{4}-\d{2}-\d{2}$')
    language: str | None = None
    format: str | None = None
    total: float | None = Field(default=None, gt=0, allow_inf_nan=False)
    measure: Literal['pages', 'chapters', 'percent', 'seconds'] = 'percent'
    locator: str | None = None
    ordinal: int | None = Field(default=None, ge=1)
    excerpt: str = Field(default='', max_length=600)
    sha256: str | None = Field(default=None, pattern=r'^[a-f0-9]{64}$')
    locations: list[str] = Field(default_factory=list, max_length=1000)
    aliases: list[str] = Field(default_factory=list, max_length=100)
    provenance: list[Evidence] = Field(min_length=1, max_length=100)
    metadata: dict = Field(default_factory=dict)
    status: Literal['active', 'superseded'] = 'active'
    merged_into: str | None = None

    @field_validator('published')
    @classmethod
    def valid_date(cls, value):
        if value is not None:
            date.fromisoformat(value)
        return value

    @field_validator('url')
    @classmethod
    def safe_url(cls, value):
        if value is not None:
            from urllib.parse import urlsplit
            parts = urlsplit(value)
            if parts.scheme not in {'https', 'http'} or not parts.netloc or parts.username or parts.password:
                raise ValueError('URL must be http(s), without embedded credentials')
        return value

class Member(Payload):
    node_id: str
    role: str = Field(min_length=1, max_length=60, pattern=r'^[a-z_]+$')

class Edge(Payload):
    type: Literal['covers', 'prerequisite_for', 'overlaps_with', 'adds_material', 'illustrates', 'created_by', 'features_person', 'related_to', 'user_likes', 'user_dislikes', 'user_wants_to_explore']
    members: list[Member] = Field(min_length=2, max_length=100)
    provenance: list[Evidence] = Field(min_length=1, max_length=100)
    confidence: float = Field(default=1, ge=0, le=1, allow_inf_nan=False)
    status: Literal['proposed', 'confirmed', 'rejected', 'superseded'] = 'confirmed'
    explanation: str = Field(min_length=1, max_length=4000)
    valid_from: str | None = None
    valid_until: str | None = None
    supersedes: str | None = None

    @field_validator('valid_from', 'valid_until')
    @classmethod
    def valid_date(cls, value):
        if value is not None:
            date.fromisoformat(value)
        return value

    @model_validator(mode='after')
    def trustworthy(self):
        if len({(m.node_id, m.role) for m in self.members}) != len(self.members):
            raise ValueError('Duplicate membership')
        if len({m.node_id for m in self.members}) < 2:
            raise ValueError('An edge needs distinct participants')
        if self.valid_from and self.valid_until and self.valid_from > self.valid_until:
            raise ValueError('Invalid relation validity interval')
        kinds = {p.kind for p in self.provenance}
        if kinds <= {'model', 'heuristic'} and self.status == 'confirmed':
            raise ValueError('Inferred relationships require explicit user confirmation')
        return self

class Activity(Payload):
    kind: Literal['reading', 'position', 'revisit', 'correction', 'reaction']
    at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    source: Literal['manual', 'reader_import', 'estimate'] = 'manual'
    start: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    end: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    corrects: str | None = None
    reaction: Literal['like', 'dislike', 'neutral'] | None = None
    note: str = Field(default='', max_length=2000)
    @field_validator('at')
    @classmethod
    def utc(cls, value):
        if value.tzinfo is None:
            raise ValueError('Activity time must include a timezone')
        return value.astimezone(timezone.utc)

class Preference(Payload):
    scope: str = Field(min_length=1, max_length=200)
    statement: str = Field(min_length=1, max_length=2000)
    origin: Literal['explicit', 'inferred'] = 'explicit'
    confirmed: bool = True
    confidence: float = Field(default=1, ge=0, le=1)
    provenance: list[Evidence] = Field(min_length=1, max_length=50)

class Feedback(Payload):
    action: Literal['accepted', 'dismissed', 'deferred', 'seen', 'ignored', 'completed']
    note: str = Field(default='', max_length=1000)

class Settings(Payload):
    recommendations_enabled: bool = True
    daily_limit: int = Field(default=3, ge=0, le=5)
