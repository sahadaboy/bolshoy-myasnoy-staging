import re
from datetime import timedelta
from django.db import transaction
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .models import Customer


def normalize_phone(value):
    if not isinstance(value, str) or not re.fullmatch(r'\+?[0-9 ()-]+', value):
        raise ValidationError('Укажите контактный номер в международном формате.')
    digits = re.sub(r'\D', '', value)
    if len(digits) == 11 and digits.startswith('8'):
        digits = '7' + digits[1:]
    elif not value.startswith('+') and not (len(digits) == 11 and digits.startswith('7')):
        raise ValidationError('Начните номер с + и кода страны.')
    if not 10 <= len(digits) <= 15 or digits.startswith('0') or (digits.startswith('7') and len(digits) != 11):
        raise ValidationError('Проверьте длину контактного номера.')
    return '+' + digits


@transaction.atomic
def sync_customer(identity):
    now = timezone.now()
    customer, _ = Customer.objects.get_or_create(telegram_id=identity.id)
    customer = Customer.objects.select_for_update().get(pk=customer.pk)
    changed = []
    if identity.auth_date >= customer.identity_date:
        for key in ('first_name', 'last_name', 'username', 'photo_url'):
            value = getattr(identity, key)
            if getattr(customer, key) != value:
                setattr(customer, key, value); changed.append(key)
        if customer.identity_date != identity.auth_date:
            customer.identity_date = identity.auth_date; changed.append('identity_date')
    if now - customer.last_seen_at >= timedelta(seconds=60):
        customer.last_seen_at = now; changed.append('last_seen_at')
    if changed:
        customer.save(update_fields=changed)
    return customer
