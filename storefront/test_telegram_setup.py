from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, override_settings
from .telegram_config import public_app_url
from .notifications import DeliveryError


@override_settings(TELEGRAM_BOT_TOKEN='server-unit-test-secret', MINIAPP_BOT_USERNAME='store_bot',
                   TELEGRAM_ADMIN_CHAT_ID='', MINIAPP_ADMIN_URL='', MINIAPP_PUBLIC_URL='')
class TelegramSetupTests(SimpleTestCase):
    def test_menu_update_needs_no_order_chat_or_admin_and_preserves_other_environment(self):
        url = 'https://current-launch.example'
        with TemporaryDirectory() as folder, self.settings(BASE_DIR=Path(folder)):
            path = Path(folder) / '.env'
            original = 'TELEGRAM_BOT_TOKEN=server-unit-test-secret\nMINIAPP_DATABASE=existing.sqlite3\n'
            path.write_text(original + 'MINIAPP_PUBLIC_URL=https://previous.example\n', encoding='utf-8')
            output = StringIO()
            with patch('storefront.management.commands.check_telegram_store.telegram_call',
                       side_effect=[{'username':'store_bot'}, True, {'type':'web_app','web_app':{'url':url}}]) as api:
                call_command('check_telegram_store', set_menu=True, url=url, stdout=output)
            self.assertEqual([call.args[0] for call in api.call_args_list], ['getMe','setChatMenuButton','getChatMenuButton'])
            self.assertEqual(api.call_args_list[1].args[1]['menu_button']['web_app']['url'], url)
            self.assertEqual(path.read_text(encoding='utf-8'), original + f'MINIAPP_PUBLIC_URL={url}\n')
            self.assertNotIn('server-unit-test-secret', output.getvalue())

    def test_invalid_urls_never_reach_telegram(self):
        for url in ('http://local.example', 'https://user:pass@public.example', 'https://public.example:8001',
                    'https://public.example/admin/', 'https://public.example?initData=private',
                    'https://public.example/#secret', 'https://*.example', 'https://127.0.0.1',
                    'https://public\n.example'):
            with self.subTest(url=url), patch('storefront.management.commands.check_telegram_store.telegram_call') as api:
                with self.assertRaises(CommandError):
                    call_command('check_telegram_store', set_menu=True, url=url, stdout=StringIO())
                api.assert_not_called()
        self.assertEqual(public_app_url('https://Public.Example:443/'), 'https://public.example')

    def test_missing_token_or_wrong_bot_never_changes_menu(self):
        with self.settings(TELEGRAM_BOT_TOKEN=''), patch('storefront.management.commands.check_telegram_store.telegram_call') as api:
            with self.assertRaises(CommandError):
                call_command('check_telegram_store', set_menu=True, url='https://public.example', stdout=StringIO())
            api.assert_not_called()
        with patch('storefront.management.commands.check_telegram_store.telegram_call', return_value={'username':'another_bot'}) as api:
            with self.assertRaises(CommandError):
                call_command('check_telegram_store', set_menu=True, url='https://public.example', stdout=StringIO())
            self.assertEqual(api.call_count, 1)

    def test_failed_or_unconfirmed_update_does_not_overwrite_saved_url(self):
        with TemporaryDirectory() as folder, self.settings(BASE_DIR=Path(folder)):
            path = Path(folder) / '.env'
            original = 'MINIAPP_PUBLIC_URL=https://previous.example\n'
            path.write_text(original, encoding='utf-8')
            for responses in ([{'username':'store_bot'}, DeliveryError('Telegram HTTP 503')],
                              [{'username':'store_bot'}, True, {'type':'default'}]):
                with patch('storefront.management.commands.check_telegram_store.telegram_call', side_effect=responses):
                    with self.assertRaises(CommandError):
                        call_command('check_telegram_store', set_menu=True, url='https://public.example', stdout=StringIO())
                self.assertEqual(path.read_text(encoding='utf-8'), original)

    def test_network_auth_check_does_not_require_order_delivery_configuration(self):
        with patch('storefront.management.commands.check_telegram_store.telegram_call', return_value={'username':'store_bot'}) as api:
            call_command('check_telegram_store', network=True, stdout=StringIO())
        self.assertEqual(api.call_count, 1)
