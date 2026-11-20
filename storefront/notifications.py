"""Persistent outbox; network failures never roll back a buyer's order."""
from datetime import timedelta
import json
import uuid
from time import monotonic
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from django.conf import settings
from django.db import transaction
from django.utils import timezone
from django.views.decorators.debug import sensitive_variables
from .models import OrderNotification


class DeliveryError(Exception):
    def __init__(self, message, *, uncertain=False, retryable=False):
        super().__init__(message); self.uncertain = uncertain; self.retryable = retryable


@sensitive_variables()
def telegram_call(method, data, *, timeout=10):
    if method not in ('sendMessage', 'getMe', 'getChat', 'getChatMember', 'getUpdates', 'getWebhookInfo', 'setWebhook', 'setChatMenuButton', 'getChatMenuButton', 'editMessageText', 'editMessageReplyMarkup', 'answerCallbackQuery'):
        raise ValueError('Unsupported Telegram method')
    request = Request(f'https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}',
        data=json.dumps(data).encode(), headers={'Content-Type': 'application/json'}, method='POST')
    try:
        with urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read(65536))
    except HTTPError as exc:
        if exc.code == 400 and method in ('editMessageText','editMessageReplyMarkup'):
            try:
                description=json.loads(exc.read(8192)).get('description','').lower()
                if description.startswith('bad request: message is not modified'): return True
            except (ValueError,AttributeError): pass
        hints = {400: 'Проверьте chat ID и тип группы.', 401: 'Проверьте серверный токен бота.',
                 403: 'Добавьте бота в группу и разрешите отправку сообщений.',
                 409: 'Уже работает другой получатель обновлений; не отключайте его.',
                 429: 'Слишком много запросов. Повторите позже.'}
        # Never log the request URL, raw exception or remote response body.
        raise DeliveryError(f'Telegram HTTP {exc.code}. {hints.get(exc.code, "Сервис временно недоступен.")}',
            retryable=exc.code in (429, 500, 502, 503, 504)) from None
    except (URLError, TimeoutError, OSError, ValueError):
        raise DeliveryError('Не удалось подтвердить доставку. Проверьте чат перед повторной отправкой.', uncertain=method == 'sendMessage') from None
    if not isinstance(payload, dict) or not payload.get('ok'):
        raise DeliveryError('Telegram отклонил запрос', retryable=payload.get('error_code') in (429, 500, 502, 503, 504) if isinstance(payload, dict) else False)
    return payload['result']


from .order_messages import message_parts


def deliver_one(pk, *, time_budget=8):
    if not settings.TELEGRAM_NOTIFICATIONS_ENABLED or not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_ADMIN_CHAT_ID:
        return False
    deadline = monotonic() + time_budget
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
            row.payload_format = 'html'
            row.destination = settings.TELEGRAM_ADMIN_CHAT_ID
        row.attempts += 1
        OrderNotification.objects.filter(pk=pk, claim_id=claim).update(
            payload_parts=row.payload_parts, payload_format=row.payload_format, destination=row.destination, attempts=row.attempts)
    try:
        ids = list(row.telegram_message_ids)
        for index in range(row.sent_parts, len(row.payload_parts)):
            remaining = deadline - monotonic()
            if remaining < .5:
                # All preceding parts were acknowledged. Resume at the next
                # unsent part from Admin, without sending acknowledged parts again.
                OrderNotification.objects.filter(pk=pk, claim_id=claim).update(status='pending', lease_until=None,
                    next_attempt_at=timezone.now(), last_error='Требуется отправить оставшиеся части из Admin.')
                return False
            data = {'chat_id': row.destination, 'text': row.payload_parts[index], 'link_preview_options': {'is_disabled': True}}
            if row.payload_format == 'html': data['parse_mode'] = 'HTML'
            from .order_acceptance import notification_markup
            markup = notification_markup(row, index)
            if markup['inline_keyboard']: data['reply_markup'] = markup
            result = telegram_call('sendMessage', data, timeout=min(4, remaining))
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


def dispatch_after_commit(pk):
    """One bounded attempt in the HTTP request; the database outbox is durable.

    Never leak network exceptions into a successfully committed checkout.
    A crash/unknown delivery is deliberately not retried without a chat check.
    """
    try:
        return deliver_one(pk)
    except Exception:
        try:
            OrderNotification.objects.filter(pk=pk, status='sending').update(
                status='uncertain', lease_until=None,
                last_error='Отправка прервана. Проверьте чат перед повторной отправкой.')
        except Exception:
            pass  # An expired sending lease is recovered by the Admin retry action.
        return False


def recover_abandoned():
    return OrderNotification.objects.filter(status='sending', lease_until__lt=timezone.now()).update(
        status='uncertain', last_error='Отправка прервана. Проверьте чат перед повторной отправкой.', lease_until=None)
