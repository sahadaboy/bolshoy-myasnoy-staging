"""Small server-only .env loader. Existing process values take precedence."""
import os
import re
import tempfile


def load_env(path):
    if not path.is_file():
        return
    for line in path.read_text(encoding='utf-8-sig').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, value = line.split('=', 1)
        key, value = key.strip(), value.strip()
        if not re.fullmatch(r'[A-Z][A-Z0-9_]*', key):
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ('"', "'"):
            value = value[1:-1]
        os.environ.setdefault(key, value)


def save_public_url(path, value):
    """Replace only the public URL; never display or rewrite other env values."""
    if not isinstance(value, str) or any(char in value for char in '\r\n'):
        raise ValueError('Public URL must be a single line.')
    content = path.read_text(encoding='utf-8-sig') if path.exists() else ''
    lines, found = [], False
    for line in content.splitlines(keepends=True):
        if re.match(r'^\s*MINIAPP_PUBLIC_URL\s*=', line):
            if not found:
                lines.append(f'MINIAPP_PUBLIC_URL={value}\n')
                found = True
        else:
            lines.append(line)
    if not found:
        if lines and not lines[-1].endswith(('\n', '\r')):
            lines.append('\n')
        lines.append(f'MINIAPP_PUBLIC_URL={value}\n')
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode='w', encoding='utf-8', dir=path.parent,
                                         prefix='.env.', suffix='.tmp', delete=False) as handle:
            temporary = handle.name
            handle.write(''.join(lines))
            handle.flush()
            os.fsync(handle.fileno())
        if path.exists():
            os.chmod(temporary, path.stat().st_mode & 0o777)
        os.replace(temporary, path)
    finally:
        if temporary and os.path.exists(temporary):
            os.unlink(temporary)
