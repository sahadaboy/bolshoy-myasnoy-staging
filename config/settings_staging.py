"""Opt-in Render/Neon settings. Local config.settings and SQLite are unchanged."""
import os
from pathlib import Path
from urllib.parse import urlsplit
from .env import load_env

load_env(Path(__file__).resolve().parent.parent / '.env.staging')
from .settings import *  # noqa: E402,F403
import dj_database_url


def required(name):
    value = os.environ.get(name, '').strip()
    if not value:
        raise ImproperlyConfigured(f'Configure {name} in the staging server environment.')
    return value


DEBUG = False
STAGING_DEPLOYMENT = True
SECRET_KEY = required('DJANGO_SECRET_KEY')
if len(SECRET_KEY) < 50:
    raise ImproperlyConfigured('Staging DJANGO_SECRET_KEY must have at least 50 random characters.')
database_url = required('DATABASE_URL')
if urlsplit(database_url).scheme not in ('postgres', 'postgresql'):
    raise ImproperlyConfigured('Staging requires PostgreSQL; SQLite fallback is disabled.')
try:
    DATABASES = {'default': dj_database_url.parse(database_url, conn_max_age=0, conn_health_checks=True, ssl_require=True)}
except ValueError:
    raise ImproperlyConfigured('Invalid staging DATABASE_URL.') from None
DATABASES['default']['DISABLE_SERVER_SIDE_CURSORS'] = True
DATABASES['default']['OPTIONS'].update(sslmode='require', connect_timeout=10)

render_host = os.environ.get('RENDER_EXTERNAL_HOSTNAME', '').strip()
ALLOWED_HOSTS = [v.strip() for v in os.environ.get('STAGING_ALLOWED_HOSTS', render_host).split(',') if v.strip()]
if not ALLOWED_HOSTS or any('*' in host or '/' in host or host.startswith('.') for host in ALLOWED_HOSTS):
    raise ImproperlyConfigured('Configure exact STAGING_ALLOWED_HOSTS or RENDER_EXTERNAL_HOSTNAME.')
CSRF_TRUSTED_ORIGINS = [f'https://{host}' for host in ALLOWED_HOSTS]
if not MINIAPP_PUBLIC_URL and render_host:
    MINIAPP_PUBLIC_URL = f'https://{render_host}'

# Old releases ignored both flags, so inherited values must not open checkout
# on deployment. The new staging launch gate requires an explicit owner opt-in.
pickup_launch_enabled = os.environ.get('STAGING_PICKUP_ENABLED', '0') == '1'
MINIAPP_ORDERS_ENABLED = pickup_launch_enabled and os.environ.get('MINIAPP_ORDERS_ENABLED', '0') == '1'
TELEGRAM_NOTIFICATIONS_ENABLED = pickup_launch_enabled and os.environ.get('TELEGRAM_NOTIFICATIONS_ENABLED', '0') == '1'
if TELEGRAM_NOTIFICATIONS_ENABLED and (not TELEGRAM_BOT_TOKEN or not TELEGRAM_ADMIN_CHAT_ID):
    raise ImproperlyConfigured('Notification delivery requires the server bot token and TELEGRAM_ADMIN_CHAT_ID.')
MINIAPP_SHOW_DEMO_CONTENT = False
# The store has no transactional email feature. Keep the intentional dummy
# mailer; acknowledge only this deployment check rather than enabling fake SMTP.
SILENCED_SYSTEM_CHECKS = [*globals().get('SILENCED_SYSTEM_CHECKS', []), 'mail.E001']
ROOT_URLCONF = 'config.urls_staging'
SECURE_SSL_REDIRECT = True
SECURE_PROXY_SSL_HEADER = ('HTTP_X_FORWARDED_PROTO', 'https')
SECURE_REDIRECT_EXEMPT = [r'^healthz$']
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SECURE_HSTS_SECONDS = 31536000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
MIDDLEWARE = [MIDDLEWARE[0], 'whitenoise.middleware.WhiteNoiseMiddleware', 'deploy.web.SecurityHeaders', *MIDDLEWARE[1:]]
STATIC_URL = '/static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'
WHITENOISE_ROOT = BASE_DIR / '.build/frontend'
WHITENOISE_USE_FINDERS = False
WHITENOISE_AUTOREFRESH = False
WHITENOISE_MAX_AGE = 3600
MEDIA_ROOT = BASE_DIR / '.unused-media'  # No filesystem storage fallback.
MEDIA_URL = '/media/'
s3_endpoint = required('AWS_ENDPOINT_URL_S3')
parsed_endpoint = urlsplit(s3_endpoint)
if (parsed_endpoint.scheme != 'https' or not (parsed_endpoint.hostname or '').endswith('.neon.tech')
        or parsed_endpoint.username or parsed_endpoint.query or parsed_endpoint.fragment or parsed_endpoint.path not in ('', '/')):
    raise ImproperlyConfigured('Use the HTTPS Neon branch S3 endpoint, without credentials in its URL.')
STORAGES = {
    'default': {'BACKEND': 'storages.backends.s3.S3Storage', 'OPTIONS': {
        'bucket_name': required('AWS_STORAGE_BUCKET_NAME'),
        'endpoint_url': s3_endpoint.rstrip('/'),
        'access_key': required('AWS_ACCESS_KEY_ID'),
        'secret_key': required('AWS_SECRET_ACCESS_KEY'),
        'region_name': required('AWS_REGION'),
        'addressing_style': 'path', 'signature_version': 's3v4',
        'default_acl': None, 'file_overwrite': False,
        'querystring_auth': False,  # Only the public_read product-photo bucket.
        'object_parameters': {'CacheControl': 'public, max-age=3600'},
    }},
    'staticfiles': {'BACKEND': 'whitenoise.storage.CompressedManifestStaticFilesStorage'},
}
DATA_UPLOAD_MAX_MEMORY_SIZE = 12 * 1024 * 1024
FILE_UPLOAD_MAX_MEMORY_SIZE = 1024 * 1024
