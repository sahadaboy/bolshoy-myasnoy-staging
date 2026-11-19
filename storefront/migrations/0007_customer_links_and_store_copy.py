from django.db import migrations

DESCRIPTION = ('Уже несколько лет мы радуем наших покупателей качественными продуктами, широким ассортиментом и внимательным отношением к каждой детали.\n\n'
    'Мы тщательно подходим к выбору продукции, постоянно обновляем ассортимент и стараемся, чтобы каждый визит в наш магазин был приятным.\n\n'
    'От свежего мяса и продукции собственного производства до любимых продуктов на каждый день — у нас всегда найдётся что-то вкусное для вашего стола')


def populate(apps, schema_editor):
    Customer = apps.get_model('storefront', 'Customer')
    Order = apps.get_model('storefront', 'Order')
    for order in Order.objects.filter(customer__isnull=True).order_by('created_at', 'pk').iterator():
        customer, created = Customer.objects.get_or_create(telegram_id=order.telegram_user_id,
            defaults={'registered_at': order.created_at, 'last_seen_at': order.created_at, 'phone': order.phone})
        if not created and customer.identity_date == 0 and customer.last_seen_at <= order.created_at:
            customer.last_seen_at, customer.phone = order.created_at, order.phone
            customer.save(update_fields=['last_seen_at', 'phone'])
        Order.objects.filter(pk=order.pk).update(customer_id=customer.pk)
    Store = apps.get_model('storefront', 'StoreProfile')
    Store.objects.filter(pk=1).update(description=DESCRIPTION)
    Store.objects.filter(pk=1, address='Севастополь, Камышовое шоссе, 25', map_embed_url='',
        map_url='https://yandex.ru/maps/-/CXG9IXk~').update(map_embed_url='https://yandex.ru/map-widget/v1/?oid=174956281155&ol=biz&z=16')
    apps.get_model('storefront', 'DinnerOption').objects.filter(question__key='preferences', value='no_meat').update(is_active=False)


class Migration(migrations.Migration):
    dependencies = [('storefront', '0006_storeprofile_map_embed_url')]
    operations = [migrations.RunPython(populate, migrations.RunPython.noop)]
