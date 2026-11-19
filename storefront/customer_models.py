from django.conf import settings
from django.db import models
from django.utils import timezone


class Customer(models.Model):
    telegram_id = models.BigIntegerField('Telegram ID', unique=True, editable=False)
    first_name = models.CharField('Имя Telegram', max_length=256, blank=True)
    last_name = models.CharField('Фамилия Telegram', max_length=256, blank=True)
    username = models.CharField('Username', max_length=256, blank=True)
    photo_url = models.URLField('Аватар Telegram', max_length=2048, blank=True)
    phone = models.CharField('Контактный телефон', max_length=20, blank=True)
    registered_at = models.DateTimeField('Первый вход', default=timezone.now, editable=False)
    last_seen_at = models.DateTimeField('Последняя активность', default=timezone.now, editable=False)
    identity_date = models.BigIntegerField(default=0, editable=False)

    @property
    def display_name(self):
        return ' '.join(filter(None, [self.first_name, self.last_name])) or self.username or str(self.telegram_id)

    class Meta:
        verbose_name = 'Покупатель'
        verbose_name_plural = 'Покупатели'
        ordering = ['-last_seen_at', '-pk']

    def __str__(self):
        return self.display_name


class OrderStatusEvent(models.Model):
    order = models.ForeignKey('storefront.Order', on_delete=models.CASCADE, related_name='status_events')
    previous_status = models.CharField('Предыдущий статус', max_length=16, blank=True)
    status = models.CharField('Новый статус', max_length=16)
    created_at = models.DateTimeField('Изменён', auto_now_add=True)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.SET_NULL, verbose_name='Сотрудник')

    class Meta:
        ordering = ['created_at', 'pk']
        verbose_name = 'Изменение статуса'
        verbose_name_plural = 'История статусов'


class OrderNotification(models.Model):
    class Status(models.TextChoices):
        PENDING = 'pending', 'В очереди'
        SENDING = 'sending', 'Отправляется'
        SENT = 'sent', 'Доставлено в Telegram'
        FAILED = 'failed', 'Ошибка отправки'
        UNCERTAIN = 'uncertain', 'Требуется проверить доставку'
    order = models.OneToOneField('storefront.Order', on_delete=models.PROTECT, related_name='notification', verbose_name='Заказ')
    status = models.CharField('Доставка', max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    attempts = models.PositiveIntegerField('Попыток', default=0)
    last_error = models.CharField('Ошибка', max_length=1000, blank=True)
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    sent_at = models.DateTimeField('Доставлено', null=True, blank=True)
    next_attempt_at = models.DateTimeField('Следующая попытка', default=timezone.now)
    lease_until = models.DateTimeField(null=True, blank=True)
    claim_id = models.UUIDField(null=True, blank=True)
    telegram_message_ids = models.JSONField(default=list, blank=True)
    sent_parts = models.PositiveIntegerField(default=0)
    payload_parts = models.JSONField(default=list, blank=True)
    destination = models.CharField(max_length=100, blank=True)

    class Meta:
        verbose_name = 'Уведомление о заказе'
        verbose_name_plural = 'Уведомления о заказах'
        ordering = ['-created_at']
