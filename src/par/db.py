import json
import sqlite3
import threading
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4
from .security import redact_data

TABLES = {"projects", "tasks", "requests", "runs", "artifacts", "memories"}
def now():
    return datetime.now(timezone.utc).isoformat()
def uid():
    return str(uuid4())

class Store:
    def __init__(self, root: Path):
        self.root = root.resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.path = root / "state.sqlite3"
        with self.connect() as db:
            db.execute("PRAGMA journal_mode=WAL")
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version > 1:
                raise ValueError("Database is newer than this runtime")
            if version < 1:
                sql = (Path(__file__).parent / "migrations/001_initial.sql").read_text()
                db.executescript("BEGIN IMMEDIATE;\n" + sql + "\nCOMMIT;")
            if db.execute("PRAGMA integrity_check").fetchone()[0] != "ok" or db.execute("PRAGMA foreign_key_check").fetchall():
                raise ValueError("Database integrity check failed")

    @contextmanager
    def connect(self):
        with self.lock:
            db = sqlite3.connect(self.path, timeout=10)
            db.row_factory = sqlite3.Row
            db.execute("PRAGMA foreign_keys=ON")
            try:
                with db:
                    yield db
            finally:
                db.close()

    def add(self, table, data, db=None, **refs):
        if table not in TABLES:
            raise ValueError("Unknown table")
        if db is None:
            with self.connect() as connection:
                return self.add(table, data, connection, **refs)
        obj = {"id": uid(), "created": now(), **refs, **data}
        allowed = {"tasks": {"project_id"}, "requests": {"task_id"}, "runs": {"task_id"}, "artifacts": {"run_id"}}.get(table, set())
        if not refs.keys() <= allowed:
            raise ValueError("Invalid reference")
        cols = ["id", "created", "data", *refs]
        db.execute(f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' for _ in cols)})", [obj['id'], obj['created'], json.dumps(obj), *refs.values()])
        return obj

    def get(self, table, id, db=None):
        if table not in TABLES:
            raise ValueError("Unknown table")
        if db is None:
            with self.connect() as connection:
                return self.get(table, id, connection)
        row = db.execute(f"SELECT data FROM {table} WHERE id=?", (id,)).fetchone()
        if not row:
            raise KeyError(id)
        return json.loads(row[0])

    def list(self, table):
        if table not in TABLES:
            raise ValueError("Unknown table")
        with self.connect() as db:
            return [json.loads(r[0]) for r in db.execute(f"SELECT data FROM {table} ORDER BY created")]

    def update(self, table, id, changes, db=None):
        if db is None:
            with self.connect() as connection:
                return self.update(table, id, changes, connection)
        obj = self.get(table, id, db)
        if changes.keys() & {"id", "created", "task_id", "project_id", "run_id"}:
            raise ValueError("Immutable identity/reference")
        if table in {'tasks', 'runs'} and 'status' in changes and changes['status'] != obj.get('status'):
            transitions = {
                'queued': {'running', 'blocked', 'paused', 'cancelled', 'failed'},
                'running': {'completed', 'failed', 'paused', 'cancelled', 'blocked'},
                'paused': {'queued'} if table == 'tasks' else set(),
                'failed': {'queued'} if table == 'tasks' else set(),
                'blocked': {'queued'} if table == 'tasks' else set(),
                'cancelled': {'queued'} if table == 'tasks' else set(),
                'completed': set(),
            }
            if changes['status'] not in transitions.get(obj.get('status'), set()):
                raise ValueError(f"Invalid {table} transition: {obj.get('status')} -> {changes['status']}")
        obj.update(changes)
        db.execute(f"UPDATE {table} SET data=? WHERE id=?", (json.dumps(obj), id))
        return obj

    def event(self, entity, kind, data=None, db=None):
        if db is None:
            with self.connect() as connection:
                return self.event(entity, kind, data, connection)
        db.execute("INSERT INTO events(created,entity,kind,data) VALUES (?,?,?,?)", (now(), entity, kind, json.dumps(redact_data(data or {}))))

    def events(self, entity=None):
        with self.connect() as db:
            rows = db.execute("SELECT * FROM events" + (" WHERE entity=?" if entity else "") + " ORDER BY seq", (entity,) if entity else ()).fetchall()
            return [dict(r) for r in rows]

    def depend(self, task, prerequisite):
        with self.connect() as db:
            if self.get('tasks', task, db)['status'] != 'queued':
                raise ValueError('Dependencies are editable only before execution')
            if task == prerequisite:
                raise ValueError('Dependency cycle')
            rows = db.execute('WITH RECURSIVE reach(id) AS (SELECT depends_on FROM dependencies WHERE task_id=? UNION SELECT d.depends_on FROM dependencies d JOIN reach r ON d.task_id=r.id) SELECT id FROM reach', (prerequisite,)).fetchall()
            if task in [r[0] for r in rows]:
                raise ValueError('Dependency cycle')
            db.execute('INSERT INTO dependencies VALUES (?,?)', (task, prerequisite))
            self.event(task, 'dependency_added', {'prerequisite': prerequisite}, db)

    def prerequisites(self, task):
        with self.connect() as db:
            return [self.get('tasks', r[0], db) for r in db.execute('SELECT depends_on FROM dependencies WHERE task_id=?', (task,))]

    def recover(self):
        with self.connect() as db:
            for run in self.list('runs'):
                if run['status'] in {'running', 'queued'}:
                    self.update('runs', run['id'], {'status': 'paused', 'error_kind': 'interrupted', 'ended': now(), 'error': 'Interrupted; explicit retry required. In-flight worker effects may be uncertain.'}, db)
                    self.update('tasks', run['task_id'], {'status': 'paused'}, db)
                    self.event(run['id'], 'run_interrupted', db=db)
