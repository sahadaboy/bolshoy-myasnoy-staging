from django.conf import settings
from django.core.files import File
from django.core.management.base import BaseCommand
from django.db import transaction
from storefront.models import Article, ArticleMember, IdeaCategory, Ingredient, RecipeStep


RECIPES = [
    dict(slug='demo-pesto', title='Паста с песто', description='Базилик, сыр и любимая паста', cover='pasta', body='Простой домашний обед с зелёным соусом. Это демонстрационный рецепт, который редактор магазина может использовать как образец.', ingredients=[('Паста', '250 г'), ('Песто', '3 ст. л.'), ('Твёрдый сыр', '40 г'), ('Свежий базилик', 'для подачи')], steps=['Отварите пасту в подсоленной воде по инструкции на упаковке. Перед тем как слить воду, сохраните небольшую чашку отвара.', 'Соедините горячую пасту с песто в миске. Понемногу подливайте отвар и перемешивайте, пока соус не покроет пасту.', 'Добавьте тёртый сыр, украсьте базиликом и сразу подавайте.']),
    dict(slug='demo-salad', title='Больше свежести', description='Салат с нутом и авокадо', cover='salad', body='Овощи, зелень и нут: лёгкое блюдо само по себе или дополнение к мясу.', breakfast=True, ingredients=[('Нут отварной', '150 г'), ('Авокадо', '1 шт.'), ('Помидоры черри', '150 г'), ('Морковь', '1 шт.'), ('Салатные листья', '1 горсть'), ('Оливковое масло', '2 ст. л.'), ('Лимонный сок', '1 ст. л.')], steps=['Промойте овощи и салатные листья. Обсушите листья, нарежьте помидоры, морковь и авокадо.', 'Смешайте оливковое масло и лимонный сок. Добавьте соль по вкусу.', 'Разложите овощи, нут и зелень в миске. Заправьте непосредственно перед подачей.']),
    dict(slug='demo-sunday', title='Воскресный обед', description='Курица из духовки, овощи и любимые гарниры', cover='family-dinner', body='Большое общее блюдо для семейного стола. Время зависит от размера птицы: готовность проверяют термометром.', featured=True, ingredients=[('Целая курица', '1 шт.'), ('Картофель', '600 г'), ('Сладкий перец', '2 шт.'), ('Чеснок', '4 зубчика'), ('Растительное масло', '3 ст. л.'), ('Травы и соль', 'по вкусу')], steps=['Разогрейте духовку до 180 °C. Вымойте овощи, нарежьте крупными кусками, смешайте с частью масла, травами и солью.', 'Обсушите курицу бумажным полотенцем. Натрите оставшимся маслом, солью и травами, положите в форму, рядом разложите овощи.', 'Запекайте до полной готовности. Проверьте пищевым термометром, что в самой толстой части грудки и бедра достигнуто не менее 74 °C; щуп не должен касаться кости.', 'Дайте птице немного отдохнуть, разделите на порции и подавайте с овощами.']),
]


class Command(BaseCommand):
    help = 'Создать шесть явно демонстрационных материалов, без публикации и без привязки случайных товаров.'

    @transaction.atomic
    def handle(self, *args, **options):
        category, _ = IdeaCategory.objects.get_or_create(slug='home', defaults={'name': 'Готовим дома'})
        recipes = []
        for index, data in enumerate(RECIPES):
            article, created = Article.objects.get_or_create(slug=data['slug'], defaults={'title': data['title'], 'description': data['description'], 'body': data['body'], 'kind': 'recipe', 'category': category, 'is_demo': True, 'is_featured': data.get('featured', False), 'breakfast': data.get('breakfast', False), 'sort_order': 10 + index})
            if created:
                self.cover(article, data['cover'])
                Ingredient.objects.bulk_create([Ingredient(article=article, name=name, amount=quantity, sort_order=i) for i, (name, quantity) in enumerate(data['ingredients'])])
                RecipeStep.objects.bulk_create([RecipeStep(article=article, sort_order=i + 1, text=text) for i, text in enumerate(data['steps'])])
            recipes.append(article)
        for index, (slug, title, description, image, members) in enumerate([
            ('demo-pasta-and-sauce', 'Паста и соусы', 'Простые сочетания на каждый день', 'pasta', [0]),
            ('demo-salads', 'Салаты к мясу', 'Овощи, зелень и лёгкие заправки', 'salad', [1]),
            ('demo-slow-dinner', 'Ужин без спешки', 'Любимые блюда для уютного вечера', 'carbonara', [2, 0, 1]),
        ]):
            article, created = Article.objects.get_or_create(slug=slug, defaults={'title': title, 'description': description, 'kind': 'collection', 'is_topic': True, 'is_demo': True, 'sort_order': index, 'category': category})
            if created:
                self.cover(article, image)
                ArticleMember.objects.bulk_create([ArticleMember(collection=article, recipe=recipes[i], sort_order=position) for position, i in enumerate(members)])
        self.stdout.write(self.style.SUCCESS('Демо-материалы созданы отдельно от публикаций магазина.'))

    def cover(self, article, name):
        path = settings.BASE_DIR / 'frontend/public/preview' / f'{name}.webp'
        if path.is_file():
            with path.open('rb') as image:
                article.cover.save(f'{article.slug}.webp', File(image), save=True)
