"""Initial, manually curated content. Does not create or edit catalogue products."""
from decimal import Decimal
from django.core.management.base import BaseCommand
from django.db import transaction
from shop.models import Product
from storefront.models import (StoreProfile, ProductCollection, ProductCollectionItem, Article, Ingredient,
    RecipeStep, DinnerSettings, DinnerQuestion, DinnerOption, DinnerRecipe, PantryIngredient)


class Command(BaseCommand):
    help = 'Настроить витрины, контакты и рецепты ужина, сохраняя существующие ручные настройки.'

    @transaction.atomic
    def handle(self, *args, **options):
        StoreProfile.objects.get_or_create(pk=1, defaults={
            'description': 'Большой выбор хорошего мяса и продуктов к вашему столу. '
                           'Приходите за повседневными покупками и всем необходимым для домашнего ужина.',
            'phone': '+79786544777', 'telegram_url': 'https://t.me/bmm_sev', 'vk_url': 'https://vk.ru/bm_sev',
            'map_url': 'https://yandex.ru/maps/-/CXG9IXk~',
            'opening_hours': '\n'.join(f'{day}: 08:00–{end}' for day, end in [
                ('Понедельник', '20:00'), ('Вторник', '20:00'), ('Среда', '19:00'),
                ('Четверг', '20:00'), ('Пятница', '20:00'), ('Суббота', '20:00'), ('Воскресенье', '20:00')]),
        })
        DinnerSettings.objects.get_or_create(pk=1)
        definitions = [
            ('pantry', 'Что уже есть дома?', 'Отметьте продукты, которые не нужно покупать.', []),
            ('dish', 'Что хочется приготовить?', '', [('any', 'Пока не решил', True), ('pasta', 'Паста', False),
                ('grain', 'Блюдо с крупой', False), ('meat', 'Мясное', False), ('fish', 'С рыбой', False)]),
            ('spice', 'Как насчёт острого?', '', [('any', 'Неважно', True), ('mild', 'Неострое', False), ('hot', 'Острое', False)]),
            ('servings', 'На сколько персон?', 'Количество продуктов пересчитается на выбранное число порций.', []),
            ('preferences', 'Есть пожелания к ужину?', 'Можно выбрать несколько.', [('quick', 'Быстро', False),
                ('hearty', 'Сытно', False)]),
            ('exclude', 'Что исключить?', 'Блюда с этими ингредиентами не попадут в результат.', []),
        ]
        answers = {}
        for index, (key, title, hint, choices) in enumerate(definitions):
            question, created = DinnerQuestion.objects.get_or_create(key=key, defaults={
                'title': title, 'help_text': hint, 'sort_order': index * 10})
            if created:
                for order, (value, label, is_any) in enumerate(choices):
                    option = DinnerOption.objects.create(question=question, value=value, label=label,
                                                          is_any=is_any, sort_order=order)
                    answers[value if key != 'dish' else 'dish_' + value] = option
            else:
                for option in question.options.all():
                    answers[option.value if key != 'dish' else 'dish_' + option.value] = option

        # These exact IDs/names were inspected in the existing price catalogue.
        # A renamed/missing SKU is not replaced with a similar item on rerun.
        products = {item.pk: item for item in Product.objects.filter(pk__in=[
            1394, 2, 167, 381, 2753, 3750, 452, 170, 3168, 124, 4633, 4634, 4635, 4785, 4787, 4783, 83, 4338, 1251, 67, 428])}
        showcases = [
            ('home-breakfast', 'Для завтрака', 'Хлопья, молоко и готовый завтрак', [2753, 3750, 452]),
            ('home-sweets', 'Сладкое', 'К чаю и для небольшого перерыва', [3168, 170, 124]),
            ('home-sausages', 'Колбасы', 'Мясные колбаски из нашего ассортимента', [4634, 4633, 4635]),
            ('meat', 'К мясу', 'Соусы и приправы к любимым блюдам', [167, 381]),
            ('home-drinks', 'Напитки', 'Фруктовые соки к вашему столу', [4787, 4785, 4783]),
            ('home-fast-dinner', 'Быстрый ужин', 'Основа для простых домашних блюд', [1394, 2, 4338, 1251]),
        ]
        for order, (slug, title, description, ids) in enumerate(showcases, 1):
            legacy = ProductCollection.objects.filter(slug='k-horoshemu-myasu').first() if slug == 'meat' else None
            if legacy:
                collection, created = legacy, False
            else:
                collection, created = ProductCollection.objects.get_or_create(slug=slug, defaults={
                    'title': title, 'description': description, 'sort_order': order * 10, 'is_published': True, 'home_limit': 4})
            if slug == 'meat' and collection.title == 'К хорошему мясу':
                collection.title, collection.sort_order = title, 40
                collection.save(update_fields=['title', 'sort_order'])
            if created:
                for item_order, product_id in enumerate(ids):
                    if product_id in products:
                        ProductCollectionItem.objects.create(collection=collection, product=products[product_id], sort_order=item_order)

        recipes = [
            ('pasta-tomato', 'Паста с томатным соусом', 'Простой домашний ужин из двух основных ингредиентов.', 20,
             ['dish_pasta', 'mild', 'quick', 'no_meat'],
             [('pasta', 'Макароны', 1394, '.400', '200 г'), ('tomato-sauce', 'Томатный соус', 2, '.500', 'по вкусу')],
             ['Отварите пасту по инструкции на упаковке. Сохраните немного воды от варки.',
              'Прогрейте томатный соус, добавьте пасту и немного отвара. Перемешайте и подавайте.']),
            ('spicy-pasta', 'Острая паста с аджикой', 'Для тех, кому хочется яркого вкуса без долгой готовки.', 20,
             ['dish_pasta', 'hot', 'quick', 'no_meat'],
             [('pasta', 'Макароны', 1394, '.400', '200 г'), ('adjika', 'Острая аджика', 167, '.150', 'по вкусу')],
             ['Отварите пасту по инструкции на упаковке и сохраните немного отвара.',
              'Добавляйте аджику небольшими порциями, разбавляя отваром до желаемой насыщенности. Соедините с пастой.']),
            ('rice-tuna-corn', 'Рис с тунцом и кукурузой', 'Сытное сочетание риса, консервированного тунца и сладкой кукурузы.', 25,
             ['dish_grain', 'dish_fish', 'mild', 'quick', 'hearty'],
             [('rice', 'Рис', 83, '.160', '160 г'), ('tuna', 'Тунец', 4338, '1.000', '1 банка'),
              ('corn', 'Кукуруза', 1251, '.500', 'половина банки')],
             ['Отварите рис до готовности по инструкции на упаковке.',
              'Слейте лишнюю жидкость из кукурузы. Разберите тунец вилкой, соедините с рисом и кукурузой, прогрейте и подавайте.']),
            ('buckwheat-mushrooms', 'Гречка с грибами', 'Горячая гречка с готовыми грибами — простой ужин без мяса.', 25,
             ['dish_grain', 'mild', 'quick', 'no_meat'],
             [('buckwheat', 'Гречка', 67, '.160', '160 г'), ('mushrooms', 'Грибы', 428, '.500', 'половина банки')],
             ['Отварите гречку до готовности по инструкции на упаковке.',
              'Слейте заливку из грибов, соедините их с горячей гречкой и прогрейте. Приправьте по своему вкусу.']),
        ]
        for order, (slug, title, description, minutes, tags, ingredients, steps) in enumerate(recipes):
            if any(product_id not in products for _, _, product_id, _, _ in ingredients):
                self.stdout.write(f'Skipped recipe without exact products: {slug}')
                continue
            article, created = Article.objects.get_or_create(slug=slug, defaults={
                'title': title, 'description': description, 'duration_minutes': minutes,
                'servings': 2, 'is_published': True, 'dinner': True, 'sort_order': order})
            if not created:
                continue
            for item_order, (key, name, product_id, quantity, amount) in enumerate(ingredients):
                ingredient_type, _ = PantryIngredient.objects.get_or_create(slug=key, defaults={'name': name, 'sort_order': item_order})
                product = products[product_id]
                Ingredient.objects.create(article=article, name=name, amount=amount, ingredient_type=ingredient_type,
                    product=product, recipe_quantity=Decimal(quantity), recipe_unit=product.unit, sort_order=item_order)
            for number, text in enumerate(steps, 1):
                RecipeStep.objects.create(article=article, sort_order=number, text=text)
            rule = DinnerRecipe.objects.create(article=article, is_active=True, sort_order=order)
            rule.options.set([answers[key] for key in tags if key in answers])
        self.stdout.write(self.style.SUCCESS('Store information, six showcases and dinner rules configured; products unchanged.'))
