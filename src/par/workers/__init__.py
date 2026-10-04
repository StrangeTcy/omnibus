from .mock import MockWorker
from .codex_sdk import CodexSdkWorker

def worker_for(name):
    if name == 'mock':
        return MockWorker()
    if name == 'codex':
        return CodexSdkWorker()
    raise ValueError('Unknown worker')
