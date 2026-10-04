import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import urlparse
from fastapi import FastAPI, Request, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse, JSONResponse, Response
from fastapi.templating import Jinja2Templates
from filelock import FileLock, Timeout
from .config import Config
from .db import Store
from .runtime import Runtime
from .schemas import Submission, Memory, ProjectChange
from .workers import worker_for
from .artifacts import MAX_FILE


def create_app(config=None, worker=None):
    config = config or Config.load()
    store = Store(config.root)
    runtime = Runtime(store, worker or worker_for(config.worker))
    csrf = secrets.token_urlsafe(32)
    token = os.environ.get('PAR_ACCESS_TOKEN', '')
    if token and len(token) < 32:
        raise ValueError('PAR_ACCESS_TOKEN must contain at least 32 characters')
    lock = FileLock(str(config.root / 'runtime.lock'))

    @asynccontextmanager
    async def lifespan(app):
        try:
            lock.acquire(timeout=0)
        except Timeout as exc:
            raise RuntimeError('Another authoritative runtime is using this data root') from exc
        store.recover()
        try:
            yield
        finally:
            await runtime.shutdown()
            lock.release()

    app = FastAPI(title='Personal Agent Runtime', lifespan=lifespan, docs_url=None, redoc_url=None)
    app.state.runtime = runtime
    templates = Jinja2Templates(directory=str(Path(__file__).parent / 'templates'))

    @app.middleware('http')
    async def boundary(request, call_next):
        host = request.url.hostname
        if not token and host not in {'localhost', '127.0.0.1', '::1', 'testserver'}:
            return JSONResponse({'detail': 'Remote access requires PAR_ACCESS_TOKEN'}, 403)
        if token:
            supplied = request.headers.get('authorization', '').removeprefix('Bearer ')
            supplied = supplied or request.cookies.get('par_access', '')
            if request.url.path != '/login' and not secrets.compare_digest(supplied, token):
                return HTMLResponse('<h1>PAR access token required</h1><form method="post" action="/login"><input type="password" name="token" required><button>Sign in</button></form>', 401)
        if request.method not in {'GET', 'HEAD', 'OPTIONS'}:
            origin = request.headers.get('origin')
            if origin and urlparse(origin).netloc != request.url.netloc:
                return JSONResponse({'detail': 'Cross-origin mutation forbidden'}, 403)
            if request.url.path != '/login' and not secrets.compare_digest(request.headers.get('x-par-csrf', ''), csrf):
                return JSONResponse({'detail': 'Missing/invalid X-PAR-CSRF; fetch /api/session first'}, 403)
            # Enforce even when Content-Length is absent or misleading.
            data = bytearray()
            async for chunk in request.stream():
                data.extend(chunk)
                if len(data) > 26 * 1024 * 1024:
                    return JSONResponse({'detail': 'Request body too large'}, 413)
            request._body = bytes(data)
        response = await call_next(request)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        response.headers['Referrer-Policy'] = 'no-referrer'
        response.headers['Cache-Control'] = 'no-store'
        return response

    @app.exception_handler(ValueError)
    async def invalid(request, exc):
        return JSONResponse({'detail': str(exc)}, 400)

    @app.exception_handler(KeyError)
    async def missing(request, exc):
        return JSONResponse({'detail': 'Object not found'}, 404)

    @app.post('/login')
    async def login(token_input: str = Form(alias='token')):
        if not token or not secrets.compare_digest(token_input, token):
            raise HTTPException(403, 'Invalid access token')
        response = HTMLResponse('<a href="/">Open runtime</a>')
        response.set_cookie('par_access', token, httponly=True, samesite='strict')
        return response

    @app.get('/', response_class=HTMLResponse)
    async def home(request: Request):
        return templates.TemplateResponse(request=request, name='index.html', context={'csrf': csrf, 'worker': runtime.worker.descriptor.id})

    @app.get('/api/session')
    async def session():
        return {'csrf': csrf, 'worker': runtime.worker.descriptor.id}

    @app.get('/api/state')
    async def state():
        return {name: store.list(name) for name in ['tasks', 'runs', 'projects', 'memories']}

    @app.post('/api/requests')
    async def submit(payload: Submission):
        obj = runtime.accept(payload)
        runtime.schedule(obj['run_id'])
        return obj

    @app.post('/api/upload')
    async def upload(text: str = Form(), route: str = Form('auto'), project_id: str = Form(''), files: list[UploadFile] = File(default=[])):
        payload = Submission(text=text, route=route, project_id=project_id or None, source='web')
        if len(files) > 5:
            raise ValueError('At most five files')
        uploads = []
        for file in files:
            if file.filename:
                data = await file.read(MAX_FILE+1)
                uploads.append((file.content_type or 'application/octet-stream', data))
            await file.close()
        obj = runtime.accept(payload, uploads)
        runtime.schedule(obj['run_id'])
        return obj

    @app.get('/api/runs/{id}')
    async def run_detail(id: str):
        run = store.get('runs', id)
        task = store.get('tasks', run['task_id'])
        requests = [r for r in store.list('requests') if r['task_id'] == task['id']]
        ids = {id, task['id'], *(r['id'] for r in requests)}
        artifact_ids = {a for r in requests for a in r['attachment_ids']}
        artifacts = [a for a in store.list('artifacts') if a.get('run_id') == id or a['id'] in artifact_ids]
        ids |= {a['id'] for a in artifacts}
        return {'run': run, 'task': task, 'requests': requests, 'artifacts': artifacts, 'events': [e for e in store.events() if e['entity'] in ids]}

    @app.post('/api/runs/{id}/cancel')
    async def cancel(id: str):
        return runtime.cancel(id)

    @app.post('/api/runs/{id}/retry')
    async def retry(id: str, acknowledge_uncertainty: bool = False):
        obj = runtime.retry(id, acknowledge_uncertainty)
        runtime.schedule(obj['id'])
        return obj

    @app.post('/api/runs/{id}/continue')
    async def continue_conversation(id: str, payload: Submission):
        if payload.execution_mode != 'read_only' or payload.fixture or payload.authorize_workspace_write:
            raise ValueError('Conversation continuation is read-only; use an explicitly authorized new fixture task')
        obj = runtime.continue_run(id, payload.text)
        runtime.schedule(obj['run_id'])
        return obj

    @app.get('/api/worker/readiness')
    async def worker_readiness():
        from .smoke import readiness
        result = await readiness(runtime.worker.descriptor.id)
        return JSONResponse(result, 200 if result['available'] else 503)

    @app.get('/api/artifacts/{id}')
    async def artifact(id: str):
        obj = store.get('artifacts', id)
        return Response(runtime.artifacts.read(id), media_type=obj['mime'], headers={'Content-Disposition': f'attachment; filename="{id}"'})

    @app.patch('/api/projects/{id}')
    async def project_change(id: str, payload: ProjectChange):
        return runtime.change_project(id, payload)

    @app.get('/api/memories')
    async def memory_list(q: str = ''):
        return runtime.memories.search(q)

    @app.post('/api/memories')
    async def memory_add(payload: Memory):
        return runtime.memories.save(payload)

    @app.put('/api/memories/{id}')
    async def memory_edit(id: str, payload: Memory):
        return runtime.memories.save(payload, id)

    @app.delete('/api/memories/{id}')
    async def memory_delete(id: str):
        runtime.memories.forget(id)
        return {'forgotten': id}

    return app
