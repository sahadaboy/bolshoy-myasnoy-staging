"""Persistent, private audit data for the price-list workflow."""
import uuid

from django.conf import settings
from django.db import models
from django.db.models import Q


class ImportSource(models.Model):
    name = models.CharField('Источник / область ассортимента', max_length=150, unique=True)
    sheet_mapping = models.JSONField('Настройки колонок', default=dict, blank=True)

    class Meta:
        verbose_name = 'Источник прайсов'
        verbose_name_plural = 'Источники прайсов'

    def __str__(self):
        return self.name


class CatalogImport(models.Model):
    class Mode(models.TextChoices):
        PARTIAL = 'partial', 'Частичное обновление'
        FULL = 'full', 'Полный ассортимент источника'

    class Status(models.TextChoices):
        REVIEW = 'review', 'На проверке'
        APPLIED = 'applied', 'Применён'
        ROLLED_BACK = 'rolled_back', 'Откачен'
        FAILED = 'failed', 'Ошибка применения'

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    source = models.ForeignKey(ImportSource, on_delete=models.PROTECT, verbose_name='Источник')
    filename = models.CharField('Файл', max_length=255)
    file_sha256 = models.CharField(max_length=64)
    mode = models.CharField('Режим', choices=Mode.choices, max_length=10, default=Mode.PARTIAL)
    category_policy = models.CharField('Категории', max_length=20, default='add', choices=[
        ('add', 'Добавлять, сохраняя ручные категории'),
        ('sync_source', 'Синхронизировать только категории этого источника'),
    ])
    created_at = models.DateTimeField('Загружен', auto_now_add=True)
    applied_at = models.DateTimeField('Применён', null=True, blank=True)
    rolled_back_at = models.DateTimeField('Откачен', null=True, blank=True)
    uploaded_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                                    related_name='+', verbose_name='Загрузил')
    applied_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                                   related_name='+', verbose_name='Применил')
    rolled_back_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL,
                                       related_name='+', verbose_name='Откачен пользователем')
    status = models.CharField('Состояние', max_length=15, choices=Status.choices, default=Status.REVIEW)
    version = models.PositiveIntegerField(default=1)
    # Frozen rows and product snapshots are the reviewed plan, never a session path
    # that is silently re-parsed and re-matched during confirmation.
    plan = models.JSONField(default=dict)
    changes = models.JSONField(default=list)
    backup_path = models.TextField(blank=True)
    error = models.TextField('Ошибка', blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name = 'Импорт прайса'
        verbose_name_plural = 'История импортов'

    def __str__(self):
        return f'{self.filename} · {self.created_at:%d.%m.%Y %H:%M}'


class SourceProduct(models.Model):
    source = models.ForeignKey(ImportSource, on_delete=models.PROTECT)
    product = models.ForeignKey('shop.Product', on_delete=models.PROTECT, related_name='price_sources')
    # Manufacturer and packaging remain separate identity attributes. Do not infer
    # equivalence between differently sized packs from a similar display name.
    identity = models.JSONField(default=dict)
    managed_categories = models.JSONField(default=list)
    is_current = models.BooleanField(default=True)
    last_import = models.ForeignKey(CatalogImport, null=True, on_delete=models.PROTECT)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['source', 'product'], name='unique_price_source_product')]


class ProductIdentifier(models.Model):
    kind = models.CharField(max_length=10, choices=[('external', 'Код источника'), ('barcode', 'Штрихкод')])
    # External IDs are namespaced by source; verified GTINs have a global namespace.
    namespace = models.CharField(max_length=40)
    value = models.CharField(max_length=100)
    product = models.ForeignKey('shop.Product', on_delete=models.PROTECT, related_name='price_identifiers')

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=['kind', 'namespace', 'value'], name='unique_price_identifier'),
            models.CheckConstraint(condition=Q(kind__in=['external', 'barcode']), name='valid_price_identifier_kind'),
        ]
