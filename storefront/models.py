from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator, MaxValueValidator
from django.db import models
from django.utils import timezone
import uuid


def validate_image(image):
    if image and image.size > 8 * 1024 * 1024:
        raise ValidationError('Изображение не должно превышать 8 МБ.')


class Banner(models.Model):
    name = models.CharField('Название в Admin', max_length=150)
    image = models.ImageField('Готовый баннер', upload_to='storefront_uploads/banners/', validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp']), validate_image], help_text='Готовая композиция примерно 1100 × 500 px, с текстом внутри изображения.')
    alt_text = models.CharField('Описание изображения', max_length=250)
    sort_order = models.PositiveIntegerField('Порядок', default=0)
    is_active = models.BooleanField('Опубликован', default=False)
    target_type = models.CharField('Переход', max_length=16, choices=[('category', 'Категория'), ('product', 'Товар'), ('catalog', 'Весь каталог'), ('ideas', 'Идеи')], default='catalog')
    target_id = models.PositiveIntegerField('ID товара или категории', null=True, blank=True)

    class Meta:
        ordering = ['sort_order', 'pk']
        verbose_name = 'Баннер'
        verbose_name_plural = 'Баннеры'

    def __str__(self):
        return self.name

    @property
    def target_url(self):
        return {'category': f'/catalog?category={self.target_id}', 'product': f'/product/{self.target_id}', 'catalog': '/catalog?all=1', 'ideas': '/ideas'}.get(self.target_type, '')

    def clean(self):
        super().clean()
        from shop.models import Category, Product
        if self.target_type in {'category', 'product'}:
            model = Category if self.target_type == 'category' else Product
            if not self.target_id or not model.objects.filter(pk=self.target_id).exists():
                raise ValidationError({'target_id': 'Выберите существующий товар или категорию.'})
        if self.image and self.image.width and not 1.8 <= self.image.width / self.image.height <= 2.6:
            raise ValidationError({'image': 'Пропорции баннера должны быть примерно 2,2:1.'})


class CategoryImage(models.Model):
    category = models.OneToOneField('shop.Category', on_delete=models.CASCADE, verbose_name='Категория', related_name='storefront_image')
    image = models.ImageField('Фотография', upload_to='storefront_uploads/categories/', validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp']), validate_image])

    class Meta:
        verbose_name = 'Фотография категории'
        verbose_name_plural = 'Фотографии категорий'

    def __str__(self):
        return self.category.name


class ProductCollection(models.Model):
    title = models.CharField('Название', max_length=150)
    slug = models.SlugField('Адрес', unique=True)
    description = models.CharField('Краткое описание', max_length=250, blank=True)
    sort_order = models.PositiveIntegerField('Порядок', default=0)
    is_published = models.BooleanField('Опубликована на главной', default=False)
    home_limit = models.PositiveSmallIntegerField('Товаров на витрине', default=4,
        validators=[MinValueValidator(1), MaxValueValidator(8)])

    class Meta:
        ordering = ['sort_order', 'pk']
        verbose_name = 'Подборка товаров'
        verbose_name_plural = 'Подборки товаров'

    def __str__(self):
        return self.title


class ProductCollectionItem(models.Model):
    collection = models.ForeignKey(ProductCollection, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('shop.Product', on_delete=models.CASCADE, verbose_name='Товар', related_name='showcase_memberships')
    sort_order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        ordering = ['sort_order', 'pk']
        constraints = [models.UniqueConstraint(fields=['collection', 'product'], name='unique_collection_product')]
        verbose_name = 'Товар подборки'
        verbose_name_plural = 'Товары подборки'


class IdeaCategory(models.Model):
    name = models.CharField('Название', max_length=100)
    slug = models.SlugField('Адрес', unique=True)
    sort_order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        ordering = ['sort_order', 'pk']
        verbose_name = 'Раздел идей'
        verbose_name_plural = 'Разделы идей'

    def __str__(self):
        return self.name


class Article(models.Model):
    title = models.CharField('Заголовок', max_length=180)
    slug = models.SlugField('Адрес', unique=True)
    kind = models.CharField('Тип', max_length=16, choices=[('recipe', 'Рецепт'), ('collection', 'Подборка')], default='recipe')
    cover = models.ImageField('Обложка', upload_to='storefront_uploads/ideas/', blank=True, validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp']), validate_image])
    description = models.CharField('Краткое описание', max_length=250, blank=True)
    body = models.TextField('Вступление', blank=True)
    category = models.ForeignKey(IdeaCategory, null=True, blank=True, on_delete=models.SET_NULL, verbose_name='Раздел')
    breakfast = models.BooleanField('Завтрак', default=False)
    lunch = models.BooleanField('Обед', default=True)
    dinner = models.BooleanField('Ужин', default=True)
    duration_minutes = models.PositiveIntegerField('Время, минут', null=True, blank=True)
    servings = models.PositiveIntegerField('Количество порций', null=True, blank=True)
    is_topic = models.BooleanField('В тематической ленте', default=False)
    is_featured = models.BooleanField('Крупный материал', default=False)
    sort_order = models.PositiveIntegerField('Порядок', default=0)
    is_demo = models.BooleanField('Демонстрационный материал', default=False)
    is_published = models.BooleanField('Опубликован', default=False)

    class Meta:
        ordering = ['sort_order', 'pk']
        verbose_name = 'Рецепт или подборка'
        verbose_name_plural = 'Рецепты и подборки'

    def __str__(self):
        return self.title

    @property
    def meals(self):
        return [name for name in ['breakfast', 'lunch', 'dinner'] if getattr(self, name)]

    def clean(self):
        if self.is_demo and self.is_published:
            raise ValidationError({'is_published': 'Демонстрационные материалы не публикуются. Создайте проверенный материал магазина отдельно.'})


class Ingredient(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='ingredients')
    name = models.CharField('Ингредиент', max_length=180)
    amount = models.CharField('Количество в рецепте', max_length=100, blank=True, help_text='Например: 200 г, 2 шт., по вкусу.')
    product = models.ForeignKey('shop.Product', on_delete=models.SET_NULL, null=True, blank=True, verbose_name='Точный товар каталога')
    purchase_quantity = models.DecimalField('Количество для корзины', max_digits=9, decimal_places=3, null=True, blank=True, help_text='В единице продажи товара: кг или шт. Без указания добавляется минимальная доступная порция.')
    sort_order = models.PositiveIntegerField('Порядок', default=0)
    ingredient_type = models.ForeignKey('storefront.PantryIngredient', null=True, blank=True,
        on_delete=models.SET_NULL, verbose_name='Ингредиент для вопросов', related_name='recipe_ingredients')
    recipe_quantity = models.DecimalField('Количество на базовые порции', max_digits=9, decimal_places=3,
        null=True, blank=True, help_text='В единице продажи привязанного товара. Может быть меньше упаковки или минимума покупки.')
    is_optional = models.BooleanField('Необязательный ингредиент', default=False)
    recipe_unit = models.CharField('Единица количества в рецепте', max_length=3, blank=True,
        choices=[('kg', 'кг'), ('pcs', 'шт')], help_text='Фиксируется при привязке. Смена единицы товара требует повторной проверки рецепта.')

    class Meta:
        ordering = ['sort_order', 'pk']
        verbose_name = 'Ингредиент'
        verbose_name_plural = 'Ингредиенты'

    def clean(self):
        from .quantities import valid_quantity
        if self.product_id and self.ingredient_type_id and not self.recipe_unit:
            self.recipe_unit = self.product.unit
        if self.recipe_unit and self.product_id and self.recipe_unit != self.product.unit:
            raise ValidationError({'recipe_unit': 'Единица товара изменилась. Проверьте количество и укажите актуальную единицу.'})
        if self.purchase_quantity is not None and (not self.product_id or not valid_quantity(self.product, self.purchase_quantity)):
            raise ValidationError({'purchase_quantity': 'Количество должно соответствовать единице, минимуму и шагу выбранного товара.'})
        if self.recipe_quantity is not None and (not self.product_id or self.recipe_quantity <= 0):
            raise ValidationError({'recipe_quantity': 'Укажите товар и положительное количество в его единице продажи.'})


class RecipeStep(models.Model):
    article = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='steps')
    sort_order = models.PositiveIntegerField('Номер шага', default=1)
    text = models.TextField('Приготовление')

    class Meta:
        ordering = ['sort_order', 'pk']
        verbose_name = 'Шаг'
        verbose_name_plural = 'Шаги приготовления'


class ArticleMember(models.Model):
    collection = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='members', limit_choices_to={'kind': 'collection'})
    recipe = models.ForeignKey(Article, on_delete=models.CASCADE, related_name='in_collections', limit_choices_to={'kind': 'recipe'}, verbose_name='Рецепт')
    sort_order = models.PositiveIntegerField('Порядок', default=0)

    class Meta:
        ordering = ['sort_order', 'pk']
        constraints = [models.UniqueConstraint(fields=['collection', 'recipe'], name='unique_article_member')]
        verbose_name = 'Рецепт в подборке'
        verbose_name_plural = 'Рецепты в подборке'

    def clean(self):
        if self.collection_id and self.recipe_id and (self.collection_id == self.recipe_id or self.collection.kind != 'collection' or self.recipe.kind != 'recipe' or self.collection.is_demo != self.recipe.is_demo):
            raise ValidationError('Выберите рецепт с таким же демонстрационным статусом, как у подборки.')


def order_number():
    return f'БМ-{timezone.localdate():%Y%m%d}-{uuid.uuid4().hex[:12].upper()}'


class Order(models.Model):
    class Status(models.TextChoices):
        NEW = 'new', 'Новый'
        CONFIRMED = 'confirmed', 'Принят'
        PREPARING = 'preparing', 'Собирается'
        READY = 'ready', 'Готов'
        COLLECTED = 'collected', 'Завершён'
        CANCELLED = 'cancelled', 'Отменён'

    public_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    number = models.CharField('Номер', max_length=32, unique=True, default=order_number, editable=False)
    created_at = models.DateTimeField('Создан', auto_now_add=True)
    telegram_user_id = models.BigIntegerField('Telegram ID покупателя', db_index=True, editable=False)
    customer = models.ForeignKey('storefront.Customer', null=True, blank=True, on_delete=models.PROTECT,
        related_name='orders', verbose_name='Покупатель')
    fulfillment = models.CharField('Способ получения', max_length=12, choices=[('pickup', 'Самовывоз')], default='pickup')
    request_id = models.UUIDField('Ключ повторной отправки', editable=False)
    request_fingerprint = models.CharField(max_length=64, editable=False)
    buyer_name = models.CharField('Имя покупателя', max_length=100)
    phone = models.CharField('Контактный номер', max_length=20)
    comment = models.TextField('Комментарий', blank=True, max_length=1000)
    pickup_address = models.CharField('Адрес самовывоза', max_length=200)
    total = models.DecimalField('Сумма', max_digits=14, decimal_places=2)
    weight_estimate = models.BooleanField('Сумма уточняется по фактическому весу', default=False)
    status = models.CharField('Статус', max_length=16, choices=Status.choices, default=Status.NEW)

    class Meta:
        ordering = ['-created_at', '-pk']
        constraints = [models.UniqueConstraint(fields=['telegram_user_id', 'request_id'], name='unique_customer_order_request')]
        verbose_name = 'Заказ на самовывоз'
        verbose_name_plural = 'Заказы на самовывоз'

    def __str__(self):
        return self.number


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey('shop.Product', on_delete=models.SET_NULL, null=True, editable=False)
    product_name = models.CharField('Товар на момент заказа', max_length=255)
    sku = models.CharField('Артикул', max_length=100)
    quantity = models.DecimalField('Количество', max_digits=9, decimal_places=3)
    unit = models.CharField('Единица', max_length=3, choices=[('kg', 'кг'), ('pcs', 'шт')])
    unit_price = models.DecimalField('Цена на момент заказа', max_digits=12, decimal_places=2)
    subtotal = models.DecimalField('Стоимость', max_digits=14, decimal_places=2)

    class Meta:
        ordering = ['pk']
        verbose_name = 'Позиция заказа'
        verbose_name_plural = 'Состав заказа'


from .experience_models import (StoreProfile, StorePhoto, DinnerSettings, DinnerQuestion,
                                DinnerOption, PantryIngredient, DinnerRecipe)  # noqa: E402,F401
from .customer_models import Customer, OrderStatusEvent, OrderNotification  # noqa: E402,F401
