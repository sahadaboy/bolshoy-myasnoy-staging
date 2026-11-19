from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from storefront.notifications import telegram_call, DeliveryError
from storefront.telegram_config import public_app_url
from config.env import save_public_url


class Command(BaseCommand):
    help = 'Проверить настройки Telegram без вывода секретов. --network проверяет бота и чат; --set-menu устанавливает кнопку магазина.'

    def add_arguments(self, parser):
        parser.add_argument('--network', action='store_true')
        parser.add_argument('--set-menu', action='store_true')
        parser.add_argument('--url', help='Новый HTTPS URL: обновить кнопку и сохранить MINIAPP_PUBLIC_URL в серверном .env (с --set-menu).')

    def handle(self, *args, **options):
        if options['url'] and not options['set_menu']:
            raise CommandError('--url используется вместе с --set-menu.')
        candidate = options['url'] or settings.MINIAPP_PUBLIC_URL
        try:
            launch_url = public_app_url(candidate)
        except ValueError as exc:
            launch_url = ''
            if options['set_menu']:
                raise CommandError(str(exc)) from None
        values = {'TELEGRAM_BOT_TOKEN': bool(settings.TELEGRAM_BOT_TOKEN),
            'TELEGRAM_ADMIN_CHAT_ID': bool(settings.TELEGRAM_ADMIN_CHAT_ID),
            'MINIAPP_BOT_USERNAME': bool(settings.MINIAPP_BOT_USERNAME),
            'MINIAPP_PUBLIC_URL (HTTPS)': bool(launch_url),
            'MINIAPP_ADMIN_URL (HTTPS)': settings.MINIAPP_ADMIN_URL.startswith('https://')}
        for key, present in values.items():
            self.stdout.write(f'{key}: {"configured" if present else "missing"}')
        if options['network'] or options['set_menu']:
            if not settings.TELEGRAM_BOT_TOKEN or not settings.MINIAPP_BOT_USERNAME:
                raise CommandError('Задайте TELEGRAM_BOT_TOKEN и MINIAPP_BOT_USERNAME в серверном .env. Токен не передавайте в командной строке.')
            try:
                bot = telegram_call('getMe', {})
                if bot.get('username', '').lower() != settings.MINIAPP_BOT_USERNAME.lower():
                    raise CommandError('Username не соответствует настроенному токену бота.')
                if options['network'] and settings.TELEGRAM_ADMIN_CHAT_ID:
                    telegram_call('getChat', {'chat_id': settings.TELEGRAM_ADMIN_CHAT_ID})
                if options['set_menu']:
                    result = telegram_call('setChatMenuButton', {'menu_button': {'type': 'web_app', 'text': 'Открыть магазин', 'web_app': {'url': launch_url}}})
                    if result is not True:
                        raise CommandError('Telegram не подтвердил изменение кнопки.')
                    menu = telegram_call('getChatMenuButton', {})
                    if not isinstance(menu, dict) or menu.get('type') != 'web_app' or menu.get('web_app', {}).get('url') != launch_url:
                        raise CommandError('Не удалось подтвердить новый URL кнопки Telegram. Проверьте настройки бота.')
                    if options['url']:
                        try:
                            save_public_url(settings.BASE_DIR / '.env', launch_url)
                        except OSError:
                            raise CommandError('Кнопка обновлена, но MINIAPP_PUBLIC_URL не сохранён в .env. Проверьте права на файл.') from None
                    self.stdout.write(self.style.SUCCESS('Кнопка «Открыть магазин» обновлена и проверена. Закройте старое Mini App и откройте его заново из меню бота.'))
                else:
                    self.stdout.write(self.style.SUCCESS('Бот доступен; username соответствует токену.'))
                if options['network']:
                    self.stdout.write('Чат заказов проверен.' if settings.TELEGRAM_ADMIN_CHAT_ID else 'Чат заказов не задан. Для авторизации он не требуется.')
            except DeliveryError as exc:
                raise CommandError(str(exc)) from None
