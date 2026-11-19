
from rest_framework import generics
from rest_framework.exceptions import ValidationError
from django.db import connection
from django.db.models import Count
import re
from .models import Category, Product
from .serializers import CategorySerializer, ProductSerializer
from .catalog_tags import rules_for

# Presentation groups leave the original categories and their product links intact.
CATEGORY_GROUPS = {
    'meat': ('Мясо',),
    'grocery': ('Бакалея', 'Крупы и бакалея'),
    'seafood': ('Морепродукты',),
    'dairy': ('Молочная продукция', 'Сыры'),
    'drinks': ('Вода', 'Безалкогольные напитки', 'Соки', 'Вода и напитки'),
}


class CategoryListView(generics.ListAPIView):
    serializer_class = CategorySerializer
    queryset = Category.objects.all()



from rest_framework.pagination import PageNumberPagination


class ProductPagination(PageNumberPagination):
    page_size = 24
    page_size_query_param = "page_size"
    max_page_size = 100

    def paginate_queryset(self, queryset, request, view=None):
        self.catalog_tags = getattr(view, 'catalog_tags', [])
        return super().paginate_queryset(queryset, request, view=view)

    def get_paginated_response(self, data):
        response = super().get_paginated_response(data)
        response.data['tags'] = self.catalog_tags
        return response

class ProductListView(generics.ListAPIView):
    serializer_class = ProductSerializer
    pagination_class = ProductPagination  

    def get_queryset(self):
        queryset = Product.objects.filter(
            is_active=True
        ).prefetch_related("categories")

        category_id = self.request.query_params.get("category")
        search = self.request.query_params.get("search")
        group = self.request.query_params.get('category_group')
        if group:
            if group not in CATEGORY_GROUPS:
                raise ValidationError({'category_group': 'Неизвестная группа категорий.'})
            queryset = queryset.filter(categories__name__in=CATEGORY_GROUPS[group])

        if category_id:
            if not re.fullmatch(r'[1-9][0-9]{0,9}', category_id):
                raise ValidationError({'category': 'Некорректная категория.'})
            queryset = queryset.filter(
                categories__id=category_id
            )

        category_name = (
            Category.objects.filter(pk=category_id).values_list('name', flat=True).first()
            if category_id else None
        )
        rules = rules_for((category_name or '') if category_id else None, group)
        # Keep the nonempty category chips stable while search/other filters
        # narrow the results. Distinct counts also handle multiple category links.
        counts = queryset.order_by().aggregate(**{
            f'tag_{index}': Count('pk', filter=rule.condition, distinct=True)
            for index, rule in enumerate(rules)
        }) if rules else {}
        self.catalog_tags = [
            {'slug': rule.slug, 'label': rule.label, 'count': counts[f'tag_{index}']}
            for index, rule in enumerate(rules) if counts[f'tag_{index}'] > 0
        ]
        tag = self.request.query_params.get('tag')
        if tag:
            rule = next((rule for rule in rules if rule.slug == tag), None)
            if rule is None:
                raise ValidationError({'tag': 'Тег не относится к выбранной категории.'})
            queryset = queryset.filter(rule.condition)

        if search:
            if len(search) > 120:
                raise ValidationError({'search': 'Введите не более 120 символов.'})
            # SQLite LIKE only folds ASCII. Django's escaped REGEXP supports
            # Cyrillic case-insensitive search without changing stored names.
            queryset = queryset.filter(**{'name__iregex' if connection.vendor == 'sqlite' else 'name__icontains': re.escape(search) if connection.vendor == 'sqlite' else search})

        unit = self.request.query_params.get('unit')
        if unit in {'kg', 'pcs'}:
            queryset = queryset.filter(unit=unit)
        if self.request.query_params.get('available') == '1':
            queryset = queryset.filter(is_available=True)
        collection = self.request.query_params.get('collection')
        if collection:
            queryset = queryset.filter(showcase_memberships__collection__slug=collection, showcase_memberships__collection__is_published=True)
        ordering = self.request.query_params.get('ordering', 'name')
        if ordering not in {'name', 'price', '-price'}:
            ordering = 'name'
        queryset = queryset.order_by(ordering, 'id')

        return queryset.distinct()
