"""Explicit diagnostics only: never creates orders or changes bot settings."""
import os
import re
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone
from storefront.notifications import telegram_call, DeliveryError


class Command(BaseCommand):
    help = 'Проверить закрытую группу и права бота. --test-message отправляет помеченное сообщение без заказа.'
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument('--chat-id', help='Числовой ID; иначе TELEGRAM_TEST_CHAT_ID или TELEGRAM_ADMIN_CHAT_ID.')
        parser.add_argument('--test-message', action='store_true')
        parser.add_argument('--list-groups', action='store_true', help='Показать только ID групп из непрочитанных обновлений; без подтверждения/удаления обновлений.')

    def handle(self, *args, **options):
        if not settings.TELEGRAM_BOT_TOKEN:
            raise CommandError('Задайте TELEGRAM_BOT_TOKEN только в серверном окружении.')
        if options['list_groups'] and (options['test_message'] or options['chat_id']):
            raise CommandError('--list-groups запускается отдельно.')
        try:
            bot = telegram_call('getMe', {})
            if not settings.MINIAPP_BOT_USERNAME or bot.get('username', '').lower() != settings.MINIAPP_BOT_USERNAME.lower():
                raise CommandError('Токен принадлежит другому боту. Настройки не изменены.')
            if options['list_groups']:
                webhook = telegram_call('getWebhookInfo', {})
                if webhook.get('url'):
                    raise CommandError('У бота установлен webhook. Получите ID из существующего обработчика; webhook не изменён.')
                # No offset, negative offset or allowed_updates: do not acknowledge
                # pending updates or change the bot's subscriptions.
                updates = telegram_call('getUpdates', {'timeout': 0, 'limit': 100})
                ids = set()
                for update in updates:
                    for key in ('message', 'edited_message', 'my_chat_member'):
                        chat = update.get(key, {}).get('chat', {})
                        if chat.get('type') in ('group', 'supergroup'):
                            ids.add(chat['id'])
                self.stdout.write('ID закрытых/групповых чатов: ' + ', '.join(map(str, sorted(ids))) if ids else
                    'Новых групповых событий нет. Добавьте бота в группу или отправьте в ней /start@' + settings.MINIAPP_BOT_USERNAME + ' и повторите.')
                return
            chat_id = options['chat_id'] or os.environ.get('TELEGRAM_TEST_CHAT_ID') or settings.TELEGRAM_ADMIN_CHAT_ID
            if not chat_id or not re.fullmatch(r'-[1-9][0-9]{1,19}', str(chat_id)):
                raise CommandError('Нужен отрицательный числовой ID группы (серверное окружение или --chat-id).')
            chat = telegram_call('getChat', {'chat_id': str(chat_id)})
            if chat.get('type') not in ('group', 'supergroup') or chat.get('username') or chat.get('active_usernames'):
                raise CommandError('Нужна закрытая группа сотрудников без публичного username.')
            member = telegram_call('getChatMember', {'chat_id': str(chat_id), 'user_id': bot['id']})
            role = member.get('status')
            if role in ('left', 'kicked') or role == 'restricted' and not member.get('can_send_messages'):
                raise CommandError('Бот не может отправлять сообщения: проверьте членство и ограничения группы.')
            if role not in ('creator', 'administrator', 'member', 'restricted'):
                raise CommandError('Telegram не подтвердил участие бота в группе.')
            if role == 'member' and chat.get('permissions', {}).get('can_send_messages') is False:
                raise CommandError('Участникам запрещена отправка сообщений. Разрешите боту отправлять сообщения.')
            self.stdout.write('Бот и закрытая группа доступны; членство и права проверены.')
            if options['test_message']:
                result = telegram_call('sendMessage', {'chat_id': str(chat_id),
                    'text': 'ПРОВЕРКА ПОДКЛЮЧЕНИЯ\nБольшой Мясной Маркет\n\nЭто не заказ. Сборка и выдача товаров не требуются.\n'
                            'Проверяется только доставка уведомлений в тестовую группу.\n'
                            f'Время: {timezone.localtime():%d.%m.%Y %H:%M}',
                    'link_preview_options': {'is_disabled': True}})
                if not isinstance(result.get('message_id'), int):
                    raise CommandError('Нет подтверждения доставки. Проверьте чат перед повтором.')
                self.stdout.write(self.style.SUCCESS('Тестовое сообщение доставлено. Заказ не создавался.'))
        except DeliveryError as exc:
            raise CommandError(str(exc)) from None
