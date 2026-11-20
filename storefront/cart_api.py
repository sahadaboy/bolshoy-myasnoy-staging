from decimal import Decimal
from hashlib import sha256
import json
from django.db import transaction
from rest_framework import serializers
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from shop.models import Product
from shop.serializers import ProductSerializer
from .models import Customer, CustomerCart, CartOperation
from .order_api import PrivateAPI
from .quantities import valid_quantity


def cart_payload(cart, request):
    products = {p.pk: p for p in Product.objects.filter(pk__in=cart.items).prefetch_related('categories')}
    lines = []
    for key, quantity in cart.items.items():
        product = products.get(int(key))
        data = ProductSerializer(product, context={'request': request}).data if product else None
        if data and (not product.is_active or not valid_quantity(product, Decimal(quantity))):
            data['is_available'] = False
        lines.append({'product_id': int(key), 'product': data, 'quantity': quantity})
    return {'revision': cart.revision, 'items': lines}


class CartLine(serializers.Serializer):
    product_id = serializers.IntegerField(min_value=1, max_value=2**63-1)
    quantity = serializers.DecimalField(max_digits=9, decimal_places=3, min_value=Decimal('0'))
    expected_quantity = serializers.DecimalField(max_digits=9, decimal_places=3, min_value=Decimal('0'), default=Decimal('0'))


class CartChange(serializers.Serializer):
    operation_id = serializers.UUIDField()
    base_revision = serializers.IntegerField(min_value=0)
    mode = serializers.ChoiceField(choices=['patch', 'merge'], default='patch')
    changes = CartLine(many=True, max_length=100, allow_empty=False)

    def validate_changes(self, value):
        if len({line['product_id'] for line in value}) != len(value):
            raise serializers.ValidationError('Товар повторяется в изменениях корзины.')
        return value


class CartView(PrivateAPI):
    permission_classes = [IsAuthenticated]

    @transaction.atomic
    def get(self, request):
        Customer.objects.select_for_update().get(pk=request.customer.pk)
        cart, _ = CustomerCart.objects.get_or_create(customer=request.customer)
        return Response(cart_payload(cart, request))

    @transaction.atomic
    def post(self, request):
        form = CartChange(data=request.data)
        form.is_valid(raise_exception=True)
        data = form.validated_data
        signature = sha256(json.dumps(data, sort_keys=True, default=str).encode()).hexdigest()
        Customer.objects.select_for_update().get(pk=request.customer.pk)
        cart, _ = CustomerCart.objects.get_or_create(customer=request.customer)
        receipt = CartOperation.objects.filter(cart=cart, operation_id=data['operation_id']).first()
        if receipt:
            if receipt.fingerprint != signature:
                return Response({'detail': 'Ключ операции уже использован с другими данными.'}, status=409)
            return Response(cart_payload(cart, request))
        if data['mode'] == 'patch' and data['base_revision'] != cart.revision:
            if any(Decimal(cart.items.get(str(line['product_id']), '0')) not in (line['expected_quantity'], line['quantity']) for line in data['changes']):
                return Response({'detail': 'Корзина изменена на другом устройстве.', 'cart': cart_payload(cart, request)}, status=409)
        products = {p.pk: p for p in Product.objects.filter(pk__in=[line['product_id'] for line in data['changes']])}
        items = dict(cart.items)
        for line in data['changes']:
            key, quantity = str(line['product_id']), line['quantity']
            if data['mode'] == 'merge':
                quantity = max(quantity, Decimal(items.get(key, '0')))
            if quantity:
                product = products.get(line['product_id'])
                if not product or not product.is_active or not valid_quantity(product, quantity):
                    raise serializers.ValidationError({'detail': 'Проверьте товар, единицу и шаг количества в корзине.'})
                if not product.is_available and quantity > Decimal(items.get(key, '0')):
                    raise serializers.ValidationError({'detail': 'Товар недоступен для добавления.'})
                items[key] = format(quantity, '.3f')
            else:
                items.pop(key, None)
        if len(items) > 100:
            raise serializers.ValidationError({'detail': 'В корзине может быть до 100 разных товаров.'})
        cart.items = items
        cart.revision += 1
        cart.save(update_fields=['items', 'revision', 'updated_at'])
        CartOperation.objects.create(cart=cart, operation_id=data['operation_id'], fingerprint=signature)
        return Response(cart_payload(cart, request))


def consume_order_cart(customer, lines):
    """Successful order transaction only; preserve unrelated or concurrently changed lines."""
    cart = CustomerCart.objects.filter(customer=customer).first()
    if not cart:
        return
    items = dict(cart.items)
    for line in lines:
        key = str(line.product_id)
        if Decimal(items.get(key, '0')) == line.quantity:
            items.pop(key, None)
    if items != cart.items:
        cart.items = items
        cart.revision += 1
        cart.save(update_fields=['items', 'revision', 'updated_at'])
