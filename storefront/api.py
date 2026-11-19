from django.db.models import Prefetch
from rest_framework import generics, serializers
from rest_framework.response import Response
from rest_framework.views import APIView
from shop.models import Category, Product
from shop.serializers import ProductSerializer
from .models import Banner, CategoryImage, ProductCollection, ProductCollectionItem
from django.conf import settings
from django.db.models import Q
from .models import Article, Ingredient, IdeaCategory, DinnerSettings
from .quantities import valid_quantity


class BannerSerializer(serializers.ModelSerializer):
    target_url = serializers.CharField(read_only=True)
    class Meta:
        model = Banner
        fields = ['id', 'image', 'alt_text', 'sort_order', 'target_type', 'target_id', 'target_url']


class CategorySerializer(serializers.ModelSerializer):
    image = serializers.SerializerMethodField()
    class Meta:
        model = Category
        fields = ['id', 'name', 'image']

    def get_image(self, obj):
        image = self.context['images'].get(obj.pk)
        return self.context['request'].build_absolute_uri(image.image.url) if image and image.image else None


class CategoryListView(generics.ListAPIView):
    serializer_class = CategorySerializer
    pagination_class = None
    queryset = Category.objects.all()

    def get_serializer_context(self):
        return {**super().get_serializer_context(), 'images': {row.category_id: row for row in CategoryImage.objects.all()}}


class BannerListView(generics.ListAPIView):
    serializer_class = BannerSerializer
    pagination_class = None
    queryset = Banner.objects.filter(is_active=True).exclude(image='')


class CollectionSerializer(serializers.ModelSerializer):
    products = serializers.SerializerMethodField()
    class Meta:
        model = ProductCollection
        fields = ['id', 'title', 'slug', 'description', 'products']

    def get_products(self, obj):
        return ProductSerializer([item.product for item in obj.live_items[:obj.home_limit]], many=True, context=self.context).data


class StorefrontView(APIView):
    def get(self, request):
        items = ProductCollectionItem.objects.filter(product__is_active=True, product__is_available=True).select_related('product').prefetch_related('product__categories')[:8]
        collections = ProductCollection.objects.filter(is_published=True,
            items__product__is_active=True, items__product__is_available=True).distinct().prefetch_related(
                Prefetch('items', queryset=items, to_attr='live_items'))[:12]
        return Response({'banners': BannerSerializer(BannerListView.queryset.all(), many=True, context={'request': request}).data,
                         'collections': CollectionSerializer(collections, many=True, context={'request': request}).data,
                         'dinner_enabled': DinnerSettings.objects.filter(pk=1, is_active=True).exists()})


class ProductDetailView(generics.RetrieveAPIView):
    serializer_class = ProductSerializer
    queryset = Product.objects.filter(is_active=True).prefetch_related('categories')


class ArticleCardSerializer(serializers.ModelSerializer):
    image = serializers.ImageField(source='cover', read_only=True)
    meals = serializers.ListField(read_only=True)
    category = serializers.CharField(source='category.name', read_only=True, default='')

    class Meta:
        model = Article
        fields = ['id', 'slug', 'title', 'kind', 'image', 'description', 'category', 'meals', 'duration_minutes', 'servings', 'is_demo', 'is_topic', 'is_featured']


class IngredientSerializer(serializers.ModelSerializer):
    product = serializers.SerializerMethodField()
    cart_quantity = serializers.SerializerMethodField()
    amount = serializers.SerializerMethodField()

    class Meta:
        model = Ingredient
        fields = ['id', 'name', 'amount', 'product', 'cart_quantity']

    def get_amount(self, obj):
        if obj.amount_value is not None:
            from .dinner import ingredient_amount
            return ingredient_amount(obj, obj.article.servings or 1, obj.article.servings or 1)[1]
        return obj.amount

    def get_product(self, obj):
        return ProductSerializer(obj.product, context=self.context).data if obj.product and obj.product.is_active else None

    def get_cart_quantity(self, obj):
        if not obj.product or not obj.product.is_active or not obj.product.is_available:
            return None
        if obj.recipe_unit and obj.recipe_unit != obj.product.unit:
            return None
        if obj.amount_value is not None:
            from .dinner import ingredient_amount, purchase_quantity
            needed, _ = ingredient_amount(obj, obj.article.servings or 1, obj.article.servings or 1)
            quantity = purchase_quantity(obj.product, needed) if needed is not None else None
            return str(quantity) if quantity is not None else None
        quantity = obj.purchase_quantity if obj.purchase_quantity is not None else obj.product.min_quantity
        return str(quantity) if valid_quantity(obj.product, quantity) else None


class ArticleDetailSerializer(ArticleCardSerializer):
    ingredients = IngredientSerializer(many=True, read_only=True)
    steps = serializers.SerializerMethodField()
    recipes = serializers.SerializerMethodField()

    class Meta(ArticleCardSerializer.Meta):
        fields = [*ArticleCardSerializer.Meta.fields, 'body', 'ingredients', 'steps', 'recipes']

    def get_steps(self, obj):
        return [row.text for row in obj.steps.all()]

    def get_recipes(self, obj):
        recipes = [row.recipe for row in obj.members.all() if row.recipe.is_published and not row.recipe.is_demo]
        return ArticleCardSerializer(recipes, many=True, context=self.context).data


class IdeasView(generics.ListAPIView):
    serializer_class = ArticleCardSerializer

    def get_queryset(self):
        published = Article.objects.filter(is_published=True, is_demo=False)
        source = published
        meal = self.request.query_params.get('meal')
        if meal in {'breakfast', 'lunch', 'dinner'}:
            source = source.filter(**{meal: True})
        kind = self.request.query_params.get('kind')
        if kind in {'recipe', 'collection'}:
            source = source.filter(kind=kind)
        category = self.request.query_params.get('category')
        if category:
            source = source.filter(category__slug=category)
        return source.select_related('category')

    def list(self, request, *args, **kwargs):
        result = super().list(request, *args, **kwargs)
        result.data['demo'] = False
        result.data['dinner_enabled'] = DinnerSettings.objects.filter(pk=1, is_active=True).exists()
        result.data['categories'] = list(IdeaCategory.objects.values('name', 'slug'))
        return result


class ArticleDetailView(generics.RetrieveAPIView):
    serializer_class = ArticleDetailSerializer
    lookup_field = 'slug'

    def get_queryset(self):
        return Article.objects.filter(is_published=True, is_demo=False).select_related('category').prefetch_related('ingredients__product__categories', 'steps', 'members__recipe__category')
