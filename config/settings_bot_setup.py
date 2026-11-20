"""One-off bot administration on Windows; no connection to a shop database."""
import os
from pathlib import Path
from django.core.exceptions import ImproperlyConfigured
from .env import load_env

private_file=Path(os.environ.get('MINIAPP_SERVER_ENV_FILE',''))
if not private_file.is_absolute() or not private_file.is_file():
    raise ImproperlyConfigured('MINIAPP_SERVER_ENV_FILE must name an existing private server environment file.')
load_env(private_file)
from .settings import *  # noqa: E402,F403

DATABASES={'default':{'ENGINE':'django.db.backends.sqlite3','NAME':':memory:'}}
