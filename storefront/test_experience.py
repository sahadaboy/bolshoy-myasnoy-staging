from decimal import Decimal
from io import BytesIO
from pathlib import Path
import tempfile
from django.contrib import admin
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.urls import reverse
from PIL import Image
from rest_framework.test import APIClient
from shop.models import Product
from .models import (StoreProfile, StorePhoto, ProductCollection, ProductCollectionItem, Article, Ingredient,
    RecipeStep, DinnerSettings, DinnerQuestion, DinnerOption, DinnerRecipe, PantryIngredient)


class DinnerFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.settings = DinnerSettings.objects.create()
        for index, key in enumerate(('pantry', 'dish', 'spice', 'servings', 'preferences', 'exclude')):
            DinnerQuestion.objects.create(key=key, title=key, sort_order=index)
        self.mild = DinnerOption.objects.create(question=DinnerQuestion.objects.get(key='spice'), label='Неострое', value='mild')
        self.quick = DinnerOption.objects.create(question=DinnerQuestion.objects.get(key='preferences'), label='Быстро', value='quick')
        self.pasta_type = PantryIngredient.objects.create(name='Макароны', slug='pasta')
        self.rice_type = PantryIngredient.objects.create(name='Рис', slug='rice')
        self.pasta = Product.objects.create(name='Макароны 500 г', sku='pasta', price='100', unit='pcs', min_quantity='1', quantity_step='1')
        self.rice = Product.objects.create(name='Рис весовой', sku='rice', price='200', unit='kg', min_quantity='.5', quantity_step='.1')
        self.article = Article.objects.create(title='Ужин', slug='dinner', servings=2, is_published=True)
        self.rule = DinnerRecipe.objects.create(article=self.article, is_active=True)
        self.rule.options.add(self.mild, self.quick)
        self.pasta_ingredient = Ingredient.objects.create(article=self.article, name='Макароны', product=self.pasta,
            ingredient_type=self.pasta_type, recipe_quantity='.400', recipe_unit='pcs')
        self.rice_ingredient = Ingredient.objects.create(article=self.article, name='Рис', product=self.rice,
            ingredient_type=self.rice_type, recipe_quantity='.100', recipe_unit='kg')
        RecipeStep.objects.create(article=self.article, text='Приготовьте по инструкции на упаковке.')

    def payload(self, **kwargs):
        return {'servings': 2, 'pantry': [], 'exclude': [], 'answers': {}, **kwargs}

    def suggest(self, **kwargs):
        return self.client.post('/api/dinner/suggestions/', self.payload(**kwargs), format='json')

    def test_questions_are_editable_ordered_and_hidden_options_are_not_public(self):
        question = DinnerQuestion.objects.get(key='spice')
        question.title, question.sort_order = 'Любите острое?', 0
        question.save()
        DinnerOption.objects.create(question=question, label='Скрытый ответ', value='hidden', is_active=False)
        data = self.client.get('/api/dinner/schema/').data
        self.assertEqual(len(data['questions']), 6)
        self.assertEqual(next(item for item in data['questions'] if item['key'] == 'spice')['title'], 'Любите острое?')
        self.assertEqual(len(next(item for item in data['questions'] if item['key'] == 'spice')['options']), 1)
        self.assertEqual({item['id'] for item in data['ingredients']}, {self.pasta_type.pk, self.rice_type.pk})

    def test_servings_scale_and_round_up_for_weight_and_whole_packs(self):
        response = self.suggest(servings=12)
        self.assertEqual(response.status_code, 200, response.data)
        result = response.data['results'][0]
        quantities = {item['product']['id']: item['quantity'] for item in result['shopping']}
        self.assertEqual(quantities, {self.pasta.pk: '3.000', self.rice.pk: '0.600'})
        self.assertEqual(result['total'], '420.00')
        self.assertEqual(result['ingredients'][1]['amount'], '600 г')

    def test_products_at_home_are_marked_and_not_added_to_shopping(self):
        result = self.suggest(pantry=[self.pasta_type.pk]).data['results'][0]
        self.assertTrue(result['ingredients'][0]['have'])
        self.assertEqual([item['product']['id'] for item in result['shopping']], [self.rice.pk])

    def test_exclusions_take_precedence_even_for_ingredients_at_home(self):
        self.assertEqual(self.suggest(pantry=[self.pasta_type.pk], exclude=[self.pasta_type.pk]).data['results'], [])

    def test_unavailable_required_products_are_not_replaced_with_similar_products(self):
        Product.objects.create(name=self.pasta.name, sku='similar-pasta', price=1)
        self.pasta.is_available = False; self.pasta.save()
        self.assertEqual(self.suggest().data['results'], [])
        self.assertEqual(len(self.suggest(pantry=[self.pasta_type.pk]).data['results']), 1)
        self.pasta.is_active = False; self.pasta.save()
        self.assertEqual(self.suggest().data['results'], [])

    def test_unknown_required_ingredient_can_only_be_used_if_it_is_already_at_home(self):
        self.pasta_ingredient.product = None; self.pasta_ingredient.save()
        self.assertEqual(self.suggest().data['results'], [])
        self.assertEqual(len(self.suggest(pantry=[self.pasta_type.pk]).data['results']), 1)

    def test_unit_change_blocks_recipe_until_its_quantity_is_reviewed(self):
        self.pasta.unit = 'kg'; self.pasta.save()
        self.assertEqual(self.suggest().data['results'], [])
        self.assertIsNone(self.client.get('/api/ideas/dinner/').data['ingredients'][0]['cart_quantity'])
        owned = self.suggest(pantry=[self.pasta_type.pk]).data['results'][0]
        self.assertEqual(owned['ingredients'][0]['amount'], '0,4 упак.')

    def test_optional_unavailable_ingredient_is_never_added_as_a_product(self):
        self.pasta.is_available = False; self.pasta.save()
        self.pasta_ingredient.is_optional = True; self.pasta_ingredient.save()
        result = self.suggest().data['results'][0]
        self.assertEqual(result['ingredients'][0]['status'], 'optional_unavailable')
        self.assertEqual([item['product']['id'] for item in result['shopping']], [self.rice.pk])

    def test_preferences_and_spice_use_only_explicit_recipe_rules(self):
        response = self.suggest(answers={'spice': [self.mild.pk], 'preferences': [self.quick.pk]})
        self.assertEqual(len(response.data['results']), 1)
        hot = DinnerOption.objects.create(question=self.mild.question, label='Острое', value='hot')
        self.assertEqual(self.suggest(answers={'spice': [hot.pk]}).data['results'], [])
        self.rule.options.add(hot)
        self.assertEqual(self.suggest(answers={'spice': [self.mild.pk]}).data['results'], [])

    def test_multiple_matching_ideas_are_returned_with_owned_ingredients_prioritized(self):
        second = Article.objects.create(title='Другой ужин', slug='second', servings=2, is_published=True)
        DinnerRecipe.objects.create(article=second, is_active=True, sort_order=0)
        Ingredient.objects.create(article=second, name='Макароны', product=self.pasta, ingredient_type=self.pasta_type,
                                  recipe_quantity='1', recipe_unit='pcs')
        data = self.suggest().data['results']
        self.assertEqual(len(data), 2)
        self.assertEqual([item['title'] for item in data], ['Ужин', 'Другой ужин'])

    def test_invalid_or_hidden_answers_and_too_many_servings_are_rejected(self):
        for fields in ({'servings': 13}, {'pantry': [99999]}, {'answers': {'unknown': [1]}},
                       {'answers': {'spice': [99999]}}, {'servings': 0}):
            self.assertEqual(self.suggest(**fields).status_code, 400)
        self.mild.is_active = False; self.mild.save()
        self.assertEqual(self.suggest(answers={'spice': [self.mild.pk]}).status_code, 400)

    def test_required_question_and_disabled_planner_are_enforced_on_server(self):
        question = self.mild.question
        question.required = True; question.save()
        self.assertEqual(self.suggest().status_code, 400)
        self.settings.is_active = False; self.settings.save()
        self.assertEqual(self.client.get('/api/dinner/schema/').status_code, 404)
        self.assertEqual(self.suggest().status_code, 404)

    def preparation(self, items=None):
        return self.payload(recipe_id=self.rule.pk, items=items if items is not None else [
            {'product_id': self.pasta.pk, 'quantity': '2', 'expected_price': '100'},
            {'product_id': self.rice.pk, 'quantity': '.7', 'expected_price': '200'}])

    def test_edited_shopping_list_is_validated_and_current_prices_are_returned(self):
        self.rice.price = Decimal('250'); self.rice.save()
        response = self.client.post('/api/dinner/prepare/', self.preparation(), format='json')
        self.assertEqual(response.status_code, 200, response.data)
        self.assertTrue(response.data['prices_changed'])
        self.assertEqual(response.data['total'], '375.00')
        self.assertEqual(response.data['items'][1]['product']['price'], '250.00')
        self.assertEqual(response.data['items'][1]['quantity'], '0.700')
        self.assertEqual(Product.objects.get(pk=self.pasta.pk).price, Decimal('100'))

    def test_prepare_rejects_duplicates_foreign_products_and_invalid_quantities(self):
        for items in ([{'product_id': self.pasta.pk, 'quantity': '1.5', 'expected_price': '100'}],
                      [{'product_id': 99999, 'quantity': '1', 'expected_price': '1'}],
                      [{'product_id': self.pasta.pk, 'quantity': '1', 'expected_price': '100'}] * 2):
            self.assertIn(self.client.post('/api/dinner/prepare/', self.preparation(items), format='json').status_code, (400, 409))

    def test_prepare_rechecks_stock_publication_and_recipe_rules(self):
        self.pasta.is_available = False; self.pasta.save()
        self.assertEqual(self.client.post('/api/dinner/prepare/', self.preparation(), format='json').status_code, 409)
        self.pasta.is_available = True; self.pasta.save()
        self.article.is_published = False; self.article.save()
        self.assertEqual(self.client.post('/api/dinner/prepare/', self.preparation(), format='json').status_code, 409)

    def test_physical_recipe_measures_scale_without_fractional_pack_display_or_rounding_down(self):
        item = self.pasta_ingredient
        item.amount_value, item.amount_unit, item.pack_size = Decimal('200'), 'g', Decimal('500')
        item.save()
        result = self.suggest(servings=6).data['results'][0]
        self.assertEqual(result['ingredients'][0]['amount'], '600 г')
        self.assertEqual(result['shopping'][0]['quantity'], '2.000')
        detail = self.client.get('/api/ideas/dinner/').data['ingredients'][0]
        self.assertEqual(detail['amount'], '200 г')
        self.assertEqual(detail['cart_quantity'], '1')

    def test_time_limit_requires_known_recipe_duration_and_is_not_a_recipe_tag(self):
        question = DinnerQuestion.objects.create(key='time', title='Время')
        limit = DinnerOption.objects.create(question=question, label='30 минут', value='30', max_minutes=30)
        self.assertEqual(self.suggest(answers={'time':[limit.pk]}).data['results'], [])
        self.article.duration_minutes = 30; self.article.save()
        self.assertEqual(len(self.suggest(answers={'time':[limit.pk]}).data['results']), 1)
        self.article.duration_minutes = 31; self.article.save()
        self.assertEqual(self.suggest(answers={'time':[limit.pk]}).data['results'], [])

    def test_only_reviewed_replacement_can_be_selected_and_prepared(self):
        from .models import IngredientAlternative
        item = self.pasta_ingredient
        item.amount_value, item.amount_unit, item.pack_size = Decimal('200'), 'g', Decimal('500')
        item.save()
        smaller = Product.objects.create(name='Другая паста 250 г', sku='reviewed', price='70', unit='pcs')
        option = IngredientAlternative.objects.create(ingredient=item, product=smaller, pack_size=250, sale_unit='pcs', is_active=True)
        replacements = {str(item.pk):option.pk}
        result = self.suggest(recipe_id=self.rule.pk, replacements=replacements, servings=6)
        self.assertEqual(result.status_code,200,result.data)
        idea = result.data['results'][0]
        self.assertEqual(idea['shopping'][0]['product']['id'], smaller.pk)
        self.assertEqual(idea['shopping'][0]['quantity'], '3.000')
        prepared = self.client.post('/api/dinner/prepare/', self.payload(recipe_id=self.rule.pk, servings=6, replacements=replacements,
            items=[{'product_id':smaller.pk,'quantity':'3','expected_price':'70'}]),format='json')
        self.assertEqual(prepared.status_code,200,prepared.data)
        self.assertEqual(self.suggest(recipe_id=self.rule.pk, replacements={str(item.pk):99999}).status_code,409)
        self.assertEqual(self.suggest(recipe_id=self.rule.pk, replacements={'99999':option.pk}).status_code,400)
        smaller.is_available=False; smaller.save()
        self.assertEqual(self.suggest(recipe_id=self.rule.pk,replacements=replacements).status_code,409)

    def test_physical_conversion_is_blocked_when_catalogue_sales_unit_changes(self):
        item = self.pasta_ingredient
        item.amount_value, item.amount_unit, item.pack_size = Decimal('200'), 'g', Decimal('500')
        item.save()
        self.pasta.unit='kg'; self.pasta.save()
        self.assertEqual(self.suggest().data['results'], [])
        self.assertIsNone(self.client.get('/api/ideas/dinner/').data['ingredients'][0]['cart_quantity'])


class StoreAndShowcaseTests(TestCase):
    def test_real_store_photos_are_ordered_visibility_controlled_and_optimized(self):
        with tempfile.TemporaryDirectory() as folder, override_settings(MEDIA_ROOT=folder):
            store = StoreProfile.objects.create(phone='+79786544777', opening_hours='Среда: 08:00–19:00')
            output = BytesIO(); Image.new('RGB', (2000, 1500), '#abcdef').save(output, 'PNG')
            first = StorePhoto.objects.create(store=store, image=ContentFile(output.getvalue(), name='first.png'), sort_order=20)
            second = StorePhoto.objects.create(store=store, image=ContentFile(output.getvalue(), name='second.png'), sort_order=10)
            StorePhoto.objects.create(store=store, image=ContentFile(output.getvalue(), name='hidden.png'), is_active=False)
            response = self.client.get('/api/store/').data
            self.assertEqual([item['id'] for item in response['photos']], [second.pk, first.pk])
            with Image.open(Path(folder) / first.image.name) as photo:
                self.assertEqual(photo.format, 'WEBP')
                self.assertLessEqual(photo.width, 1600)
            self.assertEqual(self.client.get('/api/session/').data['store']['phone'], '+79786544777')

    def test_showcases_are_curated_sorted_limited_and_never_include_hidden_products(self):
        for index in range(2):
            collection = ProductCollection.objects.create(title=f'Витрина {index}', slug=f'c{index}', sort_order=10-index, is_published=True, home_limit=1)
            for item in range(2):
                product = Product.objects.create(name=f'Товар {index}/{item}', sku=f'{index}-{item}', price=100)
                ProductCollectionItem.objects.create(collection=collection, product=product, sort_order=item)
        hidden = ProductCollection.objects.create(title='Не видно', slug='hidden', is_published=False)
        data = self.client.get('/api/storefront/').data['collections']
        self.assertEqual([item['title'] for item in data], ['Витрина 1', 'Витрина 0'])
        self.assertTrue(all(len(item['products']) == 1 for item in data))
        Product.objects.update(is_available=False)
        self.assertEqual(self.client.get('/api/storefront/').data['collections'], [])

    def test_seed_is_idempotent_and_preserves_manual_settings_and_product_fields(self):
        product = Product.objects.create(pk=1394, name='Макароны', sku='keep-sku', price=100, description='Ручное описание')
        before = list(Product.objects.values())
        call_command('configure_shopping_scenarios', verbosity=0)
        collection = ProductCollection.objects.get(slug='home-breakfast')
        collection.title, collection.is_published = 'Ручная витрина', False
        collection.save()
        call_command('configure_shopping_scenarios', verbosity=0)
        self.assertEqual(ProductCollection.objects.count(), 6)
        self.assertEqual(list(Product.objects.values()), before)
        collection.refresh_from_db()
        self.assertEqual((collection.title, collection.is_published), ('Ручная витрина', False))

    def test_experience_admin_is_available_to_existing_admin_and_not_unprivileged_staff(self):
        user = get_user_model().objects.create_superuser('experience-admin', password='test-only')
        self.client.force_login(user)
        for name in ('storeprofile', 'storephoto', 'dinnersettings', 'dinnerquestion', 'dinneroption', 'dinnerrecipe', 'pantryingredient'):
            self.assertEqual(self.client.get(reverse(f'admin:storefront_{name}_changelist')).status_code, 200)
        staff = get_user_model().objects.create_user('no-permissions', is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get(reverse('admin:storefront_storephoto_add')).status_code, 403)
