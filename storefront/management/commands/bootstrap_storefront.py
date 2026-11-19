from pathlib import Path
from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction
from shop.models import Product
from storefront.models import Banner, ProductCollection, ProductCollectionItem


class Command(BaseCommand):
    help = 'Добавить утверждённый фирменный баннер и подборку к мясу; товары не меняются.'

    @transaction.atomic
    def handle(self, *args, **options):
        source = settings.BASE_DIR / 'frontend/public/preview/dinner-banner.webp'
        if source.is_file() and not Banner.objects.filter(name='Большой выбор для большого ужина').exists():
            banner = Banner(name='Большой выбор для большого ужина', alt_text='Большой выбор для большого ужина. Всегда большой выбор хорошего мяса!', is_active=True, target_type='catalog')
            with source.open('rb') as image:
                banner.image.save('brand-dinner.webp', File(image), save=False)
            banner.full_clean()
            banner.save()
        collection, _ = ProductCollection.objects.get_or_create(slug='k-horoshemu-myasu', defaults={'title': 'К хорошему мясу', 'is_published': True})
        for position, (pk, prefix) in enumerate([(167, 'аджика'), (381, 'горчица'), (166, 'аджика'), (380, 'горчица')]):
            product = Product.objects.filter(pk=pk, is_active=True).first()
            if product and product.name.casefold().startswith(prefix):
                ProductCollectionItem.objects.get_or_create(collection=collection, product=product, defaults={'sort_order': position})
        self.stdout.write(self.style.SUCCESS('Фирменная витрина готова. Товары и их фотографии не изменены.'))
