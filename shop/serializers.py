
from rest_framework import serializers
from .models import Category, Product


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ["id", "name"]


class ProductSerializer(serializers.ModelSerializer):
    categories = CategorySerializer(many=True, read_only=True)
    image = serializers.SerializerMethodField()

    def get_image(self, obj):
        # A logo accidentally attached to a product is not a product photo.
        # Only presentation changes; the original record remains intact.
        if not obj.image or obj.image.name.rsplit('/', 1)[-1].casefold().startswith('logo'):
            return None
        request = self.context.get('request')
        return request.build_absolute_uri(obj.image.url) if request else obj.image.url

    class Meta:
        model = Product
        fields = [
            "id",
            "name",
            "sku",
            "price",
            "unit",
            "min_quantity",
            "quantity_step",
            "description",
            "image",
            "categories",
            "is_available",
        ]
