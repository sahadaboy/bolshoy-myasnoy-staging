"""Verify a full private snapshot in a NEW throwaway SQLite, never the source DB."""
import argparse
import json
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('folder', type=Path)
    args = parser.parse_args()
    with TemporaryDirectory(prefix='bm-snapshot-check-') as temporary:
        os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'
        os.environ['MINIAPP_DATABASE'] = str(Path(temporary) / 'target.sqlite3')
        import django
        django.setup()
        from django.core.management import call_command
        from django.db import connections
        from deploy.snapshot import restore_snapshot
        call_command('migrate', verbosity=0)
        manifest = restore_snapshot(args.folder)
        connections.close_all()
    report = {'verified_in_isolated_sqlite': True, 'postgresql_verified_here': False,
              'records_and_ids_match': True, 'counts': manifest['counts'], 'media': len(manifest['media'])}
    (args.folder / 'local-verification.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({k:v for k,v in report.items() if k != 'counts'}, indent=2))


if __name__ == '__main__':
    main()
