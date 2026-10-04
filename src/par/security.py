"""Conservative text redaction; never a substitute for withholding credentials."""
import re
from pathlib import Path

def redact(text: str) -> str:
    text = re.sub(r'(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|authorization|cookie)\s*[:=]\s*(?:bearer\s+)?[^\s,;\"\'{}\[\]]+', r'\1=[REDACTED]', text)
    return re.sub(r'\b(?:sk-[A-Za-z0-9_-]{8,}|gh[pousr]_[A-Za-z0-9_]+)\b', '[REDACTED]', text)

def inside(root: Path, relative: str) -> Path:
    path = (root / relative).resolve()
    if Path(relative).is_absolute() or path == root.resolve() or not path.is_relative_to(root.resolve()):
        raise ValueError("Path escapes approved storage")
    return path


def redact_data(value):
    if isinstance(value, dict):
        return {k: '[REDACTED]' if re.fullmatch(r'(?i)(api[_-]?key|access[_-]?token|refresh[_-]?token|password|secret|authorization|cookie)', k) else redact_data(v) for k, v in value.items()}
    if isinstance(value, list):
        return [redact_data(v) for v in value]
    return redact(value) if isinstance(value, str) else value
