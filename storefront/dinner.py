"""Deterministic dinner selection. No substitutes, generated recipes or AI calls."""
from collections import defaultdict
from decimal import Decimal, ROUND_CEILING
from math import gcd
from django.db.models import Prefetch
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError, APIException
from .models import DinnerSettings, DinnerQuestion, DinnerOption, DinnerRecipe, Ingredient, PantryIngredient
from .quantities import valid_quantity, line_total


class AssortmentChanged(APIException):
    status_code = 409
    default_detail = 'Состав или наличие изменились. Подберите идею ещё раз.'


class DinnerAnswers(serializers.Serializer):
    servings = serializers.IntegerField(min_value=1, max_value=12)
    pantry = serializers.ListField(child=serializers.IntegerField(min_value=1), max_length=100, default=list)
    exclude = serializers.ListField(child=serializers.IntegerField(min_value=1), max_length=100, default=list)
    answers = serializers.DictField(child=serializers.ListField(
        child=serializers.IntegerField(min_value=1), max_length=20), default=dict)


class ShoppingItem(serializers.Serializer):
    product_id = serializers.IntegerField(min_value=1)
    quantity = serializers.DecimalField(max_digits=9, decimal_places=3, min_value=Decimal('.001'))
    expected_price = serializers.DecimalField(max_digits=12, decimal_places=2, min_value=Decimal('0'))


class DinnerPreparation(DinnerAnswers):
    recipe_id = serializers.IntegerField(min_value=1)
    items = ShoppingItem(many=True, allow_empty=False, max_length=40)


def settings_and_questions():
    config = DinnerSettings.objects.filter(pk=1, is_active=True).first()
    if not config:
        raise NotFound('Подбор ужина сейчас недоступен.')
    questions = list(DinnerQuestion.objects.filter(is_active=True).prefetch_related(Prefetch(
        'options', queryset=DinnerOption.objects.filter(is_active=True), to_attr='live_options')))
    return config, questions


def ingredient_choices():
    return PantryIngredient.objects.filter(is_active=True,
        recipe_ingredients__article__dinner_rule__is_active=True,
        recipe_ingredients__article__is_published=True,
        recipe_ingredients__article__is_demo=False).distinct()


def schema():
    config, questions = settings_and_questions()
    return {'enabled': True, 'title': config.title, 'description': config.description,
            'default_servings': config.default_servings, 'max_servings': config.max_servings,
            'ingredients': list(ingredient_choices().values('id', 'name')),
            'questions': [{'key': question.key, 'title': question.title, 'help_text': question.help_text,
                           'required': question.required,
                           'options': [{'id': option.pk, 'label': option.label, 'is_any': option.is_any}
                                       for option in question.live_options]} for question in questions]}


def validate_answers(data):
    config, questions = settings_and_questions()
    active = {question.key: question for question in questions}
    if data['servings'] > config.max_servings:
        raise ValidationError({'servings': 'Превышено доступное число порций.'})
    if 'servings' not in active and data['servings'] != config.default_servings:
        raise ValidationError({'servings': 'Настройки числа порций изменились. Обновите вопросы.'})
    allowed_ingredients = set(ingredient_choices().values_list('pk', flat=True))
    for key in ('pantry', 'exclude'):
        values = set(data[key])
        if values - allowed_ingredients or values and key not in active:
            raise ValidationError({key: 'Список ингредиентов изменился. Обновите вопросы.'})
        if key in active and active[key].required and not values:
            raise ValidationError({key: 'Ответьте на обязательный вопрос.'})
    if set(data['answers']) - {key for key in active if key in ('dish', 'spice', 'preferences')}:
        raise ValidationError({'answers': 'Вопросы изменились. Начните подбор заново.'})
    chosen = set()
    for key, question in active.items():
        if key not in ('dish', 'spice', 'preferences'):
            continue
        values = set(data['answers'].get(key, []))
        options = {option.pk: option for option in question.live_options}
        if values - options.keys() or key != 'preferences' and len(values) > 1:
            raise ValidationError({'answers': 'Выбран недоступный ответ.'})
        if question.required and not values:
            raise ValidationError({'answers': f'Ответьте на вопрос «{question.title}».'})
        chosen.update(value for value in values if not options[value].is_any)
    return config, chosen


def purchase_quantity(product, needed):
    """Round UP to the actual kg/pcs sales lattice, never infer pack conversion."""
    minimum = int(product.min_quantity * 1000)
    step = int(product.quantity_step * 1000)
    target = int((needed * 1000).to_integral_value(rounding=ROUND_CEILING))
    if minimum <= 0 or step <= 0:
        return None
    if product.unit == 'pcs':
        divisor = gcd(step, 1000)
        if minimum % divisor:
            return None
        period = 1000 // divisor
        for offset in range(period):
            candidate = minimum + step * offset
            if candidate % 1000 == 0:
                minimum, step = candidate, step * period
                break
    elif product.unit != 'kg':
        return None
    count = max(0, (target - minimum + step - 1) // step)
    quantity = Decimal(minimum + count * step) / 1000
    return quantity if valid_quantity(product, quantity) else None


def suggestions(data, request, *, recipe_id=None):
    from shop.serializers import ProductSerializer
    config, chosen_options = validate_answers(data)
    owned, excluded = set(data['pantry']), set(data['exclude'])
    rules = DinnerRecipe.objects.filter(is_active=True, article__is_published=True,
        article__is_demo=False, article__kind='recipe').select_related('article').prefetch_related(
        'options', 'article__steps', Prefetch('article__ingredients', queryset=Ingredient.objects.select_related(
            'ingredient_type', 'product').prefetch_related('product__categories')))
    if recipe_id is not None:
        rules = rules.filter(pk=recipe_id)
    result = []
    for rule in rules[:150]:
        article = rule.article
        if not article.servings or not chosen_options <= {option.pk for option in rule.options.all()}:
            continue
        ingredients = list(article.ingredients.all())
        if not ingredients or any(item.ingredient_type_id in excluded for item in ingredients):
            continue
        if any(not item.ingredient_type_id or not item.ingredient_type.is_active for item in ingredients):
            continue
        needed, products, ingredient_ids = defaultdict(Decimal), {}, defaultdict(list)
        composition, failed = [], False
        for item in ingredients:
            have = item.ingredient_type_id in owned
            product = item.product
            base = item.recipe_quantity if item.recipe_quantity is not None else (
                item.purchase_quantity if item.purchase_quantity is not None else (product.min_quantity if product else None))
            scaled = base * data['servings'] / article.servings if base is not None else None
            available = bool(product and product.is_active and product.is_available and product.unit == item.recipe_unit and scaled is not None and
                             scaled > 0 and purchase_quantity(product, scaled) is not None)
            if not have and not available and not item.is_optional:
                failed = True
                break
            display_amount = item.amount
            if scaled is not None and product:
                recipe_unit = item.recipe_unit or product.unit
                number = scaled * 1000 if recipe_unit == 'kg' else scaled
                display_amount = format(number.quantize(Decimal('.001')).normalize(), 'f').replace('.', ',') + (' г' if recipe_unit == 'kg' else ' упак.')
            composition.append({'id': item.pk, 'ingredient_type_id': item.ingredient_type_id,
                'name': item.name, 'amount': display_amount, 'have': have, 'optional': item.is_optional,
                'status': 'owned' if have else 'buy' if available else 'optional_unavailable'})
            if not have and available:
                needed[product.pk] += scaled
                products[product.pk] = product
                ingredient_ids[product.pk].append(item.pk)
        if failed:
            continue
        shopping, total = [], Decimal('0')
        for product_id, amount in needed.items():
            product = products[product_id]
            quantity = purchase_quantity(product, amount)
            if quantity is None:
                failed = True
                break
            shopping.append({'product': ProductSerializer(product, context={'request': request}).data,
                             'quantity': format(quantity, '.3f'), 'ingredient_ids': ingredient_ids[product_id]})
            total += line_total(product.price, quantity)
        if failed:
            continue
        result.append({'id': rule.pk, 'slug': article.slug, 'title': article.title,
            'description': article.description, 'servings': data['servings'],
            'duration_minutes': article.duration_minutes, 'ingredients': composition,
            'steps': [step.text for step in article.steps.all()], 'shopping': shopping,
            'total': format(total, '.2f'), 'owned_count': sum(item['have'] for item in composition),
            '_priority': rule.sort_order})
    result.sort(key=lambda item: (-item['owned_count'], item['_priority'], item['id']))
    for item in result:
        item.pop('_priority')
    return result[:config.max_results]


def prepare_shopping(data, request):
    candidates = suggestions(data, request, recipe_id=data['recipe_id'])
    if not candidates:
        raise AssortmentChanged()
    allowed = {item['product']['id']: item['product'] for item in candidates[0]['shopping']}
    seen, items, total, prices_changed = set(), [], Decimal('0'), False
    from shop.models import Product
    from shop.serializers import ProductSerializer
    products = {item.pk: item for item in Product.objects.filter(pk__in=allowed).prefetch_related('categories')}
    for item in data['items']:
        product_id = item['product_id']
        product = products.get(product_id)
        if product_id in seen or product_id not in allowed or not product or not product.is_active or not product.is_available:
            raise AssortmentChanged()
        if product.unit != allowed[product_id]['unit']:
            raise AssortmentChanged()
        if not valid_quantity(product, item['quantity']):
            raise ValidationError({'items': 'Количество не соответствует единице, минимуму или шагу товара.'})
        seen.add(product_id)
        prices_changed |= product.price != item['expected_price']
        items.append({'product': ProductSerializer(product, context={'request': request}).data,
                      'quantity': format(item['quantity'], '.3f')})
        total += line_total(product.price, item['quantity'])
    return {'items': items, 'total': format(total, '.2f'), 'prices_changed': prices_changed}
