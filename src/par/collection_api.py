"""Command workflow, retaining the application's existing auth/CSRF boundary."""
from fastapi import APIRouter
from pydantic import Field
from .schemas import Payload

class Command(Payload):
    text: str = Field(min_length=1, max_length=16000)
class Approval(Payload):
    provider: str
class Resume(Payload):
    verified_not_sent: bool = False

def install(app, collections):
    router = APIRouter(prefix='/api/assistant')
    @router.get('/state')
    def state():
        return {'config':collections.semantic.config().model_dump(), 'operations':[
            {k:j[k] for k in ['id','created','command','root','status','error']} for j in collections.store.list('collection_jobs')]}
    @router.post('/commands')
    def command(body: Command):
        return collections.prepare(body.text)
    @router.get('/operations/{id}')
    def result(id: str):
        return collections.result(id)
    @router.post('/operations/{id}/approve')
    async def approve(id: str, body: Approval):
        job = collections.approve(id, body.provider)
        if job['status'] == 'queued': collections.schedule(id)
        return job
    @router.post('/operations/{id}/pause')
    async def pause(id: str):
        return collections.pause(id)
    @router.post('/operations/{id}/resume')
    async def resume(id: str, body: Resume):
        job = collections.resume(id, body.verified_not_sent)
        if job['status'] == 'queued': collections.schedule(id)
        return job
    app.include_router(router)
