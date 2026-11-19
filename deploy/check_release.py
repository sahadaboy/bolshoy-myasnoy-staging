"""Fail CI if private/local artifacts were accidentally tracked in Git."""
from pathlib import PurePosixPath
import re
import subprocess


def forbidden(name):
    path = PurePosixPath(name)
    allowed_examples = {'.env.example', '.env.staging.example'}
    if path.name.startswith('.env') and path.name not in allowed_examples:
        return True
    if any(part in {'.venv', '.venv-staging', '.staging-transfer', '.runtime', '.build', '.codex', '.agents', '.tools', '.asset_sources', '.pnpm-store', '__pycache__', 'backups', 'node_modules', 'products', 'storefront_uploads', 'content_uploads', 'temp_imports', 'qa'} for part in path.parts):
        return True
    return bool(re.search(r'\.(?:sqlite3(?:-.*)?|db|dump|sql|xlsx|csv|log|pem|key|exe|py[co])$', name, re.I))


if __name__ == '__main__':
    names = subprocess.check_output(['git', 'ls-files', '-z'], text=True).split('\0')
    invalid = [name for name in names if name and forbidden(name)]
    if invalid:
        raise SystemExit('Private/local files tracked in Git; remove from staging index: ' + ', '.join(invalid))
    print('Tracked-file boundary passed.')
