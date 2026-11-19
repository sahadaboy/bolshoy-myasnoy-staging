from decimal import Decimal

from django import forms
from django.contrib import admin, messages
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import F
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import path, reverse
from django.utils.html import format_html

from .excel_import import ImportProblem, validate_mapping
from .models import CatalogImport, Category, ImportSource, Product
from .price_import import apply_import, create_preview, revise_preview, rollback_import


def check_import_permission(request):
    if not all(request.user.has_perm(f'shop.{permission}') for permission in
               ('add_product', 'change_product', 'add_category')):
        raise PermissionDenied


class ExcelUploadForm(forms.Form):
    file = forms.FileField(label='Excel-файл (.xlsx)')
    source = forms.ModelChoiceField(label='Источник прайса', queryset=ImportSource.objects.all(), required=False)
    new_source = forms.CharField(label='Или новый источник / область каталога', max_length=150, required=False)
    mode = forms.ChoiceField(label='Режим', choices=CatalogImport.Mode.choices, initial=CatalogImport.Mode.PARTIAL)
    category_policy = forms.ChoiceField(label='Категории', choices=CatalogImport._meta.get_field('category_policy').choices)
    mapping = forms.JSONField(label='Настройки колонок (при необходимости)', required=False,
        help_text='Пусто: распознать заголовки или использовать настройки источника. Пример приведён ниже.')

    def clean_file(self):
        file = self.cleaned_data['file']
        if not file.name.lower().endswith('.xlsx') or file.size > 10 * 1024 * 1024:
            raise forms.ValidationError('Нужен .xlsx размером до 10 МБ')
        return file

    def clean_mapping(self):
        value = self.cleaned_data['mapping']
        try:
            return validate_mapping(value) if value is not None else None
        except ImportProblem as exc:
            raise forms.ValidationError(str(exc)) from exc

    def clean(self):
        values = super().clean()
        if bool(values.get('source')) == bool(values.get('new_source')):
            raise forms.ValidationError('Выберите существующий источник или укажите имя нового')
        return values


class SourceForm(forms.ModelForm):
    class Meta:
        model = ImportSource
        fields = '__all__'

    def clean_sheet_mapping(self):
        try:
            return validate_mapping(self.cleaned_data.get('sheet_mapping') or {})
        except ImportProblem as exc:
            raise forms.ValidationError(str(exc)) from exc


@admin.register(ImportSource)
class ImportSourceAdmin(admin.ModelAdmin):
    form = SourceForm
    list_display = ('name',)
    search_fields = ('name',)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'sort_order')
    search_fields = ('name',)


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'sku', 'display_categories', 'price', 'unit', 'is_available', 'is_active')
    list_filter = ('categories', 'unit', 'is_available', 'is_active')
    search_fields = ('name', 'sku')
    list_editable = ('price', 'is_available', 'is_active')
    list_per_page = 50

    def get_urls(self):
        return [path('import-excel/', self.admin_site.admin_view(self.import_excel),
                     name='shop_product_import_excel')] + super().get_urls()

    @admin.display(description='Категории')
    def display_categories(self, obj):
        return ', '.join(category.name for category in obj.categories.all())

    def import_excel(self, request):
        check_import_permission(request)
        form = ExcelUploadForm(request.POST or None, request.FILES or None)
        if request.method == 'POST' and form.is_valid():
            try:
                with transaction.atomic():
                    values = form.cleaned_data
                    source = values['source'] or ImportSource.objects.get_or_create(name=values['new_source'])[0]
                    batch = create_preview(values['file'], source, values['mode'], request.user,
                                           values['category_policy'], values['mapping'])
                return redirect('admin:shop_catalogimport_review', batch.pk)
            except Exception as exc:
                form.add_error(None, f'Не удалось прочитать прайс: {exc}')
        return render(request, 'admin/shop/product/import_excel.html', {
            **self.admin_site.each_context(request), 'title': 'Импорт прайса', 'form': form,
            'opts': self.model._meta,
        })


@admin.register(CatalogImport)
class CatalogImportAdmin(admin.ModelAdmin):
    list_display = ('created_at', 'filename', 'source', 'mode', 'status', 'uploaded_by', 'result_counts', 'review_link')
    list_filter = ('status', 'mode', 'source')
    search_fields = ('filename', 'source__name')
    readonly_fields = tuple(field.name for field in CatalogImport._meta.fields)
    list_per_page = 25
    list_display_links = None

    def get_queryset(self, request):
        # History needs only counters, not 25 complete workbook plans/snapshots.
        return super().get_queryset(request).annotate(preview_summary=F('plan__summary')).defer('plan', 'changes')

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm('shop.change_product')

    def has_change_permission(self, request, obj=None):
        return self.has_view_permission(request, obj)

    @admin.display(description='Результат')
    def result_counts(self, obj):
        counts = obj.preview_summary or {}
        return f"Новых: {counts.get('new', 0)} · цен: {counts.get('prices', 0)} · ошибок: {counts.get('errors', 0)}"

    @admin.display(description='Отчёт')
    def review_link(self, obj):
        return format_html('<a href="{}">Открыть отчёт</a>', reverse('admin:shop_catalogimport_review', args=[obj.pk]))

    def get_urls(self):
        return [path('<uuid:batch_id>/review/', self.admin_site.admin_view(self.review),
                     name='shop_catalogimport_review')] + super().get_urls()

    def review(self, request, batch_id):
        check_import_permission(request)
        batch = get_object_or_404(CatalogImport.objects.select_related('source', 'uploaded_by', 'applied_by', 'rolled_back_by'), pk=batch_id)
        if request.method == 'POST':
            try:
                version = int(request.POST.get('version', '0'))
                action = request.POST.get('action')
                if action == 'apply':
                    apply_import(batch.pk, version, request.user, confirm=request.POST.get('confirm') == 'on',
                                 archive_missing=request.POST.get('archive_missing') == 'on',
                                 reviewed_drop=request.POST.get('reviewed_drop') == 'on',
                                 accept_errors=request.POST.get('accept_errors') == 'on')
                    messages.success(request, 'Прайс применён. Исторические заказы и связанные данные сохранены.')
                elif action == 'rollback':
                    rollback_import(batch.pk, request.user, confirm=request.POST.get('confirm_rollback') == 'on')
                    messages.success(request, 'Каталожные изменения откачены. Новые товары архивированы; заказы сохранены.')
                elif action == 'categories':
                    mapping = {}
                    categories = {str(pk) for pk in Category.objects.values_list('pk', flat=True)}
                    for index, name in enumerate(batch.plan['category_map']):
                        target = request.POST.get(f'category_{index}', '')
                        if target not in categories | {'', 'new', 'ignore'}:
                            raise ImportProblem('Выбрана неизвестная категория')
                        mapping[name] = target
                    revise_preview(batch.pk, version, category_map=mapping)
                    messages.success(request, 'Сопоставления сохранены. Проверьте пересчитанный предпросмотр перед применением.')
                elif action == 'resolve':
                    key = request.POST.get('row_key')
                    if key not in {row['key'] for row in batch.plan['rows']}:
                        raise ImportProblem('Неизвестная строка')
                    resolution = request.POST.get('resolution')
                    if resolution not in ('auto', 'link', 'create', 'skip'):
                        raise ImportProblem('Неизвестное решение')
                    decision = {'action': resolution, 'confirm_unit': request.POST.get('confirm_unit') == 'on'}
                    if resolution == 'link':
                        decision['product_id'] = int(request.POST.get('product_id', '0'))
                    for field in ('min_quantity', 'quantity_step'):
                        value = request.POST.get(field, '').strip()
                        if value:
                            number = Decimal(value.replace(',', '.'))
                            if not number.is_finite() or number <= 0 or number > Decimal('99999.999') or number != number.quantize(Decimal('.001')):
                                raise ImportProblem('Минимум и шаг: положительное число, до трёх знаков после запятой')
                            decision[field] = format(number, '.3f')
                    decisions = {**batch.plan['decisions'], key: decision}
                    revise_preview(batch.pk, version, decisions=decisions)
                    messages.success(request, 'Решение сохранено. Проверьте пересчитанный предпросмотр.')
                elif action == 'refresh':
                    revise_preview(batch.pk, version)
                    messages.success(request, 'Предпросмотр пересчитан по текущему каталогу. Проверьте изменения заново.')
                else:
                    raise ImportProblem('Неизвестное действие')
            except Exception as exc:
                messages.error(request, str(exc))
            return redirect('admin:shop_catalogimport_review', batch.pk)
        rows = batch.plan.get('rows', [])
        selected = request.GET.get('show', '')
        if selected in ('create', 'update', 'ambiguous', 'error', 'skip'):
            rows = [row for row in rows if row['action'] == selected]
        page = Paginator(rows, 50).get_page(request.GET.get('page'))
        labels = {pk: f'{sku} · {name}' for pk, sku, name in Product.objects.values_list('pk', 'sku', 'name')}
        for row in page.object_list:
            row['action_label'] = {'create': 'Новый товар', 'update': 'Сопоставлен', 'ambiguous': 'Нужна проверка',
                                   'error': 'Конфликт', 'skip': 'Пропущен'}.get(row['action'], row['action'])
            row['candidates_display'] = [(pk, labels.get(pk, 'Товар удалён')) for pk in row.get('candidates', [])]
            row['decision'] = batch.plan['decisions'].get(row['key'], {})
        summary = batch.plan.get('summary', {})
        context = {
            **self.admin_site.each_context(request), 'opts': self.model._meta, 'batch': batch,
            'title': f'Проверка прайса: {batch.filename}', 'page': page, 'selected': selected,
            'counts': [(label, summary.get(key, 0)) for key, label in [
                ('total', 'Строк'), ('matched', 'Сопоставлено'), ('new', 'Новых'), ('prices', 'Изменений цен'),
                ('names', 'Переименований'), ('categories', 'Изменений категорий'), ('units', 'Смен единиц'),
                ('reactivated', 'Восстановлений'), ('missing', 'Нет в файле'), ('duplicates', 'Дублей'),
                ('errors', 'Ошибок'), ('ambiguous', 'Спорных'), ('skipped', 'Пропущено вручную')]],
            'category_mappings': list(batch.plan.get('category_map', {}).items()),
            'categories': Category.objects.all(), 'editable': batch.status in ('review', 'failed') and not batch.plan.get('read_failed'),
            'missing_page': Paginator(batch.plan.get('missing', []), 50).get_page(request.GET.get('missing_page')),
            'errors_page': Paginator(batch.plan.get('input', {}).get('errors', []), 50).get_page(request.GET.get('errors_page')),
        }
        return render(request, 'admin/shop/product/import_review.html', context)
