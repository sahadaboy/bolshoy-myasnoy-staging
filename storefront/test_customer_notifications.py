from datetime import datetime, timedelta
from io import BytesIO
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from uuid import uuid4
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import skipUnless
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

from django.conf import settings
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.db import connection, close_old_connections, IntegrityError, transaction
from django.db.migrations.executor import MigrationExecutor
from django.db.models.query import QuerySet
from django.test import RequestFactory, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from .models import Order, OrderAcceptance, OrderNotification, OrderStatusEvent, CustomerOrderNotification
from .customer_notifications import confirmation_payload, deliver_one, dispatch_after_commit, enqueue_confirmation, recover_abandoned
from .notifications import DeliveryError, telegram_call
from .order_acceptance import process_callback
from .order_messages import MOSCOW
from .test_accounts import TOKEN, credentials
from . import test_pickup_confirmation as pickup_tests


def make_order(**values):
    return Order.objects.create(telegram_user_id=7001, request_id=uuid4(), request_fingerprint='fixture',
        buyer_name='Покупатель', phone='+79780000000', pickup_address='Магазин', total='100.00',
        pickup_at=datetime(2026,11,22,11,30,tzinfo=__import__('datetime').timezone.utc), **values)


@override_settings(TELEGRAM_BOT_TOKEN=TOKEN, TELEGRAM_CUSTOMER_NOTIFICATIONS_ENABLED=True,
    TELEGRAM_ORDER_WEBHOOK_ENABLED=True, TELEGRAM_WEBHOOK_SECRET='customer-test-'+'x'*32,
    TELEGRAM_ORDER_STAFF_IDS=frozenset([100,200]), MINIAPP_BOT_USERNAME='store_bot',
    MINIAPP_PUBLIC_URL='https://store.example', MINIAPP_ADMIN_URL='https://store.example')
class CustomerNotificationTests(TransactionTestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear()
        self.order=make_order()
        self.group=OrderNotification.objects.create(order=self.order,status='sent',payload_parts=['Original order'],
            destination='-100001',sent_parts=1,telegram_message_ids=[777])
        self.acceptance=OrderAcceptance.objects.create(order=self.order)
        self.counter=0;self.client=APIClient()
        staff=patch('storefront.order_acceptance.telegram_call',return_value=True)
        buyer=patch('storefront.customer_notifications.telegram_call',return_value={'message_id':900,'chat':{'id':7001}})
        self.staff_api=staff.start();self.buyer_api=buyer.start()
        self.addCleanup(staff.stop);self.addCleanup(buyer.stop)

    def update(self, action='s', staff=100, nonce=None):
        self.counter+=1
        return {'update_id':self.counter,'callback_query':{'id':f'customer-{self.counter}',
            'from':{'id':staff,'first_name':'Employee','username':'employee'},
            'data':f'oa:{self.acceptance.token.hex}:{action}'+(':'+nonce if nonce else ''),
            'message':{'message_id':777,'chat':{'id':-100001,'type':'supergroup'},
                       'from':{'is_bot':True,'username':'store_bot'}}}}

    def post(self, update):
        response=self.client.post('/api/telegram/order-webhook/',update,format='json',
            HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=settings.TELEGRAM_WEBHOOK_SECRET)
        self.assertEqual(response.status_code,200)
        return update

    def start(self):
        self.post(self.update());self.acceptance.refresh_from_db()
        return self.acceptance.pending_nonce

    def confirm(self):
        nonce=self.start();return self.post(self.update('y',nonce=nonce))

    def notice(self): return CustomerOrderNotification.objects.get(order=self.order)

    def admin_request(self, **data):
        user,_=get_user_model().objects.get_or_create(username='notice-admin',defaults={'is_staff':True,'is_superuser':True})
        request=RequestFactory().post('/admin/storefront/customerordernotification/',data)
        request.user=user
        return request

    def action(self, name, **data):
        model_admin=admin.site._registry[CustomerOrderNotification]
        request=self.admin_request(**data)
        with patch.object(model_admin,'message_user'):
            result=getattr(model_admin,name)(request,CustomerOrderNotification.objects.filter(order=self.order))
        return result,request

    def test_only_final_confirm_sends_to_order_buyer_after_commit_and_preserves_group(self):
        nonce=self.start();self.buyer_api.assert_not_called();self.assertFalse(CustomerOrderNotification.objects.exists())
        self.post(self.update('y',staff=200,nonce=nonce));self.buyer_api.assert_not_called()
        self.post(self.update('c',nonce=nonce));self.buyer_api.assert_not_called()
        def sent(method,payload,**kwargs):
            self.assertFalse(connection.in_atomic_block)
            self.order.refresh_from_db();self.acceptance.refresh_from_db()
            self.assertEqual(self.order.status,'confirmed');self.assertIsNotNone(self.acceptance.accepted_at)
            self.assertEqual(payload['chat_id'],self.order.telegram_user_id)
            self.assertNotEqual(payload['chat_id'],self.acceptance.accepted_staff_id)
            return {'message_id':900,'chat':{'id':7001}}
        self.buyer_api.side_effect=sent
        self.confirm();row=self.notice();self.assertEqual((row.kind,row.status,row.telegram_message_id),('ORDER_CONFIRMED','sent',900))
        self.assertEqual(row.attempts,1);self.buyer_api.assert_called_once()
        self.assertEqual(self.buyer_api.call_args.args[0],'sendMessage')
        self.assertEqual(self.client.get('/api/orders/',HTTP_AUTHORIZATION=credentials()).data['results'][0]['status'],'confirmed')
        self.group.refresh_from_db();self.assertEqual(self.group.payload_parts,['Original order']);self.assertEqual(self.group.telegram_message_ids,[777])
        edits=[c for c in self.staff_api.call_args_list if c.args[0].startswith('edit')]
        self.assertTrue(edits[-1].args[1]['reply_markup']['inline_keyboard'][0][0]['text'].startswith('✅ Заказ принят · '))
        self.assertTrue(all(c.args[0] in ('editMessageReplyMarkup','answerCallbackQuery') for c in self.staff_api.call_args_list))

    def test_message_escapes_number_and_formats_moscow_pickup_with_private_web_app_button(self):
        self.order.number='БМ-<b>&';self.order.save(update_fields=['number'])
        payload=confirmation_payload(self.order)
        self.assertIn('Заказ № БМ-&lt;b&gt;&amp;',payload['text'])
        self.assertIn('📅 <b>Самовывоз:</b> 22 ноября, 14:30',payload['text'])
        self.assertIn('✅ <b>ВАШ ЗАКАЗ ПРИНЯТ!</b>',payload['text']);self.assertEqual(payload['parse_mode'],'HTML')
        button=payload['reply_markup']['inline_keyboard'][0][0]
        self.assertEqual(button,{'text':'🛒 Посмотреть заказ','web_app':{'url':f'https://store.example/profile/orders/{self.order.public_id}'}})
        self.assertNotIn('token',button['web_app']['url']);self.assertNotIn('initData',button['web_app']['url'])
        self.order.pickup_at=None
        self.assertIn('время уточняется оператором',confirmation_payload(self.order)['text'])

    def test_link_never_authorizes_a_different_buyer(self):
        path=urlsplit(confirmation_payload(self.order)['reply_markup']['inline_keyboard'][0][0]['web_app']['url']).path
        self.assertEqual(path,f'/profile/orders/{self.order.public_id}')
        endpoint=f'/api/orders/{self.order.public_id}/'
        self.assertEqual(self.client.get(endpoint,HTTP_AUTHORIZATION=credentials(7001)).status_code,200)
        self.assertEqual(self.client.get(endpoint,HTTP_AUTHORIZATION=credentials(7002)).status_code,404)
        self.assertEqual(self.client.get(endpoint).status_code,401)
        with TemporaryDirectory() as folder:
            root=Path(folder);(root/'frontend/dist').mkdir(parents=True)
            (root/'frontend/dist/index.html').write_text('<h1>Compiled Mini App shell</h1>')
            with override_settings(ROOT_URLCONF='config.urls_staging',BASE_DIR=root):
                response=self.client.get(path);self.assertEqual(response.status_code,200);response.close()

    def test_repeated_updates_old_buttons_and_indicator_never_send_another_notice(self):
        final=self.confirm();self.post(final);self.post(self.update('y',nonce=final['callback_query']['data'].split(':')[-1]))
        self.post(self.update('s'));self.post(self.update('i',staff=200))
        self.assertEqual(CustomerOrderNotification.objects.count(),1);self.buyer_api.assert_called_once()
        self.assertEqual(OrderStatusEvent.objects.filter(order=self.order,status='confirmed').count(),1)
        with self.assertRaises(IntegrityError),transaction.atomic():
            CustomerOrderNotification.objects.create(order=self.order,recipient_telegram_id=7001)

    def test_disabled_flag_and_old_confirmed_orders_are_never_backfilled(self):
        with override_settings(TELEGRAM_CUSTOMER_NOTIFICATIONS_ENABLED=False): self.confirm()
        self.assertFalse(CustomerOrderNotification.objects.exists());self.buyer_api.assert_not_called()
        self.post(self.update('s'));self.post(self.update('i'))
        self.assertFalse(CustomerOrderNotification.objects.exists());self.buyer_api.assert_not_called()

    def test_outer_transaction_defers_network_and_rollback_discards_outbox(self):
        nonce=self.start()
        with self.assertRaises(RuntimeError):
            with transaction.atomic():
                process_callback(self.update('y',nonce=nonce))
                self.assertEqual(CustomerOrderNotification.objects.count(),1);self.buyer_api.assert_not_called()
                with self.assertRaises(RuntimeError): deliver_one(self.notice().pk)
                raise RuntimeError('rollback')
        self.order.refresh_from_db();self.assertEqual(self.order.status,'new')
        self.assertFalse(CustomerOrderNotification.objects.exists());self.buyer_api.assert_not_called()
        with transaction.atomic():
            process_callback(self.update('y',nonce=nonce));self.buyer_api.assert_not_called()
        self.buyer_api.assert_called_once()

    def test_blocked_buyer_does_not_undo_order_or_employee_confirmation_and_retry_is_explicit(self):
        self.buyer_api.side_effect=DeliveryError('forbidden',code=403)
        self.confirm();self.order.refresh_from_db();row=self.notice()
        self.assertEqual(self.order.status,'confirmed');self.assertEqual((row.status,row.last_error_code),('failed',403))
        self.assertIn('заблокировать',row.last_error)
        self.post(self.update('i'));self.assertEqual(self.buyer_api.call_count,1)
        self.buyer_api.side_effect=None
        self.action('retry_failed');row.refresh_from_db();self.assertEqual(row.status,'sent');self.assertEqual(row.attempts,2)
        self.assertEqual(OrderStatusEvent.objects.filter(order=self.order,status='confirmed').count(),1)
        self.action('retry_failed');self.assertEqual(self.buyer_api.call_count,2)

    def test_rate_limit_is_known_failure_with_cooldown_and_preserved_payload(self):
        self.buyer_api.side_effect=DeliveryError('rate limit',code=429,retryable=True)
        self.confirm();row=self.notice();original=row.payload
        self.assertEqual(row.status,'failed');self.action('retry_failed');self.assertEqual(self.buyer_api.call_count,1)
        CustomerOrderNotification.objects.filter(pk=row.pk).update(next_attempt_at=timezone.now()-timedelta(seconds=1))
        self.buyer_api.side_effect=None
        self.action('retry_failed');row.refresh_from_db();self.assertEqual(row.status,'sent');self.assertEqual(row.payload,original)

    def test_ambiguous_sends_and_server_errors_cannot_be_blindly_retried(self):
        self.buyer_api.side_effect=DeliveryError('timeout',uncertain=True)
        self.confirm();row=self.notice();self.assertEqual(row.status,'uncertain')
        self.assertFalse(dispatch_after_commit(row.pk));self.action('retry_failed');self.action('send_pending')
        self.assertEqual(self.buyer_api.call_count,1)
        response,_=self.action('review_delivery');response.render();self.assertEqual(response.status_code,200)
        self.assertContains(response,'name="csrfmiddlewaretoken"')
        self.action('review_delivery',apply_review='yes',resolution='not_received')
        row.refresh_from_db();self.assertEqual(row.status,'uncertain');self.assertEqual(self.buyer_api.call_count,1)
        self.buyer_api.side_effect=DeliveryError('server error',code=503,retryable=True)
        self.action('review_delivery',apply_review='yes',resolution='not_received',checked='on')
        row.refresh_from_db();self.assertEqual((row.status,row.last_error_code),('uncertain',503));self.assertEqual(row.attempts,2)
        self.assertFalse(dispatch_after_commit(row.pk));self.assertEqual(self.buyer_api.call_count,2)

    def test_verified_non_delivery_allows_one_retry_with_audit(self):
        self.buyer_api.side_effect=DeliveryError('timeout',uncertain=True)
        self.confirm();original=self.notice().payload;self.buyer_api.side_effect=None
        _,request=self.action('review_delivery',apply_review='yes',resolution='not_received',checked='on')
        row=self.notice();self.assertEqual(row.status,'sent');self.assertEqual(row.review_result,'not_received')
        self.assertEqual(row.reviewed_by,request.user);self.assertIsNotNone(row.reviewed_at);self.assertEqual(row.payload,original)
        self.assertEqual(self.buyer_api.call_count,2)
        self.action('review_delivery',apply_review='yes',resolution='not_received',checked='on')
        self.assertEqual(self.buyer_api.call_count,2)

    def test_verified_received_marks_sent_without_resending(self):
        self.buyer_api.side_effect=DeliveryError('timeout',uncertain=True)
        self.confirm();self.action('review_delivery',apply_review='yes',resolution='received',checked='on')
        row=self.notice();self.assertEqual(row.status,'sent');self.assertEqual(row.review_result,'received')
        self.assertIsNone(row.telegram_message_id);self.assertEqual(self.buyer_api.call_count,1)
        self.assertFalse(dispatch_after_commit(row.pk))

    def test_feature_switch_blocks_pending_and_failed_admin_delivery(self):
        with patch('storefront.customer_notifications.dispatch_after_commit',return_value=False): self.confirm()
        row=self.notice();self.assertEqual(row.status,'pending')
        with override_settings(TELEGRAM_CUSTOMER_NOTIFICATIONS_ENABLED=False):
            self.assertFalse(dispatch_after_commit(row.pk));self.action('send_pending')
        self.buyer_api.assert_not_called();self.action('send_pending');self.buyer_api.assert_called_once()

    def test_lost_worker_lease_requires_manual_review(self):
        with patch('storefront.customer_notifications.dispatch_after_commit',return_value=False): self.confirm()
        row=self.notice();CustomerOrderNotification.objects.filter(pk=row.pk).update(status='sending',lease_until=timezone.now()+timedelta(seconds=120))
        self.assertEqual(recover_abandoned(),0);self.assertFalse(dispatch_after_commit(row.pk))
        CustomerOrderNotification.objects.filter(pk=row.pk).update(lease_until=timezone.now()-timedelta(seconds=1))
        self.assertEqual(recover_abandoned(),1);row.refresh_from_db();self.assertEqual(row.status,'uncertain')
        self.assertFalse(dispatch_after_commit(row.pk));self.buyer_api.assert_not_called()

    def test_missing_url_invalid_buyer_or_changed_status_fail_before_sending(self):
        with override_settings(MINIAPP_PUBLIC_URL='http://insecure.example'): self.confirm()
        row=self.notice();self.assertEqual(row.status,'failed');self.assertEqual(row.attempts,0);self.buyer_api.assert_not_called()
        self.order.status='cancelled';self.order.save(update_fields=['status'])
        self.action('retry_failed');row.refresh_from_db();self.assertEqual(row.status,'failed');self.buyer_api.assert_not_called()
        self.order.status='confirmed';self.order.telegram_user_id=9002;self.order.save(update_fields=['status','telegram_user_id'])
        self.action('retry_failed');row.refresh_from_db();self.assertEqual(row.status,'failed');self.buyer_api.assert_not_called()

    def test_unexpected_exception_is_sanitized_and_never_rolls_back_acceptance(self):
        self.buyer_api.side_effect=RuntimeError('private-token-and-data')
        self.confirm();self.order.refresh_from_db();row=self.notice()
        self.assertEqual(self.order.status,'confirmed');self.assertEqual(row.status,'uncertain')
        self.assertNotIn('private-token',row.last_error)

    def test_lost_database_ack_after_successful_send_is_uncertain_without_resend(self):
        original=QuerySet.update
        def fail_ack(queryset,**values):
            if queryset.model is CustomerOrderNotification and values.get('status')=='sent':
                raise RuntimeError('simulated receipt persistence failure')
            return original(queryset,**values)
        with patch.object(QuerySet,'update',autospec=True,side_effect=fail_ack): self.confirm()
        row=self.notice();self.order.refresh_from_db()
        self.assertEqual((self.order.status,row.status,row.attempts),('confirmed','uncertain',1))
        self.buyer_api.assert_called_once();self.assertFalse(dispatch_after_commit(row.pk));self.buyer_api.assert_called_once()

    def test_missing_telegram_receipt_is_uncertain(self):
        self.buyer_api.return_value={'ok':True}
        self.confirm();self.assertEqual(self.notice().status,'uncertain');self.assertEqual(self.notice().attempts,1)

    def test_stored_payload_cannot_redirect_delivery_to_employee(self):
        with patch('storefront.customer_notifications.dispatch_after_commit',return_value=False): self.confirm()
        row=self.notice();row.payload=confirmation_payload(self.order);row.payload['chat_id']=100
        row.save(update_fields=['payload'])
        self.assertFalse(dispatch_after_commit(row.pk));self.buyer_api.assert_not_called()
        row.refresh_from_db();self.assertEqual(row.status,'failed');self.assertEqual(row.attempts,0)

    def test_receipt_for_another_chat_is_uncertain_and_never_retargeted(self):
        self.buyer_api.return_value={'message_id':900,'chat':{'id':9002}}
        self.confirm();self.assertEqual(self.notice().status,'uncertain')
        self.assertEqual(self.buyer_api.call_args.args[1]['chat_id'],7001)
        self.assertFalse(dispatch_after_commit(self.notice().pk));self.assertEqual(self.buyer_api.call_count,1)

    def test_transport_exposes_only_sanitized_error_codes_to_customer_outbox(self):
        for code in (403,429,503):
            with patch('storefront.notifications.urlopen',side_effect=HTTPError('https://secret.invalid/private-token',code,'secret',{},BytesIO(b'{}'))):
                with self.assertRaises(DeliveryError) as result: telegram_call('sendMessage',{})
            self.assertEqual(result.exception.code,code);self.assertNotIn('private-token',str(result.exception))
        with patch('storefront.notifications.urlopen',side_effect=URLError('private-token')):
            with self.assertRaises(DeliveryError) as result: telegram_call('sendMessage',{})
        self.assertTrue(result.exception.uncertain)


@skipUnless(connection.vendor=='postgresql','Requires PostgreSQL row locks')
@override_settings(TELEGRAM_CUSTOMER_NOTIFICATIONS_ENABLED=True,TELEGRAM_BOT_TOKEN=TOKEN,MINIAPP_PUBLIC_URL='https://store.example')
class ConcurrentCustomerConfirmations(pickup_tests.ConcurrentAcceptanceTests):
    def test_two_staff_members_cannot_accept_the_same_order(self):
        with patch('storefront.customer_notifications.telegram_call',return_value={'message_id':801,'chat':{'id':1}}) as api:
            super().test_two_staff_members_cannot_accept_the_same_order()
        self.assertEqual(CustomerOrderNotification.objects.count(),1)
        row=CustomerOrderNotification.objects.get();self.assertEqual(row.status,'sent');self.assertEqual(row.recipient_telegram_id,1)
        api.assert_called_once();self.assertEqual(api.call_args.args[1]['chat_id'],1)

    def test_two_senders_claim_only_one_personal_delivery(self):
        order=make_order(status='confirmed')
        row=CustomerOrderNotification.objects.create(order=order,recipient_telegram_id=7001)
        barrier=Barrier(2)
        def worker(_):
            close_old_connections()
            try:
                barrier.wait(timeout=20);return dispatch_after_commit(row.pk)
            finally: close_old_connections()
        with patch('storefront.customer_notifications.telegram_call',return_value={'message_id':802,'chat':{'id':7001}}) as api:
            with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(worker,[1,2]))
        self.assertEqual(sum(results),1);api.assert_called_once();row.refresh_from_db();self.assertEqual(row.attempts,1)


@skipUnless(connection.vendor=='postgresql','Migration safety is verified on isolated PostgreSQL')
class CustomerNotificationMigrationTests(TransactionTestCase):
    def test_additive_migration_preserves_existing_orders_outbox_and_products_without_backfill(self):
        before=[('storefront','0013_convert_explicit_store_hours')]
        after=[('storefront','0014_customerordernotification')]
        executor=MigrationExecutor(connection)
        try:
            executor.migrate(before);apps=executor.loader.project_state(before).apps
            order=apps.get_model('storefront','Order').objects.create(telegram_user_id=9001,request_id=uuid4(),request_fingerprint='legacy',
                buyer_name='Legacy',phone='+70000000000',pickup_address='Store',total='100.00',status='confirmed')
            notification=apps.get_model('storefront','OrderNotification').objects.create(order=order,status='sent',payload_parts=['unchanged'],
                destination='-100001',sent_parts=1,telegram_message_ids=[555])
            product=apps.get_model('shop','Product').objects.create(name='Keep product',sku='migration-keep',price='123.45',image='products/keep.png')
            original=apps.get_model('storefront','Order').objects.filter(pk=order.pk).values().get()
            outbox=apps.get_model('storefront','OrderNotification').objects.filter(pk=notification.pk).values().get()
            product_data=apps.get_model('shop','Product').objects.filter(pk=product.pk).values().get()
            executor=MigrationExecutor(connection);executor.migrate(after);apps=executor.loader.project_state(after).apps
            self.assertEqual(apps.get_model('storefront','Order').objects.filter(pk=order.pk).values().get(),original)
            self.assertEqual(apps.get_model('storefront','OrderNotification').objects.filter(pk=notification.pk).values().get(),outbox)
            self.assertEqual(apps.get_model('shop','Product').objects.filter(pk=product.pk).values().get(),product_data)
            self.assertFalse(apps.get_model('storefront','CustomerOrderNotification').objects.exists())
        finally:
            MigrationExecutor(connection).migrate(after)
