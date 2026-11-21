from django.contrib import admin, messages
from django import forms
from django.db import transaction
from django.db.models import F
from django.forms.models import BaseInlineFormSet
from .models import StoreOpeningInterval, OrderAcceptance
from django.utils import timezone
from django.urls import reverse
from django.utils.html import format_html
from .models import Banner, CategoryImage, ProductCollection, ProductCollectionItem, IdeaCategory, Article, Ingredient, RecipeStep, ArticleMember
from .models import Order, OrderItem, IngredientAlternative
from .models import Customer, OrderStatusEvent, OrderNotification
from .customer_notification_admin import CustomerOrderNotificationAdmin  # noqa: F401
from .customers import normalize_phone
from .models import StoreProfile, StorePhoto, DinnerSettings, DinnerQuestion, DinnerOption, PantryIngredient, DinnerRecipe


@admin.register(Banner)
class BannerAdmin(admin.ModelAdmin):
    list_display = ['name', 'preview', 'sort_order', 'is_active', 'target_type']
    list_editable = ['sort_order', 'is_active']
    list_filter = ['is_active']
    search_fields = ['name', 'alt_text']

    @admin.display(description='Изображение')
    def preview(self, obj):
        return format_html('<img src="{}" width="110" height="50" style="object-fit:cover" alt="">', obj.image.url) if obj.image else '—'


@admin.register(CategoryImage)
class CategoryImageAdmin(admin.ModelAdmin):
    list_display = ['category']
    autocomplete_fields = ['category']


class CollectionItemInline(admin.TabularInline):
    model = ProductCollectionItem
    autocomplete_fields = ['product']
    extra = 0


@admin.register(ProductCollection)
class CollectionAdmin(admin.ModelAdmin):
    list_display = ['title', 'sort_order', 'home_limit', 'is_published']
    list_editable = ['sort_order', 'home_limit', 'is_published']
    search_fields = ['title', 'description']
    list_filter = ['is_published']
    prepopulated_fields = {'slug': ['title']}
    inlines = [CollectionItemInline]


@admin.register(IdeaCategory)
class IdeaCategoryAdmin(admin.ModelAdmin):
    list_display = ['name', 'sort_order']
    list_editable = ['sort_order']
    prepopulated_fields = {'slug': ['name']}


class IngredientInline(admin.StackedInline):
    model = Ingredient
    autocomplete_fields = ['product', 'ingredient_type']
    fields = [('name', 'amount'), ('ingredient_type', 'product'), ('recipe_quantity', 'recipe_unit'),
              ('amount_value', 'amount_unit', 'pack_size'),
              ('purchase_quantity', 'is_optional', 'sort_order')]
    show_change_link = True
    extra = 0


class AlternativeInline(admin.TabularInline):
    model = IngredientAlternative
    autocomplete_fields = ['product']
    extra = 0


@admin.register(Ingredient)
class IngredientAdmin(admin.ModelAdmin):
    list_display = ['name', 'article', 'amount_value', 'amount_unit', 'product']
    list_filter = ['article', 'amount_unit']
    search_fields = ['name', 'article__title', 'product__name']
    autocomplete_fields = ['article', 'product', 'ingredient_type']
    inlines = [AlternativeInline]


class StepInline(admin.TabularInline):
    model = RecipeStep
    extra = 0


class ArticleMemberInline(admin.TabularInline):
    model = ArticleMember
    fk_name = 'collection'
    autocomplete_fields = ['recipe']
    extra = 0


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ['title', 'kind', 'category', 'is_demo', 'is_published', 'sort_order']
    list_filter = ['kind', 'category', 'is_demo', 'is_published', 'breakfast', 'lunch', 'dinner']
    search_fields = ['title', 'description']
    list_editable = ['sort_order']
    prepopulated_fields = {'slug': ['title']}
    inlines = [IngredientInline, StepInline, ArticleMemberInline]

    def get_inlines(self, request, obj=None):
        return [ArticleMemberInline] if obj and obj.kind == 'collection' else [IngredientInline, StepInline]


class PhotoInline(admin.TabularInline):
    model = StorePhoto
    fields = ['image', 'caption', 'alt_text', 'sort_order', 'is_active']
    extra = 1


class SingletonAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return super().has_add_permission(request) and not self.model.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False


class OpeningFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors): return
        rows=[]
        for form in self.forms:
            data=form.cleaned_data
            if not data or data.get('DELETE'): continue
            day,start,end=data.get('weekday'),data.get('opens'),data.get('closes')
            if start is None or end is None: continue
            if any(day==d and start<b and end>a for d,a,b in rows):
                raise forms.ValidationError('Интервалы одного дня пересекаются.')
            rows.append((day,start,end))


class OpeningInline(admin.TabularInline):
    model=StoreOpeningInterval
    formset=OpeningFormSet
    extra=0


@admin.register(StoreProfile)
class StoreProfileAdmin(SingletonAdmin):
    inlines = [OpeningInline, PhotoInline]
    fieldsets = [('Магазин', {'fields': ['name', 'description', 'address', 'opening_hours']}),
                 ('Самовывоз и график', {'fields':['schedule_configured','preparation_minutes']}),
                 ('Связь', {'fields': ['phone', 'telegram_url', 'vk_url', 'instagram_url', 'email', 'map_url', 'map_embed_url']})]

    def get_readonly_fields(self, request, obj=None):
        return ['effective_opening_hours']

    def get_fieldsets(self, request, obj=None):
        from copy import deepcopy
        fields=deepcopy(self.fieldsets)
        if obj and obj.schedule_configured:
            fields[0][1]['fields']=['name','description','address','effective_opening_hours']
        return fields

    @admin.display(description='График по интервалам')
    def effective_opening_hours(self,obj):
        from .pickup import opening_text
        return format_html('<pre>{}</pre>',opening_text(obj))


@admin.register(StorePhoto)
class StorePhotoAdmin(admin.ModelAdmin):
    list_display = ['preview', 'caption', 'sort_order', 'is_active']
    list_editable = ['caption', 'sort_order', 'is_active']
    list_filter = ['is_active']

    @admin.display(description='Фотография')
    def preview(self, obj):
        return format_html('<img src="{}" width="100" height="75" style="object-fit:cover" alt="">', obj.image.url) if obj.image else '—'


@admin.register(DinnerSettings)
class DinnerSettingsAdmin(SingletonAdmin):
    pass


class OptionInline(admin.TabularInline):
    model = DinnerOption
    extra = 0


@admin.register(DinnerQuestion)
class DinnerQuestionAdmin(admin.ModelAdmin):
    list_display = ['title', 'key', 'sort_order', 'required', 'is_active']
    list_editable = ['sort_order', 'required', 'is_active']
    inlines = [OptionInline]

    def get_readonly_fields(self, request, obj=None):
        return ['key'] if obj else []


@admin.register(DinnerOption)
class DinnerOptionAdmin(admin.ModelAdmin):
    list_display = ['label', 'question', 'is_any', 'sort_order', 'is_active']
    list_filter = ['question', 'is_active']
    search_fields = ['label']
    list_editable = ['sort_order', 'is_active']


@admin.register(PantryIngredient)
class PantryIngredientAdmin(admin.ModelAdmin):
    list_display = ['name', 'sort_order', 'is_active']
    list_editable = ['sort_order', 'is_active']
    search_fields = ['name']
    prepopulated_fields = {'slug': ['name']}


@admin.register(DinnerRecipe)
class DinnerRecipeAdmin(admin.ModelAdmin):
    list_display = ['article', 'sort_order', 'is_active']
    list_editable = ['sort_order', 'is_active']
    autocomplete_fields = ['article']
    filter_horizontal = ['options']
    list_filter = ['is_active', 'options']
    search_fields = ['article__title']


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    can_delete = False
    readonly_fields = ['product_name', 'sku', 'quantity', 'unit', 'unit_price', 'subtotal']
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    actions=['enable_staff_confirmation']
    list_display = ['number', 'created_at', 'pickup_at', 'buyer_name', 'phone', 'total', 'fulfillment', 'status', 'customer_link']
    list_filter = ['status', 'created_at']
    search_fields = ['number', 'buyer_name', 'phone']
    date_hierarchy = 'created_at'
    readonly_fields = ['public_id', 'number', 'created_at', 'telegram_user_id', 'customer', 'fulfillment', 'buyer_name', 'phone', 'comment', 'pickup_address', 'pickup_at', 'total', 'weight_estimate']
    fields = [*readonly_fields, 'status']
    inlines = [OrderItemInline]

    @admin.action(description='Добавить кнопки подтверждения в доставленное сообщение',permissions=['change'])
    def enable_staff_confirmation(self,request,queryset):
        from django.conf import settings
        from .order_acceptance import refresh_message
        if not settings.TELEGRAM_ORDER_WEBHOOK_ENABLED:
            self.message_user(request,'Webhook подтверждений ещё не включён.',messages.WARNING);return
        orders=list(queryset.filter(status=Order.Status.NEW)[:2])
        if len(orders)!=1:
            self.message_user(request,'Выберите один новый заказ.',messages.WARNING);return
        notification=OrderNotification.objects.filter(order=orders[0]).first()
        if not notification or not notification.telegram_message_ids or len(notification.telegram_message_ids)!=len(notification.payload_parts):
            self.message_user(request,'Сначала завершите доставку исходного уведомления.',messages.WARNING);return
        row,_=OrderAcceptance.objects.get_or_create(order=orders[0])
        done=refresh_message(row.pk,force=True)
        self.message_user(request,'Кнопки обновлены.' if done else 'Обновление ожидает повтора в принятии заказа.',messages.SUCCESS if done else messages.WARNING)

    @admin.display(description='Покупатель')
    def customer_link(self, obj):
        return format_html('<a href="{}">{}</a>', reverse('admin:storefront_customer_change', args=[obj.customer_id]), obj.customer) if obj.customer_id else '—'

    def save_model(self, request, obj, form, change):
        previous = Order.objects.get(pk=obj.pk).status if change else ''
        super().save_model(request, obj, form, change)
        if previous != obj.status:
            OrderStatusEvent.objects.create(order=obj, previous_status=previous, status=obj.status, actor=request.user)
            row=OrderAcceptance.objects.filter(order=obj).first()
            if row:
                OrderAcceptance.objects.filter(pk=row.pk).update(ui_revision=F('ui_revision')+1)
                from .order_acceptance import refresh_message
                transaction.on_commit(lambda: refresh_message(row.pk))

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class CustomerForm(forms.ModelForm):
    class Meta:
        model = Customer
        fields = '__all__'

    def clean_phone(self):
        value = self.cleaned_data['phone']
        if not value:
            return ''
        try:
            return normalize_phone(value)
        except Exception:
            raise forms.ValidationError('Проверьте международный формат телефона.') from None


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    form = CustomerForm
    list_display = ['display_name', 'telegram_id', 'phone', 'registered_at', 'last_seen_at', 'order_history']
    search_fields = ['first_name', 'last_name', 'username', 'phone', '=telegram_id']
    readonly_fields = ['telegram_id', 'first_name', 'last_name', 'username', 'photo_url', 'registered_at', 'last_seen_at', 'order_history']
    fields = [*readonly_fields, 'phone']

    @admin.display(description='Заказы покупателя')
    def order_history(self, obj):
        return format_html('<a href="{}?customer__id__exact={}">Все заказы</a>', reverse('admin:storefront_order_changelist'), obj.pk)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class StatusHistoryInline(admin.TabularInline):
    model = OrderStatusEvent
    extra = 0
    can_delete = False
    readonly_fields = ['previous_status', 'status', 'created_at', 'actor']
    fields = readonly_fields

    def has_add_permission(self, request, obj=None):
        return False


class NotificationInline(admin.StackedInline):
    model = OrderNotification
    extra = 0
    can_delete = False
    fields = ['status', 'attempts', 'last_error', 'sent_at']
    readonly_fields = fields

    def has_add_permission(self, request, obj=None):
        return False


OrderAdmin.inlines = [OrderItemInline, StatusHistoryInline, NotificationInline]


class AcceptanceInline(admin.StackedInline):
    model=OrderAcceptance
    fields=['accepted_staff_id','accepted_username','accepted_name','accepted_at','pending_staff_id','pending_until','edit_error']
    readonly_fields=fields
    extra=0
    can_delete=False
    def has_add_permission(self, request, obj=None): return False

OrderAdmin.inlines=[*OrderAdmin.inlines, AcceptanceInline]


@admin.register(OrderAcceptance)
class OrderAcceptanceAdmin(admin.ModelAdmin):
    list_display=['order','accepted_at','accepted_staff_id','accepted_username','edit_error']
    readonly_fields=[field.name for field in OrderAcceptance._meta.fields]
    actions=['retry_message']
    def has_add_permission(self, request): return False
    def has_delete_permission(self, request, obj=None): return False
    @admin.action(description='Повторить обновление исходного сообщения (без новой отправки)',permissions=['change'])
    def retry_message(self, request, queryset):
        ids=list(queryset.values_list('pk',flat=True)[:2])
        if len(ids)!=1:
            self.message_user(request,'Выберите одно принятие заказа.',messages.WARNING);return
        from .order_acceptance import refresh_message
        success=refresh_message(ids[0],force=True)
        self.message_user(request,'Сообщение обновлено.' if success else 'Не обновлено. Проверьте настройки и ошибку записи.',messages.SUCCESS if success else messages.WARNING)


@admin.register(OrderNotification)
class OrderNotificationAdmin(admin.ModelAdmin):
    list_display = ['order', 'status', 'attempts', 'created_at', 'sent_at']
    list_filter = ['status']
    readonly_fields = [field.name for field in OrderNotification._meta.fields]
    actions = ['send_pending', 'retry_delivery']

    def deliver_selected(self, request, ids):
        from django.conf import settings
        from .notifications import dispatch_after_commit
        if not settings.TELEGRAM_NOTIFICATIONS_ENABLED:
            self.message_user(request, 'Уведомления выключены в серверных настройках.', messages.WARNING)
            return
        if len(ids) > 1:
            self.message_user(request, 'Выберите одно уведомление: отправка выполняется сразу, без фонового процесса.', messages.WARNING)
            return
        sent = sum(dispatch_after_commit(pk) for pk in ids)
        self.message_user(request, f'Доставлено: {sent}. Подробности — в статусе уведомления.', messages.SUCCESS if sent else messages.WARNING)

    @admin.action(description='Отправить выбранное уведомление из очереди сейчас', permissions=['change'])
    def send_pending(self, request, queryset):
        self.deliver_selected(request, list(queryset.filter(status='pending').values_list('pk', flat=True)[:2]))

    @admin.action(description='Повторить доставку (для спорных отправок сначала проверьте чат)', permissions=['change'])
    def retry_delivery(self, request, queryset):
        from django.conf import settings
        from .notifications import recover_abandoned
        if not settings.TELEGRAM_NOTIFICATIONS_ENABLED:
            self.message_user(request, 'Уведомления выключены в серверных настройках.', messages.WARNING)
            return
        recover_abandoned()
        ids = list(queryset.filter(status__in=['failed', 'uncertain']).values_list('pk', flat=True)[:2])
        if len(ids) > 1:
            self.message_user(request, 'Для повтора выберите одно уведомление и предварительно проверьте чат.', messages.WARNING)
            return
        if queryset.filter(pk__in=ids, status='uncertain').exists() and request.POST.get('confirm_delivery_checked') != 'yes':
            from django.template.response import TemplateResponse
            return TemplateResponse(request, 'admin/storefront/retry_notification.html', {
                **self.admin_site.each_context(request), 'title': 'Проверьте доставку перед повтором',
                'rows': queryset.filter(pk__in=ids), 'opts': self.model._meta,
                'action_checkbox_name': admin.helpers.ACTION_CHECKBOX_NAME})
        # Acknowledged message parts and the original destination are retained.
        queryset.filter(pk__in=ids, status__in=['failed', 'uncertain']).update(
            status='pending', next_attempt_at=timezone.now(), lease_until=None, claim_id=None)
        self.deliver_selected(request, ids)

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
