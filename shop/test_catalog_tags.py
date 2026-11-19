from decimal import Decimal
from urllib.parse import urlsplit, parse_qs
from django.test import TestCase
from .models import Category, Product


class CatalogTagTests(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.grocery = Category.objects.create(name='Бакалея')
        cls.dairy = Category.objects.create(name='Молочная продукция')
        cls.seafood = Category.objects.create(name='Морепродукты')
        cls.cheese = Category.objects.create(name='Сыры')
        cls.frozen = Category.objects.create(name='Рыба свежемороженая')
        cls.meat = Category.objects.create(name='Мясо')
        cls.counter = 0
        cls.rice = cls.add('КРУПА кг РИС длиннозерный', cls.grocery, price='90', unit='kg')
        cls.add('Рис для суши', cls.grocery, price='150')
        cls.add('Рис Басмати', cls.grocery, price='120', is_available=False)
        cls.add('Хлопья овсяные', cls.grocery)
        cls.add('Печенье овсяное', cls.grocery)
        cls.add('Мак изд Borges 500гр Спагетти', cls.grocery)
        cls.add('Крупа кг Гречневая', cls.grocery)
        cls.add('Крупа кг Манная', cls.grocery)
        cls.add('Молоко 3,2%', cls.dairy)
        cls.add('Молоко сгущённое', cls.dairy)
        cls.add('Сметана 20%', cls.dairy)
        cls.add('Сухарики со сметаной', cls.dairy)
        cls.add('Биойогурт натуральный', cls.dairy)
        cls.add('Сыр из козьего молока', cls.cheese)
        cls.add('Сметана из отдельной категории', cls.cheese)
        cls.add('КРЕВЕТКА в панировке', cls.seafood)
        cls.add('Арахис со вкусом креветки', cls.seafood)
        cls.add('Мидии в масле', cls.seafood)
        cls.add('Кальмар рубленый', cls.seafood)
        cls.add('Икра мойвы с креветкой', cls.seafood)
        cls.add('Креветка аргентинская', cls.frozen)

    @classmethod
    def add(cls, name, category, **fields):
        cls.counter += 1
        row = Product.objects.create(name=name, sku=f'tag-{cls.counter}', **{'price':'100', **fields})
        row.categories.add(category)
        return row

    def get(self, **filters):
        return self.client.get('/api/products/', filters)

    def test_tags_have_real_products_and_do_not_change_catalogue_records(self):
        before = list(Product.objects.order_by('pk').values())
        data = self.get(category=self.grocery.pk).json()
        tags = {tag['slug']:tag for tag in data['tags']}
        self.assertEqual(tags['rice']['count'],3)
        self.assertEqual(tags['buckwheat']['count'],1)
        self.assertEqual(tags['oats']['count'],1)
        self.assertNotIn('bulgur',tags)
        self.assertTrue(all(tag['count'] > 0 for tag in data['tags']))
        self.assertEqual(list(Product.objects.order_by('pk').values()),before)

    def test_tag_composes_with_search_unit_availability_and_server_ordering(self):
        data = self.get(category=self.grocery.pk,tag='rice',search='рис',unit='kg',available='1',ordering='-price').json()
        self.assertEqual(data['count'],1)
        self.assertEqual(data['results'][0]['id'],self.rice.pk)
        self.assertEqual(self.get(category=self.grocery.pk,tag='rice',search='овся').json()['count'],0)

    def test_pagination_preserves_tag_scope_search_order_and_has_no_duplicates(self):
        another = Category.objects.create(name='Крупы и бакалея')
        self.rice.categories.add(another)
        first = self.get(category_group='grocery',tag='rice',search='рис',ordering='price',page_size=2).json()
        self.assertEqual(first['count'],3)
        self.assertEqual(len(first['results']),2)
        self.assertTrue(first['next'])
        params = parse_qs(urlsplit(first['next']).query)
        self.assertEqual(params['tag'],['rice'])
        self.assertEqual(params['category_group'],['grocery'])
        self.assertEqual(params['search'],['рис'])
        second = self.client.get(first['next']).json()
        self.assertEqual(len(second['results']),1)
        self.assertEqual(len({row['id'] for row in first['results']+second['results']}),3)
        self.assertEqual([Decimal(row['price']) for row in first['results']+second['results']],sorted(Decimal(row['price']) for row in first['results']+second['results']))

    def test_product_type_not_incidental_flavour_or_other_original_category(self):
        dairy = self.get(category=self.dairy.pk,tag='sour-cream').json()
        self.assertEqual([row['name'] for row in dairy['results']],['Сметана 20%'])
        milk = self.get(category=self.dairy.pk,tag='milk').json()
        self.assertEqual([row['name'] for row in milk['results']],['Молоко 3,2%'])
        shrimp = self.get(category_group='seafood',tag='shrimp').json()
        self.assertEqual(shrimp['count'],1)
        self.assertEqual(shrimp['results'][0]['name'],'КРЕВЕТКА в панировке')
        self.assertEqual(self.get(category=self.dairy.pk,tag='yogurt').json()['count'],1)

    def test_no_tags_in_meat_or_cheese_and_foreign_tags_are_rejected(self):
        self.assertEqual(self.get(category=self.meat.pk).json()['tags'],[])
        self.assertEqual(self.get(category=self.cheese.pk).json()['tags'],[])
        for filters in ({'tag':'rice'},{'category_group':'grocery','tag':'milk'},
                        {'category':self.meat.pk,'tag':'rice'},
                        {'category':self.cheese.pk,'category_group':'dairy','tag':'milk'}):
            self.assertEqual(self.get(**filters).status_code,400)

    def test_all_ignores_tag_and_inactive_products_are_not_tagged(self):
        self.rice.is_active=False; self.rice.save()
        filtered = self.get(category=self.grocery.pk,tag='rice').json()
        self.assertEqual(filtered['count'],2)
        self.assertGreater(self.get(category=self.grocery.pk).json()['count'],filtered['count'])
        self.assertEqual(next(tag for tag in filtered['tags'] if tag['slug']=='rice')['count'],2)
