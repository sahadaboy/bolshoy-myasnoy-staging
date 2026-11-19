import time
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from storefront.models import OrderNotification
from storefront.notifications import deliver_one, recover_abandoned


class Command(BaseCommand):
    help = 'Доставлять сохранённые уведомления о заказах в настроенный Telegram-чат.'

    def add_arguments(self, parser):
        parser.add_argument('--once', action='store_true')
        parser.add_argument('--interval', type=int, default=5)

    def handle(self, *args, **options):
        if not settings.TELEGRAM_NOTIFICATIONS_ENABLED or not settings.TELEGRAM_BOT_TOKEN or not settings.TELEGRAM_ADMIN_CHAT_ID:
            raise CommandError('Задайте TELEGRAM_BOT_TOKEN, TELEGRAM_ADMIN_CHAT_ID и TELEGRAM_NOTIFICATIONS_ENABLED=1 на сервере.')
        try:
            while True:
                recover_abandoned()
                ids = list(OrderNotification.objects.filter(status__in=['pending', 'failed'], next_attempt_at__lte=timezone.now()).values_list('pk', flat=True)[:20])
                sent = sum(deliver_one(pk) for pk in ids)
                if options['once']:
                    self.stdout.write(f'Processed: {len(ids)}, delivered: {sent}'); return
                time.sleep(max(1, min(options['interval'], 60)))
        except KeyboardInterrupt:
            return
