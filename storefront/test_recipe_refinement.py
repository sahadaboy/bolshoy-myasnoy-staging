from decimal import Decimal
from importlib import import_module
from django.apps import apps
from django.test import TestCase
from shop.models import Product
from .models import Article, Ingredient, RecipeStep, PantryIngredient, IngredientAlternative


class RecipeRefinementTests(TestCase):
    def setUp(self):
        self.migration = import_module('storefront.migrations.0010_refine_existing_recipes')
        self.pasta = Product.objects.create(pk=1394, name='Мак изд Borges 500гр Спагетти', sku='pasta-500', price=234, unit='pcs')
        self.sauce = Product.objects.create(pk=2, name='Соус томатный', sku='sauce-unknown', price=145, unit='pcs')
        Product.objects.create(pk=2482, name='Соус Хэлиос 300гр ст томат с добав олив масла', sku='sauce-300', price=180, unit='pcs')
        Product.objects.create(pk=1393, name='Мак изд Borges 500гр Пенне Ригате', sku='penne-500', price=230, unit='pcs')
        self.article = Article.objects.create(pk=7, slug='pasta-tomato', title='Паста с томатным соусом',
            description=self.migration.RECIPES[0]['old_description'], servings=2, is_published=True, cover='storefront_uploads/ideas/owner-photo.webp')
        kind = PantryIngredient.objects.create(name='Паста', slug='pasta')
        self.first = Ingredient.objects.create(article=self.article,name='Макароны',product=self.pasta,ingredient_type=kind,recipe_quantity='.400',recipe_unit='pcs')
        self.second = Ingredient.objects.create(article=self.article,name='Томатный соус',product=self.sauce,ingredient_type=kind,recipe_quantity='.500',recipe_unit='pcs')
        for index,text in enumerate(self.migration.RECIPES[0]['original'],1):
            RecipeStep.objects.create(article=self.article,sort_order=index,text=text)

    def test_refinement_preserves_ids_prices_and_owner_photo_and_is_idempotent(self):
        products = list(Product.objects.order_by('pk').values())
        ids = list(self.article.steps.values_list('pk',flat=True))
        self.migration.refine(apps,None)
        self.first.refresh_from_db(); self.second.refresh_from_db(); self.article.refresh_from_db()
        self.assertEqual(self.first.amount_value,Decimal('200'))
        self.assertEqual(self.second.product_id,2482)
        self.assertEqual(list(self.article.steps.values_list('pk',flat=True))[:2],ids)
        self.assertEqual(self.article.cover.name,'storefront_uploads/ideas/owner-photo.webp')
        self.assertEqual(list(Product.objects.order_by('pk').values()),products)
        self.assertEqual(IngredientAlternative.objects.count(),1)
        self.assertEqual(self.article.steps.count(),4)
        self.migration.refine(apps,None)
        self.assertEqual(self.article.steps.count(),4)
        self.assertEqual(IngredientAlternative.objects.count(),1)

    def test_owner_edited_steps_are_not_overwritten(self):
        step=self.article.steps.first(); step.text='Рецепт владельца'; step.save()
        self.migration.refine(apps,None)
        self.first.refresh_from_db()
        self.assertIsNone(self.first.amount_value)
        self.assertEqual(self.article.steps.first().text,'Рецепт владельца')

    def test_different_catalogue_identity_never_gets_guessed_pack_conversion(self):
        Product.objects.filter(pk=2482).update(name='Другой соус неизвестной фасовки')
        self.migration.refine(apps,None)
        self.second.refresh_from_db()
        self.assertEqual(self.second.product_id,2)
        self.assertIsNone(self.second.amount_value)
