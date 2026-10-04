import json
import os
import subprocess
import sys
from fastapi.testclient import TestClient
from par.api import create_app
from par.config import Config
from par.workers.mock import MockWorker


def test_ui_api_upload_and_security(tmp_path):
    config = Config(tmp_path/'state')
    with TestClient(create_app(config, MockWorker())) as client:
        assert client.get('/').status_code == 200
        assert 'Personal Agent Runtime' in client.get('/').text
        assert client.post('/api/requests', json={'text': 'hello'}).status_code == 403
        token = client.get('/api/session').json()['csrf']
        client.headers['X-PAR-CSRF'] = token
        assert client.post('/api/requests', json={'text': 'hello'}, headers={'Origin': 'https://evil.example'}).status_code == 403
        assert client.get('/api/state', headers={'Host': 'evil.example'}).status_code == 403
        assert client.post('/api/requests', json={'text': '', 'unknown': True}).status_code == 422
        response = client.post('/api/upload', data={'text': 'How do I separate the white from the yolk?', 'route': 'answer'}, files={'files': ('../../escape.txt', b'untrusted', 'text/plain')})
        assert response.status_code == 200, response.text
        id = response.json()['run_id']
        async def wait_for_run():
            job = client.app.state.runtime.jobs.get(id)
            if job:
                await job
        client.portal.call(wait_for_run)
        detail = client.get('/api/runs/'+id).json()
        assert detail['requests'][0]['attachment_ids']
        assert detail['run']['status'] == 'completed'
        artifact = detail['artifacts'][0]
        download = client.get('/api/artifacts/'+artifact['id'])
        assert download.status_code == 200 and 'attachment;' in download.headers['content-disposition']
        memory = client.post('/api/memories', json={'kind':'fact','subject':'books','predicate':'owns','value':'Book A'})
        assert memory.status_code == 200
        assert client.get('/api/memories?q=Book').json()
        assert client.delete('/api/memories/'+memory.json()['id']).status_code == 200
    with TestClient(create_app(config)) as client:
        assert client.get('/api/runs/'+id).json()['run']['status'] == 'completed'
    assert not (tmp_path/'escape.txt').exists()


def test_token_auth(tmp_path, monkeypatch):
    monkeypatch.setenv('PAR_ACCESS_TOKEN', 't'*40)
    with TestClient(create_app(Config(tmp_path))) as client:
        assert client.get('/api/state').status_code == 401
        client.headers['Authorization'] = 'Bearer '+ 't'*40
        assert client.get('/api/state', headers={'Host':'preview.example'}).status_code == 200
        assert client.post('/login', data={'token': 'wrong'}).status_code == 403


def test_cli_full_process_restart_export_import(tmp_path):
    root = tmp_path/'cli-data'
    def cli(*args, data=root):
        return subprocess.run([sys.executable, '-m', 'par', '--data-root', str(data), *args], capture_output=True, text=True, timeout=30)
    result = cli('run', 'Consume music discography and commentary', '--route', 'project')
    assert result.returncode == 0, result.stderr
    run = json.loads(result.stdout)
    status = cli('status')
    assert status.returncode == 0
    state = json.loads(status.stdout)
    assert state['projects'][0]['goal'] == 'Consume music discography and commentary'
    assert state['runs'][0]['id'] == run['id']
    backup = tmp_path/'export.zip'
    assert cli('export', str(backup)).returncode == 0
    new = tmp_path/'new-data'
    assert cli('import', str(backup), data=new).returncode == 0
    assert json.loads(cli('status', data=new).stdout) == state
    refused = cli('serve', '--host', '0.0.0.0')
    assert refused.returncode == 2 and 'PAR_ACCESS_TOKEN' in refused.stderr


def test_cli_explicit_verification(tmp_path):
    root = tmp_path/'verify-data'
    prefix = [sys.executable, '-m', 'par', '--data-root', str(root)]
    result = subprocess.run([*prefix, 'run', 'hello'], capture_output=True, text=True, timeout=30)
    assert result.returncode == 0
    id = json.loads(result.stdout)['id']
    # An explicit harmless operator-selected command, not a worker-proposed action.
    checked = subprocess.run([*prefix, 'verify', '--approve', '--seconds', '5', id, sys.executable, '-c', 'print("checked")'], capture_output=True, text=True, timeout=30)
    assert checked.returncode == 0, checked.stderr
    assert json.loads(checked.stdout)['verification'] == 'passed'
