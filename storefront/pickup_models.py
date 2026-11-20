import uuid
from django.db import models
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, MaxValueValidator


class StoreOpeningInterval(models.Model):
    store = models.ForeignKey('storefront.StoreProfile', on_delete=models.CASCADE, related_name='opening_intervals')
    weekday = models.PositiveSmallIntegerField('День недели', choices=list(enumerate(['Понедельник','Вторник','Среда','Четверг','Пятница','Суббота','Воскресенье'])), validators=[MinValueValidator(0),MaxValueValidator(6)])
    opens = models.TimeField('Открытие')
    closes = models.TimeField('Закрытие')

    class Meta:
        ordering = ['weekday','opens']
        verbose_name = 'Интервал работы'
        verbose_name_plural = 'Интервалы работы (пустой день — закрыто)'
        constraints = [models.CheckConstraint(condition=models.Q(opens__lt=models.F('closes')), name='opening_before_closing')]

    def clean(self):
        if self.opens and self.closes:
            if self.opens >= self.closes:
                raise ValidationError('Открытие должно быть раньше закрытия в пределах дня.')
            if self.store_id and type(self).objects.filter(store_id=self.store_id,weekday=self.weekday,opens__lt=self.closes,closes__gt=self.opens).exclude(pk=self.pk).exists():
                raise ValidationError('Интервалы одного дня пересекаются.')


class OrderAcceptance(models.Model):
    order = models.OneToOneField('storefront.Order', on_delete=models.PROTECT, related_name='acceptance')
    token = models.UUIDField(unique=True, default=uuid.uuid4, editable=False)
    pending_staff_id = models.BigIntegerField(null=True, blank=True)
    pending_nonce = models.CharField(max_length=16, blank=True)
    pending_until = models.DateTimeField(null=True, blank=True)
    accepted_staff_id = models.BigIntegerField('Telegram ID сотрудника', null=True, blank=True)
    accepted_username = models.CharField('Username сотрудника', max_length=32, blank=True)
    accepted_name = models.CharField('Имя сотрудника', max_length=128, blank=True)
    accepted_at = models.DateTimeField('Заказ принят', null=True, blank=True)
    ui_revision = models.PositiveBigIntegerField(default=0)
    rendered_revision = models.PositiveBigIntegerField(default=0)
    edit_claim = models.UUIDField(null=True, blank=True)
    edit_lease_until = models.DateTimeField(null=True, blank=True)
    edit_error = models.CharField('Ошибка обновления сообщения', max_length=1000, blank=True)

    class Meta:
        verbose_name = 'Принятие заказа в Telegram'
        verbose_name_plural = 'Принятие заказов и обновление сообщений'


class TelegramCallbackReceipt(models.Model):
    update_id = models.BigIntegerField(unique=True)
    callback_id = models.CharField(max_length=128, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
