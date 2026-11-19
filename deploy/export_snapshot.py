"""Run with the staging venv, from the project root. Source SQLite is read-only."""
import argparse
import json
import os
from pathlib import Path
import sqlite3
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--output', required=True, help='New directory under .staging-transfer/')
    args = parser.parse_args()
    folder = (ROOT / args.output).resolve()
    if not folder.is_relative_to(ROOT / '.staging-transfer') or folder.exists():
        parser.error('Use a new directory inside .staging-transfer/. Never export into a Git directory.')
    folder.mkdir(parents=True)
    from hashlib import file_digest
    def file_hash(path):
        with path.open('rb') as file:
            return file_digest(file, 'sha256').hexdigest()
    sources = {}
    for relative, target in [('db.sqlite3', 'source.sqlite3'), ('frontend/content.sqlite3', 'legacy-content.sqlite3')]:
        source = ROOT / relative
        if not source.is_file():
            raise RuntimeError(f'Missing source: {relative}')
        before = file_hash(source)
        with sqlite3.connect(source.as_uri() + '?mode=ro', uri=True) as origin, sqlite3.connect(folder / target) as destination:
            origin.backup(destination)
        if file_hash(source) != before:
            raise RuntimeError('Source changed during export. Stop local writes and repeat with a new folder.')
        sources[relative] = before
    with sqlite3.connect((folder / 'legacy-content.sqlite3').as_uri() + '?mode=ro', uri=True) as legacy:
        legacy_counts = {name: legacy.execute(f'SELECT COUNT(*) FROM "{name}"').fetchone()[0] for name in ('storefront_content_banner', 'storefront_content_categoryimage')}
    if any(legacy_counts.values()):
        raise RuntimeError('Legacy content is not empty. Stop: it needs an explicit mapping to storefront before migration.')
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
    os.environ['MINIAPP_DATABASE'] = str(folder / 'source.sqlite3')
    import django
    django.setup()
    from django.conf import settings
    settings.DATABASES['default']['NAME'] = (folder / 'source.sqlite3').as_uri() + '?mode=ro'
    settings.DATABASES['default']['OPTIONS'] = {'uri': True}
    from deploy.snapshot import write_snapshot
    manifest = write_snapshot(folder, ROOT)
    manifest.update(source_hashes=sources, legacy_content={'used_by_current_app': False, 'counts': legacy_counts})
    (folder / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    for name, expected in sources.items():
        if file_hash(ROOT / name) != expected:
            raise RuntimeError('Source changed during export. Re-export after stopping local writes.')
    print(json.dumps({'folder': str(folder), 'products': manifest['counts']['shop.product'], 'categories': manifest['counts']['shop.category'],
                      'category_links': manifest['counts']['shop.product_categories'], 'media_files': len(manifest['media']),
                      'media_bytes': sum(item['size'] for item in manifest['media']), 'source_unchanged': True}, indent=2))


if __name__ == '__main__':
    main()
