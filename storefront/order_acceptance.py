"""Two-stage staff confirmation. Database transitions precede idempotent UI edits."""
from datetime import timedelta
from html import escape
import re
import uuid
from django.conf import settings
from django.db import transaction, IntegrityError
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from .models import Order, OrderAcceptance, OrderNotification, OrderStatusEvent, TelegramCallbackReceipt
from .notifications import telegram_call, DeliveryError
from .order_messages import acceptance_footer


def admin_buttons(notification):
    base=settings.MINIAPP_ADMIN_URL
    return [[{'text':'Открыть заказ в Admin','url':f'{base}/admin/storefront/order/{notification.order_id}/change/'}]] if base.startswith('https://') else []


def markup(row, notification, *, now=None):
    buttons=admin_buttons(notification)
    if settings.TELEGRAM_ORDER_WEBHOOK_ENABLED and row.order.status==Order.Status.NEW and not row.accepted_at:
        prefix=f'oa:{row.token.hex}'
        if row.pending_staff_id and row.pending_until and row.pending_until>(now or timezone.now()):
            buttons.insert(0,[{'text':'Да, всё верно','callback_data':f'{prefix}:y:{row.pending_nonce}'},
                              {'text':'Отмена','callback_data':f'{prefix}:c:{row.pending_nonce}'}])
        else: buttons.insert(0,[{'text':'✅ Подтвердить заказ','callback_data':f'{prefix}:s'}])
    return {'inline_keyboard':buttons}


def notification_markup(notification, index):
    if settings.TELEGRAM_ORDER_WEBHOOK_ENABLED and index==len(notification.payload_parts)-1:
        row,_=OrderAcceptance.objects.get_or_create(order=notification.order)
        return markup(row,notification)
    return {'inline_keyboard':admin_buttons(notification)}


def refresh_message(pk, *, force=False):
    """Bounded request/Admin attempt. A failed edit never undoes an acceptance."""
    if not settings.TELEGRAM_ORDER_WEBHOOK_ENABLED: return False
    for _ in range(2):
        now=timezone.now();claim=uuid.uuid4()
        with transaction.atomic():
            row=OrderAcceptance.objects.select_for_update(of=('self',)).select_related('order').get(pk=pk)
            notification=OrderNotification.objects.filter(order_id=row.order_id).first()
            if not notification or len(notification.telegram_message_ids)!=len(notification.payload_parts) or not notification.telegram_message_ids: return False
            if row.edit_claim and row.edit_lease_until and row.edit_lease_until>now: return False
            if row.rendered_revision==row.ui_revision and not row.edit_error and not force: return True
            revision=row.ui_revision
            OrderAcceptance.objects.filter(pk=pk).update(edit_claim=claim,edit_lease_until=now+timedelta(seconds=60))
            data={'chat_id':notification.destination,'message_id':notification.telegram_message_ids[-1], 'reply_markup':markup(row,notification,now=now)}
            if row.accepted_at:
                original=notification.payload_parts[-1]
                data.update(text=(original if notification.payload_format=='html' else escape(original))+acceptance_footer(row),parse_mode='HTML',link_preview_options={'is_disabled':True})
                method='editMessageText'
            else: method='editMessageReplyMarkup'
        try:
            telegram_call(method,data,timeout=3)
        except DeliveryError as exc:
            OrderAcceptance.objects.filter(pk=pk,edit_claim=claim).update(edit_claim=None,edit_lease_until=None,edit_error=str(exc)[:1000])
            return False
        except Exception:
            OrderAcceptance.objects.filter(pk=pk,edit_claim=claim).update(edit_claim=None,edit_lease_until=None,edit_error='Обновление прервано. Повторите из Admin.')
            return False
        OrderAcceptance.objects.filter(pk=pk,edit_claim=claim).update(rendered_revision=revision,edit_claim=None,edit_lease_until=None,edit_error='')
        if not OrderAcceptance.objects.filter(pk=pk).exclude(ui_revision=revision).exists(): return True
    return False


@sensitive_variables()
def process_callback(update):
    """Called only after the HTTPS webhook secret has been validated."""
    query=update.get('callback_query');update_id=update.get('update_id')
    if not isinstance(query,dict) or type(update_id) is not int or not 0<=update_id<2**63: return
    callback_id=query.get('id');actor=query.get('from')
    if not isinstance(callback_id,str) or not 0<len(callback_id)<=128 or not isinstance(actor,dict): return
    staff_id=actor.get('id');response='Действие недоступно.';target=None
    try:
        if type(staff_id) is not int or staff_id not in settings.TELEGRAM_ORDER_STAFF_IDS or actor.get('is_bot'):
            response='Недостаточно прав для подтверждения заказа.';return
        data=query.get('data')
        if not isinstance(data,str): return
        match=re.fullmatch(r'oa:([a-f0-9]{32}):(s|y|c)(?::([a-f0-9]{16}))?',data)
        if not match: return
        token,action,nonce=match.groups()
        if (action=='s' and nonce) or (action!='s' and not nonce): return
        candidate=OrderAcceptance.objects.filter(token=token).values_list('order_id',flat=True).first()
        if not candidate: response='Заказ или кнопка устарели.';return
        with transaction.atomic():
            order=Order.objects.select_for_update().get(pk=candidate)
            row=OrderAcceptance.objects.select_for_update().get(order=order)
            notification=OrderNotification.objects.filter(order=order).first()
            message=query.get('message')
            if not isinstance(message,dict): return
            chat=message.get('chat');sender=message.get('from')
            if not isinstance(chat,dict) or not isinstance(sender,dict): return
            if not notification or not notification.telegram_message_ids or len(notification.telegram_message_ids)!=len(notification.payload_parts): return
            if str(chat.get('id'))!=notification.destination or chat.get('type') not in ('group','supergroup') or message.get('message_id')!=notification.telegram_message_ids[-1]: return
            if not sender.get('is_bot') or not isinstance(sender.get('username'),str) or sender['username'].lower()!=settings.MINIAPP_BOT_USERNAME.lower(): return
            if type(message.get('message_id')) is not int: return
            target=row.pk
            if TelegramCallbackReceipt.objects.filter(update_id=update_id).exists() or TelegramCallbackReceipt.objects.filter(callback_id=callback_id).exists():
                response='Действие уже обработано.';return
            try:
                with transaction.atomic(): TelegramCallbackReceipt.objects.create(update_id=update_id,callback_id=callback_id)
            except IntegrityError:
                response='Действие уже обработано.';return
            now=timezone.now()
            if row.accepted_at or order.status!=Order.Status.NEW:
                row.ui_revision+=1;row.save(update_fields=['ui_revision'])
                response='Заказ уже принят или его статус изменён.';return
            pending=bool(row.pending_staff_id and row.pending_until and row.pending_until>now)
            if action=='s':
                if pending and row.pending_staff_id!=staff_id:
                    response='Этот заказ сейчас подтверждает другой сотрудник.';return
                if not pending:
                    row.pending_staff_id=staff_id;row.pending_nonce=uuid.uuid4().hex[:16];row.pending_until=now+timedelta(minutes=5)
                response='Проверьте заказ и подтвердите вторым нажатием.'
            else:
                if not pending:
                    row.pending_staff_id=None;row.pending_nonce='';row.pending_until=None
                    response='Подтверждение истекло. Начните заново.'
                elif row.pending_staff_id!=staff_id or row.pending_nonce!=nonce:
                    response='Завершить подтверждение может только начавший его сотрудник.';return
                elif action=='c':
                    row.pending_staff_id=None;row.pending_nonce='';row.pending_until=None
                    response='Подтверждение отменено. Статус заказа не изменён.'
                else:
                    username=actor.get('username','')
                    if not isinstance(username,str) or not re.fullmatch(r'[A-Za-z0-9_]{1,32}',username): username=''
                    name=' '.join(' '.join(actor.get(k,'') for k in ('first_name','last_name') if isinstance(actor.get(k,''),str)).split())[:128] or str(staff_id)
                    changed=Order.objects.filter(pk=order.pk,status=Order.Status.NEW).update(status=Order.Status.CONFIRMED)
                    if not changed: response='Статус заказа уже изменён.';return
                    OrderStatusEvent.objects.create(order=order,previous_status=Order.Status.NEW,status=Order.Status.CONFIRMED)
                    row.accepted_staff_id=staff_id;row.accepted_username=username;row.accepted_name=name;row.accepted_at=now
                    row.pending_staff_id=None;row.pending_nonce='';row.pending_until=None
                    response='Заказ принят.'
            row.ui_revision+=1;row.save()
    except Exception:
        response='Не удалось сохранить подтверждение. Повторите попытку.'
        target=None
        raise
    finally:
        # Persisted state is authoritative, even when either Telegram edit/answer fails.
        if target is not None: refresh_message(target)
        try: telegram_call('answerCallbackQuery',{'callback_query_id':callback_id,'text':response,'show_alert':False},timeout=2)
        except DeliveryError: pass
