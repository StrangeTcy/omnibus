import argparse
import asyncio
import json
import os
import platform
from importlib.metadata import version
from pathlib import Path
from filelock import FileLock, Timeout
from .config import Config
from .db import Store
from .artifacts import Artifacts, restore
from .runtime import Runtime
from .schemas import Submission
from .workers import worker_for
from .workers.codex_sdk import health


def main():
    parser = argparse.ArgumentParser(prog='par')
    parser.add_argument('--data-root', type=Path)
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('doctor')
    commands.add_parser('status')
    serve = commands.add_parser('serve')
    serve.add_argument('--host', default='127.0.0.1')
    serve.add_argument('--port', type=int, default=8000)
    for name in ['backup', 'export']:
        commands.add_parser(name).add_argument('destination', nargs='?', type=Path, default=Path('par-backup.zip'))
    commands.add_parser('import').add_argument('archive', type=Path)
    run = commands.add_parser('run')
    run.add_argument('text')
    run.add_argument('--route', choices=['auto', 'answer', 'task', 'investigation', 'project'], default='auto')
    run.add_argument('--worker', choices=['mock', 'codex'])
    ready = commands.add_parser('worker-ready')
    ready.add_argument('--worker', choices=['codex', 'mock'])
    smoke = commands.add_parser('smoke')
    smoke.add_argument('--worker', choices=['codex', 'mock'])
    smoke.add_argument('--writable', action='store_true')
    smoke.add_argument('--authorize-workspace-write', action='store_true')
    resume = commands.add_parser('resume')
    resume.add_argument('run_id')
    resume.add_argument('--worker', choices=['codex', 'mock'])
    resume.add_argument('--acknowledge-uncertainty', action='store_true')
    continuation = commands.add_parser('continue')
    continuation.add_argument('run_id')
    continuation.add_argument('text')
    continuation.add_argument('--worker', choices=['codex', 'mock'])
    verification = commands.add_parser('verify')
    verification.add_argument('run_id')
    verification.add_argument('--approve', action='store_true')
    verification.add_argument('--seconds', type=float, default=30)
    verification.add_argument('argv', nargs=argparse.REMAINDER)
    from . import life_cli
    life_cli.configure(commands)
    args = parser.parse_args()
    try:
        config = Config.load()
        if args.data_root:
            config.root = args.data_root.expanduser().resolve()
        if args.command == 'worker-ready':
            from .smoke import readiness
            result = asyncio.run(readiness(args.worker or config.worker))
            print(json.dumps(result, indent=2))
            raise SystemExit(0 if result['available'] else 1)
        if args.command == 'import':
            restore(args.archive, config.root)
            print('Restored into', config.root)
            return
        if args.command == 'serve':
            if args.host not in {'127.0.0.1', 'localhost', '::1'} and len(os.environ.get('PAR_ACCESS_TOKEN', '')) < 32:
                parser.error('Public/LAN binding requires PAR_ACCESS_TOKEN (32+ characters); use TLS/private network')
            import uvicorn
            from .api import create_app
            uvicorn.run(create_app(config), host=args.host, port=args.port)
            return
        store = Store(config.root)
        artifacts = Artifacts(store)
        if args.command == 'doctor':
            probe = artifacts.root / '.write-probe'
            probe.write_text('ok')
            probe.unlink()
            print(json.dumps({'python': platform.python_version(), 'dependencies': {name: version(name) for name in ['fastapi', 'uvicorn', 'pydantic', 'jinja2', 'platformdirs', 'filelock']}, 'database': str(store.path), 'database_integrity': 'ok', 'artifact_directory_writable': True, 'configured_worker': config.worker, 'codex': asyncio.run(health()), 'security': 'Loopback default; read-only Codex sandbox; no automatic external actions'}, indent=2))
            return
        if args.command == 'status':
            print(json.dumps({name: store.list(name) for name in ['tasks', 'runs', 'projects']}, indent=2))
            return
        with FileLock(str(config.root / 'runtime.lock'), timeout=0):
            if args.command == 'life':
                result = life_cli.run(store, args)
                print(json.dumps(result, indent=2))
                if (args.life_command == 'analyze' and result['status'] != 'completed') or (args.life_command in {'model', 'browser'} and args.check and not result['available']):
                    raise SystemExit(1)
            elif args.command in {'smoke', 'resume', 'continue'}:
                from .smoke import smoke
                store.recover()
                runtime = Runtime(store, worker_for(args.worker or config.worker))
                if args.command == 'smoke':
                    result = asyncio.run(smoke(runtime, writable=args.writable, authorized=args.authorize_workspace_write))
                else:
                    if args.command == 'resume':
                        id = runtime.retry(args.run_id, args.acknowledge_uncertainty)['id']
                    else:
                        id = runtime.continue_run(args.run_id, args.text)['run_id']
                    asyncio.run(runtime.execute(id))
                    result = store.get('runs', id)
                print(json.dumps(result, indent=2))
                raise SystemExit(0 if result['status'] == 'completed' and result['verification'] != 'failed' else 1)
            elif args.command in {'backup', 'export'}:
                print(artifacts.backup(args.destination))
            elif args.command == 'verify':
                from .verification import verify
                runtime = Runtime(store, worker_for(config.worker))
                report = asyncio.run(verify(runtime, args.run_id, args.argv, approved=args.approve, seconds=args.seconds))
                print(json.dumps(report, indent=2))
                if report['verification'] != 'passed':
                    raise SystemExit(1)
            elif args.command == 'run':
                store.recover()
                if (args.worker or config.worker) == 'mock':
                    import sys
                    print('MockWorker explicitly configured: simulated output, not a real model.', file=sys.stderr)
                runtime = Runtime(store, worker_for(args.worker or config.worker))
                result = runtime.accept(Submission(text=args.text, route=args.route, source='cli'))
                asyncio.run(runtime.execute(result['run_id']))
                run = store.get('runs', result['run_id'])
                print(json.dumps(run, indent=2))
                if run['status'] != 'completed':
                    raise SystemExit(1)
    except KeyError:
        parser.exit(2, 'Run or referenced durable state not found.\n')
    except KeyboardInterrupt:
        parser.exit(130, 'Interrupted; inspect par status before explicit resume. No automatic replay.\n')
    except Timeout:
        parser.exit(2, 'Data root is in use. Use the web/API client, or stop the server before offline run/backup.\n')
    except (ValueError, OSError) as exc:
        parser.exit(2, f'{exc}\n')
