from urllib.parse import urlsplit
import re
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from storefront.notifications import telegram_call, DeliveryError
from storefront.telegram_config import public_app_url


class Command(BaseCommand):
    requires_system_checks=[]
    help='Read-only webhook check. --apply requires explicit owner approval and verification that no other bot consumer exists.'
    def add_arguments(self, parser):
        parser.add_argument('--apply',action='store_true')
        parser.add_argument('--acknowledge-no-other-consumer',action='store_true')
    def handle(self,*args,**options):
        if not settings.TELEGRAM_BOT_TOKEN: raise CommandError('Configure the bot token on the server.')
        try:
            bot=telegram_call('getMe',{})
            if bot.get('username','').lower()!=settings.MINIAPP_BOT_USERNAME.lower(): raise CommandError('Configured bot username does not match.')
            info=telegram_call('getWebhookInfo',{})
            current=info.get('url','')
            self.stdout.write('Webhook: '+('configured at '+str(urlsplit(current).hostname) if current else 'not configured'))
            self.stdout.write('getWebhookInfo cannot prove getUpdates is inactive. No updates were read/acknowledged.')
            self.stdout.write('Pending updates: '+str(info.get('pending_update_count',0)))
            if not options['apply']: return
            if not options['acknowledge_no_other_consumer']: raise CommandError('Verify existing bot integrations and obtain owner approval first.')
            if not re.fullmatch(r'[A-Za-z0-9_-]{32,256}',settings.TELEGRAM_WEBHOOK_SECRET) or not settings.TELEGRAM_ORDER_STAFF_IDS: raise CommandError('Configure the protected webhook secret and staff IDs first.')
            target=public_app_url(settings.MINIAPP_PUBLIC_URL)+'/api/telegram/order-webhook/'
            if current and (current!=target or set(info.get('allowed_updates',[]))!={'callback_query'}):
                raise CommandError('Existing webhook/integration must be preserved; refuse to replace it.')
            if not current and info.get('pending_update_count',0):
                raise CommandError('Pending updates must be reviewed/handled by the existing consumer before first setup. Refuse to drop or silently acknowledge them.')
            result=telegram_call('setWebhook',{'url':target,'secret_token':settings.TELEGRAM_WEBHOOK_SECRET,'allowed_updates':['callback_query'],'drop_pending_updates':False})
            if result is not True: raise CommandError('Telegram did not confirm the webhook.')
            self.stdout.write('Order callback webhook configured. Pending updates were not dropped.')
        except (DeliveryError,ValueError) as exc:
            raise CommandError(str(exc)) from None
