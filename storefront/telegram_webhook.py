import hmac
import json
from django.conf import settings
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.views.decorators.debug import sensitive_post_parameters
from .order_acceptance import process_callback


@csrf_exempt  # This endpoint accepts no cookie identity; only the Telegram secret.
@require_POST
@sensitive_post_parameters()
def webhook(request):
    if not settings.TELEGRAM_ORDER_WEBHOOK_ENABLED or not settings.TELEGRAM_WEBHOOK_SECRET: return HttpResponse(status=404)
    supplied=request.headers.get('X-Telegram-Bot-Api-Secret-Token','')
    if not hmac.compare_digest(supplied.encode(),settings.TELEGRAM_WEBHOOK_SECRET.encode()): return HttpResponse(status=403)
    if request.content_type!='application/json' or len(request.body)>65536: return HttpResponse(status=400)
    try:
        update=json.loads(request.body)
        if not isinstance(update,dict): raise ValueError
    except (ValueError,UnicodeError): return HttpResponse(status=400)
    query=update.get('callback_query')
    if not isinstance(query,dict) or not isinstance(query.get('data'),str) or not query['data'].startswith('oa:'):
        # Do not acknowledge/discard updates belonging to an existing bot feature.
        return HttpResponse(status=503)
    process_callback(update)
    return JsonResponse({'ok':True})
