from io import StringIO
from unittest.mock import patch
from django.core.management import call_command, CommandError
from django.test import SimpleTestCase, override_settings
from .notifications import DeliveryError


@override_settings(TELEGRAM_BOT_TOKEN='unit-test-only', MINIAPP_BOT_USERNAME='store_bot', TELEGRAM_ADMIN_CHAT_ID='-100001')
class OrderChatTests(SimpleTestCase):
    def replies(self, **member):
        return [{'id':123,'username':'store_bot'}, {'id':-100001,'type':'supergroup'},
                {'status':'member', **member}, {'message_id':19}]

    def test_explicit_test_message_checks_bot_group_membership_and_creates_no_database_rows(self):
        output=StringIO()
        with patch('storefront.management.commands.check_order_chat.telegram_call',side_effect=self.replies()) as api:
            call_command('check_order_chat',chat_id='-100001',test_message=True,stdout=output)
        self.assertEqual([call.args[0] for call in api.call_args_list],['getMe','getChat','getChatMember','sendMessage'])
        self.assertIn('Это не заказ',api.call_args_list[-1].args[1]['text'])
        self.assertNotIn('unit-test-only',output.getvalue())

    def test_read_only_check_never_sends_a_message(self):
        with patch('storefront.management.commands.check_order_chat.telegram_call',side_effect=self.replies()[:3]) as api:
            call_command('check_order_chat',chat_id='-100001',stdout=StringIO())
        self.assertEqual(api.call_count,3)

    def test_wrong_bot_public_group_and_restricted_bot_are_rejected(self):
        replies = [[{'id':123,'username':'different'}],
                   [{'id':123,'username':'store_bot'},{'type':'supergroup','username':'public_group'}],
                   self.replies(status='restricted',can_send_messages=False)]
        for responses in replies:
            with patch('storefront.management.commands.check_order_chat.telegram_call',side_effect=responses) as api:
                with self.assertRaises(CommandError):
                    call_command('check_order_chat',chat_id='-100001',test_message=True,stdout=StringIO())
                self.assertNotIn('sendMessage',[call.args[0] for call in api.call_args_list])

    def test_listing_group_ids_does_not_change_webhook_or_acknowledge_updates(self):
        responses=[{'id':123,'username':'store_bot'},{'url':''},
                   [{'update_id':2,'message':{'chat':{'id':-100001,'type':'supergroup'},'text':'private-group-text'}}]]
        output=StringIO()
        with patch('storefront.management.commands.check_order_chat.telegram_call',side_effect=responses) as api:
            call_command('check_order_chat',list_groups=True,stdout=output)
        self.assertEqual(api.call_args.args,('getUpdates',{'timeout':0,'limit':100}))
        self.assertIn('-100001',output.getvalue()); self.assertNotIn('private-group-text',output.getvalue())
        with patch('storefront.management.commands.check_order_chat.telegram_call',side_effect=[responses[0],{'url':'https://handler.example'}]) as api:
            with self.assertRaises(CommandError): call_command('check_order_chat',list_groups=True,stdout=StringIO())
            self.assertEqual(api.call_count,2)
