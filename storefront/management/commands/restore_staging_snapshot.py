from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from deploy.snapshot import restore_snapshot


class Command(BaseCommand):
    help = 'Restore a private verified snapshot into an EMPTY staging PostgreSQL database. Never touches local SQLite.'

    def add_arguments(self, parser):
        parser.add_argument('folder', type=Path)

    def handle(self, *args, **options):
        if not getattr(settings, 'STAGING_DEPLOYMENT', False) or connection.vendor != 'postgresql':
            raise CommandError('Use config.settings_staging and a new PostgreSQL target. Local SQLite import is forbidden.')
        try:
            manifest = restore_snapshot(options['folder'])
        except (ValueError, OSError) as exc:
            raise CommandError(str(exc)) from None
        self.stdout.write(self.style.SUCCESS(f"Verified import: {manifest['counts']['shop.product']} products; all exported IDs, fields and relations match."))
