"""One durable personal confirmation per order; never blindly resend ambiguous sends."""
from datetime import timedelta
from functools import partial
from html import escape
import uuid

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables

from .models import CustomerOrderNotification, Order
from .notifications import DeliveryError, telegram_call
from .order_messages import MOSCOW
from .telegram_config import public_app_url

MONTHS = ('января', 'февраля', 'марта', 'апреля', 'мая', 'июня',
          'июля', 'августа', 'сентября', 'октября', 'ноября', 'декабря')


def confirmation_payload(order):
    origin = public_app_url(settings.MINIAPP_PUBLIC_URL)
    if type(order.telegram_user_id) is not int or order.telegram_user_id <= 0:
        raise ValueError('Не указан корректный Telegram ID покупателя.')
    if order.pickup_at:
        local = order.pickup_at.astimezone(MOSCOW)
        pickup = f'{local.day} {MONTHS[local.month - 1]}, {local:%H:%M}'
    else:
        pickup = 'время уточняется оператором'
    return {
        'chat_id': order.telegram_user_id,
        'text': '✅ <b>ВАШ ЗАКАЗ ПРИНЯТ!</b>\n\n'
                f'Заказ № {escape(order.number)}\n\n'
                '🛍️ Мы подтвердили ваш заказ и приступаем к сборке.\n\n'
                f'📅 <b>Самовывоз:</b> {escape(pickup)}\n\n'
                'Спасибо, что выбираете «Большой Мясной»!',
        'parse_mode': 'HTML',
        'reply_markup': {'inline_keyboard': [[{
            'text': '🛒 Посмотреть заказ',
            'web_app': {'url': f'{origin}/profile/orders/{order.public_id}'},
        }]]},
    }


def enqueue_confirmation(order):
    """Called only by the final staff transition, inside its database transaction."""
    if not settings.TELEGRAM_CUSTOMER_NOTIFICATIONS_ENABLED:
        return None
    if order.status != Order.Status.CONFIRMED:
        raise ValueError('A personal confirmation requires a confirmed order.')
    row, created = CustomerOrderNotification.objects.get_or_create(
        order=order, kind=CustomerOrderNotification.Kind.ORDER_CONFIRMED,
        defaults={'recipient_telegram_id': order.telegram_user_id},
    )
    if created:
        transaction.on_commit(partial(dispatch_after_commit, row.pk), robust=True)
    return row


def recover_abandoned():
    # A process may have died after Telegram accepted the message but before saving its ID.
    return CustomerOrderNotification.objects.filter(
        status='sending', lease_until__lt=timezone.now(),
    ).update(status='uncertain', lease_until=None,
             last_error='Отправка прервана. Сначала уточните у покупателя результат доставки.')


@sensitive_variables()
def deliver_one(pk):
    if connection.in_atomic_block:
        raise RuntimeError('Personal delivery must run after the outer database commit.')
    if not settings.TELEGRAM_CUSTOMER_NOTIFICATIONS_ENABLED or not settings.TELEGRAM_BOT_TOKEN:
        return False
    now, claim = timezone.now(), uuid.uuid4()
    with transaction.atomic():
        row = CustomerOrderNotification.objects.select_for_update(of=('self',)).select_related('order').get(pk=pk)
        if row.status != 'pending' or row.next_attempt_at > now:
            return False
        try:
            if row.kind != CustomerOrderNotification.Kind.ORDER_CONFIRMED:
                raise ValueError('Этот тип личного уведомления не поддерживается.')
            if row.recipient_telegram_id != row.order.telegram_user_id or row.recipient_telegram_id <= 0:
                raise ValueError('Telegram ID получателя не соответствует покупателю заказа.')
            if row.order.status not in (Order.Status.CONFIRMED, Order.Status.PREPARING, Order.Status.READY):
                raise ValueError('Статус заказа изменён. Отправка принятия больше не актуальна.')
            payload = row.payload or confirmation_payload(row.order)
            if not isinstance(payload, dict):
                raise ValueError('Некорректное сохранённое сообщение. Требуется проверка администратора.')
            if type(payload.get('chat_id')) is not int or payload['chat_id'] != row.recipient_telegram_id:
                raise ValueError('Получатель сохранённого сообщения не соответствует заказу.')
        except ValueError as exc:
            CustomerOrderNotification.objects.filter(pk=pk).update(status='failed', last_error=str(exc), last_error_code=None)
            return False
        # Conditional claim also protects SQLite, where SELECT FOR UPDATE is a no-op.
        count = CustomerOrderNotification.objects.filter(pk=pk, status='pending', claim_id=row.claim_id).update(
            status='sending', claim_id=claim, lease_until=now + timedelta(seconds=120),
            payload=payload, attempts=row.attempts + 1, last_error='', last_error_code=None,
        )
        if not count:
            return False
    try:
        result = telegram_call('sendMessage', payload, timeout=2)
        if (not isinstance(result, dict) or type(result.get('message_id')) is not int
                or result['message_id'] <= 0
                or not isinstance(result.get('chat'), dict)
                or type(result['chat'].get('id')) is not int
                or result['chat']['id'] != row.recipient_telegram_id):
            raise DeliveryError('Telegram не подтвердил ID личного сообщения.', uncertain=True)
        saved = CustomerOrderNotification.objects.filter(pk=pk, claim_id=claim, status='sending').update(
            status='sent', telegram_message_id=result['message_id'], sent_at=timezone.now(),
            last_error='', last_error_code=None, lease_until=None,
        )
        return bool(saved)
    except DeliveryError as exc:
        code = exc.code if type(exc.code) is int and 100 <= exc.code <= 599 else None
        uncertain = exc.uncertain or code is None or code >= 500
        error = 'Результат отправки неизвестен. Уточните у покупателя; автоматический повтор запрещён.' if uncertain else (
            'Личные сообщения недоступны: покупатель мог заблокировать бота или не открыть с ним чат.' if code == 403
            else f'Telegram отклонил личное сообщение (код {code}).')
        CustomerOrderNotification.objects.filter(pk=pk, claim_id=claim, status='sending').update(
            status='uncertain' if uncertain else 'failed', last_error=error, last_error_code=code,
            next_attempt_at=timezone.now() + timedelta(seconds=60 if code == 429 else 0), lease_until=None,
        )
        return False


def dispatch_after_commit(pk):
    if connection.in_atomic_block:
        transaction.on_commit(partial(dispatch_after_commit, pk), robust=True)
        return False
    try:
        return deliver_one(pk)
    except Exception:
        try:
            CustomerOrderNotification.objects.filter(pk=pk, status='sending').update(
                status='uncertain', lease_until=None,
                last_error='Отправка прервана. Сначала уточните у покупателя результат доставки.',
            )
        except Exception:
            pass  # An expired sending lease is recovered from Admin, never blindly retried.
        return False
