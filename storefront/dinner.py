"""Deterministic recipes and explicitly reviewed catalogue links. No AI calls."""
from collections import defaultdict
from decimal import Decimal, ROUND_CEILING
from math import gcd
from django.db.models import Prefetch
from rest_framework import serializers
from rest_framework.exceptions import NotFound, ValidationError, APIException
from .models import DinnerSettings, DinnerQuestion, DinnerOption, DinnerRecipe, Ingredient, PantryIngredient, IngredientAlternative
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
    recipe_id = serializers.IntegerField(min_value=1, required=False)
    replacements = serializers.DictField(child=serializers.IntegerField(min_value=0), default=dict)

    def validate_replacements(self, value):
        if len(value) > 40 or any(not key.isdecimal() or int(key) < 1 for key in value):
            raise serializers.ValidationError('Некорректный список замен.')
        return value


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
                           'options': [{'id': option.pk, 'label': option.label, 'value': option.value, 'is_any': option.is_any}
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
    if set(data['answers']) - {key for key in active if key in ('dish', 'spice', 'preferences', 'time')}:
        raise ValidationError({'answers': 'Вопросы изменились. Начните подбор заново.'})
    chosen, time_limit = set(), None
    for key, question in active.items():
        if key not in ('dish', 'spice', 'preferences', 'time'):
            continue
        values = set(data['answers'].get(key, []))
        options = {option.pk: option for option in question.live_options}
        if values - options.keys() or key != 'preferences' and len(values) > 1:
            raise ValidationError({'answers': 'Выбран недоступный ответ.'})
        if question.required and not values:
            raise ValidationError({'answers': f'Ответьте на вопрос «{question.title}».'})
        if key == 'time':
            if values:
                option = options[next(iter(values))]
                if not option.is_any:
                    if not option.max_minutes:
                        raise ValidationError({'answers': 'Ограничение времени не настроено.'})
                    time_limit = option.max_minutes
        else:
            chosen.update(value for value in values if not options[value].is_any)
    if data.get('replacements') and not data.get('recipe_id'):
        raise ValidationError({'replacements': 'Сначала выберите рецепт.'})
    return config, chosen, time_limit


def ingredient_amount(item, servings, base_servings, product=None, pack_size=None):
    """Physical recipe measures are independent of rounded purchasable packs."""
    factor = Decimal(servings) / base_servings
    product = product or item.product
    if item.amount_value is not None:
        physical = item.amount_value * factor
        size = pack_size if pack_size is not None else item.pack_size
        valid = size is not None and size > 0 and item.amount_unit
        if product and product.unit == 'kg' and (item.amount_unit != 'g' or size != 1000):
            valid = False
        needed = physical / size if valid else None
        number = format(physical.quantize(Decimal('.001')).normalize(), 'f').replace('.', ',')
        label = dict(Ingredient._meta.get_field('amount_unit').choices).get(item.amount_unit, '')
        if item.amount_unit == 'can':
            label = 'банка' if physical == 1 else 'банки' if physical % 1 else ('банки' if physical % 10 in (2, 3, 4) and physical % 100 not in (12, 13, 14) else 'банок')
        return needed, f'{number} {label}'.strip()
    base = item.recipe_quantity if item.recipe_quantity is not None else (
        item.purchase_quantity if item.purchase_quantity is not None else (product.min_quantity if product else None))
    needed = base * factor if base is not None else None
    display = item.amount
    if needed is not None and product:
        unit = item.recipe_unit or product.unit
        number = needed * 1000 if unit == 'kg' else needed
        display = format(number.quantize(Decimal('.001')).normalize(), 'f').replace('.', ',') + (' г' if unit == 'kg' else ' упак.')
    return needed, display


def reviewed_alternatives(item):
    return [option for option in item.alternatives.all() if option.is_active and item.amount_value
            and option.product.is_active and option.product.is_available and option.pack_size > 0
            and option.product.price.is_finite() and option.product.price >= 0
            and option.sale_unit == option.product.unit
            and (option.product.unit != 'kg' or item.amount_unit == 'g' and option.pack_size == 1000)]


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
    config, chosen_options, time_limit = validate_answers(data)
    recipe_id = recipe_id or data.get('recipe_id')
    owned, excluded = set(data['pantry']), set(data['exclude'])
    rules = DinnerRecipe.objects.filter(is_active=True, article__is_published=True,
        article__is_demo=False, article__kind='recipe').select_related('article').prefetch_related(
        Prefetch('options', queryset=DinnerOption.objects.select_related('question')), 'article__steps', Prefetch('article__ingredients', queryset=Ingredient.objects.select_related(
            'ingredient_type', 'product').prefetch_related('product__categories', Prefetch('alternatives',
                queryset=IngredientAlternative.objects.select_related('product').prefetch_related('product__categories')))))
    if recipe_id is not None:
        rules = rules.filter(pk=recipe_id)
    result = []
    for rule in rules[:150]:
        article = rule.article
        if not article.servings or not chosen_options <= {option.pk for option in rule.options.all()}:
            continue
        selected_spice = set(data['answers'].get('spice', [])) & chosen_options
        recipe_spice = {option.pk for option in rule.options.all() if option.question.key == 'spice' and not option.is_any}
        if selected_spice and recipe_spice != selected_spice:
            # A contradictory Admin rule must not make a hot recipe "mild".
            continue
        if time_limit and (not article.duration_minutes or article.duration_minutes > time_limit):
            continue
        ingredients = list(article.ingredients.all())
        if not ingredients or any(item.ingredient_type_id in excluded for item in ingredients):
            continue
        if any(not item.ingredient_type_id or not item.ingredient_type.is_active for item in ingredients):
            continue
        if set(data.get('replacements', {})) - {str(item.pk) for item in ingredients}:
            raise ValidationError({'replacements': 'Замена не относится к выбранному рецепту.'})
        needed, products, ingredient_ids = defaultdict(Decimal), {}, defaultdict(list)
        composition, failed = [], False
        for item in ingredients:
            have = item.ingredient_type_id in owned
            product = item.product
            alternatives = reviewed_alternatives(item)
            replacement_id = data.get('replacements', {}).get(str(item.pk), 0)
            replacement = next((option for option in alternatives if option.pk == replacement_id), None)
            if replacement_id and not replacement:
                raise AssortmentChanged('Выбранная замена больше не доступна в каталоге.')
            if replacement:
                product = replacement.product
            scaled, display_amount = ingredient_amount(item, data['servings'], article.servings, product,
                replacement.pack_size if replacement else None)
            sale_unit = replacement.sale_unit if replacement else item.recipe_unit
            available = bool(product and product.is_active and product.is_available and product.price.is_finite() and product.price >= 0 and product.unit == sale_unit and scaled is not None and
                             scaled > 0 and purchase_quantity(product, scaled) is not None)
            if not have and not available and not item.is_optional:
                failed = True
                break
            choices = []
            if not have and alternatives:
                if item.product and item.product.is_active and item.product.is_available:
                    choices.append({'id': 0, 'product': ProductSerializer(item.product, context={'request': request}).data})
                choices.extend({'id': option.pk, 'product': ProductSerializer(option.product, context={'request': request}).data} for option in alternatives)
            composition.append({'id': item.pk, 'ingredient_type_id': item.ingredient_type_id,
                'name': item.name, 'amount': display_amount, 'have': have, 'optional': item.is_optional,
                'replacement_id': replacement_id, 'alternatives': choices,
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
            'image': request.build_absolute_uri(article.cover.url) if article.cover else None,
            'notes': article.body,
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
