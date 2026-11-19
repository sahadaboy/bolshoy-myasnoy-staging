"""Rehearse a JSONL backup restore in a NEW isolated PostgreSQL database only.

Uses the existing private QA config, never DATABASE_URL or .env.staging.
No restore into an existing database, no Render changes, no S3 operations.
The private report contains counts/checks only; never row contents or credentials.
"""
import argparse
from collections import Counter
from decimal import Decimal
import hashlib
import importlib
import json
import os
from pathlib import Path
import re
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def read_backup(folder):
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format') != 'postgres-public-jsonl-v1':
        raise ValueError('Unsupported backup format.')
    schema_file = folder / 'schema.json'
    if hashlib.sha256(schema_file.read_bytes()).hexdigest() != manifest['schema_sha256']:
        raise ValueError('Schema checksum mismatch.')
    schema = json.loads(schema_file.read_text(encoding='utf-8'))
    raw = {}
    for table, info in manifest['tables'].items():
        if not re.fullmatch(r'[a-z][a-z0-9_]*', table):
            raise ValueError('Invalid table name.')
        data = (folder / f'{table}.jsonl').read_bytes()
        if hashlib.sha256(data).hexdigest() != info['sha256']:
            raise ValueError(f'Checksum mismatch: {table}')
        lines = [line for line in data.decode('utf-8').splitlines() if line.strip()]
        if len(lines) != info['rows']:
            raise ValueError(f'Row count mismatch: {table}')
        raw[table] = '[' + ','.join(lines) + ']'
    return manifest, schema, raw


def decoded_rows(payload):
    return json.loads(payload, parse_float=Decimal)


def same_rows(first, second):
    # PostgreSQL JSON field/key order and heap row order do not affect equality.
    # Decimal preserves numeric values; do not round through binary floats.
    def canonical(rows):
        return Counter(json.dumps(row, sort_keys=True, ensure_ascii=False, default=str)
                       for row in rows)
    return canonical(first) == canonical(second)


def run(options):
    import psycopg
    from psycopg import sql
    folder = Path(options.backup).resolve()
    manifest, schema, raw = read_backup(folder)
    report_path = Path(options.report).resolve()
    if report_path.exists():
        raise ValueError('Report already exists; use a new report file.')
    qa = json.loads(Path(options.qa_config).read_text(encoding='utf-8'))
    source = dict(qa['connection'])
    if not source.get('dbname', '').startswith('bm_codex_qa_'):
        raise ValueError('Only a dedicated bm_codex_qa_ maintenance database is allowed.')
    name = 'bm_codex_restore_' + uuid.uuid4().hex[:12]
    # CREATE only. An existing database is never truncated, reused or replaced.
    with psycopg.connect(**source, autocommit=True) as maintenance:
        if maintenance.execute('SELECT 1 FROM pg_database WHERE datname=%s', (name,)).fetchone():
            raise ValueError('Restore database already exists; refusing to reuse it.')
        maintenance.execute(sql.SQL('CREATE DATABASE {}').format(sql.Identifier(name)))
    report = {'format':'backup-restore-rehearsal-v1', 'target_database':name,
              'backup_created_at':manifest['created_at'],
              'backup_manifest_sha256':hashlib.sha256((folder/'manifest.json').read_bytes()).hexdigest(),
              'new_empty_database':True, 'production_connection_used':False,
              'object_storage_modified':False}
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps({**report, 'complete':False}, indent=2), encoding='utf-8')
    print('Created a new isolated restore database.', flush=True)

    from django.conf import settings
    config = importlib.import_module('config.settings_build')
    values = {key:getattr(config,key) for key in dir(config) if key.isupper()}
    values.update(DATABASES={'default':{
        'ENGINE':'django.db.backends.postgresql','NAME':name,
        'HOST':source['host'],'PORT':source.get('port',5432),
        'USER':source['user'],'PASSWORD':source['password'],
        'OPTIONS':{'sslmode':'require','connect_timeout':10},
        'DISABLE_SERVER_SIDE_CURSORS':True, 'CONN_MAX_AGE':0}},
        TELEGRAM_BOT_TOKEN='', TELEGRAM_NOTIFICATIONS_ENABLED=False,
        MINIAPP_ORDERS_ENABLED=False, STAGING_DEPLOYMENT=False)
    settings.configure(**values)
    import django
    django.setup()
    from django.db import connection, transaction
    from django.db.migrations.executor import MigrationExecutor

    with connection.cursor() as cursor:
        cursor.execute('SELECT current_database()')
        if cursor.fetchone()[0] != name or not name.startswith('bm_codex_restore_'):
            raise ValueError('Wrong restore target.')
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='public'")
        if cursor.fetchall():
            raise ValueError('New restore database must be empty.')
    executor = MigrationExecutor(connection)
    applied = {(row['app'],row['name']) for row in decoded_rows(raw['django_migrations'])}
    if applied - executor.loader.graph.nodes.keys():
        raise ValueError('Backup references migrations absent from this checkout.')
    targets = [key for key in applied if not any(child.key in applied
                for child in executor.loader.graph.node_map[key].children)]
    executor.migrate(targets)
    print('Recreated the exact migration level recorded in the backup.', flush=True)
    quote = connection.ops.quote_name
    expected_columns = [tuple(row) for row in schema['columns']]
    with transaction.atomic(), connection.cursor() as cursor:
        cursor.execute("SELECT table_name,column_name,data_type,is_nullable,column_default FROM information_schema.columns WHERE table_schema='public' ORDER BY table_name,ordinal_position")
        if cursor.fetchall() != expected_columns:
            raise ValueError('Reconstructed schema differs from the backup.')
        cursor.execute("SELECT tablename FROM pg_tables WHERE schemaname='public' ORDER BY tablename")
        if [row[0] for row in cursor.fetchall()] != sorted(raw):
            raise ValueError('Reconstructed table set differs from the backup.')
        # The target was created above and verified empty before migrations.
        # Remove only migration-generated seed rows, then load the exact snapshot.
        cursor.execute('TRUNCATE TABLE ' + ','.join('public.'+quote(table) for table in raw) + ' RESTART IDENTITY')
        cursor.execute('SET CONSTRAINTS ALL DEFERRED')
        for table, payload in raw.items():
            cursor.execute(f'INSERT INTO public.{quote(table)} SELECT * FROM json_populate_recordset(NULL::public.{quote(table)}, %s::json)', [payload])
        cursor.execute('SET CONSTRAINTS ALL IMMEDIATE')
    print('Loaded all backup tables; foreign key and check constraints passed.', flush=True)

    checked = {}
    for table, payload in raw.items():
        with connection.cursor() as cursor:
            cursor.execute(f'SELECT row_to_json(t)::text FROM public.{quote(table)} t')
            actual = [json.loads(row[0], parse_float=Decimal) for row in cursor]
        if not same_rows(decoded_rows(payload), actual):
            raise ValueError(f'Restored values/IDs differ: {table}')
        checked[table] = len(actual)
    with connection.cursor() as cursor:
        cursor.execute("SELECT c.relname,p.conname,pg_get_constraintdef(p.oid) FROM pg_constraint p JOIN pg_class c ON c.oid=p.conrelid JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' ORDER BY c.relname,p.conname")
        if cursor.fetchall() != [tuple(row) for row in schema['constraints']]:
            raise ValueError('Constraint definitions differ from the backup.')
        cursor.execute("SELECT table_name,column_name FROM information_schema.columns WHERE table_schema='public' AND (is_identity='YES' OR column_default LIKE 'nextval(%') ORDER BY table_name,column_name")
        sequence_columns = cursor.fetchall()
        for table, column in sequence_columns:
            cursor.execute('SELECT pg_get_serial_sequence(%s,%s)', ['public.'+quote(table), column])
            sequence = cursor.fetchone()[0]
            cursor.execute(f'SELECT MAX({quote(column)}) FROM public.{quote(table)}')
            maximum = cursor.fetchone()[0]
            cursor.execute('SELECT setval(%s::regclass,%s,%s)', [sequence, maximum if maximum is not None else 1, maximum is not None])
            cursor.execute('SELECT nextval(%s::regclass)', [sequence])
            if cursor.fetchone()[0] <= (maximum if maximum is not None else 0):
                raise ValueError('Sequence would reuse a restored ID.')
            cursor.execute('SELECT setval(%s::regclass,%s,%s)', [sequence, maximum if maximum is not None else 1, maximum is not None])
    report.update(tables_restored=checked, all_values_and_ids_match=True,
        constraints_match=True, foreign_keys_valid=True, sequences_verified=len(sequence_columns))
    print('All row values/IDs and next generated IDs verified.', flush=True)

    # Rehearse only the pending release migrations, not the application test suite.
    executor = MigrationExecutor(connection)
    pending = executor.migration_plan(executor.loader.graph.leaf_nodes())
    report['release_migrations'] = [migration.name for migration, backwards in pending]
    executor.migrate(executor.loader.graph.leaf_nodes())
    protected = ['shop_product','shop_category','shop_product_categories','storefront_customer',
        'storefront_order','storefront_orderitem','storefront_ordernotification',
        'storefront_orderstatusevent','storefront_storephoto','auth_user']
    for table in protected:
        with connection.cursor() as cursor:
            cursor.execute(f'SELECT row_to_json(t)::text FROM public.{quote(table)} t')
            actual = [json.loads(row[0], parse_float=Decimal) for row in cursor]
        if not same_rows(decoded_rows(raw[table]), actual):
            raise ValueError(f'Release migrations changed protected data: {table}')
    report.update(protected_tables_unchanged_after_release=protected, complete=True)
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    connection.close()
    print(json.dumps({'complete':True,'tables':len(checked),'rows':sum(checked.values()),
        'sequences':len(sequence_columns),'migrations':report['release_migrations'],
        'production_database_unchanged':True}))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backup', required=True)
    parser.add_argument('--qa-config', required=True, help='Private existing QA JSON, never production .env.')
    parser.add_argument('--report', required=True, help='New private report file.')
    arguments = parser.parse_args()
    try:
        run(arguments)
    except Exception as error:
        # Database driver exceptions can contain private row values/DSNs.
        print('Restore rehearsal failed (' + type(error).__name__ + '). No production connection was used.', file=sys.stderr)
        if type(error) is ValueError:
            print(str(error), file=sys.stderr)
        sys.exit(1)
