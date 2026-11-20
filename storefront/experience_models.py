"""Store information and editable rules for the dinner planner."""
from decimal import Decimal
from django.core.exceptions import ValidationError
from django.core.validators import FileExtensionValidator, MinValueValidator, MaxValueValidator, RegexValidator
from django.db import models


class SingletonModel(models.Model):
    class Meta:
        abstract = True

    def save(self, *args, **kwargs):
        self.pk = 1
        return super().save(*args, **kwargs)


class StoreProfile(SingletonModel):
    schedule_configured = models.BooleanField('Использовать структурированный график', default=False,
        help_text='Интервалы ниже — единый график для О нас и самовывоза. День без интервалов закрыт.')
    preparation_minutes = models.PositiveIntegerField('Время на сборку, минут', default=60,
        validators=[MinValueValidator(1), MaxValueValidator(1440)])
    name = models.CharField('Название магазина', max_length=150, default='Большой Мясной Маркет')
    description = models.TextField('О магазине', blank=True, max_length=2500)
    address = models.CharField('Адрес', max_length=250, default='Севастополь, Камышовое шоссе, 25')
    opening_hours = models.TextField('График работы', blank=True, max_length=1000,
        help_text='Каждый день с новой строки, например: Понедельник: 08:00–20:00')
    phone = models.CharField('Телефон', max_length=20, blank=True,
        validators=[RegexValidator(r'^\+?[0-9 ()-]{7,20}$', 'Укажите телефон с кодом страны.')])
    telegram_url = models.URLField('Telegram', blank=True)
    vk_url = models.URLField('ВКонтакте', blank=True)
    instagram_url = models.URLField('Instagram', blank=True)
    email = models.EmailField('Электронная почта', blank=True)
    map_url = models.URLField('Ссылка на карту', blank=True)
    map_embed_url = models.URLField('Встраиваемая карта', max_length=500, blank=True,
        help_text='HTTPS-виджет Яндекса /map-widget/v1/. Ключ платного API не требуется.')

    def clean(self):
        from urllib.parse import urlsplit
        if self.map_embed_url:
            url = urlsplit(self.map_embed_url)
            if url.scheme != 'https' or url.hostname not in ('yandex.ru', 'yandex.com') or url.path != '/map-widget/v1/' or url.username or url.fragment:
                raise ValidationError({'map_embed_url': 'Нужен HTTPS-виджет Яндекса /map-widget/v1/.'})

    class Meta:
        verbose_name = 'О нас и контакты'
        verbose_name_plural = 'О нас и контакты'

    def __str__(self):
        return self.name


class StorePhoto(models.Model):
    store = models.ForeignKey(StoreProfile, on_delete=models.CASCADE, related_name='photos', verbose_name='Магазин')
    image = models.ImageField('Фотография магазина', upload_to='storefront_uploads/store/',
        validators=[FileExtensionValidator(['jpg', 'jpeg', 'png', 'webp'])])
    caption = models.CharField('Подпись', max_length=200, blank=True)
    alt_text = models.CharField('Описание для доступности', max_length=250, blank=True)
    sort_order = models.PositiveIntegerField('Порядок', default=0)
    is_active = models.BooleanField('Показывать', default=True)

    class Meta:
        ordering = ['sort_order', 'pk']
        verbose_name = 'Фотография магазина'
        verbose_name_plural = 'Фотографии магазина'

    def __str__(self):
        return self.caption or f'Фото магазина #{self.pk or ""}'

    def clean(self):
        from .models import validate_image
        validate_image(self.image)

    def save(self, *args, **kwargs):
        # New uploads are normalized once, without modifying the source file.
        # Published mobile pages never download the original multi-megabyte PNG.
        if self.image and not self.image._committed:
            from io import BytesIO
            from pathlib import Path
            from PIL import Image, ImageOps
            from django.core.files.base import ContentFile
            self.full_clean()
            self.image.seek(0)
            with Image.open(self.image) as original:
                image = ImageOps.exif_transpose(original).convert('RGB')
                image.thumbnail((1600, 1200), Image.Resampling.LANCZOS)
                output = BytesIO()
                image.save(output, 'WEBP', quality=86, method=6)
            self.image = ContentFile(output.getvalue(), name=Path(self.image.name).stem + '.webp')
        return super().save(*args, **kwargs)


class DinnerSettings(SingletonModel):
    title = models.CharField('Название', max_length=150, default='Собрать идею для ужина')
    description = models.CharField('Описание', max_length=250,
        default='Учтём продукты дома и ваши предпочтения. Выберите блюдо и проверьте список покупок.')
    is_active = models.BooleanField('Показывать подбор ужина', default=True)
    default_servings = models.PositiveSmallIntegerField('Порций по умолчанию', default=2,
        validators=[MinValueValidator(1), MaxValueValidator(12)])
    max_servings = models.PositiveSmallIntegerField('Максимум порций', default=12,
        validators=[MinValueValidator(1), MaxValueValidator(12)])
    max_results = models.PositiveSmallIntegerField('Вариантов в результате', default=3,
        validators=[MinValueValidator(1), MaxValueValidator(6)])

    class Meta:
        verbose_name = 'Настройки подбора ужина'
        verbose_name_plural = 'Настройки подбора ужина'

    def __str__(self):
        return self.title

    def clean(self):
        if self.default_servings > self.max_servings:
            raise ValidationError({'default_servings': 'Порций по умолчанию должно быть не больше максимума.'})


class PantryIngredient(models.Model):
    name = models.CharField('Продукт / ингредиент', max_length=100)
    slug = models.SlugField('Код', unique=True)
    sort_order = models.PositiveIntegerField('Порядок', default=0)
    is_active = models.BooleanField('Показывать в вопросах', default=True)

    class Meta:
        ordering = ['sort_order', 'name', 'pk']
        verbose_name = 'Ингредиент для подбора'
        verbose_name_plural = 'Ингредиенты для подбора'

    def __str__(self):
        return self.name


class DinnerQuestion(models.Model):
    KEYS = [('pantry', 'Продукты дома'), ('dish', 'Тип блюда'), ('spice', 'Острота'),
            ('servings', 'Число порций'), ('preferences', 'Предпочтения'), ('exclude', 'Исключить ингредиенты'),
            ('time', 'Время приготовления')]
    key = models.CharField('Назначение вопроса', choices=KEYS, unique=True, max_length=20)
    title = models.CharField('Вопрос', max_length=150)
    help_text = models.CharField('Подсказка', max_length=250, blank=True)
    sort_order = models.PositiveIntegerField('Порядок', default=0)
    is_active = models.BooleanField('Показывать', default=True)

    required = models.BooleanField('Обязательный ответ', default=False)

    class Meta:
        ordering = ['sort_order', 'pk']
        verbose_name = 'Вопрос подбора ужина'
        verbose_name_plural = 'Вопросы подбора ужина'

    def __str__(self):
        return self.title


class DinnerOption(models.Model):
    question = models.ForeignKey(DinnerQuestion, on_delete=models.CASCADE, related_name='options', verbose_name='Вопрос')
    label = models.CharField('Ответ', max_length=100)
    value = models.SlugField('Код ответа')
    is_any = models.BooleanField('Подходит любое блюдо', default=False,
        help_text='Этот ответ не ограничивает рецепты. Для предпочтений используется только явное соответствие рецепту.')
    sort_order = models.PositiveIntegerField('Порядок', default=0)
    is_active = models.BooleanField('Показывать', default=True)
    max_minutes = models.PositiveSmallIntegerField('Не больше минут', null=True, blank=True,
        validators=[MinValueValidator(1), MaxValueValidator(240)],
        help_text='Только для вопроса о времени. У рецепта должно быть указано время приготовления.')

    class Meta:
        ordering = ['sort_order', 'pk']
        constraints = [models.UniqueConstraint(fields=['question', 'value'], name='unique_dinner_answer')]
        verbose_name = 'Ответ для подбора'
        verbose_name_plural = 'Ответы для подбора'

    def __str__(self):
        return f'{self.question.get_key_display()}: {self.label}'

    def clean(self):
        if self.question_id and self.question.key not in ('dish', 'spice', 'preferences', 'time'):
            raise ValidationError('У этого вопроса ответы берутся из ингредиентов или числа порций.')
        if self.question_id and self.is_any and self.question.key == 'preferences':
            raise ValidationError({'is_any': 'Для предпочтений задавайте явные соответствия рецептам.'})
        if self.question_id and self.question.key == 'time' and not self.is_any and not self.max_minutes:
            raise ValidationError({'max_minutes': 'Укажите максимальное время приготовления.'})
        if self.max_minutes and self.question_id and (self.question.key != 'time' or self.is_any):
            raise ValidationError({'max_minutes': 'Ограничение времени относится только к конкретному ответу о времени.'})


class DinnerRecipe(models.Model):
    article = models.OneToOneField('storefront.Article', on_delete=models.CASCADE,
        limit_choices_to={'kind': 'recipe', 'is_demo': False}, related_name='dinner_rule', verbose_name='Рецепт')
    options = models.ManyToManyField(DinnerOption, blank=True, verbose_name='Подходит для ответов',
        help_text='Отметьте тип блюда, остроту и подходящие предпочтения. Выбранные ответы пользователя должны совпасть со всеми правилами.')
    is_active = models.BooleanField('Участвует в подборе', default=False)
    sort_order = models.PositiveIntegerField('Приоритет', default=0)

    class Meta:
        ordering = ['sort_order', 'pk']
        verbose_name = 'Блюдо в подборе ужина'
        verbose_name_plural = 'Блюда в подборе ужина'

    def __str__(self):
        return str(self.article)

    def clean(self):
        if self.article_id and (self.article.kind != 'recipe' or self.article.is_demo):
            raise ValidationError({'article': 'Выберите настоящий рецепт магазина.'})
        if self.is_active and self.article_id and (not self.article.is_published or not self.article.servings):
            raise ValidationError('Для участия опубликуйте рецепт и укажите базовое число порций.')
