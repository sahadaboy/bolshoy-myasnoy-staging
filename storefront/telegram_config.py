"""Public launch URL validation, independent from Telegram identity and the DB."""
import re
from urllib.parse import urlsplit


def public_app_url(value):
    try:
        value = value.strip()
        if re.search(r'[\x00-\x20\x7f]', value):
            raise ValueError
        url = urlsplit(value)
        host = url.hostname or ''
        labels = host.split('.')
        if (url.scheme != 'https' or url.username is not None or url.password is not None
                or url.port not in (None, 443) or url.path not in ('', '/')
                or url.query or url.fragment or len(host) > 253 or len(labels) < 2
                or any(not re.fullmatch(r'[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?', label) for label in labels)
                or all(label.isdigit() for label in labels)):
            raise ValueError
        return f'https://{host}'
    except (AttributeError, TypeError, ValueError):
        raise ValueError('Укажите один публичный HTTPS-адрес без пути, параметров, пароля и нестандартного порта.') from None
