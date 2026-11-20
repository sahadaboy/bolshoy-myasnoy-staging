from decimal import Decimal
from hashlib import sha256
import json
import re
from django.conf import settings
from django.db import IntegrityError, OperationalError, transaction
from django.db.models import Count
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.exceptions import APIException, ValidationError
from rest_framework.pagination import PageNumberPagination
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView
from shop.models import Product
from .models import Order, OrderItem, StoreProfile, Customer, OrderNotification, OrderStatusEvent
from .customers import sync_customer, normalize_phone
from .quantities import line_total, valid_quantity
from .telegram_auth import TelegramAuthentication, CustomerAuthentication
from django.middleware.csrf import get_token, rotate_token
from rest_framework.authentication import SessionAuthentication
from django.utils.cache import patch_vary_headers


class PrivateAPI(APIView):
    authentication_classes = [CustomerAuthentication]

    def perform_authentication(self, request):
        super().perform_authentication(request)
        if request.user and request.user.is_authenticated and not hasattr(request, 'customer'):
            request.customer = sync_customer(request.user)

    def finalize_response(self, request, response, *args, **kwargs):
        result = super().finalize_response(request, response, *args, **kwargs)
        result['Cache-Control'] = 'private, no-store'
        patch_vary_headers(result, ['Authorization', 'Cookie'])
        result['X-Content-Type-Options'] = 'nosniff'
        return result


class SessionView(PrivateAPI):
    def get(self, request):
        user = request.user
        verified = bool(user and user.is_authenticated)
        profile = StoreProfile.objects.filter(pk=1).first()
        return Response({
            'csrf_token': get_token(request),
            'authenticated': verified,
            'user': {'id': str(user.id), 'customer_id': request.customer.pk,
                     'first_name': request.customer.first_name, 'last_name': request.customer.last_name,
                     'username': request.customer.username, 'photo_url': request.customer.photo_url or None,
                     'phone': request.customer.phone, 'registered_at': request.customer.registered_at} if verified else None,
            # The bot menu URL can be changed through Bot API. A ?startapp link
            # would use the separate Main App URL from BotFather, which may be stale.
            'telegram_url': f'https://t.me/{settings.MINIAPP_BOT_USERNAME}' if settings.MINIAPP_BOT_USERNAME else None,
            'checkout_enabled': bool(settings.MINIAPP_ORDERS_ENABLED and settings.TELEGRAM_BOT_TOKEN),
            'weight_estimate': settings.MINIAPP_WEIGHT_ESTIMATE,
            'store': {'address': profile.address if profile else settings.PICKUP_ADDRESS,
                      'phone': (profile.phone if profile else settings.MINIAPP_STORE_PHONE) or None,
                      'email': (profile.email if profile else settings.MINIAPP_STORE_EMAIL) or None},
        })


class SessionLoginView(PrivateAPI):
    authentication_classes = [TelegramAuthentication]
    permission_classes = [IsAuthenticated]

    def perform_authentication(self, request):
        APIView.perform_authentication(self, request)

    def post(self, request):
        SessionAuthentication().enforce_csrf(request)
        request.customer = sync_customer(request.user)
        request.customer_session.cycle_key()
        rotate_token(request)
        request.customer_session['miniapp_customer_id'] = request.customer.pk
        request.customer_session['miniapp_telegram_id'] = request.user.id
        request.customer_session.set_expiry(settings.MINIAPP_SESSION_AGE)
        return SessionView.get(self, request)


class OrderItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = OrderItem
        fields = ['product_id', 'product_name', 'sku', 'quantity', 'unit', 'unit_price', 'subtotal']


class OrderSerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source='public_id', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    class Meta:
        model = Order
        fields = ['id', 'number', 'created_at', 'buyer_name', 'phone', 'comment', 'pickup_address', 'pickup_at', 'total', 'weight_estimate', 'status', 'status_label', 'fulfillment', 'items']


class OrderSummarySerializer(serializers.ModelSerializer):
    id = serializers.UUIDField(source='public_id', read_only=True)
    status_label = serializers.CharField(source='get_status_display', read_only=True)
    item_count = serializers.IntegerField(read_only=True)
    class Meta:
        model = Order
        fields = ['id', 'number', 'created_at', 'pickup_at', 'total', 'status', 'status_label', 'item_count']


class RequestItemSerializer(serializers.Serializer):
    product_id = serializers.IntegerField(min_value=1, max_value=2**63 - 1)
    quantity = serializers.DecimalField(max_digits=9, decimal_places=3, min_value=Decimal('0.001'))
    expected_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0'), required=False)


class OrderRequestSerializer(serializers.Serializer):
    pickup_at = serializers.DateTimeField(required=False)
    request_id = serializers.UUIDField()
    buyer_name = serializers.CharField(max_length=100, trim_whitespace=True)
    phone = serializers.CharField(max_length=32)
    fulfillment = serializers.ChoiceField(choices=['pickup'], default='pickup')
    comment = serializers.CharField(max_length=1000, required=False, allow_blank=True, default='')
    items = RequestItemSerializer(many=True, allow_empty=False, max_length=100)

    def validate_phone(self, value):
        return normalize_phone(value)

    def validate_pickup_at(self, value):
        from django.utils.dateparse import parse_datetime
        raw = self.initial_data.get('pickup_at')
        try:
            parsed = parse_datetime(raw) if isinstance(raw,str) else raw
            if parsed is None or timezone.is_naive(parsed): raise ValueError
        except (ValueError,TypeError):
            raise serializers.ValidationError('Укажите время с часовым поясом магазина.') from None
        return value

    def validate_items(self, items):
        if len({item['product_id'] for item in items}) != len(items):
            raise serializers.ValidationError('Один товар не должен повторяться в составе заявки.')
        return items


class OrderConflict(APIException):
    status_code = 409
    default_detail = 'Состав или цена изменились. Проверьте корзину и подтвердите ещё раз.'


class OrdersUnavailable(APIException):
    status_code = 503
    default_detail = 'Приём заявок пока выключен. Корзина сохранена.'


class OrderThrottle(SimpleRateThrottle):
    scope = 'order_submission'
    rate = '10/min'
    def get_cache_key(self, request, view):
        return self.cache_format % {'scope': self.scope, 'ident': str(request.user.id)}


def fingerprint(data):
    payload = [data['buyer_name'], data['phone'], data['comment'], sorted((item['product_id'], format(item['quantity'], '.3f')) for item in data['items'])]
    if data.get('pickup_at') is not None:
        from datetime import timezone as dt_timezone
        payload.append(data['pickup_at'].astimezone(dt_timezone.utc).isoformat())
    return sha256(json.dumps(payload, ensure_ascii=True, separators=(',', ':')).encode()).hexdigest()


def repeated_order(user_id, request_id, expected):
    order = Order.objects.filter(telegram_user_id=user_id, request_id=request_id).prefetch_related('items').first()
    if order and order.request_fingerprint != expected:
        raise OrderConflict('Эта заявка уже отправлена с другим составом. Обновите страницу оформления.')
    return order


class OrderListCreateView(PrivateAPI):
    permission_classes = [IsAuthenticated]

    def initial(self, request, *args, **kwargs):
        result = super().initial(request, *args, **kwargs)
        if request.method == 'POST':
            try:
                size = int(request.META.get('CONTENT_LENGTH') or 0)
            except ValueError:
                raise ValidationError('Некорректная длина запроса.') from None
            if not 0 <= size <= 64 * 1024:
                error = APIException('Заявка слишком большая.')
                error.status_code = 413
                raise error
        return result

    def get_throttles(self):
        return [OrderThrottle()] if self.request.method == 'POST' else []

    def get(self, request):
        queryset = Order.objects.filter(telegram_user_id=request.user.id).annotate(item_count=Count('items')).order_by('-created_at', '-pk')
        paginator = PageNumberPagination()
        page = paginator.paginate_queryset(queryset, request, view=self)
        return paginator.get_paginated_response(OrderSummarySerializer(page, many=True).data)

    def post(self, request):
        serializer = OrderRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        signature = fingerprint(data)
        existing = repeated_order(request.user.id, data['request_id'], signature)
        if existing:
            return Response(OrderSerializer(existing).data, status=200)
        if not settings.MINIAPP_ORDERS_ENABLED or not settings.TELEGRAM_BOT_TOKEN:
            raise OrdersUnavailable()
        try:
            with transaction.atomic():
                from .pickup import validate_pickup
                profile = StoreProfile.objects.select_for_update().filter(pk=1).first()
                existing = repeated_order(request.user.id, data['request_id'], signature)
                if existing:
                    return Response(OrderSerializer(existing).data, status=200)
                if data.get('pickup_at') is None:
                    validate_pickup(None, profile)
                products = {product.pk: product for product in Product.objects.select_for_update().filter(pk__in=[item['product_id'] for item in data['items']])}
                lines = []
                for item in data['items']:
                    product = products.get(item['product_id'])
                    if not product or not product.is_active or not product.is_available:
                        raise ValidationError({'items': 'Один из товаров больше не доступен. Обновите корзину.'})
                    if not product.price.is_finite() or product.price < 0:
                        raise ValidationError({'items': 'Цена одного из товаров уточняется. Обновите корзину.'})
                    quantity = item['quantity']
                    if not valid_quantity(product, quantity):
                        raise ValidationError({'items': f'Проверьте количество товара «{product.name}».'})
                    if 'expected_price' in item and item['expected_price'] != product.price:
                        raise OrderConflict()
                    lines.append(OrderItem(product=product, product_name=product.name, sku=product.sku, quantity=quantity, unit=product.unit, unit_price=product.price, subtotal=line_total(product.price, quantity)))
                total = sum((line.subtotal for line in lines), Decimal('0.00'))
                if not Decimal('0') <= total <= Decimal('9999999999.99'):
                    raise ValidationError({'items': 'Сумма заявки слишком велика. Уменьшите количество.'})
                customer = Customer.objects.select_for_update().get(pk=request.customer.pk)
                created_at = timezone.now()
                validate_pickup(data['pickup_at'], profile, now=created_at)
                order = Order.objects.create(customer=customer, created_at=created_at, fulfillment=data['fulfillment'], pickup_at=data['pickup_at'], telegram_user_id=request.user.id, request_id=data['request_id'], request_fingerprint=signature, buyer_name=data['buyer_name'], phone=data['phone'], comment=data['comment'], pickup_address=settings.PICKUP_ADDRESS, total=total, weight_estimate=settings.MINIAPP_WEIGHT_ESTIMATE and any(line.unit == 'kg' for line in lines))
                for line in lines:
                    line.order = order
                OrderItem.objects.bulk_create(lines)
                from .cart_api import consume_order_cart
                consume_order_cart(customer, lines)
                customer.phone = data['phone']; customer.save(update_fields=['phone'])
                notification = OrderNotification.objects.create(order=order)
                OrderStatusEvent.objects.create(order=order, status=Order.Status.NEW)
                from .notifications import dispatch_after_commit
                transaction.on_commit(lambda: dispatch_after_commit(notification.pk), robust=True)
            return Response(OrderSerializer(order).data, status=201)
        except IntegrityError:
            existing = repeated_order(request.user.id, data['request_id'], signature)
            if existing:
                return Response(OrderSerializer(existing).data, status=200)
            raise OrdersUnavailable('Не удалось сохранить заявку. Попробуйте ещё раз.') from None
        except OperationalError:
            raise OrdersUnavailable('Сервер временно занят. Повторите отправку; повторная заявка не создастся.') from None


class OrderDetailView(PrivateAPI):
    permission_classes = [IsAuthenticated]
    def get(self, request, order_id):
        order = get_object_or_404(Order.objects.filter(telegram_user_id=request.user.id).prefetch_related('items'), public_id=order_id)
        return Response(OrderSerializer(order).data)


class CustomerProfileView(PrivateAPI):
    permission_classes = [IsAuthenticated]

    def patch(self, request):
        class PhoneForm(serializers.Serializer):
            phone = serializers.CharField(allow_blank=True, max_length=32)
        form = PhoneForm(data=request.data)
        form.is_valid(raise_exception=True)
        value = form.validated_data['phone']
        if value != '':
            value = normalize_phone(value)
        # Independent of checkout and Telegram message delivery. Read the saved
        # value before acknowledging, rather than returning the submitted text.
        with transaction.atomic():
            customer = Customer.objects.select_for_update().get(pk=request.customer.pk)
            customer.phone = value
            customer.save(update_fields=['phone'])
            customer.refresh_from_db(fields=['phone'])
        return Response({'phone': customer.phone})

    def post(self, request):
        # POST also works through intermediaries that restrict PATCH. Keep PATCH
        # for already-open older clients; both use the exact same authentication.
        return self.patch(request)


class RepeatOrderView(PrivateAPI):
    permission_classes = [IsAuthenticated]

    def post(self, request, order_id):
        from shop.serializers import ProductSerializer
        order = get_object_or_404(Order.objects.filter(telegram_user_id=request.user.id).prefetch_related('items'), public_id=order_id)
        products = {item.pk: item for item in Product.objects.filter(pk__in=order.items.values_list('product_id', flat=True)).prefetch_related('categories')}
        items, unavailable, changed = [], [], []
        for row in order.items.all():
            product = products.get(row.product_id)
            reason = ''
            if not product or not product.is_active or not product.is_available:
                reason = 'Нет в продаже'
            elif product.unit != row.unit or not valid_quantity(product, row.quantity):
                reason = 'Изменилась единица или допустимое количество. Выберите количество в каталоге.'
            if reason:
                unavailable.append({'name': row.product_name, 'reason': reason})
                continue
            items.append({'product': ProductSerializer(product, context={'request': request}).data, 'quantity': format(row.quantity, '.3f')})
            if product.price != row.unit_price:
                changed.append({'name': product.name, 'before': str(row.unit_price), 'after': str(product.price)})
        return Response({'items': items, 'unavailable': unavailable, 'changed': changed})
