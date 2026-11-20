from ._test_pickup_fixtures import available_pickup
from datetime import timedelta
from uuid import uuid4
import time
from django.conf import settings
from django.contrib.sessions.models import Session
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient
from shop.models import Product
from .models import Customer, CustomerCart, CartOperation, Order
from .test_accounts import credentials, TOKEN
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from unittest import skipUnless
from django.db import connection, close_old_connections
from django.test import TransactionTestCase


@override_settings(TELEGRAM_BOT_TOKEN=TOKEN, MINIAPP_ORDERS_ENABLED=True, TELEGRAM_NOTIFICATIONS_ENABLED=False)
class SessionCartTests(TestCase):
    def setUp(self):
        self.a=self.login(7001);self.b=self.login(7002);self.a2=self.login(7001)
        self.p=Product.objects.create(name='Крупа',sku='cart-p',price='100',unit='pcs')
        self.w=Product.objects.create(name='Весовой',sku='cart-w',price='300',unit='kg',min_quantity='0.250',quantity_step='0.050')

    def login(self, user):
        client=APIClient(enforce_csrf_checks=True)
        token=client.get('/api/session/').data['csrf_token']
        response=client.post('/api/session/login/',HTTP_AUTHORIZATION=credentials(user),HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code,200,response.data)
        client.credentials(HTTP_X_CSRFTOKEN=response.data['csrf_token'])
        return client

    def post(self, client, changes, revision=0, mode='patch', operation=None):
        return client.post('/api/cart/', {'operation_id':operation or str(uuid4()),'base_revision':revision,'mode':mode,'changes':changes},format='json')

    def line(self,p=None,q='2.000',before='0.000'):
        return {'product_id':(p or self.p).pk,'quantity':q,'expected_quantity':before}

    def test_reload_and_reopen_without_init_data_keep_phone_identity_and_cookie(self):
        self.assertEqual(self.a.post('/api/profile/',{'phone':'+79780000001'},format='json').status_code,200)
        reopened=APIClient();reopened.cookies=self.a.cookies
        response=reopened.get('/api/session/')
        self.assertTrue(response.data['authenticated']);self.assertEqual(response.data['user']['id'],'7001')
        self.assertEqual(response.data['user']['phone'],'+79780000001')
        self.assertTrue(self.a.cookies[settings.MINIAPP_SESSION_COOKIE_NAME]['httponly'])
        self.assertEqual(self.a.cookies[settings.MINIAPP_SESSION_COOKIE_NAME]['samesite'],'Lax')
        self.assertEqual(Customer.objects.filter(telegram_id=7001).count(),1)

    @override_settings(SESSION_COOKIE_SECURE=True, CSRF_COOKIE_SECURE=True)
    def test_https_session_cookies_are_secure_httponly_and_reads_do_not_extend_expiry(self):
        client=self.login(7003)
        self.assertTrue(client.cookies[settings.MINIAPP_SESSION_COOKIE_NAME]['secure'])
        self.assertTrue(client.cookies[settings.CSRF_COOKIE_NAME]['secure'])
        self.assertTrue(client.cookies[settings.CSRF_COOKIE_NAME]['httponly'])
        row=Session.objects.get(session_key=client.cookies[settings.MINIAPP_SESSION_COOKIE_NAME].value)
        expiry=row.expire_date
        client.get('/api/session/');row.refresh_from_db();self.assertEqual(row.expire_date,expiry)

    def test_initial_login_requires_valid_signature_recent_date_and_csrf(self):
        guest=APIClient(enforce_csrf_checks=True)
        self.assertEqual(guest.post('/api/session/login/',HTTP_AUTHORIZATION=credentials()).status_code,403)
        token=guest.get('/api/session/').data['csrf_token']
        for header in ('tma bad',credentials(timestamp=int(time.time())-7200)):
            self.assertEqual(guest.post('/api/session/login/',HTTP_AUTHORIZATION=header,HTTP_X_CSRFTOKEN=token).status_code,401)
        self.assertFalse(guest.get('/api/session/').data['authenticated'])

    def test_cookie_writes_require_csrf_and_check_origin(self):
        self.a.credentials()
        self.assertEqual(self.a.post('/api/profile/',{'phone':'+79780000000'},format='json').status_code,403)
        token=self.a.get('/api/session/').data['csrf_token']
        self.a.credentials(HTTP_X_CSRFTOKEN=token,HTTP_ORIGIN='https://evil.example')
        self.assertEqual(self.post(self.a,[self.line()]).status_code,403)
        self.assertFalse(CustomerCart.objects.exists())

    def test_expired_session_does_not_extend_itself_or_accept_expired_init_data(self):
        session=Session.objects.get(session_key=self.a.cookies[settings.MINIAPP_SESSION_COOKIE_NAME].value)
        session.expire_date=timezone.now()-timedelta(seconds=1);session.save()
        self.assertFalse(self.a.get('/api/session/').data['authenticated'])
        self.assertEqual(self.a.get('/api/cart/').status_code,401)
        self.a.credentials(HTTP_AUTHORIZATION=credentials(timestamp=int(time.time())-7200))
        self.assertEqual(self.a.get('/api/cart/').status_code,401)

    def test_signature_login_rotates_session_and_can_switch_verified_customer(self):
        old=self.a.cookies[settings.MINIAPP_SESSION_COOKIE_NAME].value
        token=self.a.get('/api/session/').data['csrf_token']
        response=self.a.post('/api/session/login/',HTTP_AUTHORIZATION=credentials(7002),HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.data['user']['id'],'7002')
        self.assertNotEqual(old,self.a.cookies[settings.MINIAPP_SESSION_COOKIE_NAME].value)
        self.assertEqual(self.a.get('/api/session/').data['user']['id'],'7002')

    def test_customer_cookie_is_separate_from_existing_admin_session(self):
        from django.contrib.auth import get_user_model
        staff=get_user_model().objects.create_user(username='cart-admin-test',password='test-only-password',is_staff=True)
        client=APIClient(enforce_csrf_checks=True);client.force_login(staff)
        admin_cookie=client.cookies[settings.SESSION_COOKIE_NAME].value
        token=client.get('/api/session/').data['csrf_token']
        response=client.post('/api/session/login/',HTTP_AUTHORIZATION=credentials(7003),HTTP_X_CSRFTOKEN=token)
        self.assertEqual(response.status_code,200)
        self.assertEqual(client.cookies[settings.SESSION_COOKIE_NAME].value,admin_cookie)
        self.assertNotEqual(client.cookies[settings.MINIAPP_SESSION_COOKIE_NAME].value,admin_cookie)
        self.assertEqual(client.session['_auth_user_id'],str(staff.pk))

    def test_two_devices_share_one_cart_and_current_catalog_prices(self):
        response=self.post(self.a,[self.line(),self.line(self.w,'0.350')]);self.assertEqual(response.status_code,200)
        loaded=self.a2.get('/api/cart/').data
        self.assertEqual(len(loaded['items']),2)
        self.assertEqual(CustomerCart.objects.filter(customer__telegram_id=7001).count(),1)
        self.assertEqual(self.post(self.a2,[self.line(q='3.000',before='2.000')],loaded['revision']).status_code,200)
        self.p.price='125';self.p.save()
        loaded=self.a.get('/api/cart/').data
        row=next(i for i in loaded['items'] if i['product_id']==self.p.pk)
        self.assertEqual((row['quantity'],row['product']['price']),('3.000','125.00'))
        self.assertEqual(CustomerCart.objects.get(customer__telegram_id=7001).items[str(self.p.pk)],'3.000')

    def test_local_import_is_maximum_not_sum_and_receipt_survives_later_removal(self):
        self.post(self.a,[self.line(q='3.000')])
        key=str(uuid4())
        first=self.post(self.a2,[self.line(q='2.000')],1,'merge',key)
        self.assertEqual(first.data['items'][0]['quantity'],'3.000')
        self.post(self.a,[self.line(q='0',before='3')],first.data['revision'])
        again=self.post(self.a2,[self.line(q='2.000')],1,'merge',key)
        self.assertEqual(again.data['items'],[])

    def test_duplicate_operation_is_idempotent_and_changed_payload_rejected(self):
        key=str(uuid4());first=self.post(self.a,[self.line()],operation=key)
        second=self.post(self.a,[self.line()],operation=key)
        self.assertEqual(first.data,second.data);self.assertEqual(CartOperation.objects.count(),1)
        self.assertEqual(self.post(self.a,[self.line(q='9')],operation=key).status_code,409)

    def test_disjoint_changes_merge_but_same_product_conflict_keeps_server(self):
        self.post(self.a,[self.line()])
        self.assertEqual(self.post(self.a2,[self.line(self.w,'0.350')],0).status_code,200)
        conflict=self.post(self.a2,[self.line(q='3',before='0')],0)
        self.assertEqual(conflict.status_code,409);self.assertEqual(len(conflict.data['cart']['items']),2)
        self.assertEqual(CustomerCart.objects.get(customer__telegram_id=7001).items[str(self.p.pk)],'2.000')

    def test_quantities_active_products_and_limits_are_validated_atomically(self):
        for line in [self.line(self.w,'0.333'),self.line(q='1.500'),self.line(q='-1'),{'product_id':99999999,'quantity':'1'}]:
            self.assertEqual(self.post(self.a,[line]).status_code,400)
        self.p.is_available=False;self.p.save()
        self.assertEqual(self.post(self.a,[self.line()]).status_code,400)
        self.assertFalse(CustomerCart.objects.exists())

    def test_read_and_other_customer_never_clear_or_expose_a_cart(self):
        self.post(self.a,[self.line()])
        self.assertEqual(self.b.get('/api/cart/?customer_id=7001').data['items'],[])
        self.assertEqual(len(self.a.get('/api/cart/').data['items']),1)
        guest=APIClient();self.assertEqual(guest.get('/api/cart/').status_code,401)
        self.assertEqual(self.b.get('/api/session/').data['user']['id'],'7002')

    def test_successful_order_consumes_matching_cart_only_and_retry_does_not_clear_new_items(self):
        self.post(self.a,[self.line()])
        payload={'pickup_at': available_pickup(), 'request_id':str(uuid4()),'buyer_name':'Тест','phone':'+79780000001','items':[{'product_id':self.p.pk,'quantity':'2','expected_price':'100'}]}
        result=self.a.post('/api/orders/',payload,format='json');self.assertEqual(result.status_code,201,result.data)
        self.assertEqual(self.a.get('/api/cart/').data['items'],[])
        revision=self.a.get('/api/cart/').data['revision']
        self.post(self.a,[self.line(q='4')],revision)
        self.assertEqual(self.a.post('/api/orders/',payload,format='json').status_code,200)
        self.assertEqual(self.a.get('/api/cart/').data['items'][0]['quantity'],'4.000')
        self.assertEqual(Order.objects.count(),1)
        self.assertEqual(self.b.get('/api/orders/').data['count'],0)

    def test_failed_order_and_different_device_quantity_preserve_cart(self):
        self.post(self.a,[self.line(q='3')])
        payload={'pickup_at': available_pickup(), 'request_id':str(uuid4()),'buyer_name':'Тест','phone':'+79780000001','items':[{'product_id':self.p.pk,'quantity':'2','expected_price':'999'}]}
        self.assertEqual(self.a.post('/api/orders/',payload,format='json').status_code,409)
        self.assertEqual(self.a.get('/api/cart/').data['items'][0]['quantity'],'3.000')


        payload['items'][0]['expected_price']='100'
        self.assertEqual(self.a.post('/api/orders/',payload,format='json').status_code,201)
        self.assertEqual(self.a.get('/api/cart/').data['items'][0]['quantity'],'3.000')


@skipUnless(connection.vendor=='postgresql', 'Requires PostgreSQL row locks')
@override_settings(TELEGRAM_BOT_TOKEN=TOKEN)
class ConcurrentCartTests(TransactionTestCase):
    def setUp(self):
        Customer.objects.create(telegram_id=7001)
        self.products=[Product.objects.create(name=f'Concurrent {i}',sku=f'cart-concurrent-{i}',price='100') for i in range(2)]

    def race(self, same_product):
        barrier=Barrier(2)
        def write(index):
            close_old_connections()
            try:
                client=APIClient();client.credentials(HTTP_AUTHORIZATION=credentials())
                barrier.wait(timeout=15)
                response=client.post('/api/cart/',{'operation_id':str(uuid4()),'base_revision':0,'changes':[{'product_id':self.products[0 if same_product else index].pk,'quantity':str(index+2),'expected_quantity':'0'}]},format='json')
                return response.status_code
            finally: close_old_connections()
        with ThreadPoolExecutor(max_workers=2) as pool: statuses=list(pool.map(write,range(2)))
        self.assertEqual(CustomerCart.objects.count(),1)
        return statuses

    def test_parallel_disjoint_changes_are_both_saved(self):
        self.assertEqual(self.race(False),[200,200])
        self.assertEqual(len(CustomerCart.objects.get().items),2)

    def test_parallel_same_product_has_one_explicit_conflict(self):
        self.assertEqual(sorted(self.race(True)),[200,409])
