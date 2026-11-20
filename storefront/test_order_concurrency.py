from ._test_pickup_fixtures import available_pickup
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from uuid import uuid4
from django.core.cache import cache
from django.db import connection, connections
from django.test import TransactionTestCase, override_settings
from rest_framework.test import APIClient
from shop.models import Product
from .models import Customer, Order, OrderNotification
from .test_accounts import credentials, TOKEN


@skipUnless(connection.vendor == 'postgresql', 'Row locking must be checked on PostgreSQL.')
@override_settings(TELEGRAM_BOT_TOKEN=TOKEN, MINIAPP_ORDERS_ENABLED=True, TELEGRAM_NOTIFICATIONS_ENABLED=False)
class ConcurrentCheckoutTests(TransactionTestCase):
    def test_simultaneous_same_request_creates_one_order_and_outbox(self):
        cache.clear()
        product=Product.objects.create(name='Тестовый товар',sku='concurrent-test',price='100',unit='pcs')
        Customer.objects.create(telegram_id=7001,first_name='Анна')
        payload={'pickup_at': available_pickup(), 'request_id':str(uuid4()),'buyer_name':'Проверка','phone':'+70000000000',
            'items':[{'product_id':product.pk,'quantity':'1','expected_price':'100'}]}
        barrier=Barrier(2)
        def submit():
            client=APIClient(); client.credentials(HTTP_AUTHORIZATION=credentials())
            try:
                barrier.wait(timeout=10)
                response=client.post('/api/orders/',payload,format='json')
                return response.status_code,response.data.get('id')
            finally:
                connections.close_all()
        with ThreadPoolExecutor(max_workers=2) as pool:
            results=list(pool.map(lambda _:submit(),range(2)))
        self.assertEqual(sorted(status for status,_ in results),[200,201],results)
        self.assertEqual(len({pk for _,pk in results}),1)
        self.assertEqual(Order.objects.count(),1)
        self.assertEqual(OrderNotification.objects.count(),1)
