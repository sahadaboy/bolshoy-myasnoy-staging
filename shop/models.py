
from decimal import Decimal

from django.core.validators import MinValueValidator
from django.db import models


class Category(models.Model):
    name = models.CharField("Название", max_length=150)
    sort_order = models.PositiveIntegerField("Порядок", default=0)

    class Meta:
        verbose_name = "Категория"
        verbose_name_plural = "Категории"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


class Product(models.Model):
    class Unit(models.TextChoices):
        KG = "kg", "кг"
        PCS = "pcs", "шт"

    name = models.CharField("Название", max_length=255)

    categories = models.ManyToManyField(
    Category,
    related_name="catalog_products",
    verbose_name="Категории",
    blank=True,
    )

    sku = models.CharField(
        "Артикул",
        max_length=100,
        unique=True,
    )

    price = models.DecimalField(
        "Цена",
        max_digits=12,
        decimal_places=2,
        validators=[MinValueValidator(Decimal("0.00"))],
    )

    unit = models.CharField(
        "Единица продажи",
        max_length=3,
        choices=Unit.choices,
        default=Unit.PCS,
    )

    min_quantity = models.DecimalField(
        "Минимальное количество",
        max_digits=8,
        decimal_places=3,
        default=Decimal("1.000"),
        validators=[MinValueValidator(Decimal("0.001"))],
    )

    quantity_step = models.DecimalField(
        "Шаг количества",
        max_digits=8,
        decimal_places=3,
        default=Decimal("1.000"),
        validators=[MinValueValidator(Decimal("0.001"))],
    )

    description = models.TextField(
        "Описание",
        blank=True,
    )

    image = models.ImageField(
        "Фото",
        upload_to="products/",
        blank=True,
        null=True,
    )

    is_available = models.BooleanField(
        "В наличии",
        default=True,
    )

    is_active = models.BooleanField(
        "Показывать в магазине",
        default=True,
    )

    class Meta:
        verbose_name = "Товар"
        verbose_name_plural = "Товары"
        ordering = ["name"]

    def __str__(self):
        return self.name


from .import_models import CatalogImport, ImportSource, ProductIdentifier, SourceProduct  # noqa: E402,F401
