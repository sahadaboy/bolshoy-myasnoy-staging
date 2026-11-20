from datetime import datetime, timedelta, time as daytime
from decimal import Decimal
from uuid import uuid4
from unittest import skipUnless
from unittest.mock import patch
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from django.db import connection, close_old_connections
from django.test import TestCase, TransactionTestCase, override_settings
from django.test import SimpleTestCase, RequestFactory
from django.core.management import call_command, CommandError
from io import StringIO
from io import BytesIO
from urllib.error import HTTPError
import json
from django.utils import timezone
from rest_framework.test import APIClient
from shop.models import Product
from .models import StoreProfile, StoreOpeningInterval, Order, OrderItem, OrderNotification, OrderAcceptance, OrderStatusEvent, TelegramCallbackReceipt
from .pickup import slots, validate_pickup, parse_legacy_hours, opening_text, MOSCOW
from .order_messages import message_parts
from .order_acceptance import process_callback, refresh_message
from .order_api import OrderRequestSerializer, fingerprint
from .notifications import DeliveryError, deliver_one, telegram_call
from .test_accounts import credentials, TOKEN


from ._test_pickup_fixtures import schedule, available_pickup

class PickupCalendarTests(TestCase):
    def setUp(self):
        self.store=schedule();self.now=datetime(2026,11,21,10,5,tzinfo=MOSCOW)

    def test_eight_days_moscow_half_hour_grid_and_minimum_preparation(self):
        calendar=slots(self.store,now=self.now)
        self.assertEqual(len(calendar['days']),8)
        self.assertEqual(calendar['days'][-1]['date'],'2026-11-28')
        today=calendar['days'][0]['slots']
        self.assertEqual(next(r['time'] for r in today if r['available']),'11:30')
        self.assertFalse(next(r for r in today if r['time']=='11:00')['available'])
        self.assertEqual(today[-1]['time'],'19:30')
        self.assertTrue(all(r['at'].endswith('+03:00') for r in today))

    def test_last_day_allowed_future_day_past_time_and_non_grid_rejected(self):
        from rest_framework.exceptions import ValidationError
        for value in [self.now-timedelta(days=1), self.now+timedelta(minutes=30), datetime(2026,11,29,12,tzinfo=MOSCOW), datetime(2026,11,21,12,15,tzinfo=MOSCOW), datetime(2026,11,21,20,tzinfo=MOSCOW)]:
            with self.assertRaises(ValidationError): validate_pickup(value,self.store,now=self.now)
        validate_pickup(datetime(2026,11,28,19,30,tzinfo=MOSCOW),self.store,now=self.now)
        validate_pickup(datetime(2026,11,22,8,tzinfo=MOSCOW),self.store,now=self.now)

    def test_closed_day_split_intervals_and_real_wednesday_schedule(self):
        self.assertIn('Среда: 08:00–19:00',opening_text(self.store))
        StoreOpeningInterval.objects.filter(weekday=5).delete()
        StoreOpeningInterval.objects.create(store=self.store,weekday=5,opens='08:15',closes='12:00')
        StoreOpeningInterval.objects.create(store=self.store,weekday=5,opens='13:00',closes='17:00')
        today=slots(self.store,now=self.now)['days'][0]['slots']
        self.assertEqual(today[0]['time'],'08:30');self.assertNotIn('12:00',[r['time'] for r in today])
        StoreOpeningInterval.objects.filter(weekday=6).delete()
        self.assertEqual(slots(self.store,now=self.now)['days'][1]['slots'],[])
        self.assertIn('Воскресенье: Закрыто',opening_text(self.store))

    def test_no_today_intervals_proposes_tomorrow_and_midnight_uses_store_date(self):
        late=datetime(2026,11,21,23,30,tzinfo=MOSCOW)
        calendar=slots(self.store,now=late)
        self.assertFalse(any(r['available'] for r in calendar['days'][0]['slots']))
        self.assertTrue(any(r['available'] for r in calendar['days'][1]['slots']))
        utc=late.astimezone(__import__('datetime').timezone.utc)
        self.assertEqual(calendar,slots(self.store,now=utc))
        self.store.preparation_minutes=120;self.store.save()
        self.assertEqual(next(r['time'] for r in slots(self.store,now=self.now)['days'][0]['slots'] if r['available']),'12:30')

    def test_ambiguous_legacy_graph_is_not_invented(self):
        self.assertIsNone(parse_legacy_hours('Ежедневно с утра до вечера'))
        self.assertIsNone(parse_legacy_hours('Понедельник: 08:00–20:00'))
        text='\n'.join(f'{name}: 08:00–20:00' for name in ['Понедельник','Вторник','Среда','Четверг','Пятница','Суббота','Воскресенье'])
        self.assertEqual(len(parse_legacy_hours(text)),7)
        self.store.schedule_configured=False;self.store.save()
        self.assertFalse(slots(self.store,now=self.now)['configured'])
        self.assertTrue(all(not d['slots'] for d in slots(self.store,now=self.now)['days']))


@override_settings(TELEGRAM_BOT_TOKEN=TOKEN, MINIAPP_ORDERS_ENABLED=True, TELEGRAM_NOTIFICATIONS_ENABLED=False,
    TELEGRAM_ORDER_WEBHOOK_ENABLED=True, TELEGRAM_WEBHOOK_SECRET='test-secret-'+'x'*32,
    TELEGRAM_ORDER_STAFF_IDS=frozenset([100,200]), MINIAPP_BOT_USERNAME='store_bot', MINIAPP_ADMIN_URL='https://admin.example')
class PickupOrderTests(TestCase):
    def setUp(self):
        from django.core.cache import cache
        cache.clear();schedule()
        self.client=APIClient();self.client.credentials(HTTP_AUTHORIZATION=credentials())
        self.product=Product.objects.create(name='Хлопья <b>500 г</b>',sku='pickup-product',price='132.99')
        self.counter=0

    def payload(self):
        return {'request_id':str(uuid4()),'buyer_name':'Анна <x>','phone':'+79781234567','comment':'Без <лука> & соуса',
            'pickup_at':available_pickup(),'items':[{'product_id':self.product.pk,'quantity':'4','expected_price':'132.99'}]}

    def create_order(self):
        response=self.client.post('/api/orders/',self.payload(),format='json')
        self.assertEqual(response.status_code,201,response.data)
        return Order.objects.get(public_id=response.data['id'])

    def delivered(self,order,legacy=False):
        row=order.notification
        row.payload_parts=['<old plain>','legacy final part'] if legacy else message_parts(order)
        row.payload_format='plain' if legacy else 'html';row.destination='-100001'
        row.telegram_message_ids=list(range(10,10+len(row.payload_parts)));row.sent_parts=len(row.payload_parts);row.status='sent';row.save()
        acceptance=OrderAcceptance.objects.create(order=order)
        return row,acceptance

    def update(self,row,notification,action='s',staff=100,nonce=None,**actor):
        self.counter+=1
        return {'update_id':self.counter,'callback_query':{'id':str(self.counter),'from':{'id':staff,'is_bot':False,'first_name':'Сотрудник <А>','username':'employee',**actor},
            'data':f'oa:{row.token.hex}:{action}'+(':'+nonce if nonce else ''),
            'message':{'message_id':notification.telegram_message_ids[-1],'chat':{'id':-100001,'type':'supergroup'},'from':{'is_bot':True,'username':'store_bot'}}}}

    def post_callback(self,data,secret=None):
        return self.client.post('/api/telegram/order-webhook/',data,format='json',HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN=secret or 'test-secret-'+'x'*32)

    def test_pickup_is_required_and_naive_or_tampered_time_rejected(self):
        body=self.payload();body.pop('pickup_at')
        self.assertEqual(self.client.post('/api/orders/',body,format='json').status_code,400)
        for value in ['2026-11-22T14:30:00','2099-11-22T14:30:00+03:00','2000-01-01T14:30:00+03:00']:
            body['pickup_at']=value
            self.assertEqual(self.client.post('/api/orders/',body,format='json').status_code,400)
        self.assertFalse(Order.objects.exists())

    def test_stale_calendar_is_rechecked_at_the_moment_of_submission(self):
        moment=datetime(2026,11,21,10,0,tzinfo=MOSCOW)
        body=self.payload();body['pickup_at']='2026-11-21T11:00:00+03:00'
        self.assertTrue(next(r for r in slots(now=moment)['days'][0]['slots'] if r['time']=='11:00')['available'])
        with patch('storefront.pickup.timezone.now',return_value=moment+timedelta(seconds=1)):
            response=self.client.post('/api/orders/',body,format='json')
        self.assertEqual(response.status_code,400);self.assertFalse(Order.objects.exists())

    @patch('storefront.order_acceptance.telegram_call',return_value=True)
    def test_unknown_updates_are_not_acknowledged_and_malformed_payloads_fail_closed(self,api):
        self.assertEqual(self.post_callback({'update_id':1,'message':{'text':'existing bot feature'}}).status_code,503)
        self.assertEqual(self.client.post('/api/telegram/order-webhook/','{',content_type='application/json',HTTP_X_TELEGRAM_BOT_API_SECRET_TOKEN='test-secret-'+'x'*32).status_code,400)
        with override_settings(TELEGRAM_ORDER_WEBHOOK_ENABLED=False): self.assertEqual(self.post_callback({}).status_code,404)
        api.assert_not_called()

    def test_admin_uses_structured_hours_and_exposes_readonly_pickup(self):
        from django.contrib import admin
        request=RequestFactory().get('/admin/')
        profile=StoreProfile.objects.get(pk=1)
        model_admin=admin.site._registry[StoreProfile]
        fields=model_admin.get_fieldsets(request,profile)[0][1]['fields']
        self.assertIn('effective_opening_hours',fields);self.assertNotIn('opening_hours',fields)
        self.assertIn('pickup_at',admin.site._registry[Order].readonly_fields)

    @patch('storefront.order_acceptance.telegram_call',return_value=True)
    def test_admin_can_add_buttons_to_a_legacy_message_without_resending_it(self,api):
        from django.contrib import admin
        order=self.create_order();notification,row=self.delivered(order,legacy=True);row.delete()
        model_admin=admin.site._registry[Order];request=RequestFactory().post('/admin/')
        with patch.object(model_admin,'message_user'):
            model_admin.enable_staff_confirmation(request,Order.objects.filter(pk=order.pk))
        self.assertEqual(OrderAcceptance.objects.filter(order=order).count(),1)
        self.assertEqual(api.call_args.args[0],'editMessageReplyMarkup')
        self.assertTrue(api.call_args.args[1]['reply_markup']['inline_keyboard'][0][0]['callback_data'].endswith(':s'))
        order.refresh_from_db();notification.refresh_from_db();self.assertEqual(order.status,'new');self.assertEqual(notification.payload_parts,['<old plain>','legacy final part'])

    def test_idempotence_includes_pickup_and_normalizes_equivalent_timezones(self):
        body=self.payload();first=self.client.post('/api/orders/',body,format='json');self.assertEqual(first.status_code,201,first.data)
        body['pickup_at']=datetime.fromisoformat(body['pickup_at']).astimezone(__import__('datetime').timezone.utc).isoformat()
        self.assertEqual(self.client.post('/api/orders/',body,format='json').status_code,200)
        body['pickup_at']=(datetime.fromisoformat(body['pickup_at'])+timedelta(minutes=30)).isoformat()
        self.assertEqual(self.client.post('/api/orders/',body,format='json').status_code,409)
        self.assertEqual(Order.objects.count(),1)
        response=self.client.get('/api/orders/').data['results'][0];self.assertIsNotNone(response['pickup_at'])

    def test_legacy_retry_without_pickup_remains_idempotent_and_old_orders_readable(self):
        body=self.payload();body.pop('pickup_at');form=OrderRequestSerializer(data=body);self.assertTrue(form.is_valid())
        old=Order.objects.create(telegram_user_id=7001,request_id=body['request_id'],request_fingerprint=fingerprint(form.validated_data),buyer_name=body['buyer_name'],phone=body['phone'],comment=body['comment'],pickup_address='Магазин',total=0)
        response=self.client.post('/api/orders/',body,format='json');self.assertEqual(response.status_code,200,response.data)
        self.assertIsNone(response.data['pickup_at']);self.assertEqual(Order.objects.count(),1)
        self.assertEqual(self.client.get(f'/api/orders/{old.public_id}/').status_code,200)

    @patch('storefront.order_acceptance.telegram_call',return_value=True)
    def test_two_stage_cancel_owner_guard_and_exact_acceptance_footer(self,api):
        order=self.create_order();notification,row=self.delivered(order)
        self.assertEqual(self.post_callback(self.update(row,notification)).status_code,200)
        order.refresh_from_db();row.refresh_from_db();self.assertEqual(order.status,'new');nonce=row.pending_nonce
        self.post_callback(self.update(row,notification,'y',staff=200,nonce=nonce));order.refresh_from_db();self.assertEqual(order.status,'new')
        self.post_callback(self.update(row,notification,'c',nonce=nonce));row.refresh_from_db();self.assertIsNone(row.pending_staff_id)
        self.post_callback(self.update(row,notification));row.refresh_from_db()
        self.post_callback(self.update(row,notification,'y',nonce=row.pending_nonce));row.refresh_from_db();order.refresh_from_db()
        self.assertEqual((order.status,row.accepted_staff_id,row.accepted_username),('confirmed',100,'employee'))
        self.assertEqual(OrderStatusEvent.objects.filter(order=order,status='confirmed').count(),1)
        edit=next(call for call in reversed(api.call_args_list) if call.args[0]=='editMessageText').args[1]
        self.assertTrue(edit['text'].startswith(notification.payload_parts[-1]));self.assertIn('✅ ЗАКАЗ ПРИНЯЛ: @employee',edit['text'])
        expected=row.accepted_at.astimezone(MOSCOW).strftime('%d.%m.%Y %H:%M')
        self.assertIn('Заказ принят в '+expected,edit['text']);self.assertNotIn('Время принятия',edit['text'])
        self.assertEqual(len(edit['reply_markup']['inline_keyboard']),1)
        self.assertFalse(any(c.args[0]=='sendMessage' for c in api.call_args_list))

    @patch('storefront.order_acceptance.telegram_call',return_value=True)
    def test_secret_staff_chat_message_and_bot_are_all_checked(self,api):
        order=self.create_order();notification,row=self.delivered(order)
        data=self.update(row,notification)
        self.assertEqual(self.post_callback(data,secret='wrong').status_code,403);api.assert_not_called()
        self.post_callback(self.update(row,notification,staff=999))
        for key,value in [('message_id',999),('chat',{'id':-999,'type':'supergroup'}),('from',{'is_bot':True,'username':'other'})]:
            invalid=self.update(row,notification);invalid['callback_query']['message'][key]=value;self.post_callback(invalid)
        row.refresh_from_db();self.assertIsNone(row.pending_staff_id);self.assertFalse(TelegramCallbackReceipt.objects.exists())

    @patch('storefront.order_acceptance.telegram_call',return_value=True)
    def test_expiry_stale_nonce_and_duplicate_updates_do_not_accept_twice(self,api):
        order=self.create_order();notification,row=self.delivered(order)
        first=self.update(row,notification);self.post_callback(first);row.refresh_from_db();nonce=row.pending_nonce
        edits=len([c for c in api.call_args_list if c.args[0].startswith('edit')]);self.post_callback(first)
        self.assertEqual(len([c for c in api.call_args_list if c.args[0].startswith('edit')]),edits)
        OrderAcceptance.objects.filter(pk=row.pk).update(pending_until=timezone.now()-timedelta(seconds=1))
        self.post_callback(self.update(row,notification,'y',nonce=nonce));row.refresh_from_db();self.assertIsNone(row.pending_staff_id)
        self.post_callback(self.update(row,notification));row.refresh_from_db();self.assertNotEqual(row.pending_nonce,nonce)
        self.post_callback(self.update(row,notification,'y',nonce=nonce));order.refresh_from_db();self.assertEqual(order.status,'new')

    def test_telegram_failure_never_loses_confirmation_and_admin_retry_is_idempotent(self):
        order=self.create_order();notification,row=self.delivered(order,legacy=True)
        with patch('storefront.order_acceptance.telegram_call',return_value=True): self.post_callback(self.update(row,notification))
        row.refresh_from_db()
        def failing(method,*args,**kwargs):
            if method.startswith('edit'): raise DeliveryError('Telegram временно недоступен',retryable=True)
            return True
        with patch('storefront.order_acceptance.telegram_call',side_effect=failing): self.post_callback(self.update(row,notification,'y',nonce=row.pending_nonce,username='',first_name='<Анна &>'))
        order.refresh_from_db();row.refresh_from_db();self.assertEqual(order.status,'confirmed');self.assertTrue(row.edit_error)
        with patch('storefront.order_acceptance.telegram_call',return_value=True) as api:
            self.assertTrue(refresh_message(row.pk,force=True));self.assertTrue(refresh_message(row.pk,force=True))
        for call in api.call_args_list:
            text=call.args[1]['text'];self.assertEqual(text.count('ЗАКАЗ ПРИНЯЛ'),1);self.assertIn('&lt;Анна &amp;&gt;',text)
        self.assertEqual(OrderStatusEvent.objects.filter(status='confirmed').count(),1)

    def test_database_rollback_never_answers_that_order_was_accepted(self):
        order=self.create_order();notification,row=self.delivered(order)
        with patch('storefront.order_acceptance.telegram_call',return_value=True): self.post_callback(self.update(row,notification))
        row.refresh_from_db()
        with patch('storefront.order_acceptance.telegram_call',return_value=True) as api,patch.object(OrderAcceptance,'save',side_effect=RuntimeError('simulated database failure')):
            with self.assertRaises(RuntimeError): process_callback(self.update(row,notification,'y',nonce=row.pending_nonce))
        order.refresh_from_db();row.refresh_from_db();self.assertEqual(order.status,'new');self.assertIsNone(row.accepted_at)
        self.assertEqual(OrderStatusEvent.objects.filter(order=order,status='confirmed').count(),0)
        self.assertTrue(all(c.args[1].get('text')!='Заказ принят.' for c in api.call_args_list))

    @patch('storefront.order_acceptance.telegram_call',return_value=True)
    def test_canceled_completed_and_partial_notifications_cannot_be_accepted(self,api):
        for status in ('cancelled','collected'):
            order=self.create_order();notification,row=self.delivered(order);order.status=status;order.save()
            self.post_callback(self.update(row,notification));row.refresh_from_db();self.assertIsNone(row.accepted_at)
        order=self.create_order();notification,row=self.delivered(order);notification.telegram_message_ids=[];notification.save()
        self.post_callback(self.update(row,self.delivered_message_stub(notification)));row.refresh_from_db();self.assertIsNone(row.pending_staff_id)

    def delivered_message_stub(self,row):
        row.telegram_message_ids=[777];return row

    def test_html_format_long_orders_and_frozen_legacy_delivery(self):
        order=self.create_order()
        for n in range(45): OrderItem.objects.create(order=order,product_name='<&>'*80,sku=str(n),quantity=Decimal('0.350'),unit='kg',unit_price=100,subtotal=35)
        order.comment='<'*1000;order.save();parts=message_parts(order)
        self.assertGreater(len(parts),2)
        self.assertTrue(all(len(p.encode('utf-16-le'))//2<=3500 for p in parts))
        text=''.join(parts);self.assertIn('&lt;b&gt;',text);self.assertIn('531,96 ₽',text);self.assertNotIn(order.pickup_address,text);self.assertNotIn('<лука>',text)
        row=order.notification;row.payload_parts=['legacy'];row.payload_format='plain';row.destination='-100001';row.save()
        with override_settings(TELEGRAM_NOTIFICATIONS_ENABLED=True,TELEGRAM_ADMIN_CHAT_ID='-100002'),patch('storefront.notifications.telegram_call',return_value={'message_id':999}) as api:
            self.assertTrue(deliver_one(row.pk))
        self.assertEqual(api.call_args.args[1]['text'],'legacy');self.assertNotIn('parse_mode',api.call_args.args[1]);self.assertEqual(api.call_args.args[1]['chat_id'],'-100001')


@skipUnless(connection.vendor=='postgresql','Requires PostgreSQL row locks')
@override_settings(TELEGRAM_ORDER_WEBHOOK_ENABLED=True,TELEGRAM_ORDER_STAFF_IDS=frozenset([100,200]),MINIAPP_BOT_USERNAME='store_bot',MINIAPP_ADMIN_URL='https://admin.example')
class ConcurrentAcceptanceTests(TransactionTestCase):
    def test_two_staff_members_cannot_accept_the_same_order(self):
        order=Order.objects.create(telegram_user_id=1,request_id=uuid4(),request_fingerprint='x',buyer_name='Test',phone='+70000000000',pickup_address='Store',total=0)
        notification=OrderNotification.objects.create(order=order,payload_parts=['order'],destination='-100001',telegram_message_ids=[12],sent_parts=1,status='sent')
        row=OrderAcceptance.objects.create(order=order)
        def race(action,nonce=None):
            barrier=Barrier(2)
            def worker(staff):
                close_old_connections()
                try:
                    barrier.wait(timeout=20)
                    query={'update_id':staff+(1000 if action=='y' else 0),'callback_query':{'id':str(staff)+action,'from':{'id':staff,'first_name':'Employee','username':'user'+str(staff)},'data':f'oa:{row.token.hex}:{action}'+(':'+nonce if nonce else ''),'message':{'message_id':12,'chat':{'id':-100001,'type':'supergroup'},'from':{'is_bot':True,'username':'store_bot'}}}}
                    process_callback(query)
                finally: close_old_connections()
            with patch('storefront.order_acceptance.telegram_call',return_value=True),ThreadPoolExecutor(max_workers=2) as pool:list(pool.map(worker,[100,200]))
        race('s');row.refresh_from_db();owner=row.pending_staff_id;self.assertIn(owner,[100,200]);order.refresh_from_db();self.assertEqual(order.status,'new')
        race('y',row.pending_nonce);row.refresh_from_db();order.refresh_from_db();self.assertEqual(order.status,'confirmed');self.assertEqual(row.accepted_staff_id,owner)
        self.assertEqual(OrderStatusEvent.objects.filter(order=order,status='confirmed').count(),1)


@override_settings(TELEGRAM_BOT_TOKEN='unit-only',MINIAPP_BOT_USERNAME='store_bot',MINIAPP_PUBLIC_URL='https://store.example',TELEGRAM_ORDER_WEBHOOK_ENABLED=True,TELEGRAM_WEBHOOK_SECRET='unit-secret-'+'x'*32,TELEGRAM_ORDER_STAFF_IDS=frozenset([100]))
class WebhookSetupTests(SimpleTestCase):
    def test_windows_setup_settings_never_connect_to_the_store_database(self):
        from pathlib import Path
        from tempfile import TemporaryDirectory
        import os,sys,subprocess
        with TemporaryDirectory() as folder:
            env_file=Path(folder)/'.env.private';env_file.write_text('TELEGRAM_BOT_TOKEN=unit-only\nMINIAPP_BOT_USERNAME=store_bot\n')
            environment={**os.environ,'DJANGO_SETTINGS_MODULE':'config.settings_bot_setup','MINIAPP_SERVER_ENV_FILE':str(env_file),'TELEGRAM_ORDER_WEBHOOK_ENABLED':'0'}
            result=subprocess.run([sys.executable,'-c','import django;django.setup();from django.conf import settings;print(settings.DATABASES["default"]["NAME"])'],env=environment,capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr);self.assertEqual(result.stdout.strip(),':memory:')

    def test_already_applied_edit_is_success_and_bot_secret_is_not_in_error(self):
        body=json.dumps({'description':'Bad Request: message is not modified'}).encode()
        with patch('storefront.notifications.urlopen',side_effect=HTTPError('https://secret.invalid/bot-private',400,'bad',{},BytesIO(body))):
            self.assertTrue(telegram_call('editMessageText',{}))
        with patch('storefront.notifications.urlopen',side_effect=HTTPError('https://secret.invalid/bot-private',403,'bad',{},BytesIO(b'{}'))):
            with self.assertRaises(DeliveryError) as error: telegram_call('editMessageText',{})
        self.assertNotIn('bot-private',str(error.exception));self.assertNotIn('unit-only',str(error.exception))

    def test_default_check_is_read_only_and_never_reads_or_acknowledges_updates(self):
        with patch('storefront.management.commands.check_order_webhook.telegram_call',side_effect=[{'username':'store_bot'},{'url':'','pending_update_count':1}]) as api:
            call_command('check_order_webhook',stdout=StringIO())
        self.assertEqual([c.args[0] for c in api.call_args_list],['getMe','getWebhookInfo'])

    def test_foreign_webhook_pending_updates_and_missing_ack_are_not_replaced(self):
        for info,ack in [({'url':'https://another.example/webhook'},True),({'url':'','pending_update_count':1},True),({'url':''},False)]:
            with patch('storefront.management.commands.check_order_webhook.telegram_call',side_effect=[{'username':'store_bot'},info]) as api:
                with self.assertRaises(CommandError): call_command('check_order_webhook',apply=True,acknowledge_no_other_consumer=ack,stdout=StringIO())
            self.assertNotIn('setWebhook',[c.args[0] for c in api.call_args_list])

    def test_explicit_approved_setup_keeps_pending_updates_and_does_not_print_secret(self):
        output=StringIO()
        with patch('storefront.management.commands.check_order_webhook.telegram_call',side_effect=[{'username':'store_bot'},{'url':'','pending_update_count':0},True]) as api:
            call_command('check_order_webhook',apply=True,acknowledge_no_other_consumer=True,stdout=output)
        call=api.call_args.args;self.assertEqual(call[0],'setWebhook');self.assertFalse(call[1]['drop_pending_updates'])
        self.assertEqual(call[1]['allowed_updates'],['callback_query']);self.assertNotIn('unit-secret',output.getvalue())

    def test_webhook_can_be_registered_before_enabling_new_staff_buttons(self):
        with override_settings(TELEGRAM_ORDER_WEBHOOK_ENABLED=False),patch('storefront.management.commands.check_order_webhook.telegram_call',side_effect=[{'username':'store_bot'},{'url':'','pending_update_count':0},True]) as api:
            call_command('check_order_webhook',apply=True,acknowledge_no_other_consumer=True,stdout=StringIO())
        self.assertEqual(api.call_args.args[0],'setWebhook')
