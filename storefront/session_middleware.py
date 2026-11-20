"""Database-backed customer sessions use a separate cookie from Django Admin."""
import time
from importlib import import_module
from django.conf import settings
from django.contrib.sessions.exceptions import SessionInterrupted
from django.contrib.sessions.backends.base import UpdateError
from django.utils.cache import patch_vary_headers
from django.utils.http import http_date


class CustomerSessionMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.store = import_module(settings.SESSION_ENGINE).SessionStore

    def __call__(self, request):
        if not request.path.startswith('/api/'):
            return self.get_response(request)
        name = settings.MINIAPP_SESSION_COOKIE_NAME
        request.customer_session = self.store(request.COOKIES.get(name))
        response = self.get_response(request)
        session = request.customer_session
        if session.accessed:
            patch_vary_headers(response, ['Cookie'])
        if session.is_empty():
            if name in request.COOKIES:
                response.delete_cookie(name, path='/', samesite='Lax')
                patch_vary_headers(response, ['Cookie'])
        elif session.modified and response.status_code < 500:
            try:
                session.save()
            except UpdateError:
                raise SessionInterrupted('Customer session expired during this request.') from None
            age = session.get_expiry_age()
            response.set_cookie(name, session.session_key, max_age=age,
                expires=http_date(time.time()+age), path='/', secure=settings.SESSION_COOKIE_SECURE,
                httponly=True, samesite='Lax')
            patch_vary_headers(response, ['Cookie'])
        return response
