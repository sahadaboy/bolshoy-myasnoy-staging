"""CI-only SQLite -> actual PostgreSQL check. Refuses remote hosts/other DB names."""
import os
from pathlib import Path
import sys
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    import dj_database_url
    config = dj_database_url.parse(os.environ['STAGING_TEST_POSTGRES_URL'], conn_max_age=0)
    if config['HOST'] not in ('localhost', '127.0.0.1') or config['NAME'] != 'bm_transfer_ci':
        raise RuntimeError('Only the disposable localhost bm_transfer_ci test database is allowed.')
    os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings_build'
    import django
    django.setup()
    from django.conf import settings
    from django.core.management import call_command
    from django.db import connections
    from shop.models import Product, Category
    from deploy.snapshot import write_snapshot, restore_snapshot
    with TemporaryDirectory() as folder:
        connections.close_all()
        settings.DATABASES['default']['NAME'] = str(Path(folder) / 'source.sqlite3')
        settings.DATABASES['transfer_target'] = {**connections.settings['default'], **config, 'DISABLE_SERVER_SIDE_CURSORS': True}
        call_command('migrate', verbosity=0)
        call_command('migrate', database='transfer_target', verbosity=0)
        category = Category.objects.create(pk=71, name='Молочная продукция')
        product = Product.objects.create(pk=501, name='Молоко', sku='ci-milk', price='123.45')
        Product.categories.through.objects.create(pk=901, product=product, category=category)
        write_snapshot(Path(folder), Path(folder))
        restore_snapshot(Path(folder), using='transfer_target')
        assert Product.objects.using('transfer_target').get().pk == 501
        assert Product.categories.through.objects.using('transfer_target').get().pk == 901
        next_product = Product.objects.using('transfer_target').create(name='Sequence test', sku='ci-next', price='1')
        assert next_product.pk > 501
        assert Product.categories.through.objects.using('transfer_target').create(product=next_product, category_id=71).pk > 901
        connections.close_all()
    print('PostgreSQL transfer: data, IDs, M2M IDs and sequences verified.')


if __name__ == '__main__':
    main()
