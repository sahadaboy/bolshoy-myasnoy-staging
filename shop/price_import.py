"""Reviewed, transactional catalogue imports and conflict-checked rollback.

Product IDs, SKUs, stock flags, media, descriptions and order snapshots are never
replaced. Full import scope consists only of products linked to its source.
"""
from collections import defaultdict
from copy import deepcopy
from decimal import Decimal
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import uuid

from django.conf import settings
from django.db import connection, transaction
from django.utils import timezone

from .excel_import import ImportProblem, identity, normalized, read_excel
from .models import CatalogImport, Category, Product, ProductIdentifier, SourceProduct

MANAGED_FIELDS = ('name', 'price', 'unit', 'min_quantity', 'quantity_step', 'is_active')


def identity_signature(products):
    values = sorted((item.pk, normalized(item.name), item.unit) for item in products)
    return sha256(json.dumps(values, ensure_ascii=False).encode()).hexdigest()


def product_snapshot(product):
    scales = {'price': 2, 'min_quantity': 3, 'quantity_step': 3}
    return {**{key: (format(Decimal(getattr(product, key)), f'.{scales[key]}f') if key in scales
                    else getattr(product, key)) for key in MANAGED_FIELDS},
            'categories': sorted(item.pk for item in product.categories.all())}


def membership_snapshot(source, product_id):
    item = SourceProduct.objects.filter(source=source, product_id=product_id).first()
    return member_value(item)


def member_value(item):
    if not item:
        return None
    return {'identity': item.identity, 'managed_categories': item.managed_categories,
            'is_current': item.is_current, 'last_import_id': str(item.last_import_id) if item.last_import_id else None}


def identifier_snapshot(product_id):
    return list(ProductIdentifier.objects.filter(product_id=product_id).order_by('kind', 'namespace', 'value')
                .values('kind', 'namespace', 'value'))


def row_identifiers(row, source):
    result = []
    if row.get('external_id'):
        result.append({'kind': 'external', 'namespace': str(source.pk), 'value': row['external_id']})
    if row.get('barcode'):
        result.append({'kind': 'barcode', 'namespace': 'global', 'value': row['barcode']})
    return result


def grouped_rows(rows):
    groups = defaultdict(list)
    for row in rows:
        key = ('external', row['external_id']) if row['external_id'] else (
            ('barcode', row['barcode']) if row['barcode'] else ('identity', json.dumps(identity(row), sort_keys=True)))
        groups[key].append(row)
    result, duplicates = [], 0
    for entries in groups.values():
        row = deepcopy(entries[0])
        duplicates += len(entries) - 1
        row['locations'] = [f"{item['sheet']}, {item['row']}" for item in entries]
        row['categories'] = sorted({name for item in entries for name in item['categories']})
        values = {json.dumps({**identity(item), **{key: item.get(key, '') for key in
                             ('price', 'sku', 'barcode')}}, sort_keys=True)
                  for item in entries}
        row['conflict'] = 'Дубли одного товара содержат разные цены или реквизиты' if len(values) > 1 else ''
        result.append(row)
    return result, duplicates


def prepare_plan(parsed, source, category_policy='add', decisions=None, category_map=None):
    decisions, category_map = decisions or {}, category_map or {}
    products = {item.pk: item for item in Product.objects.prefetch_related('categories')}
    members = {item.product_id: item for item in SourceProduct.objects.filter(source=source)}
    identifiers, ids_by_product, external_products = {}, defaultdict(list), set()
    for item in ProductIdentifier.objects.order_by('kind', 'namespace', 'value'):
        identifiers[(item.kind, item.namespace, item.value)] = item.product_id
        ids_by_product[item.product_id].append({'kind': item.kind, 'namespace': item.namespace, 'value': item.value})
        if item.kind == 'external' and item.namespace == str(source.pk):
            external_products.add(item.product_id)
    by_sku = {item.sku: item.pk for item in products.values()}
    by_identity, by_name = defaultdict(set), defaultdict(set)
    for product in products.values():
        known = members.get(product.pk)
        row_identity = known.identity if known else identity({'name': product.name, 'unit': product.unit})
        by_identity[json.dumps(row_identity, sort_keys=True)].add(product.pk)
        by_name[normalized(product.name)].add(product.pk)
    categories = list(Category.objects.all())
    valid_category_ids = {str(item.pk) for item in categories}
    category_labels = {item.pk: item.name for item in categories}
    other_managed = defaultdict(set)
    for member in SourceProduct.objects.exclude(source=source):
        other_managed[member.product_id].update(member.managed_categories)
    previous = CatalogImport.objects.filter(source=source, status=CatalogImport.Status.APPLIED).first()
    saved_mapping = previous.plan.get('category_map', {}) if previous else {}
    names = sorted({name for row in parsed['products'] for name in row['categories']})
    mappings = {}
    for name in names:
        found = [item.pk for item in categories if normalized(item.name) == normalized(name)]
        target = category_map.get(name, saved_mapping.get(name, str(found[0]) if len(found) == 1 else ''))
        if target not in valid_category_ids | {'', 'new', 'ignore'}:
            target = ''
        # A new spelling may need a category; an already existing category must
        # be selected rather than duplicated under the same normalized name.
        mappings[name] = str(found[0]) if target == 'new' and len(found) == 1 else target
    rows, duplicates = grouped_rows(parsed['products'])
    repeated_codes = defaultdict(list)
    for row in rows:
        for field in ('barcode', 'sku'):
            if row[field]:
                repeated_codes[(field, row[field])].append(row)
    for entries in repeated_codes.values():
        if len(entries) > 1:
            for row in entries:
                row['conflict'] = 'Один штрихкод / SKU указан у строк с разными кодами товара; исправьте файл или пропустите лишние строки'
    used, current = set(), set()
    counters = dict(total=parsed['total'], matched=0, new=0, prices=0, names=0, categories=0,
                    units=0, reactivated=0, duplicates=duplicates, errors=len(parsed['errors']), ambiguous=0, skipped=0)
    for index, row in enumerate(rows):
        row['key'] = str(index)
        decision = decisions.get(str(index), {})
        is_kg = row['unit'] == 'kg'
        row['min_quantity'] = decision.get('min_quantity', '.500' if is_kg else '1.000')
        row['quantity_step'] = decision.get('quantity_step', '.100' if is_kg else '1.000')
        strong = {identifiers[(key['kind'], key['namespace'], key['value'])]
                  for key in row_identifiers(row, source) if (key['kind'], key['namespace'], key['value']) in identifiers}
        if row['sku'] in by_sku:
            strong.add(by_sku[row['sku']])
        candidates = by_identity.get(json.dumps(identity(row), sort_keys=True), set())
        reason = 'Внешний код / штрихкод / внутренний SKU' if strong else 'Точное название, производитель, фасовка и единица'
        matched = next(iter(strong)) if len(strong) == 1 else (next(iter(candidates)) if len(candidates) == 1 else None)
        problem = row['conflict']
        if len(strong) > 1:
            problem = 'Код, SKU и штрихкод указывают на разные товары; исправьте файл'
        elif not strong and len(candidates) > 1:
            problem = 'Несколько точных совпадений: выберите товар вручную'
        elif not strong and matched and row['external_id'] and matched in external_products:
            problem = 'У точного совпадения другой код этого источника; проверьте вручную'
        if not matched and by_name.get(normalized(row['name'])):
            candidates = candidates | by_name[normalized(row['name'])]
            problem = problem or 'Совпало название, различаются реквизиты или единица; проверьте вручную'
        action = decision.get('action', 'auto')
        if action == 'skip':
            row.update(action='skip', reason='Пропущено при ручной проверке', product_id=None)
            counters['skipped'] += 1
            continue
        # Conflicting source identifiers and conflicting duplicate payloads cannot
        # be made safe by selecting an arbitrary product; skip or correct the file.
        hard_error = bool(row['conflict'] or len(strong) > 1)
        if action == 'link' and not hard_error:
            matched = decision.get('product_id')
            if matched not in products:
                problem = 'Выбранный товар не найден'
            elif strong and matched not in strong:
                problem = 'Ручной выбор противоречит постоянному идентификатору'
            else:
                problem, reason = '', 'Подтверждено вручную'
        elif action == 'create' and not hard_error:
            if strong:
                problem = 'Этот идентификатор уже связан с товаром'
            else:
                matched, problem, reason = None, '', 'Новый товар подтверждён вручную'
        row.update(candidates=sorted(candidates | strong), reason=reason, product_id=matched)
        if matched in used:
            problem = 'Несколько строк с разными идентификаторами сопоставлены одному товару'
        if problem:
            row.update(action='error' if hard_error else 'ambiguous', reason=problem)
            counters['errors' if hard_error else 'ambiguous'] += 1
            continue
        if matched:
            used.add(matched)
            current.add(matched)
            product = products[matched]
            before = product_snapshot(product)
            row['before'] = before
            row['unit_changed'] = product.unit != row['unit']
            if not row['unit_changed']:
                row['min_quantity'], row['quantity_step'] = before['min_quantity'], before['quantity_step']
            row['membership_before'] = member_value(members.get(matched))
            row['identifiers_before'] = ids_by_product[matched]
            if product.unit != row['unit'] and not decision.get('confirm_unit'):
                row.update(action='ambiguous', reason='Смена кг ↔ шт: отдельно подтвердите единицу, минимум и шаг')
                counters['ambiguous'] += 1
                continue
            counters['matched'] += 1
            counters['prices'] += Decimal(row['price']) != product.price
            counters['names'] += row['name'] != product.name
            counters['units'] += row['unit'] != product.unit
            counters['reactivated'] += not product.is_active
            row['action'] = 'update'
        else:
            counters['new'] += 1
            row['action'] = 'create'
    missing = []
    if source and parsed['products']:
        for product_id, member in members.items():
            if member.is_current and product_id not in current:
                product = products[product_id]
                missing.append({'product_id': product_id, 'name': product.name, 'before': product_snapshot(product),
                                'membership_before': member_value(member),
                                'identifiers_before': ids_by_product[product_id]})
    counters['missing'] = len(missing)
    used_names = {name for row in rows if row['action'] != 'skip' for name in row['categories']}
    mappings = {name: value for name, value in mappings.items() if name in used_names}
    for row in rows:
        if row['action'] not in ('create', 'update'):
            continue
        before_ids = set(row.get('before', {}).get('categories', []))
        incoming = {int(mappings[name]) for name in row['categories'] if str(mappings[name]).isdigit()}
        managed = set((row.get('membership_before') or {}).get('managed_categories', []))
        removed = managed - incoming - other_managed[row.get('product_id')] if category_policy == 'sync_source' else set()
        after_ids = (before_ids - removed) | incoming
        row['category_before'] = sorted(category_labels[pk] for pk in before_ids)
        row['category_after'] = sorted([category_labels[pk] for pk in after_ids] +
                                      [name for name in row['categories'] if mappings[name] == 'new'] +
                                      [f'Требует сопоставления: {name}' for name in row['categories'] if not mappings[name]])
        if row['action'] == 'update' and row['category_before'] != row['category_after']:
            counters['categories'] += 1
    return {'input': parsed, 'rows': rows, 'summary': counters, 'missing': missing,
            'category_map': mappings, 'decisions': decisions,
            'category_snapshot': {str(item.pk): item.name for item in categories},
            'identity_signature': identity_signature(products.values()),
            'scope_snapshot': {str(key): member_value(item) for key, item in members.items()},
            'large_drop': bool(missing and (len(missing) >= 100 or len(missing) / max(len(members), 1) >= .2))}


def create_preview(file, source, mode, actor=None, category_policy='add', mapping=None):
    if mode not in CatalogImport.Mode.values or category_policy not in ('add', 'sync_source'):
        raise ImportProblem('Неизвестный режим импорта')
    file.seek(0, 2)
    if file.tell() > 10 * 1024 * 1024:
        raise ImportProblem('Максимальный размер файла — 10 МБ')
    file.seek(0)
    digest = sha256(file.read()).hexdigest()
    error = ''
    try:
        parsed = read_excel(file, source.sheet_mapping if mapping is None else mapping)
    except Exception as exc:
        error = str(exc)[:2000]
        parsed = {'products': [], 'errors': [{'sheet': '', 'row': 0, 'name': '', 'error': error}],
                  'sheets': [], 'total': 0}
    plan = prepare_plan(parsed, source, category_policy)
    if error:
        plan['read_failed'] = True
    return CatalogImport.objects.create(source=source, filename=Path(file.name).name[:255], file_sha256=digest,
        mode=mode, category_policy=category_policy, uploaded_by=actor,
        plan=plan, error=error, status=CatalogImport.Status.FAILED if error else CatalogImport.Status.REVIEW)


@transaction.atomic
def revise_preview(batch_id, version, decisions=None, category_map=None):
    batch = CatalogImport.objects.select_for_update().select_related('source').get(pk=batch_id)
    if batch.status not in (CatalogImport.Status.REVIEW, CatalogImport.Status.FAILED) or batch.version != version:
        raise ImportProblem('Предпросмотр уже изменён. Обновите страницу')
    if batch.plan.get('read_failed'):
        raise ImportProblem('Файл не прочитан. Загрузите исправленный Excel заново')
    batch.plan = prepare_plan(batch.plan['input'], batch.source, batch.category_policy,
                              decisions if decisions is not None else batch.plan['decisions'],
                              category_map if category_map is not None else batch.plan['category_map'])
    batch.version += 1
    batch.status, batch.error = CatalogImport.Status.REVIEW, ''
    batch.save(update_fields=['plan', 'version', 'status', 'error'])
    return batch


def backup_database(batch, operation):
    """Fail closed if a durable backup cannot be made before a catalogue write."""
    database = str(connection.settings_dict['NAME'])
    if database == ':memory:' or 'mode=memory' in database:
        return 'in-memory test database'
    directory = Path(settings.BASE_DIR) / 'backups' / 'price-imports'
    directory.mkdir(parents=True, exist_ok=True)
    destination = directory / f'{batch.pk}-{operation}-{uuid.uuid4().hex[:8]}'
    if connection.vendor == 'sqlite':
        destination = destination.with_suffix('.sqlite3')
        with sqlite3.connect(f'{Path(database).resolve().as_uri()}?mode=ro', uri=True) as source:
            with sqlite3.connect(destination) as target:
                source.backup(target)
    else:
        # A portable catalogue backup; order tables are never mutated by imports.
        from django.core import serializers
        destination = destination.with_suffix('.json')
        objects = [*Category.objects.all(), *Product.objects.prefetch_related('categories'),
                   *SourceProduct.objects.all(), *ProductIdentifier.objects.all()]
        destination.write_text(serializers.serialize('json', objects), encoding='utf-8')
    return str(destination)


def _assert_unchanged(entry, source):
    product = Product.objects.select_for_update().filter(pk=entry['product_id']).first()
    if not product or product_snapshot(product) != entry['before'] or \
       membership_snapshot(source, product.pk) != entry['membership_before'] or \
       identifier_snapshot(product.pk) != entry['identifiers_before']:
        raise ImportProblem(f"Товар #{entry['product_id']} изменился после просмотра. Пересчитайте предпросмотр")
    return product


def _set_membership(source, product, value):
    if value is None:
        SourceProduct.objects.filter(source=source, product=product).delete()
    else:
        SourceProduct.objects.update_or_create(source=source, product=product, defaults=value)


def _record(batch, product, before, member_before, identifiers_before):
    return {'product_id': product.pk, 'before': before, 'after': product_snapshot(product),
            'membership_before': member_before, 'membership_after': membership_snapshot(batch.source, product.pk),
            'identifiers_before': identifiers_before, 'identifiers_after': identifier_snapshot(product.pk)}


def apply_import(batch_id, version, actor=None, *, confirm=False, archive_missing=False,
                 reviewed_drop=False, accept_errors=False):
    batch = CatalogImport.objects.select_related('source').get(pk=batch_id)
    if not confirm:
        raise ImportProblem('Подтвердите применение прайса')
    if batch.version != version or batch.status != CatalogImport.Status.REVIEW:
        raise ImportProblem('Этот предпросмотр уже применён, изменён или требует пересчёта')
    plan, summary = batch.plan, batch.plan['summary']
    if summary['ambiguous'] or any(row['action'] == 'error' for row in plan['rows']):
        raise ImportProblem('Сначала разберите неоднозначные совпадения и конфликтующие дубли')
    if summary['errors'] and not accept_errors:
        raise ImportProblem('Исправьте ошибки или явно разрешите частичное применение корректных строк')
    if not any(row['action'] in ('create', 'update') for row in plan['rows']):
        raise ImportProblem('Нет корректных строк для применения')
    if any(value == '' for value in plan['category_map'].values()):
        raise ImportProblem('Сопоставьте новые категории, подтвердите создание или пропуск')
    if archive_missing and batch.mode != CatalogImport.Mode.FULL:
        raise ImportProblem('Архивация доступна только при полном импорте')
    if archive_missing and (summary['errors'] or summary['skipped']):
        raise ImportProblem('Архивация запрещена для файла с ошибками или пропущенными строками')
    if batch.mode == CatalogImport.Mode.FULL and plan['large_drop'] and not reviewed_drop:
        raise ImportProblem('Ассортимент существенно сократился. Сначала подтвердите ручную проверку')
    backup = ''
    try:
        backup = backup_database(batch, 'apply')
        with transaction.atomic():
            batch = CatalogImport.objects.select_for_update().select_related('source').get(pk=batch_id)
            # Serialize imports for the same source, including its membership set.
            list(type(batch.source).objects.select_for_update().order_by('pk'))
            if batch.status != CatalogImport.Status.REVIEW or batch.version != version:
                raise ImportProblem('Предпросмотр уже изменён или применён')
            actual_scope = {str(item.product_id): member_value(item) for item in SourceProduct.objects.filter(source=batch.source)}
            if actual_scope != plan['scope_snapshot']:
                raise ImportProblem('Ассортимент источника изменился после просмотра. Пересчитайте предпросмотр')
            if {str(item.pk): item.name for item in Category.objects.all()} != plan['category_snapshot']:
                raise ImportProblem('Справочник категорий изменился. Пересчитайте предпросмотр')
            if any(row['action'] == 'create' for row in plan['rows']) and identity_signature(
                Product.objects.select_for_update().only('id', 'name', 'unit')
            ) != plan['identity_signature']:
                raise ImportProblem('Состав или названия каталога изменились. Пересчитайте предпросмотр перед добавлением товаров')
            existing = {row['product_id']: _assert_unchanged(row, batch.source) for row in plan['rows']
                        if row['action'] == 'update'}
            missing_products = {row['product_id']: _assert_unchanged(row, batch.source) for row in plan['missing']} if archive_missing else {}
            category_ids = {}
            for name, target in plan['category_map'].items():
                if target == 'ignore':
                    category_ids[name] = None
                elif target == 'new':
                    same = next((pk for label, pk in category_ids.items() if pk and normalized(label) == normalized(name)), None)
                    category_ids[name] = same or Category.objects.create(name=name).pk
                else:
                    category_ids[name] = Category.objects.get(pk=int(target)).pk
            changes, applied_ids = [], {}
            for row in plan['rows']:
                if row['action'] not in ('create', 'update'):
                    continue
                product = existing.get(row.get('product_id'))
                before = product_snapshot(product) if product else None
                member_before = membership_snapshot(batch.source, product.pk) if product else None
                ids_before = identifier_snapshot(product.pk) if product else []
                if not product:
                    # Recheck new identities to avoid a stale preview creating a duplicate.
                    if Product.objects.filter(name=row['name'], unit=row['unit']).exists():
                        if plan['decisions'].get(row['key'], {}).get('action') != 'create':
                            raise ImportProblem(f"Появился товар «{row['name']}». Пересчитайте предпросмотр")
                    product = Product(sku='BM-' + uuid.uuid4().hex[:16].upper())
                change_unit = product.unit != row['unit'] or before is None
                product.name, product.price, product.unit, product.is_active = row['name'], Decimal(row['price']), row['unit'], True
                if change_unit:
                    product.min_quantity, product.quantity_step = Decimal(row['min_quantity']), Decimal(row['quantity_step'])
                    if product.min_quantity <= 0 or product.quantity_step <= 0 or \
                       product.unit == 'pcs' and (product.min_quantity % 1 or product.quantity_step % 1):
                        raise ImportProblem('Проверьте минимум и шаг количества при смене единицы')
                product.full_clean(exclude=['image'])
                product.save()
                incoming = {category_ids[name] for name in row['categories'] if category_ids[name] is not None}
                previous_categories = set(before['categories']) if before else set()
                managed = set(member_before['managed_categories']) if member_before else set()
                if batch.category_policy == 'sync_source':
                    other_managed = set()
                    for other in SourceProduct.objects.filter(product=product).exclude(source=batch.source):
                        other_managed.update(other.managed_categories)
                    product.categories.remove(*(managed - incoming - other_managed))
                    managed &= incoming
                product.categories.add(*incoming)
                managed |= incoming - previous_categories
                _set_membership(batch.source, product, {'identity': identity(row), 'managed_categories': sorted(managed),
                                                        'is_current': True, 'last_import_id': str(batch.pk)})
                for identifier in row_identifiers(row, batch.source):
                    known, _ = ProductIdentifier.objects.get_or_create(**identifier, defaults={'product': product})
                    if known.product_id != product.pk:
                        raise ImportProblem('Идентификатор уже занят другим товаром. Пересчитайте предпросмотр')
                changes.append(_record(batch, product, before, member_before, ids_before))
                applied_ids[row['key']] = product.pk
            for row in plan['missing'] if archive_missing else []:
                product = missing_products[row['product_id']]
                member = deepcopy(row['membership_before'])
                member.update(is_current=False, last_import_id=str(batch.pk))
                _set_membership(batch.source, product, member)
                # Another current supplier/source may still list this product.
                if not SourceProduct.objects.filter(product=product, is_current=True).exists():
                    product.is_active = False
                    product.save(update_fields=['is_active'])
                changes.append(_record(batch, product, row['before'], row['membership_before'], row['identifiers_before']))
            # Reuse explicitly reviewed category aliases for the next price list.
            for row in batch.plan['rows']:
                if row['key'] in applied_ids:
                    row['product_id'] = applied_ids[row['key']]
            batch.plan['category_map'] = {name: ('ignore' if pk is None else str(pk)) for name, pk in category_ids.items()}
            batch.changes, batch.backup_path = changes, backup
            batch.status, batch.applied_at, batch.applied_by = CatalogImport.Status.APPLIED, timezone.now(), actor
            batch.save(update_fields=['changes', 'backup_path', 'status', 'applied_at', 'applied_by', 'plan'])
        return batch
    except Exception as exc:
        CatalogImport.objects.filter(pk=batch_id, status=CatalogImport.Status.REVIEW, version=version).update(
            status=CatalogImport.Status.FAILED, error=str(exc)[:2000], backup_path=backup)
        raise


def rollback_import(batch_id, actor=None, *, confirm=False):
    if not confirm:
        raise ImportProblem('Подтвердите откат каталожных изменений')
    batch = CatalogImport.objects.select_related('source').get(pk=batch_id)
    if batch.status != CatalogImport.Status.APPLIED:
        raise ImportProblem('Откат доступен только для применённого импорта')
    backup = backup_database(batch, 'rollback')
    with transaction.atomic():
        batch = CatalogImport.objects.select_for_update().select_related('source').get(pk=batch_id)
        list(type(batch.source).objects.select_for_update().order_by('pk'))
        if batch.status != CatalogImport.Status.APPLIED:
            raise ImportProblem('Состояние импорта изменилось')
        products = {}
        for change in batch.changes:
            product = Product.objects.select_for_update().filter(pk=change['product_id']).first()
            if not product or product_snapshot(product) != change['after'] or \
               membership_snapshot(batch.source, product.pk) != change['membership_after'] or \
               identifier_snapshot(product.pk) != change['identifiers_after']:
                raise ImportProblem(f"Откат заблокирован: товар #{change['product_id']} изменён позже. Данные сохранены")
            # An import from a second source counts as a later edit even when its
            # price happens to be identical. Never invalidate its identifiers.
            if SourceProduct.objects.filter(product=product, last_import__applied_at__gt=batch.applied_at).exists():
                raise ImportProblem(f'Откат заблокирован: товар #{product.pk} обновлён другим импортом')
            if change['before'] and not Category.objects.filter(pk__in=change['before']['categories']).count() == len(change['before']['categories']):
                raise ImportProblem('Категории для восстановления удалены. Требуется ручная проверка')
            products[product.pk] = product
        for change in reversed(batch.changes):
            product, before = products[change['product_id']], change['before']
            if before is None:
                product.is_active = False
                product.save(update_fields=['is_active'])
            else:
                for key in MANAGED_FIELDS:
                    setattr(product, key, before[key])
                product.save(update_fields=MANAGED_FIELDS)
                product.categories.set(before['categories'])
            _set_membership(batch.source, product, change['membership_before'])
            old_ids = change['identifiers_before']
            for identifier in change['identifiers_after']:
                if identifier not in old_ids:
                    ProductIdentifier.objects.filter(product=product, **identifier).delete()
        batch.status, batch.rolled_back_at, batch.rolled_back_by = CatalogImport.Status.ROLLED_BACK, timezone.now(), actor
        batch.backup_path += '\n' + backup
        batch.save(update_fields=['status', 'rolled_back_at', 'rolled_back_by', 'backup_path'])
    return batch
