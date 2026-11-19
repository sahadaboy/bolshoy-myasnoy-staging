from django.conf import settings
from django.http import FileResponse, JsonResponse, HttpResponseNotAllowed, Http404
from django.views.decorators.clickjacking import xframe_options_exempt


@xframe_options_exempt
def spa(request):
    if request.method not in ('GET', 'HEAD'):
        return HttpResponseNotAllowed(['GET', 'HEAD'])
    path = settings.BASE_DIR / 'frontend/dist/index.html'
    if not path.is_file():
        raise Http404
    response = FileResponse(path.open('rb'), content_type='text/html; charset=utf-8')
    response['Cache-Control'] = 'no-store'
    return response


def health(request):
    return JsonResponse({'status': 'ok'})


class SecurityHeaders:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        response['Referrer-Policy'] = 'no-referrer'
        if response.get('Content-Type', '').startswith('text/html') and not request.path.startswith('/admin/'):
            response['Content-Security-Policy'] = (
                "default-src 'self'; script-src 'self' https://telegram.org; "
                "style-src 'self' 'unsafe-inline'; img-src 'self' data: https:; "
                "font-src 'self' data:; connect-src 'self'; frame-src https://yandex.ru https://yandex.com; "
                "frame-ancestors https://web.telegram.org https://*.telegram.org; object-src 'none'; base-uri 'self'"
            )
        return response
