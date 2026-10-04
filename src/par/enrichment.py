"""Explicit optional seams. No production fake and no automatic model calls."""
from typing import Protocol
from pydantic import Field
from .schemas import Payload
from .knowledge_models import Edge, Node, Activity

class EnrichmentProposal(Payload):
    concepts: list[Node] = Field(default_factory=list, max_length=100)
    relationships: list[Edge] = Field(default_factory=list, max_length=100)

class SemanticEnricher(Protocol):
    async def propose(self, text: str, context: dict) -> EnrichmentProposal: ...

class ReaderAdapter(Protocol):
    """Adapters must label imported positions/history as reader_import."""
    def read(self, source: str) -> list[tuple[str, Activity]]: ...

class UnavailableEnricher:
    def health(self):
        return {'available': False, 'backend': None, 'diagnostic': 'No semantic backend configured. Add concepts and evidenced relationships manually; no model is called.'}
    async def propose(self, text, context):
        raise ValueError(self.health()['diagnostic'])


def validate_proposal(raw, accessible_nodes):
    """Context maps existing IDs to supplied node metadata, including locators.

    New concept proposals remain proposals; this function never writes graph state.
    A future configured adapter must expose its actual bounded source context.
    """
    proposal = EnrichmentProposal.model_validate(raw)
    def source_available(provenance):
        if not isinstance(accessible_nodes, dict):
            return False
        for p in provenance:
            n = accessible_nodes.get(p.node_id)
            if p.kind == 'model' and n and p.locator and p.locator == n.get('locator'):
                if p.sha256 is None or p.sha256 == n.get('sha256'):
                    return True
        return False
    for c in proposal.concepts:
        if c.node_type != 'concept' or any(p.kind != 'model' for p in c.provenance) or not source_available(c.provenance):
            raise ValueError('Semantic concept proposals require model provenance and a supplied evidence locator')
    for e in proposal.relationships:
        if e.status != 'proposed' or not all(m.node_id in accessible_nodes for m in e.members):
            raise ValueError('Enrichment may only propose edges on supplied context IDs')
        if not source_available(e.provenance):
            raise ValueError('Model proposals require an accessible evidence locator')
    return proposal
