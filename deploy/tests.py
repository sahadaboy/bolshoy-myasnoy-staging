from io import BytesIO, StringIO
from decimal import Decimal
from importlib.util import find_spec
import json
import os
from pathlib import Path
import subprocess
import sys
from tempfile import TemporaryDirectory
from types import SimpleNamespace
from unittest.mock import patch
from unittest import skipUnless
from django.conf import settings
from django.core.management import call_command, CommandError
from django.test import TestCase, SimpleTestCase, override_settings
from PIL import Image
from shop.models import Product, Category
from .snapshot import write_snapshot, read_snapshot, restore_snapshot, digest, records
from .collect_frontend import collect


class SnapshotTests(TestCase):
    def make_snapshot(self, folder):
        root = Path(folder)
        (root / 'products').mkdir()
        Image.new('RGB', (2, 2), 'red').save(root / 'products/test.png')
        category = Category.objects.create(pk=71, name='Категория')
        product = Product.objects.create(pk=501, name='Продукт', sku='snapshot-product', price='123.45', image='products/test.png')
        Product.categories.through.objects.create(pk=901, product=product, category=category)
        return write_snapshot(root, root)

    def test_roundtrip_keeps_product_category_and_through_ids_and_all_values(self):
        with TemporaryDirectory() as folder:
            manifest = self.make_snapshot(folder)
            self.assertEqual(len(manifest['media']), 1)
            Product.objects.all().delete(); Category.objects.all().delete()
            restore_snapshot(folder)
            self.assertEqual(digest(records()), manifest['records_sha256'])
            self.assertEqual(Product.objects.get().pk, 501)
            self.assertEqual(Product.categories.through.objects.get().pk, 901)
            self.assertEqual(Product.objects.get().price, Decimal('123.45'))
            with self.assertRaisesRegex(ValueError, 'Refusing'):
                restore_snapshot(folder)

    def test_corruption_is_detected_before_database_changes(self):
        with TemporaryDirectory() as folder:
            self.make_snapshot(folder)
            (Path(folder) / 'data.json').write_text('[]', encoding='utf-8')
            with self.assertRaises(ValueError): read_snapshot(folder)
            self.assertEqual(Product.objects.count(), 1)
            with self.assertRaises(CommandError):
                call_command('restore_staging_snapshot', folder, stdout=StringIO())

    @skipUnless(find_spec('botocore'), 'Requires the separate staging dependencies.')
    def test_media_upload_is_checked_idempotent_and_never_overwrites_different_bytes(self):
        from botocore.exceptions import ClientError
        with TemporaryDirectory() as folder, self.settings(STAGING_DEPLOYMENT=True):
            self.make_snapshot(folder)
            class Client:
                def __init__(self): self.data = {}; self.puts = 0
                def head_object(self, Bucket, Key):
                    if Key not in self.data: raise ClientError({'Error':{'Code':'404'}}, 'HeadObject')
                    return {}
                def put_object(self, Bucket, Key, Body, **kwargs):
                    self.data[Key] = Body.read(); self.puts += 1
                def get_object(self, Bucket, Key): return {'Body':BytesIO(self.data[Key])}
            client = Client()
            storage = SimpleNamespace(bucket_name='test', connection=SimpleNamespace(meta=SimpleNamespace(client=client)))
            with patch('storefront.management.commands.upload_staging_media.default_storage', storage):
                call_command('upload_staging_media', folder, dry_run=True, stdout=StringIO())
                self.assertEqual(client.puts, 0)
                for _ in range(2): call_command('upload_staging_media', folder, stdout=StringIO())
                self.assertEqual(client.puts, 1)
                self.assertEqual(set(client.data), {'products/test.png'})
                client.data['products/test.png'] = b'changed'
                with self.assertRaises(CommandError): call_command('upload_staging_media', folder, stdout=StringIO())
                self.assertEqual(client.puts, 1)


class StagingBoundaryTests(SimpleTestCase):
    def test_only_explicit_boot_assets_are_published_for_the_html_splash(self):
        with TemporaryDirectory() as folder:
            root=Path(folder);source=root/'dist';target=root/'published';source.mkdir()
            for name in ('index.html','boot.js','boot.css','private-helper.js'):
                (source/name).write_text('test-build')
            collect(source,target)
            self.assertEqual((target/'boot.js').read_text(),'test-build')
            self.assertEqual((target/'boot.css').read_text(),'test-build')
            self.assertFalse((target/'private-helper.js').exists())

    def test_asset_collection_never_copies_preview_source_env_or_maps(self):
        with TemporaryDirectory() as folder:
            source, target = Path(folder) / 'dist', Path(folder) / 'public'
            (source / 'assets').mkdir(parents=True)
            for name in ('app-Abc123.js', 'app.js.map', '.env', 'source.ts'):
                (source / 'assets' / name).write_text('fixture')
            (source / 'index.html').write_text('<h1>App</h1>')
            (source / 'private.sqlite3').write_text('private')
            collect(source, target)
            self.assertTrue((target / 'assets/app-Abc123.js').is_file())
            self.assertEqual([p.name for p in target.rglob('*') if p.is_file()], ['app-Abc123.js'])

    @override_settings(ROOT_URLCONF='config.urls_staging', DEBUG=False)
    def test_spa_is_embeddable_and_arbitrary_files_api_and_media_do_not_fall_back_to_html(self):
        with TemporaryDirectory() as folder:
            root = Path(folder)
            (root / 'frontend/dist').mkdir(parents=True)
            (root / 'frontend/dist/index.html').write_text('<h1>Compiled app</h1>')
            with self.settings(BASE_DIR=root):
                response = self.client.get('/profile')
                self.assertEqual(response.status_code, 200)
                self.assertIsNone(response.get('X-Frame-Options'))
                response.close()
                response = self.client.get('/profile/orders/22222222-2222-4222-8222-222222222222/success')
                self.assertEqual(response.status_code, 200)
                response.close()
                for path in ('/.env', '/db.sqlite3', '/src/main.tsx', '/api/private/', '/media/products/a.png', '/backups/a.zip'):
                    self.assertEqual(self.client.get(path).status_code, 404, path)

    @skipUnless(find_spec('dj_database_url') and find_spec('psycopg'), 'Requires the separate staging dependencies.')
    def test_staging_settings_default_closed_and_allow_explicit_opt_in_without_changing_database(self):
        environment = {**os.environ, 'DJANGO_SETTINGS_MODULE':'config.settings_staging',
            'DJANGO_SECRET_KEY':'ci-security-test-only-0123456789-abcdefghijklmnopqrstuvwxyz-987654321',
            'DATABASE_URL':'postgresql://fixture:fixture@localhost/staging?sslmode=require',
            'STAGING_ALLOWED_HOSTS':'staging.example',
            'AWS_ENDPOINT_URL_S3':'https://fixture.storage.eu-central-1.aws.neon.tech',
            'AWS_STORAGE_BUCKET_NAME':'test', 'AWS_ACCESS_KEY_ID':'fixture', 'AWS_SECRET_ACCESS_KEY':'fixture', 'AWS_REGION':'eu-central-1',
            'MINIAPP_ORDERS_ENABLED':'0', 'TELEGRAM_NOTIFICATIONS_ENABLED':'0', 'DJANGO_DEBUG':'1',
            'STAGING_PICKUP_ENABLED':'0',
            'TELEGRAM_ADMIN_CHAT_ID':'-100001', 'TELEGRAM_BOT_TOKEN':'ci-bot-placeholder'}
        code = 'import django,json; django.setup(); from django.conf import settings as s; print(json.dumps([s.DEBUG,s.MINIAPP_ORDERS_ENABLED,s.TELEGRAM_NOTIFICATIONS_ENABLED,s.DATABASES["default"]["ENGINE"],s.STORAGES["default"]["OPTIONS"]["addressing_style"]]))'
        result = subprocess.run([sys.executable, '-c', code], env=environment, cwd=settings.BASE_DIR, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), [False,False,False,'django.db.backends.postgresql','path'])
        environment.update(MINIAPP_ORDERS_ENABLED='1', TELEGRAM_NOTIFICATIONS_ENABLED='1')
        result = subprocess.run([sys.executable, '-c', code], env=environment, cwd=settings.BASE_DIR, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), [False,False,False,'django.db.backends.postgresql','path'])
        environment['STAGING_PICKUP_ENABLED'] = '1'
        result = subprocess.run([sys.executable, '-c', code], env=environment, cwd=settings.BASE_DIR, capture_output=True, text=True, check=True)
        self.assertEqual(json.loads(result.stdout), [False,True,True,'django.db.backends.postgresql','path'])
        environment['TELEGRAM_ADMIN_CHAT_ID'] = ''
        result = subprocess.run([sys.executable, '-c', code], env=environment, cwd=settings.BASE_DIR, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
        environment['TELEGRAM_ADMIN_CHAT_ID'] = '-100001'
        environment['DATABASE_URL'] = 'sqlite:///local.sqlite3'
        result = subprocess.run([sys.executable, '-c', code], env=environment, cwd=settings.BASE_DIR, capture_output=True, text=True)
        self.assertNotEqual(result.returncode, 0)
