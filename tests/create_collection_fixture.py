"""Create NEW disposable Markdown/EPUB input fixtures for native/live acceptance.

These are synthetic study notes, not actual Milewski/GEB books or model outputs.
Never overwrites an existing directory. No provider requests are made here.
"""
import argparse
import html
import json
import zipfile
from pathlib import Path

TOPICS = [
    ('Functions and composition', 'A function maps each input to one output. Composition passes the output of one function to the next. Composition is associative: regrouping a chain does not change its result.'),
    ('Mappings and grouping', 'Mappings can be combined in sequence. Parentheses in a sequence of composed functions can be moved without changing the resulting mapping. The identity function leaves its input unchanged.'),
    ('Categories', 'A category has objects and arrows. Arrows compose associatively when endpoints match. Every object has an identity arrow. A functor preserves identities and composition.'),
    ('Structure preserving maps', 'A functor maps objects and arrows between categories while preserving composition and identities. This is stronger than merely assigning labels. An isomorphism is an invertible arrow.'),
]

def create(root):
    root.mkdir(parents=True, exist_ok=False)
    for i,(title,paragraph) in enumerate(TOPICS):
        text='\n\n'.join([paragraph]*85)
        if i<2:
            (root/f'book-{i+1}.md').write_text('# '+title+'\n\n'+text+'\n\n## Closing notes\n'+paragraph,encoding='utf-8')
        else:
            with zipfile.ZipFile(root/f'book-{i+1}.epub','w') as z:
                z.writestr('mimetype','application/epub+zip')
                z.writestr('META-INF/container.xml','<container><rootfiles><rootfile full-path="book.opf"/></rootfiles></container>')
                z.writestr('book.opf',f'<package xmlns="http://www.idpf.org/2007/opf" version="3.0" unique-identifier="id"><metadata xmlns:dc="http://purl.org/dc/elements/1.1/"><dc:identifier id="id">fixture-{i}</dc:identifier><dc:title>{title}</dc:title><dc:language>en</dc:language></metadata><manifest><item id="one" href="one.xhtml" media-type="application/xhtml+xml"/><item id="two" href="two.xhtml" media-type="application/xhtml+xml"/></manifest><spine><itemref idref="one"/><itemref idref="two"/></spine></package>')
                for name in ['one','two']:
                    z.writestr(name+'.xhtml',f'<html xmlns="http://www.w3.org/1999/xhtml"><head><title>{title} — {name}</title></head><body><p>{html.escape(text)}</p></body></html>')
    return sorted(str(p) for p in root.iterdir())

if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('directory',type=Path)
    print(json.dumps(create(parser.parse_args().directory),indent=2))
