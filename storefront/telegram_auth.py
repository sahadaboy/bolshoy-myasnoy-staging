"""Telegram's bot-token HMAC algorithm. Never authorise initDataUnsafe."""
from dataclasses import dataclass
from hashlib import sha256
from urllib.parse import parse_qsl, urlsplit
import hmac
import json
import re
import time
from django.conf import settings
from django.views.decorators.debug import sensitive_variables
from rest_framework.authentication import BaseAuthentication, get_authorization_header
from rest_framework.exceptions import AuthenticationFailed


@dataclass(frozen=True)
class TelegramIdentity:
    id: int
    first_name: str
    last_name: str = ''
    username: str = ''
    photo_url: str = ''
    auth_date: int = 0
    is_authenticated: bool = True


@sensitive_variables('raw', 'token', 'pairs', 'fields', 'secret', 'check')
def validate_init_data(raw, token, *, now=None, max_age=3600):
    try:
        if not token or not isinstance(raw, str) or not 0 < len(raw) <= 16384:
            raise ValueError
        pairs = parse_qsl(raw, keep_blank_values=True, strict_parsing=True, encoding='utf-8', errors='strict', max_num_fields=32)
        fields = dict(pairs)
        if len(fields) != len(pairs):
            raise ValueError
        supplied = fields.pop('hash', '')
        if not re.fullmatch(r'[a-fA-F0-9]{64}', supplied):
            raise ValueError
        check = '\n'.join(f'{key}={value}' for key, value in sorted(fields.items()))
        secret = hmac.new(b'WebAppData', token.encode(), sha256).digest()
        expected = hmac.new(secret, check.encode(), sha256).hexdigest()
        if not hmac.compare_digest(expected, supplied.lower()):
            raise ValueError
        auth_date = int(fields['auth_date'])
        current = time.time() if now is None else now
        if auth_date > current + 30 or current - auth_date > max_age:
            raise ValueError
        user = json.loads(fields['user'])
        if not isinstance(user, dict) or type(user.get('id')) is not int or not 0 < user['id'] < 2**63:
            raise ValueError
        if user.get('is_bot') is True or not isinstance(user.get('first_name'), str) or not 0 < len(user['first_name']) <= 256:
            raise ValueError
        for field in ['last_name', 'username']:
            if field in user and (not isinstance(user[field], str) or len(user[field]) > 256):
                raise ValueError
        photo = user.get('photo_url', '')
        if not isinstance(photo, str) or len(photo) > 2048:
            raise ValueError
        if photo and (urlsplit(photo).scheme != 'https' or not urlsplit(photo).hostname or urlsplit(photo).username):
            photo = ''
        return TelegramIdentity(user['id'], user['first_name'], user.get('last_name', ''), user.get('username', ''), photo, auth_date)
    except (ValueError, TypeError, KeyError, UnicodeError, json.JSONDecodeError):
        raise AuthenticationFailed('Не удалось подтвердить вход через Telegram. Откройте приложение заново.') from None


class TelegramAuthentication(BaseAuthentication):
    def authenticate(self, request):
        header = get_authorization_header(request)
        if not header:
            return None
        try:
            scheme, raw = header.decode('utf-8').split(' ', 1)
        except (ValueError, UnicodeError):
            raise AuthenticationFailed('Некорректные данные входа.') from None
        if scheme.lower() != 'tma':
            raise AuthenticationFailed('Используйте вход через Telegram.')
        return validate_init_data(raw, settings.TELEGRAM_BOT_TOKEN, max_age=settings.TELEGRAM_AUTH_MAX_AGE), None

    def authenticate_header(self, request):
        return 'tma'
