from decimal import Decimal
from io import BytesIO
import re
from zipfile import ZipFile, ZIP_DEFLATED
from unittest.mock import patch
from uuid import uuid4

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from openpyxl import Workbook

from .excel_import import ImportProblem, parse_barcode, read_excel
from .models import CatalogImport, Category, ImportSource, Product, ProductIdentifier, SourceProduct
from .price_import import apply_import, create_preview, product_snapshot, revise_preview, rollback_import


HEADERS = ['Название', 'Ед. изм.', 'Цена', 'Код', 'Штрихкод', 'Производитель', 'Фасовка', 'Категория', 'SKU']


def xlsx(rows, headers=HEADERS, title='Прайс'):
    workbook = Workbook()
    workbook.active.title = title
    workbook.active.append(headers)
    for row in rows:
        workbook.active.append(row)
    file = BytesIO()
    workbook.save(file)
    file.seek(0)
    file.name = 'price.xlsx'
    return file


def row(name='Товар', price='100', unit='шт', code='', barcode='', manufacturer='', package='', category='Прайс', sku=''):
    return [name, unit, price, code, barcode, manufacturer, package, category, sku]


class PriceImportTests(TestCase):
    def setUp(self):
        self.source = ImportSource.objects.create(name='Основной поставщик')
        self.category = Category.objects.create(name='Прайс')
        self.product = Product.objects.create(name='Товар', sku='KEEP-SKU', price='90', unit='pcs',
            image='products/real.jpg', description='Описание магазина', is_available=False)
        self.manual = Category.objects.create(name='Ручная подборка')
        self.product.categories.add(self.manual)

    def preview(self, rows=None, mode='partial', source=None, policy='add', **kwargs):
        return create_preview(xlsx(rows if rows is not None else [row()]), source or self.source, mode,
                              category_policy=policy, **kwargs)

    def apply(self, batch, **kwargs):
        return apply_import(batch.pk, batch.version, confirm=True, **kwargs)

    def test_preview_is_read_only_and_reports_real_changes(self):
        before = product_snapshot(self.product)
        batch = self.preview([row(), row('Новый')])
        self.product.refresh_from_db()
        self.assertEqual(product_snapshot(self.product), before)
        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(batch.plan['summary']['matched'], 1)
        self.assertEqual(batch.plan['summary']['new'], 1)
        self.assertEqual(batch.plan['summary']['prices'], 1)

    def test_repeated_file_preserves_id_sku_and_does_not_duplicate(self):
        self.apply(self.preview([row(code='supplier-1'), row('Новый', code='supplier-2')]))
        ids = list(Product.objects.order_by('pk').values_list('pk', 'sku'))
        again = self.preview([row(code='supplier-1'), row('Новый', code='supplier-2')])
        self.assertEqual(again.plan['summary']['new'], 0)
        self.assertEqual(again.plan['summary']['prices'], 0)
        self.apply(again)
        self.assertEqual(list(Product.objects.order_by('pk').values_list('pk', 'sku')), ids)
        self.assertEqual(Product.objects.get(pk=self.product.pk).sku, 'KEEP-SKU')

    def test_price_change_and_new_product_do_not_change_stock_flag(self):
        self.apply(self.preview([row(price='105,99'), row('Весовой', '750', 'кг')]))
        self.product.refresh_from_db()
        self.assertEqual(self.product.price, Decimal('105.99'))
        self.assertFalse(self.product.is_available)
        weight = Product.objects.get(name='Весовой')
        self.assertEqual((weight.unit, weight.min_quantity, weight.quantity_step), ('kg', Decimal('.5'), Decimal('.1')))

    def test_existing_quantity_rules_are_previewed_and_preserved(self):
        self.product.min_quantity, self.product.quantity_step = Decimal('.5'), Decimal('.1')
        self.product.save()
        batch = self.preview()
        self.assertEqual(batch.plan['rows'][0]['min_quantity'], '0.500')
        self.assertEqual(batch.plan['rows'][0]['quantity_step'], '0.100')
        self.apply(batch)
        self.product.refresh_from_db()
        self.assertEqual((self.product.min_quantity, self.product.quantity_step), (Decimal('.5'), Decimal('.1')))

    def test_partial_file_keeps_missing_products_active(self):
        self.apply(self.preview([row(code='a'), row('Второй', code='b')]))
        partial = self.preview([row(code='a')])
        self.apply(partial)
        self.assertTrue(Product.objects.get(name='Второй').is_active)
        with self.assertRaises(ImportProblem):
            self.apply(self.preview([row(code='a')]), archive_missing=True)

    def test_full_file_proposes_archive_with_separate_confirmations_and_scope(self):
        unrelated = Product.objects.create(name='Не из этого источника', sku='other', price=5)
        first = self.preview([row(code='a'), row('Второй', code='b')], mode='full')
        self.assertEqual(first.plan['missing'], [])
        self.apply(first)
        full = self.preview([row(code='a')], mode='full')
        missing_id = Product.objects.get(name='Второй').pk
        self.assertEqual([item['product_id'] for item in full.plan['missing']], [missing_id])
        with self.assertRaisesMessage(ImportProblem, 'ручную проверку'):
            self.apply(full, archive_missing=True)
        self.apply(full, reviewed_drop=True, archive_missing=True)
        self.assertFalse(Product.objects.get(pk=missing_id).is_active)
        self.assertTrue(Product.objects.get(pk=unrelated.pk).is_active)
        self.assertFalse(Product.objects.get(pk=self.product.pk).is_available)
        self.assertNotIn(missing_id, [item['id'] for item in self.client.get('/api/products/').json()['results']])

    def test_full_without_archive_confirmation_leaves_absent_products_untouched(self):
        self.apply(self.preview([row(code='a'), row('Второй', code='b')]))
        self.apply(self.preview([row(code='a')], mode='full'), reviewed_drop=True)
        self.assertTrue(Product.objects.get(name='Второй').is_active)

    def test_product_stays_active_if_another_source_still_lists_it(self):
        self.apply(self.preview([row(code='a'), row('Второй', code='b')]))
        other = ImportSource.objects.create(name='Второй источник')
        self.apply(self.preview([row('Второй', code='second')], source=other))
        self.apply(self.preview([row(code='a')], mode='full'), reviewed_drop=True, archive_missing=True)
        self.assertTrue(Product.objects.get(name='Второй').is_active)

    def test_rename_uses_source_id_and_manual_link_when_id_is_absent(self):
        self.apply(self.preview([row(code='a')]))
        renamed = self.preview([row('Товар переименован', code='a')])
        self.assertEqual(renamed.plan['summary']['names'], 1)
        self.apply(renamed)
        no_code = self.preview([row('Другое написание')])
        reviewed = revise_preview(no_code.pk, no_code.version,
                                  decisions={'0': {'action': 'link', 'product_id': self.product.pk}})
        self.apply(reviewed)
        self.assertEqual(Product.objects.count(), 1)
        self.assertEqual(Product.objects.get().name, 'Другое написание')

    def test_unique_gtin_matches_across_sources_and_conflicting_identifiers_block(self):
        gtin = '4601234567893'
        self.assertEqual(parse_barcode(gtin), gtin)
        self.apply(self.preview([row(code='a', barcode=gtin), row('Второй', code='b')]))
        other = ImportSource.objects.create(name='Другой')
        renamed = self.preview([row('Новое название', barcode=gtin)], source=other)
        self.assertEqual(renamed.plan['rows'][0]['product_id'], self.product.pk)
        self.apply(renamed)
        conflict = self.preview([row('Второй', code='b', barcode=gtin)])
        with self.assertRaises(ImportProblem):
            self.apply(conflict)

    def test_conflicting_duplicate_prices_block_whole_import(self):
        batch = self.preview([row(price=100), row(price=200), row('Корректный')])
        self.assertEqual(batch.plan['summary']['duplicates'], 1)
        self.assertEqual(batch.plan['summary']['errors'], 1)
        with self.assertRaises(ImportProblem):
            self.apply(batch, accept_errors=True)
        self.assertEqual(Product.objects.count(), 1)
        fixed = revise_preview(batch.pk, batch.version, decisions={'0': {'action': 'skip'}})
        self.apply(fixed)
        self.assertTrue(Product.objects.filter(name='Корректный').exists())

    def test_identical_duplicates_merge_categories_without_losing_manual_ones(self):
        extra = Category.objects.create(name='Дополнительная')
        batch = self.preview([row(), row(category=extra.name)])
        self.assertEqual(batch.plan['summary']['duplicates'], 1)
        self.apply(batch)
        self.assertEqual(set(self.product.categories.values_list('pk', flat=True)),
                         {self.manual.pk, self.category.pk, extra.pk})

    def test_invalid_prices_are_reported_and_require_explicit_partial_apply(self):
        batch = self.preview([row('Плохой' + str(index), value) for index, value in
                              enumerate(['-1', 'NaN', 'Infinity', '', True, '12.345'])] + [row()])
        self.assertEqual(batch.plan['summary']['errors'], 6)
        with self.assertRaises(ImportProblem):
            self.apply(batch)
        self.apply(batch, accept_errors=True)
        self.assertEqual(Product.objects.count(), 1)

    def test_error_or_skipped_rows_prohibit_full_archive(self):
        self.apply(self.preview([row(code='a'), row('Второй', code='b')]))
        batch = self.preview([row(code='a'), row('С ошибкой', '-1')], mode='full')
        with self.assertRaisesMessage(ImportProblem, 'Архивация запрещена'):
            self.apply(batch, archive_missing=True, reviewed_drop=True, accept_errors=True)
        self.assertTrue(Product.objects.get(name='Второй').is_active)

    def test_archived_product_returns_with_same_id_photo_and_sku(self):
        self.apply(self.preview([row(code='a'), row('Второй', code='b')]))
        self.apply(self.preview([row('Второй', code='b')], mode='full'), reviewed_drop=True, archive_missing=True)
        self.assertFalse(Product.objects.get(pk=self.product.pk).is_active)
        batch = self.preview([row('Вернулся', code='a')])
        self.assertEqual(batch.plan['summary']['reactivated'], 1)
        self.apply(batch)
        product = Product.objects.get(pk=self.product.pk)
        self.assertTrue(product.is_active)
        self.assertEqual((product.image.name, product.sku), ('products/real.jpg', 'KEEP-SKU'))

    def test_unit_change_is_blocked_until_separate_review(self):
        self.apply(self.preview([row(code='a')]))
        batch = self.preview([row(unit='кг', code='a')])
        self.assertEqual(batch.plan['summary']['ambiguous'], 1)
        with self.assertRaises(ImportProblem):
            self.apply(batch)
        reviewed = revise_preview(batch.pk, batch.version, decisions={
            '0': {'action': 'link', 'product_id': self.product.pk, 'confirm_unit': True,
                  'min_quantity': '.500', 'quantity_step': '.100'}})
        self.apply(reviewed)
        self.product.refresh_from_db()
        self.assertEqual((self.product.unit, self.product.min_quantity), ('kg', Decimal('.5')))

    def test_packaging_or_manufacturer_difference_is_not_auto_merged(self):
        batch = self.preview([row(manufacturer='Завод', package='500 г')])
        self.assertEqual(batch.plan['summary']['ambiguous'], 1)
        with self.assertRaises(ImportProblem):
            self.apply(batch)
        reviewed = revise_preview(batch.pk, batch.version, decisions={'0': {'action': 'create'}})
        self.apply(reviewed)
        self.assertEqual(Product.objects.count(), 2)
        repeat = self.preview([row(manufacturer='Завод', package='500 г')])
        self.assertEqual(repeat.plan['summary']['new'], 0)

    def test_category_mapping_and_source_only_sync_preserve_manual_categories(self):
        self.apply(self.preview())
        next_batch = self.preview([row(category='Новое название из Excel')], policy='sync_source')
        with self.assertRaisesMessage(ImportProblem, 'категории'):
            self.apply(next_batch)
        next_batch = revise_preview(next_batch.pk, next_batch.version,
                                    category_map={'Новое название из Excel': 'new'})
        self.assertEqual(next_batch.plan['rows'][0]['category_before'], ['Прайс', 'Ручная подборка'])
        self.assertEqual(next_batch.plan['rows'][0]['category_after'], ['Новое название из Excel', 'Ручная подборка'])
        applied = self.apply(next_batch)
        new_category = Category.objects.get(name='Новое название из Excel')
        self.assertEqual(set(self.product.categories.values_list('pk', flat=True)), {self.manual.pk, new_category.pk})
        self.assertEqual(self.preview([row(category=new_category.name)]).plan['summary']['ambiguous'], 0)
        rollback_import(applied.pk, confirm=True)
        self.assertEqual(set(self.product.categories.values_list('pk', flat=True)), {self.manual.pk, self.category.pk})

    def test_media_descriptions_relations_and_historical_order_survive_apply_and_rollback(self):
        from storefront.models import Article, Ingredient, Order, OrderItem, ProductCollection, ProductCollectionItem
        recipe = Article.objects.create(title='Рецепт', slug='recipe')
        ingredient = Ingredient.objects.create(article=recipe, name='Товар', product=self.product)
        collection = ProductCollection.objects.create(title='Подборка', slug='collection')
        item = ProductCollectionItem.objects.create(collection=collection, product=self.product)
        order = Order.objects.create(telegram_user_id=10, request_id=uuid4(), request_fingerprint='x' * 64,
            buyer_name='Имя', phone='+79000000000', pickup_address='Адрес', total='90')
        order.items.create(product=self.product, product_name='Историческое название', sku=self.product.sku,
                           quantity='1', unit='pcs', unit_price='90', subtotal='90')
        order_before, items_before = list(Order.objects.values()), list(OrderItem.objects.values())
        batch = self.apply(self.preview([row(price=150), row('Новый')]))
        # A new photo/description is intentionally outside the import-owned fields.
        Product.objects.filter(pk=self.product.pk).update(description='Ручное новое описание', image='products/new.jpg')
        rollback_import(batch.pk, confirm=True)
        self.product.refresh_from_db(); ingredient.refresh_from_db(); item.refresh_from_db()
        self.assertEqual((self.product.price, self.product.description, self.product.image.name),
                         (Decimal('90'), 'Ручное новое описание', 'products/new.jpg'))
        self.assertEqual((ingredient.product_id, item.product_id), (self.product.pk, self.product.pk))
        self.assertEqual(list(Order.objects.values()), order_before)
        self.assertEqual(list(OrderItem.objects.values()), items_before)
        self.assertFalse(Product.objects.get(name='Новый').is_active)
        self.assertEqual(Product.objects.count(), 2)

    def test_rollback_blocks_all_changes_if_a_product_was_edited_later(self):
        batch = self.apply(self.preview([row(), row('Второй')]))
        Product.objects.filter(pk=self.product.pk).update(price=999)
        with self.assertRaisesMessage(ImportProblem, 'Откат заблокирован'):
            rollback_import(batch.pk, confirm=True)
        self.assertEqual(Product.objects.get(pk=self.product.pk).price, Decimal('999'))
        self.assertTrue(Product.objects.get(name='Второй').is_active)
        self.assertEqual(CatalogImport.objects.get(pk=batch.pk).status, 'applied')

    def test_stale_preview_and_double_apply_are_rejected(self):
        batch = self.preview()
        Product.objects.filter(pk=self.product.pk).update(price=999)
        with self.assertRaisesMessage(ImportProblem, 'после просмотра'):
            self.apply(batch)
        self.assertEqual(CatalogImport.objects.get(pk=batch.pk).status, 'failed')
        fresh = revise_preview(batch.pk, batch.version)
        with self.assertRaises(ImportProblem):
            self.apply(batch)
        self.apply(fresh)
        with self.assertRaises(ImportProblem):
            self.apply(fresh)

    def test_failure_mid_import_rolls_back_every_catalogue_write(self):
        batch = self.preview([row(price=150), row('Второй', code='b')])
        with patch('shop.price_import.ProductIdentifier.objects.get_or_create', side_effect=RuntimeError('Simulated failure')):
            with self.assertRaises(RuntimeError):
                self.apply(batch)
        self.assertEqual(Product.objects.get(pk=self.product.pk).price, Decimal('90'))
        self.assertEqual(Product.objects.count(), 1)
        self.assertFalse(SourceProduct.objects.exists())
        self.assertEqual(CatalogImport.objects.get(pk=batch.pk).status, 'failed')

    def test_empty_full_file_cannot_archive_anything(self):
        self.apply(self.preview())
        batch = self.preview([], mode='full')
        with self.assertRaises(ImportProblem):
            self.apply(batch, archive_missing=True, reviewed_drop=True)
        self.assertTrue(Product.objects.get(pk=self.product.pk).is_active)

    def test_archive_rollback_restores_activity_membership_and_identifier(self):
        self.apply(self.preview([row(code='a'), row('Второй', code='b')]))
        batch = self.apply(self.preview([row('Второй', code='b')], mode='full'),
                           reviewed_drop=True, archive_missing=True)
        rollback_import(batch.pk, confirm=True)
        self.assertTrue(Product.objects.get(pk=self.product.pk).is_active)
        self.assertTrue(SourceProduct.objects.get(source=self.source, product=self.product).is_current)
        self.assertTrue(ProductIdentifier.objects.filter(product=self.product, value='a').exists())

    def test_new_matching_product_after_preview_and_backup_failure_block_writes(self):
        batch = self.preview([row('Новый')])
        Product.objects.create(name=' НОВЫЙ ', sku='created-later', price=999)
        with self.assertRaisesMessage(ImportProblem, 'Состав или названия'):
            self.apply(batch)
        self.assertEqual(Product.objects.count(), 2)
        batch = self.preview()
        with patch('shop.price_import.backup_database', side_effect=OSError('Backup unavailable')):
            with self.assertRaises(OSError):
                self.apply(batch)
        self.assertEqual(Product.objects.get(pk=self.product.pk).price, Decimal('90'))
        self.assertEqual(CatalogImport.objects.get(pk=batch.pk).status, 'failed')


class ExcelReaderTests(TestCase):
    def test_changed_column_order_and_explicit_mapping(self):
        parsed = read_excel(xlsx([['10,50', 'шт', 'Чай']], headers=['Цена', 'Ед', 'Наименование']))
        self.assertEqual(parsed['products'][0]['price'], '10.50')
        unknown = xlsx([['Чай', 'шт', 10]], headers=['X', 'Y', 'Z'])
        self.assertTrue(read_excel(unknown)['errors'])
        parsed = read_excel(unknown, {'*': {'header_row': 1, 'columns': {'name': 'A', 'unit': 'B', 'price': 'C'}}})
        self.assertEqual(parsed['products'][0]['name'], 'Чай')

    def test_formulas_invalid_gtin_and_invalid_structure_are_reported(self):
        parsed = read_excel(xlsx([row(price='=2+2'), row('Плохой GTIN', barcode='4601234567890')]))
        self.assertEqual(len(parsed['errors']), 2)
        with self.assertRaises(ImportProblem):
            read_excel(BytesIO(b'not xlsx'))

    def test_missing_unit_requires_explicit_default_except_legacy_water_sheet(self):
        file = xlsx([['Чай', 10]], headers=['Название', 'Цена'])
        self.assertTrue(read_excel(file)['errors'])
        self.assertEqual(read_excel(file, {'*': {'default_unit': 'pcs'}})['products'][0]['unit'], 'pcs')
        water = xlsx([['Вода', 10]], headers=['Название', 'Цена'], title='Вода')
        self.assertEqual(read_excel(water)['products'][0]['unit'], 'pcs')

    def test_duplicate_price_columns_need_explicit_mapping(self):
        file = xlsx([['Чай', 'шт', 10, 15]], headers=['Название', 'Ед', 'Цена', 'Розничная цена'])
        self.assertIn('Несколько колонок', read_excel(file)['errors'][0]['error'])

    def test_incorrect_small_sheet_dimensions_do_not_truncate_a_full_file(self):
        original, fixed = xlsx([row(), row('Второй')]), BytesIO()
        with ZipFile(original) as source, ZipFile(fixed, 'w', ZIP_DEFLATED) as destination:
            for item in source.infolist():
                data = source.read(item.filename)
                if item.filename == 'xl/worksheets/sheet1.xml':
                    data = re.sub(br'<dimension ref="[^"]+"', b'<dimension ref="A1:A1"', data)
                destination.writestr(item.filename, data)
        parsed = read_excel(fixed)
        self.assertEqual(parsed['total'], 2)
        self.assertEqual([item['name'] for item in parsed['products']], ['Товар', 'Второй'])

    def test_xml_entities_and_oversized_archives_are_rejected(self):
        for payload in (b'<!DOCTYPE x [<!ENTITY a "b">]><x/>', b'a' * (80 * 1024 * 1024 + 1)):
            file = BytesIO()
            with ZipFile(file, 'w', ZIP_DEFLATED) as archive:
                archive.writestr('xl/workbook.xml', payload)
            with self.assertRaises(ImportProblem):
                read_excel(file)


class ImportAdminTests(TestCase):
    def setUp(self):
        self.admin = get_user_model().objects.create_superuser('import-admin', password='test-password')
        self.client.force_login(self.admin)
        self.category = Category.objects.create(name='Прайс')
        self.source = ImportSource.objects.create(name='Источник')

    def test_admin_upload_review_apply_history_and_rollback(self):
        response = self.client.post(reverse('admin:shop_product_import_excel'), {
            'file': SimpleUploadedFile('price.xlsx', xlsx([row()]).getvalue()), 'source': self.source.pk,
            'mode': 'partial', 'category_policy': 'add',
        })
        self.assertEqual(response.status_code, 302)
        batch = CatalogImport.objects.get()
        review = reverse('admin:shop_catalogimport_review', args=[batch.pk])
        response = self.client.get(review)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Прайс')
        self.client.post(review, {'action': 'apply', 'version': batch.version, 'confirm': 'on'})
        batch.refresh_from_db()
        self.assertEqual(batch.status, 'applied')
        self.assertEqual(batch.applied_by, self.admin)
        self.assertEqual(self.client.get(reverse('admin:shop_catalogimport_changelist')).status_code, 200)
        self.client.post(review, {'action': 'rollback', 'confirm_rollback': 'on'})
        batch.refresh_from_db()
        self.assertEqual(batch.status, 'rolled_back')
        self.assertFalse(Product.objects.get().is_active)

    def test_staff_without_catalogue_permissions_and_csrf_are_rejected(self):
        staff = get_user_model().objects.create_user('staff', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse('admin:shop_product_import_excel')).status_code, 403)
        protected = Client(enforce_csrf_checks=True)
        protected.force_login(self.admin)
        self.assertEqual(protected.post(reverse('admin:shop_product_import_excel'), {}).status_code, 403)

    def test_review_renders_ambiguous_conflicting_and_skipped_rows(self):
        product = Product.objects.create(name='Товар', sku='existing', price=10)
        batch = create_preview(xlsx([row(unit='кг'), row('Дубль', 10), row('Дубль', 20), row('Новый')]),
                               self.source, 'partial', self.admin)
        review = reverse('admin:shop_catalogimport_review', args=[batch.pk])
        self.assertEqual(self.client.get(review).status_code, 200)
        self.client.post(review, {'action': 'resolve', 'version': batch.version, 'row_key': '0',
                                 'resolution': 'skip'})
        self.assertEqual(self.client.get(review).status_code, 200)
        self.assertEqual(Product.objects.get(pk=product.pk).price, Decimal('10'))

    def test_unreadable_upload_is_saved_in_failed_import_history(self):
        response = self.client.post(reverse('admin:shop_product_import_excel'), {
            'file': SimpleUploadedFile('broken.xlsx', b'broken file'), 'source': self.source.pk,
            'mode': 'partial', 'category_policy': 'add',
        })
        self.assertEqual(response.status_code, 302)
        batch = CatalogImport.objects.get()
        self.assertEqual((batch.filename, batch.status, batch.uploaded_by), ('broken.xlsx', 'failed', self.admin))
        self.assertTrue(batch.error)
        self.assertContains(self.client.get(response.url), 'Файл не прочитан')
        with self.assertRaises(ImportProblem):
            revise_preview(batch.pk, batch.version)


class PrimaryCategoryApiTests(TestCase):
    def test_combined_groups_keep_original_categories_and_deduplicate_products(self):
        water, juice, dairy, cheese = [Category.objects.create(name=name) for name in
                                        ('Вода', 'Соки', 'Молочная продукция', 'Сыры')]
        product = Product.objects.create(name='Напиток', sku='drinks', price=10)
        product.categories.add(water, juice)
        milk = Product.objects.create(name='Сыр', sku='dairy', price=10)
        milk.categories.add(cheese)
        data = self.client.get('/api/products/?category_group=drinks').json()
        self.assertEqual(data['count'], 1)
        self.assertEqual(data['results'][0]['id'], product.pk)
        self.assertEqual(self.client.get('/api/products/?category_group=dairy').json()['count'], 1)
        self.assertEqual(self.client.get(f'/api/products/?category={water.pk}').json()['count'], 1)
        self.assertEqual(self.client.get('/api/products/?category_group=unknown').status_code, 400)
