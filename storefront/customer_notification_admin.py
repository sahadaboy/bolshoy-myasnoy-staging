from django import forms
from django.conf import settings
from django.contrib import admin, messages
from django.db import transaction
from django.template.response import TemplateResponse
from django.utils import timezone

from .models import CustomerOrderNotification
from .customer_notifications import dispatch_after_commit, recover_abandoned


class DeliveryReviewForm(forms.Form):
    resolution = forms.ChoiceField(label='Подтверждённый результат', widget=forms.RadioSelect,
        choices=[('received', 'Покупатель получил сообщение — отметить доставленным'),
                 ('not_received', 'Покупатель не получил сообщение — разрешить одну повторную отправку')])
    checked = forms.BooleanField(label='Я уточнил результат у покупателя или проверил достоверную запись доставки.')


@admin.register(CustomerOrderNotification)
class CustomerOrderNotificationAdmin(admin.ModelAdmin):
    list_display = ['order', 'kind', 'recipient_telegram_id', 'status', 'attempts', 'created_at', 'sent_at', 'last_error_code']
    list_filter = ['status', 'kind']
    search_fields = ['order__number', '=recipient_telegram_id']
    list_select_related = ['order', 'reviewed_by']
    readonly_fields = [field.name for field in CustomerOrderNotification._meta.fields]
    actions = ['send_pending', 'retry_failed', 'review_delivery']

    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False

    def one_id(self, request, queryset):
        ids = list(queryset.values_list('pk', flat=True)[:2])
        if len(ids) != 1:
            self.message_user(request, 'Выберите одно личное уведомление.', messages.WARNING)
            return None
        return ids[0]

    def enabled(self, request):
        if not settings.TELEGRAM_CUSTOMER_NOTIFICATIONS_ENABLED:
            self.message_user(request, 'Личные уведомления выключены в серверных настройках.', messages.WARNING)
            return False
        return True

    def deliver(self, request, pk):
        done = dispatch_after_commit(pk)
        self.message_user(request, 'Личное уведомление доставлено.' if done else
                          'Доставка не подтверждена. Проверьте статус и ошибку записи.',
                          messages.SUCCESS if done else messages.WARNING)

    @admin.action(description='Отправить одно ожидающее уведомление', permissions=['change'])
    def send_pending(self, request, queryset):
        pk = self.one_id(request, queryset)
        if pk is None or not self.enabled(request): return
        recover_abandoned()
        self.deliver(request, pk)

    @admin.action(description='Повторить после определённого отказа Telegram (failed)', permissions=['change'])
    def retry_failed(self, request, queryset):
        pk = self.one_id(request, queryset)
        if pk is None or not self.enabled(request): return
        recover_abandoned()
        with transaction.atomic():
            row = CustomerOrderNotification.objects.select_for_update().get(pk=pk)
            if row.status != 'failed' or row.next_attempt_at > timezone.now():
                self.message_user(request, 'Повтор доступен только для failed после указанного времени. Спорную доставку сначала проверьте.', messages.WARNING)
                return
            row.status = 'pending'; row.claim_id = None; row.lease_until = None
            row.save(update_fields=['status', 'claim_id', 'lease_until'])
            self.log_change(request, row, 'Разрешён повтор после определённого отказа Telegram.')
        self.deliver(request, pk)

    @admin.action(description='Проверить неопределённую доставку (без слепого повтора)', permissions=['change'])
    def review_delivery(self, request, queryset):
        pk = self.one_id(request, queryset)
        if pk is None: return
        recover_abandoned()
        row = CustomerOrderNotification.objects.select_related('order').get(pk=pk)
        if row.status != 'uncertain':
            self.message_user(request, 'Ручная проверка требуется только для uncertain. Отправляемая запись должна дождаться окончания lease.', messages.WARNING)
            return
        submitted = request.POST.get('apply_review') == 'yes'
        form = DeliveryReviewForm(request.POST if submitted else None)
        if submitted and form.is_valid():
            resolution = form.cleaned_data['resolution']
            with transaction.atomic():
                row = CustomerOrderNotification.objects.select_for_update().get(pk=pk)
                if row.status != 'uncertain':
                    self.message_user(request, 'Результат уже изменился. Обновите страницу.', messages.WARNING)
                    return
                row.reviewed_at = timezone.now(); row.reviewed_by = request.user; row.review_result = resolution
                row.claim_id = None; row.lease_until = None
                if resolution == 'received':
                    row.status = 'sent'; row.sent_at = timezone.now(); row.last_error = ''; row.last_error_code = None
                else:
                    row.status = 'pending'; row.next_attempt_at = timezone.now()
                row.save()
                self.log_change(request, row, 'Ручная проверка личной доставки: ' + resolution)
            if resolution == 'not_received' and self.enabled(request):
                self.deliver(request, pk)
            else:
                self.message_user(request, 'Результат проверки сохранён.', messages.SUCCESS)
            return
        return TemplateResponse(request, 'admin/storefront/customer_delivery_review.html', {
            **self.admin_site.each_context(request), 'title': 'Проверка личной доставки',
            'row': row, 'form': form, 'opts': self.model._meta,
            'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME,
        })
