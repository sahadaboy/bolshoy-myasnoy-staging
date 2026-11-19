"""Refine only unchanged, identifiable seed recipes. Never edits catalogue rows.

Manually edited recipes are left intact. Empty installations are not populated.
Existing article, ingredient and step IDs are retained.
"""
from decimal import Decimal
from django.db import migrations


RECIPES = [
    {
        'slug': 'pasta-tomato', 'title': 'Паста с томатным соусом', 'minutes': 20,
        'description': 'Паста в мягком томатном соусе за 20 минут.',
        'old_description': 'Простой домашний ужин из двух основных ингредиентов.',
        'original': [
            'Отварите пасту по инструкции на упаковке. Сохраните немного воды от варки.',
            'Прогрейте томатный соус, добавьте пасту и немного отвара. Перемешайте и подавайте.'],
        # old product, old quantity, physical quantity, unit, pack, verified product
        'ingredients': [(1394, '.400', '200', 'g', '500', 1394), (2, '.500', '200', 'g', '300', 2482)],
        'steps': [
            'Вскипятите воду из расчёта около 1 л на каждые 100 г сухой пасты. Соль добавьте по вкусу, если используете её.',
            'Всыпьте отмеренную по списку ингредиентов пасту. Варите по инструкции на упаковке, помешивая в начале. Перед сливом сохраните немного отвара.',
            'В широкой сковороде прогрейте отмеренный томатный соус на слабом огне 3–4 минуты. Добавьте немного отвара, перемешайте.',
            'Переложите пасту в соус и прогрейте вместе 1–2 минуты. Если соус густой, добавляйте оставшийся отвар понемногу. Разложите по тарелкам.'],
        'notes': 'Вода для варки не входит в список покупок. Соус уже приправлен: попробуйте перед добавлением соли. При изменении порций количество воды для варки подбирайте по размеру кастрюли; количества основных ингредиентов пересчитываются автоматически.',
    },
    {
        'slug': 'spicy-pasta', 'title': 'Острая паста с аджикой', 'minutes': 20,
        'description': 'Паста с насыщенной аджикой для любителей острого.',
        'old_description': 'Для тех, кому хочется яркого вкуса без долгой готовки.',
        'original': [
            'Отварите пасту по инструкции на упаковке и сохраните немного отвара.',
            'Добавляйте аджику небольшими порциями, разбавляя отваром до желаемой насыщенности. Соедините с пастой.'],
        'ingredients': [(1394, '.400', '200', 'g', '500', 1394), (167, '.150', '20', 'g', '190', 167)],
        'steps': [
            'Вскипятите воду из расчёта около 1 л на каждые 100 г сухой пасты. Соль добавляйте осторожно: аджика уже солёная.',
            'Отварите отмеренную по списку пасту по инструкции на упаковке. Сохраните немного отвара, затем слейте воду.',
            'Разведите отмеренную аджику в сковороде несколькими ложками отвара. Прогрейте на слабом огне 1 минуту, не обжаривая насухо.',
            'Добавьте пасту, перемешайте и прогрейте ещё 1–2 минуты. При необходимости добавьте немного оставшегося отвара. Подавайте сразу.'],
        'notes': 'Это острое блюдо. Острота зависит от аджики: при необходимости используйте меньше указанного количества. Вода для варки не входит в покупки. Остаток открытой аджики храните по инструкции изготовителя.',
    },
    {
        'slug': 'rice-tuna-corn', 'title': 'Рис с тунцом и кукурузой', 'minutes': 30,
        'description': 'Рассыпчатый рис, тунец и сладкая кукуруза для сытного ужина.',
        'old_description': 'Сытное сочетание риса, консервированного тунца и сладкой кукурузы.',
        'original': [
            'Отварите рис до готовности по инструкции на упаковке.',
            'Слейте лишнюю жидкость из кукурузы. Разберите тунец вилкой, соедините с рисом и кукурузой, прогрейте и подавайте.'],
        'ingredients': [(83, '.160', '160', 'g', '1000', 83), (4338, '1.000', '1', 'can', '1', 4338), (1251, '.500', '.5', 'can', '1', 1251)],
        'steps': [
            'Промойте рис. Возьмите воду из расчёта 250 мл на каждые 100 г сухого риса, если изготовитель не указал другое соотношение. Доведите до кипения и варите под крышкой на слабом огне до мягкости и впитывания воды, обычно 20–25 минут.',
            'Слейте заливку из кукурузы и отмерьте количество из списка ингредиентов. Из тунца слейте большую часть масла, оставив немного для прогревания. Разберите рыбу вилкой.',
            'Положите тунец с оставленным маслом и кукурузу в сковороду. Прогревайте 2–3 минуты на слабом огне, аккуратно перемешивая.',
            'Соедините с готовым рисом, прогрейте ещё 1 минуту. Попробуйте и при необходимости посолите. Подавайте горячим.'],
        'notes': 'Количество риса указано в сухом виде. Одна банка тунца — 185 г, банка кукурузы — 425 г до сливания жидкости. Доли банок в составе блюда пересчитываются по порциям; для покупки нужны целые упаковки. Вода не добавляется в покупки. Остаток консервов переложите в закрытую ёмкость и храните по инструкции на упаковке.',
    },
    {
        'slug': 'buckwheat-mushrooms', 'title': 'Гречка с грибами', 'minutes': 25,
        'description': 'Гречка с консервированными грибами — простой горячий ужин.',
        'old_description': 'Горячая гречка с готовыми грибами — простой ужин без мяса.',
        'original': [
            'Отварите гречку до готовности по инструкции на упаковке.',
            'Слейте заливку из грибов, соедините их с горячей гречкой и прогрейте. Приправьте по своему вкусу.'],
        'ingredients': [(67, '.160', '160', 'g', '1000', 67), (428, '.500', '1', 'can', '1', 428)],
        'steps': [
            'Переберите и промойте гречку. Возьмите воду из расчёта 200 мл на каждые 100 г сухой крупы, доведите до кипения.',
            'Убавьте огонь и варите под крышкой 15–20 минут до впитывания воды. Снимите с огня и оставьте под крышкой на 5 минут.',
            'Из готовых консервированных грибов слейте заливку. Положите отмеренное количество в сковороду с небольшим количеством воды. Прогрейте под крышкой 3–4 минуты; это можно сделать, пока варится гречка.',
            'Соедините грибы с гречкой и перемешайте. Попробуйте перед добавлением соли. Подавайте горячим.'],
        'notes': 'Используются готовые консервированные шампиньоны с вешенками. Сырые или сушёные грибы требуют другой подготовки и автоматически не заменяются. Вода для варки не входит в покупки.',
    },
]


def refine(apps, schema_editor):
    db = schema_editor.connection.alias if schema_editor else 'default'
    Store = apps.get_model('storefront', 'StoreProfile').objects.using(db)
    Store.filter(name='Большой Мясной').update(name='Большой Мясной Маркет')
    Store.filter(instagram_url='').update(instagram_url='https://www.instagram.com/bm_sev/')
    Article = apps.get_model('storefront', 'Article').objects.using(db)
    Ingredient = apps.get_model('storefront', 'Ingredient').objects.using(db)
    Step = apps.get_model('storefront', 'RecipeStep').objects.using(db)
    Product = apps.get_model('shop', 'Product').objects.using(db)
    Alternative = apps.get_model('storefront', 'IngredientAlternative').objects.using(db)
    # Verify exact catalogue identities before changing a recipe link. No guesses by title similarity.
    identities = {1394: ('Мак изд Borges 500гр Спагетти', 'pcs'),
        1393: ('Мак изд Borges 500гр Пенне Ригате', 'pcs'),
        2482: ('Соус Хэлиос 300гр ст томат с добав олив масла', 'pcs'),
        167: ('Аджика Махеевъ 190гр ст Острая', 'pcs'),
        83: ('Крупа кг Рис длиннозерн пропар рк', 'kg'),
        4338: ('Тунец 5 Морей 185гр руб в масле', 'pcs'),
        1251: ('Кукуруза Green Ray 425гр жб сладкая', 'pcs'),
        67: ('Крупа кг Гречневая КК', 'kg'),
        428: ('Грибы Baleno 425мл жб Шампиньоны с вешенками резаные', 'pcs')}
    verified = {pk for pk, (name, unit) in identities.items()
                if Product.filter(pk=pk, name=name, unit=unit).exists()}
    for recipe in RECIPES:
        article = Article.filter(slug=recipe['slug'], title=recipe['title'], kind='recipe', is_demo=False, servings=2).first()
        if not article or article.body or article.description != recipe['old_description']:
            continue
        ingredients = list(Ingredient.filter(article=article).order_by('sort_order', 'pk'))
        steps = list(Step.filter(article=article).order_by('sort_order', 'pk'))
        old = recipe['ingredients']
        if ([step.text for step in steps] != recipe['original'] or len(ingredients) != len(old)
                or any(item.product_id != row[0] or item.recipe_quantity != Decimal(row[1])
                       or item.amount_value is not None or row[5] not in verified
                       for item, row in zip(ingredients, old))):
            continue
        article.description, article.body, article.duration_minutes = recipe['description'], recipe['notes'], recipe['minutes']
        article.save(using=db, update_fields=['description', 'body', 'duration_minutes'])
        for item, row in zip(ingredients, old):
            _, _, amount, unit, pack, product_id = row
            item.product_id, item.amount_value, item.amount_unit, item.pack_size = product_id, Decimal(amount), unit, Decimal(pack)
            item.recipe_quantity = (item.amount_value / item.pack_size).quantize(Decimal('.001'))
            item.amount = f'{amount} ' + {'g': 'г', 'can': 'банки'}[unit]
            item.save(using=db, update_fields=['product', 'amount_value', 'amount_unit', 'pack_size', 'recipe_quantity', 'amount'])
            if product_id == 1394 and 1393 in verified:
                Alternative.get_or_create(ingredient=item, product_id=1393,
                    defaults={'pack_size': Decimal('500'), 'sale_unit': 'pcs', 'is_active': True})
        for index, text in enumerate(recipe['steps']):
            if index < len(steps):
                steps[index].text = text
                steps[index].save(using=db, update_fields=['text'])
            else:
                Step.create(article=article, sort_order=index + 1, text=text)

    Question = apps.get_model('storefront', 'DinnerQuestion').objects.using(db)
    Option = apps.get_model('storefront', 'DinnerOption').objects.using(db)
    if Question.filter(key='pantry').exists():
        question, created = Question.get_or_create(key='time', defaults={
            'title': 'Сколько времени есть на готовку?', 'sort_order': 70, 'required': False})
        if created:
            for index, (value, label, limit) in enumerate([
                ('15', 'До 15 минут', 15), ('30', 'До 30 минут', 30),
                ('45', 'До 45 минут', 45), ('any', 'Не тороплюсь', None)]):
                Option.create(question=question, value=value, label=label,
                    max_minutes=limit, is_any=limit is None, sort_order=index)
    # Only replace the original seed wording. Owner-customized questions are preserved.
    wording = [
        ('pantry', 'Что уже есть дома?', 'Что уже есть дома?', 10),
        ('dish', 'Что хочется приготовить?', 'Что приготовим сегодня?', 20),
        ('servings', 'На сколько персон?', 'На сколько человек готовим?', 30),
        ('spice', 'Как насчёт острого?', 'Как насчёт острого?', 40),
        ('preferences', 'Есть пожелания к ужину?', 'Что вам ближе?', 50),
        ('exclude', 'Что исключить?', 'Что точно не добавляем?', 60)]
    for key, old, new, order in wording:
        Question.filter(key=key, title=old).update(title=new, sort_order=order)


class Migration(migrations.Migration):
    dependencies = [('storefront', '0009_dinner_measures_and_order_labels')]
    operations = [migrations.RunPython(refine, migrations.RunPython.noop)]
