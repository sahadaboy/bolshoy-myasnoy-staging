from datetime import timedelta
from decimal import Decimal
from io import StringIO
from unittest.mock import patch
from urllib.parse import urlencode
import hashlib, hmac, json, time
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.management import call_command
from django.test import TestCase, RequestFactory, override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APIClient
from shop.models import Product
from .models import Customer, Order, OrderNotification, OrderStatusEvent, StoreProfile
from .notifications import deliver_one, recover_abandoned, DeliveryError, message_parts

TOKEN = 'accounts-unit-tests-only'


def credentials(user_id=7001, timestamp=None, **fields):
    data = {'auth_date': str(timestamp or int(time.time())), 'user': json.dumps({'id':user_id, 'first_name':'Анна', **fields}, separators=(',', ':'))}
    key = hmac.digest(b'WebAppData', TOKEN.encode(), 'sha256')
    data['hash'] = hmac.digest(key, '\n'.join(f'{key}={value}' for key,value in sorted(data.items())).encode(), 'sha256').hex()
    return 'tma ' + urlencode(data)


@override_settings(TELEGRAM_BOT_TOKEN=TOKEN, MINIAPP_ORDERS_ENABLED=True,
    TELEGRAM_NOTIFICATIONS_ENABLED=True, TELEGRAM_ADMIN_CHAT_ID='-100001', MINIAPP_ADMIN_URL='https://admin.example.test')
class AccountOrderTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient(); self.client.credentials(HTTP_AUTHORIZATION=credentials())
        self.product = Product.objects.create(name='Горчица', sku='account-product', price='100', unit='pcs')

    def payload(self):
        from uuid import uuid4
        return {'request_id': str(uuid4()), 'buyer_name':'Анна', 'phone':'+7 (978) 123-45-67',
                'items':[{'product_id':self.product.pk,'quantity':'2','expected_price':'100'}]}

    def order(self):
        result=self.client.post('/api/orders/',self.payload(),format='json')
        self.assertEqual(result.status_code,201,result.data)
        return Order.objects.get(public_id=result.data['id'])

    def test_first_login_creates_unique_permanent_customer_without_requesting_phone(self):
        first=self.client.get('/api/session/'); second=self.client.get('/api/session/')
        self.assertTrue(first.data['authenticated']); self.assertEqual(Customer.objects.count(),1)
        self.assertEqual(first.data['user']['customer_id'],second.data['user']['customer_id'])
        self.assertEqual(first.data['user']['phone'],'')

    def test_verified_identity_refreshes_without_erasing_manual_phone_or_replaying_old_name(self):
        self.client.get('/api/session/')
        customer=Customer.objects.get(); customer.phone='+79780000000'; customer.last_seen_at=timezone.now()-timedelta(minutes=5); customer.save()
        now=int(time.time())
        self.client.credentials(HTTP_AUTHORIZATION=credentials(timestamp=now+1,first_name='Новое имя',username='changed',photo_url='https://t.me/i/userpic/test.jpg'))
        data=self.client.get('/api/session/').data['user']
        self.assertEqual((data['first_name'],data['phone']),('Новое имя','+79780000000'))
        self.assertEqual(data['photo_url'],'https://t.me/i/userpic/test.jpg')
        self.client.credentials(HTTP_AUTHORIZATION=credentials(timestamp=now,first_name='Старое имя'))
        self.assertEqual(self.client.get('/api/session/').data['user']['first_name'],'Новое имя')

    def test_unverified_or_guest_requests_never_create_accounts(self):
        self.client.credentials(); self.assertFalse(self.client.get('/api/session/').data['authenticated'])
        self.client.credentials(HTTP_AUTHORIZATION=credentials()+'wrong')
        self.assertEqual(self.client.get('/api/session/').status_code,401)
        self.assertEqual(Customer.objects.count(),0)

    def test_expired_init_data_does_not_create_a_customer(self):
        self.client.credentials(HTTP_AUTHORIZATION=credentials(timestamp=int(time.time())-3601))
        self.assertEqual(self.client.get('/api/session/').status_code,401)
        self.assertEqual(Customer.objects.count(),0)

    def test_guest_opens_bot_chat_with_current_menu_instead_of_a_stale_main_app_link(self):
        self.client.credentials()
        with self.settings(MINIAPP_BOT_USERNAME='store_bot', MINIAPP_PUBLIC_URL='https://new-launch.example'):
            session = self.client.get('/api/session/').data
        self.assertFalse(session['authenticated'])
        self.assertEqual(session['telegram_url'], 'https://t.me/store_bot')
        self.assertEqual(Customer.objects.count(), 0)

    def test_new_launch_and_changed_public_url_keep_customer_phone_and_order_history(self):
        order = self.order()
        customer_id = order.customer_id
        for domain in ('first-launch.example', 'second-launch.example'):
            with self.settings(MINIAPP_PUBLIC_URL=f'https://{domain}'):
                client = APIClient()
                client.credentials(HTTP_AUTHORIZATION=credentials())
                session = client.get('/api/session/', HTTP_ORIGIN=f'https://{domain}').data
                self.assertTrue(session['authenticated'])
                self.assertEqual(session['user']['customer_id'], customer_id)
                self.assertEqual(session['user']['phone'], '+79781234567')
                history = client.get('/api/orders/').data
                self.assertEqual(history['count'], 1)
                self.assertEqual(history['results'][0]['id'], str(order.public_id))
        self.assertEqual(Customer.objects.count(), 1)
        guest = APIClient().get('/api/session/')
        self.assertFalse(guest.data['authenticated'])
        self.assertEqual(Customer.objects.count(), 1)

    def test_order_links_customer_saves_phone_and_preserves_snapshot_after_profile_edit(self):
        order=self.order()
        self.assertEqual(order.customer.telegram_id,7001)
        self.assertEqual(order.customer.phone,'+79781234567')
        response=self.client.patch('/api/profile/',{'phone':'+79789999999'},format='json')
        self.assertEqual(response.status_code,200,response.data)
        order.refresh_from_db(); self.assertEqual(order.phone,'+79781234567')
        self.assertEqual(self.client.get('/api/session/').data['user']['phone'],'+79789999999')

    def test_failed_order_never_saves_contact_or_creates_outbox_entry(self):
        payload=self.payload(); payload['items'][0]['expected_price']='1'
        self.assertEqual(self.client.post('/api/orders/',payload,format='json').status_code,409)
        self.assertEqual(Customer.objects.get().phone,'')
        self.assertFalse(Order.objects.exists()); self.assertFalse(OrderNotification.objects.exists())

    def test_duplicate_checkout_creates_one_order_and_one_notification(self):
        data=self.payload()
        self.assertEqual(self.client.post('/api/orders/',data,format='json').status_code,201)
        self.assertEqual(self.client.post('/api/orders/',data,format='json').status_code,200)
        self.assertEqual(Order.objects.count(),1); self.assertEqual(OrderNotification.objects.count(),1)

    def test_phone_validation_and_customer_ownership(self):
        self.order(); original=Customer.objects.get().phone
        for invalid in ('123', '+7978123456', '+797812345678', '+0000000000'):
            self.assertEqual(self.client.patch('/api/profile/',{'phone':invalid},format='json').status_code,400)
        self.client.credentials(HTTP_AUTHORIZATION=credentials(user_id=7002))
        self.client.patch('/api/profile/',{'phone':'+79781111111'},format='json')
        self.assertEqual(Customer.objects.get(telegram_id=7001).phone,original)

    def test_repeat_uses_current_price_and_does_not_change_historical_order(self):
        order=self.order(); self.product.price=Decimal('150'); self.product.save()
        data=self.client.post(f'/api/orders/{order.public_id}/repeat/',{},format='json').data
        self.assertEqual(data['items'][0]['product']['price'],'150.00')
        self.assertEqual(data['items'][0]['quantity'],'2.000')
        self.assertEqual(len(data['changed']),1)
        self.assertEqual(order.items.get().unit_price,Decimal('100'))

    def test_repeat_excludes_unavailable_and_changed_units_without_replacement(self):
        order=self.order(); self.product.is_available=False; self.product.save()
        Product.objects.create(name=self.product.name,sku='similar',price=1)
        path=f'/api/orders/{order.public_id}/repeat/'
        self.assertEqual(self.client.post(path,{},format='json').data['items'],[])
        self.product.is_available=True; self.product.unit='kg'; self.product.save()
        self.assertEqual(self.client.post(path,{},format='json').data['items'],[])

    def test_other_customer_cannot_view_or_repeat_order(self):
        order=self.order(); self.client.credentials(HTTP_AUTHORIZATION=credentials(user_id=7002))
        self.assertEqual(self.client.get(f'/api/orders/{order.public_id}/').status_code,404)
        self.assertEqual(self.client.post(f'/api/orders/{order.public_id}/repeat/',{},format='json').status_code,404)

    def test_notification_failure_never_loses_order_or_changes_customer_history(self):
        order=self.order(); row=order.notification
        with patch('storefront.notifications.telegram_call',side_effect=DeliveryError('HTTP 503',retryable=True)):
            self.assertFalse(deliver_one(row.pk))
        row.refresh_from_db(); self.assertEqual(row.status,'failed')
        self.assertEqual(Order.objects.count(),1)
        self.assertEqual(self.client.get('/api/orders/').data['count'],1)

    def test_successful_delivery_is_not_duplicated_and_has_private_admin_link(self):
        row=self.order().notification
        with patch('storefront.notifications.telegram_call',return_value={'message_id':99}) as sender:
            self.assertTrue(deliver_one(row.pk)); self.assertFalse(deliver_one(row.pk))
        self.assertEqual(sender.call_count,1)
        data=sender.call_args.args[1]
        self.assertIn('НОВЫЙ ЗАКАЗ',data['text']); self.assertIn('+79781234567',data['text'])
        self.assertIn('https://admin.example.test/admin/',data['reply_markup']['inline_keyboard'][0][0]['url'])

    def test_timeout_or_abandoned_sending_requires_manual_delivery_check(self):
        row=self.order().notification
        with patch('storefront.notifications.telegram_call',side_effect=DeliveryError('Timeout',uncertain=True)):
            self.assertFalse(deliver_one(row.pk))
        row.refresh_from_db(); self.assertEqual(row.status,'uncertain'); self.assertFalse(deliver_one(row.pk))
        OrderNotification.objects.filter(pk=row.pk).update(status='sending',lease_until=timezone.now()-timedelta(seconds=1))
        self.assertEqual(recover_abandoned(),1)
        self.assertEqual(OrderNotification.objects.get().status,'uncertain')

    def test_worker_disabled_configuration_does_not_send_or_drop_queued_order(self):
        row=self.order().notification
        with override_settings(TELEGRAM_NOTIFICATIONS_ENABLED=False), patch('storefront.notifications.telegram_call') as sender:
            self.assertFalse(deliver_one(row.pk)); sender.assert_not_called()
        self.assertEqual(OrderNotification.objects.get().status,'pending')

    def test_long_orders_are_split_into_telegram_sized_messages(self):
        order=self.order()
        for number in range(40):
            order.items.create(product_name='Продукт 😀'*20,sku=str(number),quantity=1,unit='pcs',unit_price=1,subtotal=1)
        parts=message_parts(order)
        self.assertGreater(len(parts),1)
        self.assertTrue(all(len(part.encode('utf-16-le'))//2<=4096 for part in parts))

    def test_staff_status_changes_are_audited_once_and_visible_to_owner(self):
        order=self.order(); user=get_user_model().objects.create_superuser('accounts-admin',password='test-only')
        request=RequestFactory().post('/admin/'); request.user=user
        order.status='ready'; model_admin=admin.site._registry[Order]
        model_admin.save_model(request,order,None,True); model_admin.save_model(request,order,None,True)
        self.assertEqual(OrderStatusEvent.objects.filter(order=order).count(),2)
        self.assertEqual(self.client.get(f'/api/orders/{order.public_id}/').data['status_label'],'Готов')
        self.client.force_login(user)
        for name in ('customer','ordernotification'):
            self.assertEqual(self.client.get(reverse(f'admin:storefront_{name}_changelist')).status_code,200)

    def test_map_is_configurable_but_external_script_urls_are_not_accepted(self):
        from django.core.exceptions import ValidationError
        profile=StoreProfile(map_embed_url='https://evil.example/steal')
        with self.assertRaises(ValidationError): profile.full_clean()
