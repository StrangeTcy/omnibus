import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from pathlib import Path
from .db import uid
from .security import inside

MAX_FILE = 5 * 1024 * 1024
ALLOWED = {'text/plain', 'text/markdown', 'application/json', 'image/png', 'image/jpeg', 'application/pdf', 'text/x-diff'}

class Artifacts:
    def __init__(self, store):
        self.store = store
        self.root = store.root / 'artifacts'
        self.root.mkdir(exist_ok=True)

    def write(self, content: bytes, *, kind, mime='text/plain', provenance='', run_id=None):
        if len(content) > MAX_FILE or mime not in ALLOWED:
            raise ValueError('Unsupported type or file exceeds 5 MiB')
        with self.store.lock:
            name = uid()
            dest = self.root / name
            temp = self.root / (name + '.tmp')
            with temp.open('xb') as f:
                f.write(content)
                f.flush()
                os.fsync(f.fileno())
            temp.replace(dest)
            try:
                with self.store.connect() as db:
                    obj = self.store.add('artifacts', {'kind': kind, 'mime': mime, 'path': 'artifacts/' + name, 'sha256': hashlib.sha256(content).hexdigest(), 'size': len(content), 'provenance': provenance, 'verification': 'unverified'}, db, run_id=run_id)
                    self.store.event(obj['id'], 'artifact_created', {'run': run_id, 'kind': kind}, db)
                return obj
            except BaseException:
                dest.unlink(missing_ok=True)
                raise

    def read(self, id):
        obj = self.store.get('artifacts', id)
        data = inside(self.store.root, obj['path']).read_bytes()
        if len(data) != obj['size'] or hashlib.sha256(data).hexdigest() != obj['sha256']:
            raise ValueError('Artifact integrity failure')
        return data

    def backup(self, destination: Path):
        destination = destination.resolve()
        if destination.is_relative_to(self.store.root):
            raise ValueError('Backup must be outside data root')
        destination.parent.mkdir(parents=True, exist_ok=True)
        with self.store.lock, tempfile.TemporaryDirectory() as temp:
            snapshot = Path(temp) / 'state.sqlite3'
            with self.store.connect() as source, sqlite3.connect(snapshot) as target:
                source.backup(target)
            tempzip = destination.with_suffix(destination.suffix + '.tmp')
            try:
                with zipfile.ZipFile(tempzip, 'w', zipfile.ZIP_DEFLATED) as z:
                    z.write(snapshot, 'state.sqlite3')
                    z.writestr('manifest.json', json.dumps({'format': 1}))
                    for obj in self.store.list('artifacts'):
                        z.writestr(obj['path'], self.read(obj['id']))
                tempzip.replace(destination)
            finally:
                tempzip.unlink(missing_ok=True)
        return destination


def restore(archive: Path, root: Path):
    """Offline import to a new empty root. Never merge/overwrite live state."""
    if root.exists() and any(root.iterdir()):
        raise ValueError('Restore requires a new or empty data root')
    root.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(dir=root.parent) as temp:
        stage = Path(temp)
        with zipfile.ZipFile(archive) as z:
            names = z.namelist()
            if len(names) != len(set(names)) or sum(i.file_size for i in z.infolist()) > 512 * 1024 * 1024:
                raise ValueError('Duplicate entries or oversized archive')
            for info in z.infolist():
                path = inside(stage, info.filename)
                if info.filename not in {'manifest.json', 'state.sqlite3'} and not (info.filename.startswith('artifacts/') and len(Path(info.filename).parts) == 2):
                    raise ValueError('Unexpected archive entry')
                if (info.external_attr >> 16) & 0o170000 == 0o120000:
                    raise ValueError('Symlinks forbidden')
                path.parent.mkdir(exist_ok=True)
                path.write_bytes(z.read(info))
        if json.loads((stage / 'manifest.json').read_text()) != {'format': 1}:
            raise ValueError('Unsupported archive')
        from .db import Store
        store = Store(stage)
        artifacts = Artifacts(store)
        for obj in store.list('artifacts'):
            if not obj['path'].startswith('artifacts/'):
                raise ValueError('Invalid artifact path')
            artifacts.read(obj['id'])
        with store.connect() as db:
            db.execute('PRAGMA wal_checkpoint(TRUNCATE)')
        (stage / 'manifest.json').unlink()
        root.mkdir(exist_ok=True)
        for path in stage.iterdir():
            shutil.move(str(path), root / path.name)
