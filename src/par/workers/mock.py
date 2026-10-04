import asyncio
import re
from .base import Descriptor, Result

class MockWorker:
    descriptor = Descriptor('mock')

    def __init__(self, vision=False, delay=0):
        self.delay = delay
        if vision:
            self.descriptor = Descriptor('mock-vision', modalities=('text', 'image'))

    async def run(self, invocation):
        await asyncio.sleep(self.delay)
        text = invocation.goal.lower()
        if any(a['mime'].startswith('image/') for a in invocation.attachments):
            answer = ('Synthetic vision fixture; not actual image inspection. Visible features (scripted): brick and metal pipes. '
                      'Interpretation: industrial/steampunk influence. Uncertainty: materials and historical period cannot be established.')
        elif 'yolk' in text:
            answer = 'Crack the egg into a bowl. Lift the yolk gently with clean fingers and let the white drain through into a second bowl. Wash your hands afterward.'
        elif 'book' in text or 'reading' in text:
            documents = invocation.context.get('documents', [])
            prefs = invocation.context.get('memories', [])
            books = [line.strip(' -') for doc in documents for line in doc['untrusted_text'].splitlines() if line.strip()]
            # Feedback on a project can reuse the previous request's inventory.
            if not books:
                books = invocation.context.get('book_inventory', [])
            preference_text = ' '.join(m['value'] for m in prefs) + ' ' + invocation.goal
            if 'short' in preference_text.lower():
                books.sort(key=lambda book: ('short' not in book.lower(), book.lower()))
            preferred = re.search(r'start with ([^.,;\n]+)', invocation.goal, re.I)
            if preferred:
                wanted = preferred.group(1).removesuffix(' instead').lower()
                books.sort(key=lambda book: not book.lower().startswith(wanted))
            answer = 'Reading plan (deterministic demonstration)\nPreferences used: ' + str([(m['subject'], m['value']) for m in prefs])
            answer += '\nUser-supplied inventory/preferences/feedback: ' + invocation.goal
            if books:
                answer += '\n' + '\n'.join(f'{i}. {book} — follows explicit first-book/short-first preference, otherwise supplied order.' for i, book in enumerate(books, 1))
            else:
                answer += '\nSupply an inventory with one book per line as a text attachment for a concrete ordering.'
            answer += '\nTrade-off: this mock uses labels, not literary judgment; use Codex for a tailored ordering.'

        else:
            answer = 'Recorded your request: ' + invocation.goal + '\nThis deterministic mock does not perform general reasoning or external actions. Select Codex for a real worker.'
        return Result(response='[MockWorker — simulated output]\n' + answer, usage={'worker_turns': 1})
