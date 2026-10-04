"""Actual local Ollama inference, using its documented API, never a mock fallback.

https://docs.ollama.com/api/chat : messages, format=JSON schema, stream=false.
No remote endpoints, automatic downloads, provider keys or model tools.
"""
import asyncio
import json
from urllib.parse import urlsplit
import httpx
from pydantic import Field, field_validator
from typing import Literal
from .schemas import Payload
from .workers.base import WorkerFailure

class LocalModelConfig(Payload):
    backend: Literal['disabled', 'ollama', 'browser'] = 'disabled'
    endpoint: str = 'http://127.0.0.1:11434'
    model: str = Field(default='', max_length=200)
    browser_provider: Literal['chatgpt', 'claude', 'deepseek'] = 'chatgpt'
    browser_endpoint: str = 'http://127.0.0.1:9222'
    dedicated_browser_profile: bool = False
    seconds: float = Field(default=180, ge=5, le=600)

    @field_validator('endpoint', 'browser_endpoint')
    @classmethod
    def loopback_only(cls, value):
        p = urlsplit(value)
        if p.scheme != 'http' or p.hostname not in {'127.0.0.1', 'localhost', '::1'} or p.username or p.password or p.path not in {'', '/'} or p.query or p.fragment:
            raise ValueError('Inference endpoint must be a plain HTTP loopback URL, without credentials or a path')
        if p.port is not None and not 1 <= p.port <= 65535:
            raise ValueError('Invalid port')
        return value.rstrip('/').replace('://localhost', '://127.0.0.1')

class Ollama:
    def __init__(self, config: LocalModelConfig):
        self.config = config

    async def request(self, method, path, body=None):
        try:
            async with httpx.AsyncClient(trust_env=False, follow_redirects=False, timeout=httpx.Timeout(self.config.seconds, connect=3)) as client:
                async with client.stream(method, self.config.endpoint+path, json=body) as response:
                    if response.status_code != 200:
                        raise WorkerFailure('provider', f'Local Ollama returned HTTP {response.status_code}; no fallback used')
                    content = bytearray()
                    async for chunk in response.aiter_bytes():
                        content.extend(chunk)
                        if len(content) > 1024*1024:
                            raise WorkerFailure('invalid_output', 'Local model response exceeds 1 MiB')
            result = json.loads(content)
            if not isinstance(result, dict):
                raise ValueError('Expected an object')
            return result
        except WorkerFailure:
            raise
        except httpx.TimeoutException:
            raise WorkerFailure('timeout', 'Local inference timed out; daemon computation may still be running') from None
        except (httpx.HTTPError, ValueError, UnicodeError):
            raise WorkerFailure('model_unavailable', 'Cannot read the local Ollama API. Start Ollama and install the configured model on this host.') from None

    async def ready(self):
        if self.config.backend != 'ollama' or not self.config.model:
            raise WorkerFailure('configuration', 'No semantic backend configured. Select an installed local Ollama model.')
        if 'cloud' in self.config.model.lower():
            raise WorkerFailure('configuration', 'Cloud model routes are not allowed for local semantic inference')
        models = (await self.request('GET', '/api/tags')).get('models', [])
        if not isinstance(models, list) or not all(isinstance(m, dict) for m in models):
            raise WorkerFailure('invalid_output', 'Invalid model listing from local Ollama')
        item = next((m for m in models if m.get('name') == self.config.model or m.get('model') == self.config.model), None)
        if item is None:
            raise WorkerFailure('model_missing', 'Configured model is not installed. Pull that model with the official Ollama CLI first.')
        info = await self.request('POST', '/api/show', {'model': self.config.model})
        if any(d.get(k) for d in [item, info] for k in ['remote_host', 'remote_model']):
            raise WorkerFailure('configuration', 'Remote/cloud-backed Ollama models are refused')
        if not info.get('model_info'):
            raise WorkerFailure('configuration', 'Model has no local model metadata; refusing an unverified remote route')
        return {'available': True, 'backend': 'ollama', 'model': self.config.model,
                'digest': item.get('digest'), 'parameter_size': info.get('details', {}).get('parameter_size'),
                'diagnostic': 'Installed local model found. This readiness check is not proof of successful semantic analysis.'}

    async def generate(self, messages, schema):
        async with asyncio.timeout(self.config.seconds):
            readiness = await self.ready()
            data = await self.request('POST', '/api/chat', {'model': self.config.model, 'messages': messages,
                'format': schema, 'stream': False, 'options': {'temperature': 0, 'num_ctx': 8192, 'num_predict': 2500}, 'keep_alive': '5m'})
        if data.get('done') is not True or data.get('done_reason') not in {None, 'stop'}:
            raise WorkerFailure('invalid_output', 'Model generation did not finish normally; no partial output accepted')
        message = data.get('message')
        response = message.get('content') if isinstance(message, dict) else None
        if not isinstance(response, str) or not response.strip():
            raise WorkerFailure('invalid_output', 'Model returned no answer')
        metadata = {k: data.get(k) for k in ['model', 'total_duration', 'prompt_eval_count', 'eval_count', 'done_reason']}
        metadata['installed_digest'] = readiness.get('digest')
        return response, metadata
