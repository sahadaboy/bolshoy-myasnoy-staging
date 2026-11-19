from decimal import Decimal
from hashlib import sha256
from urllib.parse import urlencode
from uuid import uuid4
import hmac
import json
import time
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.exceptions import ValidationError as DjangoValidationError
from django.test import SimpleTestCase, TestCase, override_settings
from django.urls import reverse
from rest_framework.exceptions import AuthenticationFailed
from rest_framework.test import APIClient
from shop.models import Category, Product
from .models import Article, ArticleMember, Ingredient, Order, ProductCollection, ProductCollectionItem, RecipeStep
from .telegram_auth import validate_init_data
from .models import IdeaCategory

TOKEN = 'test-only-token-not-a-real-bot'


def signed(user_id=100, timestamp=None, **extra):
    values = {'auth_date': str(int(time.time()) if timestamp is None else timestamp), 'user': json.dumps({'id': user_id, 'first_name': 'Тестовый покупатель', 'username': 'test_customer'}, separators=(',', ':')), **extra}
    secret = hmac.digest(b'WebAppData', TOKEN.encode(), 'sha256')
    check = '\n'.join(f'{key}={value}' for key, value in sorted(values.items()))
    return urlencode({**values, 'hash': hmac.digest(secret, check.encode(), 'sha256').hex()})


class TelegramValidationTests(SimpleTestCase):
    def test_valid_signed_identity_including_new_signature_field(self):
        user = validate_init_data(signed(signature='signed-extra-field'), TOKEN)
        self.assertEqual(user.id, 100)
        self.assertEqual(user.first_name, 'Тестовый покупатель')

    def test_tampered_claims_invalid_hash_wrong_bot_and_duplicates_rejected(self):
        value = signed()
        for raw, token in [(value.replace('100', '200'), TOKEN), (value[:-1] + ('0' if value[-1] != '0' else '1'), TOKEN), (value, 'wrong-bot'), (value + '&auth_date=1', TOKEN), (value, ''), ('user={"id":100}', TOKEN), ('x' * 17000, TOKEN)]:
            with self.subTest(raw=raw[:30], token=bool(token)), self.assertRaises(AuthenticationFailed):
                validate_init_data(raw, token)

    def test_expired_future_and_invalid_user_id_rejected(self):
        now = int(time.time())
        for value in [signed(timestamp=now - 3601), signed(timestamp=now + 90), signed(user_id=-1), signed(user_id=True), signed(user_id=2**64)]:
            with self.subTest(value=value[:20]), self.assertRaises(AuthenticationFailed):
                validate_init_data(value, TOKEN, now=now)


@override_settings(TELEGRAM_BOT_TOKEN=TOKEN, MINIAPP_ORDERS_ENABLED=True)
class OrderTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION='tma ' + signed())
        self.piece = Product.objects.create(name='Горчица', sku='test-pcs', price='126.99', unit='pcs', min_quantity='1', quantity_step='1')
        self.weight = Product.objects.create(name='Кешью', sku='test-kg', price='1575', unit='kg', min_quantity='.5', quantity_step='.1')

    def payload(self, product=None, quantity='1.000'):
        return {'request_id': str(uuid4()), 'buyer_name': 'Покупатель', 'phone': '+7 (900) 123-45-67', 'comment': 'Без пакета', 'items': [{'product_id': (product or self.piece).pk, 'quantity': quantity}]}

    def post(self, data):
        return self.client.post('/api/orders/', data, format='json')

    def test_server_total_owner_and_price_snapshot_ignore_client_values(self):
        data = self.payload(quantity='2')
        data.update(total='0.01', telegram_user_id=999, status='ready')
        data['items'][0].update(unit_price='0.01', unit='kg')
        response = self.post(data)
        self.assertEqual(response.status_code, 201, response.data)
        order = Order.objects.get()
        self.assertEqual(order.telegram_user_id, 100)
        self.assertEqual(order.total, Decimal('253.98'))
        self.assertEqual(order.status, Order.Status.NEW)
        self.assertEqual(order.phone, '+79001234567')
        item = order.items.get()
        self.assertEqual(item.unit_price, Decimal('126.99'))
        self.assertEqual(item.unit, 'pcs')
        self.piece.price = Decimal('999'); self.piece.name = 'Новое название'; self.piece.save()
        snapshot = self.client.get(f'/api/orders/{order.public_id}/')
        self.assertEqual(snapshot.data['items'][0]['product_name'], 'Горчица')
        self.assertEqual(snapshot.data['items'][0]['unit_price'], '126.99')

    def test_weight_minimum_step_and_piece_integer_are_enforced(self):
        for product, quantity in [(self.weight, '.4'), (self.weight, '.55'), (self.piece, '1.5'), (self.piece, '0'), (self.weight, '0.5001')]:
            with self.subTest(quantity=quantity):
                self.assertEqual(self.post(self.payload(product, quantity)).status_code, 400)
        result = self.post(self.payload(self.weight, '.6'))
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data['total'], '945.00')

    def test_line_rounding_half_up_happens_before_sum(self):
        self.weight.price = Decimal('.01'); self.weight.save()
        other = Product.objects.create(name='Другой весовой', sku='test-weight-2', price='.01', unit='kg', min_quantity='.5', quantity_step='.1')
        data = self.payload(self.weight, '.5')
        data['items'].append({'product_id': other.pk, 'quantity': '.5'})
        result = self.post(data)
        self.assertEqual(result.status_code, 201, result.data)
        self.assertEqual(result.data['total'], '0.02')

    def test_duplicate_request_returns_same_order_and_conflicting_retry_fails(self):
        data = self.payload()
        first = self.post(data); again = self.post(data)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(again.status_code, 200)
        self.assertEqual(first.data['id'], again.data['id'])
        self.assertEqual(Order.objects.count(), 1)
        data['items'][0]['quantity'] = '2'
        self.assertEqual(self.post(data).status_code, 409)
        self.assertEqual(Order.objects.count(), 1)

    def test_changed_price_unavailable_and_deleted_products_do_not_create_order(self):
        data = self.payload(); data['items'][0]['expected_price'] = '100'
        self.assertEqual(self.post(data).status_code, 409)
        self.piece.is_available = False; self.piece.save()
        self.assertEqual(self.post(self.payload()).status_code, 400)
        self.piece.is_available = True; self.piece.is_active = False; self.piece.save()
        self.assertEqual(self.post(self.payload()).status_code, 400)
        data = self.payload(); data['items'][0]['product_id'] = 99999
        self.assertEqual(self.post(data).status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_duplicate_lines_and_invalid_contacts_rejected(self):
        data = self.payload(); data['items'] *= 2
        self.assertEqual(self.post(data).status_code, 400)
        data = self.payload(); data['phone'] = 'not a phone'
        self.assertEqual(self.post(data).status_code, 400)
        self.assertFalse(Order.objects.exists())

    def test_oversized_and_out_of_range_input_rejected(self):
        data = self.payload(); data['items'][0]['product_id'] = 2**64
        self.assertEqual(self.post(data).status_code, 400)
        data = self.payload(); data['comment'] = 'x' * (65 * 1024)
        self.assertEqual(self.post(data).status_code, 413)
        self.assertFalse(Order.objects.exists())

    def test_guest_spoofed_unsafe_identity_and_other_owner_cannot_read_orders(self):
        created = self.post(self.payload()).data
        other = APIClient(); other.credentials(HTTP_AUTHORIZATION='tma ' + signed(user_id=200))
        result = other.get('/api/orders/?telegram_user_id=100')
        self.assertEqual(result.data['count'], 0)
        self.assertEqual(other.get(f"/api/orders/{created['id']}/").status_code, 404)
        guest = APIClient()
        self.assertEqual(guest.get('/api/orders/').status_code, 401)
        data = self.payload(); data['initDataUnsafe'] = {'user': {'id': 100}}
        self.assertEqual(guest.post('/api/orders/', data, format='json').status_code, 401)

    @override_settings(MINIAPP_ORDERS_ENABLED=False)
    def test_public_submission_off_and_session_reports_actual_state(self):
        self.assertEqual(self.post(self.payload()).status_code, 503)
        self.assertFalse(Order.objects.exists())
        session = self.client.get('/api/session/')
        self.assertTrue(session.data['authenticated'])
        self.assertFalse(session.data['checkout_enabled'])
        self.assertEqual(session['Cache-Control'], 'private, no-store')
        self.assertIsNone(APIClient().get('/api/session/').data['user'])

    @override_settings(MINIAPP_WEIGHT_ESTIMATE=True)
    def test_weight_notice_reflects_store_configuration(self):
        self.assertTrue(self.post(self.payload(self.weight, '.5')).data['weight_estimate'])
        self.assertFalse(self.post(self.payload()).data['weight_estimate'])

    def test_anonymous_authentication_forgery_rejected(self):
        bad = APIClient(); bad.credentials(HTTP_AUTHORIZATION='tma ' + signed().replace('100', '101'))
        self.assertEqual(bad.get('/api/session/').status_code, 401)

    def test_submission_rate_limit_and_no_customer_status_edit(self):
        created = self.post(self.payload())
        self.assertEqual(self.client.patch(f"/api/orders/{created.data['id']}/", {'status': 'ready'}, format='json').status_code, 405)
        for _ in range(9):
            self.assertEqual(self.post(self.payload()).status_code, 201)
        self.assertEqual(self.post(self.payload()).status_code, 429)


@override_settings(MINIAPP_SHOW_DEMO_CONTENT=True)
class ContentAndCatalogueTests(TestCase):
    def setUp(self):
        self.client = APIClient()
        self.category = Category.objects.create(name='Приправы')
        self.product = Product.objects.create(name='Перец Чёрный', sku='pepper', price='50.99', unit='pcs')
        self.product.categories.add(self.category)

    def test_cyrillic_search_category_filters_and_pagination(self):
        for index in range(30):
            Product.objects.create(name=f'Другой {index}', sku=f'other-{index}', price=100 + index, unit='kg')
        response = self.client.get('/api/products/?search=перец')
        self.assertEqual(response.data['count'], 1)
        self.assertEqual(response.data['results'][0]['id'], self.product.id)
        self.assertEqual(len(self.client.get('/api/products/').data['results']), 24)
        self.assertEqual(self.client.get('/api/products/?unit=kg&ordering=-price').data['results'][0]['price'], '129.00')
        self.assertEqual(self.client.get('/api/products/?category=bad').status_code, 400)
        self.assertEqual(self.client.get('/api/products/?category=' + '9' * 100).status_code, 400)
        self.assertEqual(self.client.get('/api/products/?search=(a+)+').data['count'], 0)

    def test_home_only_returns_published_curated_products(self):
        collection = ProductCollection.objects.create(title='К мясу', slug='meat', is_published=True)
        ProductCollectionItem.objects.create(collection=collection, product=self.product)
        Product.objects.create(name='Случайный', sku='random', price='10')
        response = self.client.get('/api/storefront/')
        self.assertEqual(len(response.data['collections']), 1)
        self.assertEqual([row['id'] for row in response.data['collections'][0]['products']], [self.product.pk])
        self.assertEqual(self.client.get('/api/products/?collection=meat').data['count'], 1)

    def test_real_published_content_excludes_drafts_and_demo_fallback(self):
        demo = Article.objects.create(title='Пример', slug='demo', is_demo=True)
        draft = Article.objects.create(title='Черновик', slug='draft')
        self.assertFalse(self.client.get('/api/ideas/').data['demo'])
        self.assertEqual(self.client.get('/api/ideas/').data['count'], 0)
        self.assertEqual(self.client.get(f'/api/ideas/{demo.slug}/').status_code, 404)
        self.assertEqual(self.client.get(f'/api/ideas/{draft.slug}/').status_code, 404)
        real = Article.objects.create(title='Реальный рецепт', slug='real', is_published=True)
        section = IdeaCategory.objects.create(name='Обеды', slug='lunch')
        real.category = section; real.save()
        self.assertEqual(self.client.get('/api/ideas/?category=lunch').data['count'], 1)
        self.assertEqual(self.client.get('/api/ideas/?category=missing').data['count'], 0)
        response = self.client.get('/api/ideas/')
        self.assertFalse(response.data['demo'])
        self.assertEqual([row['id'] for row in response.data['results']], [real.id])
        demo.is_published = True
        with self.assertRaises(DjangoValidationError): demo.full_clean()

    @override_settings(MINIAPP_SHOW_DEMO_CONTENT=False)
    def test_demo_disabled_in_production_content(self):
        Article.objects.create(title='Пример', slug='demo', is_demo=True)
        self.assertEqual(self.client.get('/api/ideas/').data['count'], 0)
        self.assertEqual(self.client.get('/api/ideas/demo/').status_code, 404)

    def test_recipe_detail_only_links_explicit_product_and_valid_quantity(self):
        recipe = Article.objects.create(title='Рецепт', slug='recipe', is_published=True)
        Ingredient.objects.create(article=recipe, name='Перец', product=self.product, purchase_quantity='1')
        Ingredient.objects.create(article=recipe, name='Чеснок')
        RecipeStep.objects.create(article=recipe, text='Приготовьте блюдо.')
        response = self.client.get('/api/ideas/recipe/')
        self.assertEqual(response.data['ingredients'][0]['product']['id'], self.product.id)
        self.assertEqual(response.data['ingredients'][0]['cart_quantity'], '1.000')
        self.assertIsNone(response.data['ingredients'][1]['product'])
        self.assertEqual(response.data['steps'], ['Приготовьте блюдо.'])

    def test_admin_and_excel_import_are_available_and_order_snapshot_readonly(self):
        user = get_user_model().objects.create_superuser('test-admin', password='test-only-password')
        self.client.force_login(user)
        self.assertEqual(self.client.get(reverse('admin:shop_product_import_excel')).status_code, 200)
        for name in ['storefront_banner', 'storefront_productcollection', 'storefront_article', 'storefront_order']:
            self.assertEqual(self.client.get(reverse(f'admin:{name}_changelist')).status_code, 200)
        model_admin = admin.site._registry[Order]
        self.assertIn('total', model_admin.readonly_fields)
        self.assertIn('telegram_user_id', model_admin.readonly_fields)
