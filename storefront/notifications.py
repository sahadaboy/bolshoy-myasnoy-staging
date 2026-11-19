"""Persistent outbox; network failures never roll back a buyer's order."""
from datetime import timedelta
import json
import uuid
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from .models import OrderNotification


class DeliveryError(Exception):
    def __init__(self, message, *, uncertain=False, retryable=False):
        super().__init__(message); self.uncertain = uncertain; self.retryable = retryable


def telegram_call(method, data):
    if method not in ('sendMessage', 'getMe', 'getChat', 'setChatMenuButton', 'getChatMenuButton'):
        raise ValueError('Unsupported Telegram method')
    request = Request(f'https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}',
        data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urlopen(request, timeout=15) as response:
            payload = json.loads(response.read(65536))
    except HTTPError as exc:
        raise DeliveryError(f'Telegram HTTP {exc.code}', retryable=exc.code in (429, 500, 502, 503, 504)) from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise DeliveryError('Не удалось подтвердить доставку. Проверьте чат перед повторной отправкой.', uncertain=method == 'sendMessage') from None
    if not isinstance(payload, dict) or not payload.get('ok'):
        raise DeliveryError('Telegram отклонил запрос', retryable=payload.get('error_code') in (429, 500, 502, 503, 504) if isinstance(payload, dict) else False)
    return payload['result']


def message_parts(order):
    header = f'НОВЫЙ ЗАКАЗ №{order.number}\n\nПокупатель: {order.buyer_name}\nТелефон: {order.phone}\n\nСостав заказа:\n'
    lines = [f'{item.product_name} — {item.quantity.normalize():f} {"кг" if item.unit == "kg" else "шт."} — {item.subtotal:.2f} ₽\n' for item in order.items.all()]
    footer = f'\nИтого: {order.total:.2f} ₽\nСпособ получения: Самовывоз\nАдрес: {order.pickup_address}\nКомментарий: {order.comment or "—"}\nДата: {timezone.localtime(order.created_at):%d.%m.%Y %H:%M}'
    parts, current = [], header
    for text in [*lines, footer]:
        if len((current + text).encode('utf-16-le')) // 2 > 3500:
            parts.append(current); current = f'ЗАКАЗ №{order.number} · продолжение\n'
        current += text
    parts.append(current)
    return parts


def deliver_one(pk):
    if not settings.TELEGRAM_NOTIFICATIONS_ENABLED or not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_ADMIN_CHAT_ID:
        return False
    now, claim = timezone.now(), uuid.uuid4()
    with transaction.atomic():
        row = OrderNotification.objects.select_for_update().select_related('order').get(pk=pk)
        if row.status not in ('pending', 'failed') or row.next_attempt_at > now:
            return False
        # Conditional claim is also effective on SQLite, whose SELECT FOR UPDATE
        # is a no-op. Only the winner may reach the external API.
        count = OrderNotification.objects.filter(pk=pk, status=row.status, claim_id=row.claim_id).update(
            status='sending', claim_id=claim, lease_until=now + timedelta(seconds=120))
        if not count:
            return False
        if not row.payload_parts:
            row.payload_parts = message_parts(row.order)
            row.destination = settings.TELEGRAM_ADMIN_CHAT_ID
        row.attempts += 1
        OrderNotification.objects.filter(pk=pk, claim_id=claim).update(
            payload_parts=row.payload_parts, destination=row.destination, attempts=row.attempts)
    try:
        ids = list(row.telegram_message_ids)
        for index in range(row.sent_parts, len(row.payload_parts)):
            data = {'chat_id': row.destination, 'text': row.payload_parts[index], 'link_preview_options': {'is_disabled': True}}
            if settings.MINIAPP_ADMIN_URL and settings.MINIAPP_ADMIN_URL.startswith('https://'):
                data['reply_markup'] = {'inline_keyboard': [[{'text': 'Открыть заказ в Admin',
                    'url': f'{settings.MINIAPP_ADMIN_URL}/admin/storefront/order/{row.order_id}/change/'}]]}
            result = telegram_call('sendMessage', data)
            if not isinstance(result, dict) or not isinstance(result.get('message_id'), int):
                raise DeliveryError('Telegram не подтвердил ID сообщения', uncertain=True)
            ids.append(result['message_id'])
            OrderNotification.objects.filter(pk=pk, claim_id=claim).update(
                sent_parts=index + 1, telegram_message_ids=ids,
                lease_until=timezone.now() + timedelta(seconds=120))
        OrderNotification.objects.filter(pk=pk, claim_id=claim).update(status='sent', sent_at=timezone.now(), last_error='', lease_until=None)
        return True
    except DeliveryError as exc:
        OrderNotification.objects.filter(pk=pk, claim_id=claim).update(status='uncertain' if exc.uncertain else 'failed',
            last_error=str(exc)[:1000], lease_until=None,
            next_attempt_at=timezone.now() + timedelta(seconds=min(3600, 30 * 2 ** min(row.attempts, 6)) if exc.retryable else 86400 * 365))
        return False


def recover_abandoned():
    return OrderNotification.objects.filter(status='sending', lease_until__lt=timezone.now()).update(
        status='uncertain', last_error='Отправка прервана. Проверьте чат перед повторной отправкой.', lease_until=None)
