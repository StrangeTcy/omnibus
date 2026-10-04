"""Intellectual Life routes reuse the application's existing auth/CSRF boundary."""
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from pydantic import Field
from .schemas import Payload
from .knowledge_models import Node, Edge, Activity, Preference, Feedback, Settings
from .knowledge import Knowledge
from .library import Library
from .recommendations import Recommender
from .graph_io import export_graph, import_graph
from .semantic import SemanticService, AnalysisRequest, TextMaterial
from .local_inference import LocalModelConfig
from .discovery import Discovery, DiscoveryRequest, LinkProposal, link_evidence

class Root(Payload):
    path: str = Field(min_length=1, max_length=4000)
class NodeInput(Payload):
    data: Node
    parent_id: str | None = None
class Decision(Payload):
    status: str
class Merge(Payload):
    target: str


def install(app, store, templates, csrf):
    graph, library, recommendations = Knowledge(store), Library(store), Recommender(store)
    discovery = Discovery(store)
    semantic = SemanticService(store, app.state.runtime)
    router = APIRouter(prefix='/api/life')

    @app.get('/life', response_class=HTMLResponse)
    def page(request: Request):
        return templates.TemplateResponse(request=request, name='life.html', context={'csrf': csrf})

    @router.get('/state')
    def state():
        nodes = store.list('nodes')
        return {'nodes': nodes, 'edges': graph.edges(), 'activity': store.list('activity'),
                'preferences': store.list('preferences'), 'roots': store.list('library_roots'),
                'progress': {n['id']: graph.progress(n['id']) for n in nodes if n['node_type'] in {'resource', 'unit'}},
                'recommendations': recommendations.generate(), 'settings': graph.settings(),
                'link_evidence': {n['id']: link_evidence(store, n) for n in nodes if n['node_type'] == 'resource'},
                'semantic': semantic.availability(), 'analyses': semantic.analyses(), 'reader': {'available': False, 'diagnostic': 'No reader integration configured. Record manual progress or imported positions explicitly.'}}

    @router.get('/discovery/context/{id}')
    def discovery_context(id: str):
        return discovery.context(id)

    @router.post('/discovery')
    def discover(body: DiscoveryRequest):
        return discovery.discover(body)

    @router.get('/discovery-reports')
    def discovery_reports():
        import json
        from .artifacts import Artifacts
        artifacts = Artifacts(store)
        return [{**json.loads(artifacts.read(a['id'])), 'report_id': a['id']} for a in store.list('artifacts') if a['kind'] == 'discovery-report'][-10:]

    @router.get('/discovery/{id}/evidence')
    def discovery_evidence(id: str):
        from .discovery import verified_snapshot
        snapshot = verified_snapshot(store, store.get('nodes', id))
        if not snapshot:
            raise ValueError('No intact verified page snapshot')
        return snapshot

    @router.post('/discovery/{id}/propose')
    def discovery_propose(id: str, body: LinkProposal):
        return discovery.propose_link(id, body)

    @router.get('/comparison')
    def comparison(source: str, candidate: str):
        return recommendations.compare(source, candidate)

    @router.post('/recommendations/{id}/rendered')
    def rendered(id: str):
        return recommendations.rendered(id)

    @router.put('/semantic/config')
    def semantic_config(body: LocalModelConfig):
        return semantic.config(body).model_dump()

    @router.post('/semantic/health')
    async def semantic_health():
        return await semantic.ready()

    @router.post('/semantic/text')
    def semantic_text(body: TextMaterial):
        return semantic.import_text(body)

    @router.post('/semantic/analyze')
    async def semantic_analyze(body: AnalysisRequest):
        obj = semantic.submit(body)
        semantic.runtime.schedule(obj['run_id'])
        return obj

    @router.post('/semantic/{id}/cancel')
    def semantic_cancel(id: str):
        if store.get('runs', id)['worker'] not in {'semantic-analysis', 'ollama-semantic'}:
            raise ValueError('Not a semantic analysis')
        return semantic.runtime.cancel(id)

    @router.post('/semantic/{id}/review')
    def semantic_review(id: str, body: Decision):
        return semantic.review(id, body.status)

    @router.post('/roots')
    def root(body: Root):
        return library.configure(body.path)

    @router.post('/roots/{id}/scan')
    def scan(id: str):
        with store.lock:
            return library.scan(id)

    @router.post('/nodes')
    def add_node(body: NodeInput):
        return graph.node(body.data, body.parent_id)

    @router.put('/nodes/{id}')
    def edit_node(id: str, body: Node):
        return graph.correct_node(id, body)

    @router.post('/nodes/{id}/merge')
    def merge(id: str, body: Merge):
        return graph.merge_concepts(id, body.target)

    @router.get('/nodes/{id}')
    def detail(id: str):
        node = store.get('nodes', id)
        return {'node': node, 'units': [n for n in store.list('nodes') if n['parent_id'] == id],
                'progress': graph.progress(id) if node['node_type'] != 'concept' else None,
                'graph': graph.neighborhood(id)}

    @router.post('/nodes/{id}/activity')
    def activity(id: str, body: Activity):
        return graph.activity(id, body)

    @router.post('/edges')
    def edge(body: Edge):
        return graph.edge(body)

    @router.post('/edges/{id}/decision')
    def decision(id: str, body: Decision):
        return graph.edge_status(id, body.status)

    @router.get('/graph')
    def neighborhood(focus: str | None = None, q: str = '', edge_type: str | None = None):
        return graph.neighborhood(focus, q, edge_type)

    @router.get('/export')
    def export():
        return export_graph(store)

    @router.post('/import')
    def import_(body: dict):
        return import_graph(store, body)

    @router.post('/preferences')
    def preference(body: Preference):
        return graph.preference(body)

    @router.post('/recommendations/{id}/feedback')
    def feedback(id: str, body: Feedback):
        return recommendations.feedback(id, body)

    @router.get('/recommendations/history')
    def recommendation_history():
        return store.list('recommendations')

    @router.put('/settings')
    def settings(body: Settings):
        return graph.settings(body.model_dump())

    app.include_router(router)
