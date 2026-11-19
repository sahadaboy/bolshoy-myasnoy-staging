"""Explicit isolated PostgreSQL QA target; never reads .env.staging."""
import json
import os
from pathlib import Path
from .settings import *

path = os.environ.get('BM_QA_CONFIG')
if not path:
    raise ImproperlyConfigured('BM_QA_CONFIG must point to a private QA configuration.')
qa = json.loads(Path(path).read_text(encoding='utf-8'))
connection = qa['connection']
if not connection['dbname'].startswith('bm_codex_qa_'):
    raise ImproperlyConfigured('QA settings refuse any database without the dedicated QA prefix.')
DATABASES = {'default': {'ENGINE':'django.db.backends.postgresql',
    'NAME':connection['dbname'], 'HOST':connection['host'], 'PORT':connection.get('port',5432),
    'USER':connection['user'], 'PASSWORD':connection['password'],
    'OPTIONS':{'sslmode':'require','connect_timeout':10},
    'DISABLE_SERVER_SIDE_CURSORS':True, 'CONN_MAX_AGE':0,
    'TEST':{'NAME':'test_' + connection['dbname']}}}
DEBUG = True
ROOT_URLCONF = 'config.urls_qa'
MEDIA_ROOT = Path(qa['media_root'])
ALLOWED_HOSTS = ['127.0.0.1','localhost','testserver']
TELEGRAM_BOT_TOKEN = qa['fake_bot_token']
TELEGRAM_ADMIN_CHAT_ID = ''
TELEGRAM_NOTIFICATIONS_ENABLED = False
MINIAPP_ORDERS_ENABLED = True
MINIAPP_WEIGHT_ESTIMATE = True
STAGING_DEPLOYMENT = False
