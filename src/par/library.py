"""Read-only, bounded local ingestion. No URLs fetched and no semantic inference."""
import hashlib
import io
import os
import posixpath
import re
import zipfile
from pathlib import Path, PurePosixPath
from html.parser import HTMLParser
from defusedxml.ElementTree import fromstring
from .knowledge import Knowledge
from .knowledge_models import Node
from .db import now

MAX_FILE = 50 * 1024 * 1024
MAX_TEXT = 2 * 1024 * 1024
SUPPORTED = {'.epub', '.pdf', '.txt', '.md', '.markdown', '.html', '.htm'}

class TextHTML(HTMLParser):
    def __init__(self):
        super().__init__()
        self.parts, self.title = [], []
        self.hidden, self.in_title = 0, False
    def handle_starttag(self, tag, attrs):
        if tag in {'script', 'style'}:
            self.hidden += 1
        if tag == 'title':
            self.in_title = True
        if tag in {'h1', 'h2', 'h3', 'p', 'div', 'br'}:
            self.parts.append('\n')
    def handle_endtag(self, tag):
        if tag in {'script', 'style'}:
            self.hidden = max(0, self.hidden-1)
        if tag == 'title':
            self.in_title = False
    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)
            if self.in_title:
                self.title.append(data)


def html_text(data):
    p = TextHTML()
    p.feed(data)
    return ''.join(p.title).strip(), ''.join(p.parts)


def unit(title, locator, text='', ordinal=1):
    return {'title': title[:500] or locator, 'locator': locator, 'ordinal': ordinal,
            'excerpt': re.sub(r'\s+', ' ', text).strip()[:600], 'sha256': hashlib.sha256(text.encode()).hexdigest()}


def parse_file(path, content):
    ext = path.suffix.lower()
    result = {'title': path.stem, 'creators': [], 'format': ext[1:], 'measure': 'percent', 'total': 100,
              'units': [], 'metadata': {'title_source': 'filename (not semantic analysis)'}}
    if ext in {'.txt', '.md', '.markdown', '.html', '.htm'}:
        if len(content) > MAX_TEXT:
            raise ValueError('Text file exceeds 2 MiB parsing limit')
        text = content.decode('utf-8-sig')
        if ext in {'.html', '.htm'}:
            title, text = html_text(text)
            if title:
                result.update(title=title[:500], metadata={'title_source': 'HTML title'})
        headings = list(re.finditer(r'^#{1,6}\s+(.+)$', text, re.M)) if ext in {'.md', '.markdown'} else []
        if headings:
            result.update(title=headings[0][1][:500], metadata={'title_source': 'Markdown heading'})
            for i, h in enumerate(headings[:500]):
                end = headings[i+1].start() if i+1 < len(headings) else len(text)
                result['units'].append(unit(h[1], f'char:{h.start()}:{end}', text[h.end():end], i+1))
        else:
            result['units'] = [unit(result['title'], 'text:0', text)]
    elif ext == '.epub':
        with zipfile.ZipFile(io.BytesIO(content)) as archive:
            if len(archive.infolist()) > 2000 or sum(i.file_size for i in archive.infolist()) > 30*1024*1024:
                raise ValueError('EPUB exceeds expanded archive limits')
            def xml(name):
                return fromstring(archive.read(name), forbid_dtd=True)
            container = xml('META-INF/container.xml')
            opf = next(e.attrib['full-path'] for e in container.iter() if e.tag.endswith('rootfile'))
            package = xml(opf)
            titles = [e.text for e in package.iter() if e.tag.endswith('}title') and e.text]
            result['title'] = titles[0][:500] if titles else path.stem
            languages = [e.text for e in package.iter() if e.tag.endswith('}language') and e.text]
            result['language'] = languages[0] if languages else None
            result['creators'] = [e.text[:500] for e in package.iter() if e.tag.endswith('}creator') and e.text][:30]
            result['metadata']['title_source'] = 'EPUB embedded metadata' if titles else 'filename'
            manifest = {e.attrib.get('id'): e.attrib.get('href') for e in package.iter() if e.tag.endswith('}item')}
            spine = [e.attrib['idref'] for e in package.iter() if e.tag.endswith('}itemref')][:1000]
            for i, ref in enumerate(spine):
                href = manifest[ref]
                if not href or ':' in href or href.startswith('/'):
                    raise ValueError('Invalid EPUB spine reference')
                name = posixpath.normpath(posixpath.join(posixpath.dirname(opf), href.split('#')[0]))
                if name.startswith('../'):
                    raise ValueError('Invalid EPUB archive path')
                raw = archive.read(name)
                if len(raw) > MAX_TEXT:
                    raise ValueError('EPUB chapter exceeds text limit')
                title, text = html_text(raw.decode('utf-8-sig'))
                result['units'].append(unit(title or f'Section {i+1}', name, text, i+1))
            if not result['units']:
                raise ValueError('EPUB has no readable spine units')
            result.update(measure='chapters', total=len(result['units']))
    elif ext == '.pdf':
        try:
            from pypdf import PdfReader
        except ImportError:
            raise ValueError('PDF parser unavailable; install personal-agent-runtime[books]') from None
        reader = PdfReader(io.BytesIO(content), strict=True)
        if reader.is_encrypted:
            raise ValueError('Encrypted PDF unsupported')
        count = len(reader.pages)
        if not 0 < count <= 2000:
            raise ValueError('PDF page count outside 1–2000 limit')
        metadata = reader.metadata or {}
        result.update(title=str(metadata.get('/Title') or path.stem)[:500], creators=[str(metadata['/Author'])[:500]] if metadata.get('/Author') else [], measure='pages', total=count)
        result['metadata'] = {'title_source': 'PDF metadata' if metadata.get('/Title') else 'filename', 'text_excerpt_pages': min(count, 100)}
        for i, page in enumerate(reader.pages):
            text = (page.extract_text() or '')[:MAX_TEXT] if i < 100 else ''
            result['units'].append(unit(f'Page {i+1}', f'page:{i+1}', text, i+1))
    else:
        raise ValueError('Unsupported format')
    return result


class Library:
    def __init__(self, store):
        self.store, self.graph = store, Knowledge(store)

    def configure(self, path):
        candidate = Path(path).expanduser()
        if candidate.is_symlink():
            raise ValueError('Choose a real directory, not a symlink')
        root = candidate.resolve(strict=True)
        if not root.is_dir():
            raise ValueError('Library root must be a directory')
        existing = next((r for r in self.store.list('library_roots') if r['path'] == str(root)), None)
        return existing or self.store.add('library_roots', {'path': str(root), 'last_scan': None})

    def scan(self, root_id):
        root = Path(self.store.get('library_roots', root_id)['path'])
        if root.is_symlink() or not root.is_dir():
            raise ValueError('Configured root unavailable or replaced by a symlink')
        report = {'discovered': [], 'unchanged': [], 'duplicates': [], 'changed': [], 'issues': [], 'missing': []}
        known = [n for n in self.store.list('nodes') if n['node_type'] == 'resource']
        by_hash = {n['sha256']: n for n in known if n.get('sha256')}
        by_path = {p: n for n in known for p in n['locations']}
        seen, examined = set(), 0
        for directory, dirs, names in os.walk(root, followlinks=False):
            dirs[:] = sorted(d for d in dirs if not (Path(directory)/d).is_symlink())
            for name in sorted(names):
                examined += 1
                path = Path(directory)/name
                if examined > 10000:
                    report['issues'].append({'path': str(root), 'reason': 'Scan limited to 10000 entries'})
                    break
                if path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                    report['issues'].append({'path': str(path), 'reason': 'Symlink/outside-root file skipped'})
                    continue
                if path.suffix.lower() not in SUPPORTED:
                    report['issues'].append({'path': str(path), 'reason': 'Unsupported format'})
                    continue
                try:
                    before = path.stat()
                    if before.st_size > MAX_FILE:
                        raise ValueError('File exceeds 50 MiB limit')
                    # Read only; never extract archives to disk or modify originals.
                    flags = os.O_RDONLY | getattr(os, 'O_NOFOLLOW', 0) | getattr(os, 'O_BINARY', 0)
                    with os.fdopen(os.open(path, flags), 'rb') as f:
                        opened = os.fstat(f.fileno())
                        if (opened.st_dev, opened.st_ino) != (before.st_dev, before.st_ino) or path.is_symlink() or not path.resolve().is_relative_to(root.resolve()):
                            raise ValueError('Path changed while opening')
                        content = f.read(MAX_FILE+1)
                    after = path.stat()
                    if len(content) > MAX_FILE or (before.st_mtime_ns, before.st_size) != (after.st_mtime_ns, after.st_size):
                        raise ValueError('File changed while scanning; retry later')
                    digest = hashlib.sha256(content).hexdigest()
                    canonical = str(path.resolve())
                    seen.add(canonical)
                    if old := by_hash.get(digest):
                        if canonical not in old['locations']:
                            if len(old['locations']) >= 1000:
                                raise ValueError('Resource already has 1000 recorded duplicate locations')
                            old = self.store.update('nodes', old['id'], {'locations': old['locations']+[canonical]})
                            by_hash[digest] = old
                            report['duplicates'].append({'id': old['id'], 'path': canonical, 'basis': 'identical SHA-256; additional location / possible move'})
                        else:
                            report['unchanged'].append(old['id'])
                        continue
                    parsed = parse_file(path, content)
                    units = parsed.pop('units')
                    provenance = [{'kind': 'observed', 'description': 'Read-only local file metadata; no model analysis', 'locator': canonical, 'sha256': digest}]
                    if previous := by_path.get(canonical):
                        parsed['metadata']['previous_version'] = previous['id']
                        report['changed'].append(previous['id'])
                    with self.store.connect() as db:
                        data = Node(**parsed, locations=[canonical], sha256=digest, provenance=provenance)
                        obj = self.store.add('nodes', data.model_dump(mode='json'), db, parent_id=None)
                        for u in units:
                            data = Node(node_type='unit', kind='section', **u, measure='percent', total=100,
                                        provenance=[{'kind': 'extracted', 'description': 'Bounded local excerpt; not semantic analysis', 'node_id': obj['id'], 'locator': u['locator'], 'sha256': digest}])
                            self.store.add('nodes', data.model_dump(mode='json'), db, parent_id=obj['id'])
                        self.store.event(obj['id'], 'resource_ingested', {'units': len(units), 'sha256': digest}, db)
                    by_hash[digest] = obj
                    report['discovered'].append(obj['id'])
                except Exception as exc:
                    report['issues'].append({'path': str(path), 'reason': f'{type(exc).__name__}: {str(exc)[:300]}'})
            if examined > 10000:
                break
        report['missing'] = [p for p in by_path if Path(p).is_relative_to(root) and p not in seen and not Path(p).exists()]
        self.store.update('library_roots', root_id, {'last_scan': now(), 'report': report})
        self.store.event(root_id, 'library_scanned', {k: len(v) for k, v in report.items()})
        return report
