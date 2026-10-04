from .schemas import Memory

class Memories:
    def __init__(self, store):
        self.store = store

    def save(self, memory: Memory, id=None):
        with self.store.connect() as db:
            if id:
                self.store.get('memories', id, db)
                memory = memory.model_copy(update={'supersedes': id})
                self.store.update('memories', id, {'status': 'superseded'}, db)
            obj = self.store.add('memories', memory.model_dump(), db)
            self.store.event(obj['id'], 'memory_corrected' if id else 'memory_created', {'supersedes': id}, db)
            return obj

    def forget(self, id):
        # Erase the correction chain too; event metadata contains no memory values.
        with self.store.connect() as db:
            self.store.get('memories', id, db)
            ids = {id}
            records = self.store.list('memories')
            while True:
                related = {r['id'] for r in records if r['id'] in ids or r.get('supersedes') in ids}
                related |= {r['supersedes'] for r in records if r['id'] in ids and r.get('supersedes')}
                if related <= ids:
                    break
                ids |= related
            for key in ids:
                db.execute('DELETE FROM memories WHERE id=?', (key,))
            self.store.event(id, 'memory_forgotten', db=db)

    def search(self, query=''):
        return [m for m in self.store.list('memories') if m['status'] == 'active' and query.casefold() in (m['subject'] + ' ' + m['value']).casefold()]

    def relevant(self, text, project=None):
        words = {w.strip('.,?!').casefold() for w in text.split() if len(w) > 3}
        return [m for m in self.search() if m['sensitivity'] == 'ordinary' and (m['scope'] == project or words.intersection((m['subject']+' '+m['predicate']).casefold().split()))][:10]
