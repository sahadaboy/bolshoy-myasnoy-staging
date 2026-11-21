from django.conf import settings
from django.db import models
from django.utils import timezone
from .customer_models import OrderNotification


class CustomerOrderNotification(models.Model):
    class Kind(models.TextChoices):
        ORDER_CONFIRMED = 'ORDER_CONFIRMED', 'Заказ принят'

    Status = OrderNotification.Status
    order = models.ForeignKey('storefront.Order', on_delete=models.PROTECT,
                              related_name='customer_notifications', verbose_name='Заказ')
    kind = models.CharField('Тип', max_length=24, choices=Kind.choices, default=Kind.ORDER_CONFIRMED)
    recipient_telegram_id = models.BigIntegerField('Telegram ID покупателя', editable=False)
    status = models.CharField('Доставка', max_length=12, choices=Status.choices,
                              default=Status.PENDING, db_index=True)
    attempts = models.PositiveIntegerField('Попыток', default=0)
    last_error = models.CharField('Ошибка', max_length=1000, blank=True)
    last_error_code = models.PositiveSmallIntegerField('Код Telegram', null=True, blank=True)
    created_at = models.DateTimeField('Создано', auto_now_add=True)
    sent_at = models.DateTimeField('Доставка подтверждена', null=True, blank=True)
    next_attempt_at = models.DateTimeField('Повтор не раньше', default=timezone.now)
    lease_until = models.DateTimeField(null=True, blank=True)
    claim_id = models.UUIDField(null=True, blank=True)
    telegram_message_id = models.PositiveBigIntegerField('ID сообщения Telegram', null=True, blank=True)
    payload = models.JSONField('Сохранённое сообщение', default=dict, blank=True)
    reviewed_at = models.DateTimeField('Ручная проверка', null=True, blank=True)
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, verbose_name='Проверил')
    review_result = models.CharField('Результат проверки', max_length=16, blank=True,
                                    choices=[('received', 'Получено'), ('not_received', 'Не получено')])

    class Meta:
        verbose_name = 'Личное уведомление покупателю'
        verbose_name_plural = 'Личные уведомления покупателям'
        ordering = ['-created_at']
        constraints = [models.UniqueConstraint(fields=['order', 'kind'], name='unique_customer_order_notice')]

    def __str__(self):
        return f'{self.order} — {self.get_kind_display()}'
