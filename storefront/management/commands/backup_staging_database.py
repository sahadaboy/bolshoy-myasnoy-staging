"""Consistent read-only logical backup. Never restores or imports anything."""
import hashlib
import json
from pathlib import Path
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import connection, transaction
from django.utils import timezone


class Command(BaseCommand):
    help = 'Сохранить все публичные таблицы PostgreSQL одним read-only снимком в приватную папку backups.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('--output', required=True, help='Новая папка внутри backups; никогда не включайте её в Git.')

    def handle(self, *args, **options):
        if connection.vendor != 'postgresql' or not getattr(settings, 'STAGING_DEPLOYMENT', False):
            raise CommandError('Требуются явные config.settings_staging и PostgreSQL. Локальные SQLite не используются.')
        folder = Path(options['output']).resolve()
        if 'backups' not in folder.parts or folder.exists():
            raise CommandError('Укажите новую несуществующую папку внутри backups. Существующие копии не перезаписываются.')
        folder.mkdir(parents=True)
        manifest = {'format': 'postgres-public-jsonl-v1', 'created_at': timezone.now().isoformat(),
                    'read_only': True, 'tables': {}}
        try:
            with transaction.atomic(), connection.cursor() as cursor:
                cursor.execute('SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY')
                cursor.execute("SELECT tablename FROM pg_catalog.pg_tables WHERE schemaname='public' ORDER BY tablename")
                tables = [row[0] for row in cursor.fetchall()]
                cursor.execute("SELECT table_name,column_name,data_type,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name,ordinal_position")
                columns = cursor.fetchall()
                cursor.execute("SELECT c.relname,p.conname,pg_get_constraintdef(p.oid) FROM pg_constraint p JOIN pg_class c ON c.oid=p.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY c.relname,p.conname")
                constraints = cursor.fetchall()
                (folder/'schema.json').write_text(json.dumps({'columns':columns,'constraints':constraints},ensure_ascii=False,indent=2),encoding='utf-8')
                quote = connection.ops.quote_name
                for table in tables:
                    cursor.execute(f'SELECT row_to_json(t)::text FROM {quote("public")}.{quote(table)} t')
                    count, digest = 0, hashlib.sha256()
                    with (folder/f'{table}.jsonl').open('wb') as target:
                        for row in cursor:
                            value = (row[0]+'\n').encode('utf-8')
                            target.write(value); digest.update(value); count += 1
                    manifest['tables'][table] = {'rows':count,'sha256':digest.hexdigest()}
            manifest['schema_sha256'] = hashlib.sha256((folder/'schema.json').read_bytes()).hexdigest()
            # Manifest is written last: its absence means an incomplete copy.
            (folder/'manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2),encoding='utf-8')
        except Exception:
            raise CommandError('Копия не завершена: manifest.json отсутствует. База не изменялась. Проверьте соединение и доступ к папке.') from None
        self.stdout.write(self.style.SUCCESS(f'Read-only backup complete: {len(tables)} tables; manifest.json and SHA-256 saved.'))
