"""Disposable localhost PostgreSQL only. No production credentials or fallback."""
import os
import dj_database_url
from django.core.exceptions import ImproperlyConfigured
from .settings_build import *

database = dj_database_url.parse(os.environ.get('STAGING_TEST_POSTGRES_URL', ''), conn_max_age=0)
if database.get('HOST') not in ('localhost', '127.0.0.1') or database.get('NAME') != 'bm_transfer_ci':
    raise ImproperlyConfigured('CI only accepts localhost/bm_transfer_ci.')
database.update(DISABLE_SERVER_SIDE_CURSORS=True, TEST={'NAME':'test_bm_application_ci'})
DATABASES = {'default': database}
TELEGRAM_BOT_TOKEN = 'ci-test-token-only'
TELEGRAM_ADMIN_CHAT_ID = ''
TELEGRAM_NOTIFICATIONS_ENABLED = False
MINIAPP_ORDERS_ENABLED = False
