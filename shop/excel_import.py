"""Bounded XLSX reader. Never writes catalogue data or evaluates formulas."""
from decimal import Decimal, InvalidOperation
import re
import unicodedata
from zipfile import BadZipFile, ZipFile

from openpyxl import load_workbook
from openpyxl.utils.cell import column_index_from_string

CATEGORY_NAMES = {
    'Бакалея вес': 'Бакалея', 'Бакалея шт': 'Бакалея',
    'Сыр вес': 'Сыры', 'Сыр шт': 'Сыры', 'Безалко': 'Безалкогольные напитки',
    'Вода': 'Вода', 'Молочная продукция': 'Молочная продукция',
    'Морепродукты шт': 'Морепродукты', 'Приправы': 'Приправы',
    'Рыба копч': 'Рыба копчёная', 'Рыба см': 'Рыба свежемороженая',
    'Соки': 'Соки', 'Сушка вес': 'Сухофрукты и орехи',
}
ALIASES = {
    'name': ['наименование', 'наименованиетовара', 'название', 'названиетовара', 'товар', 'name', 'product'],
    'price': ['цена', 'ценаруб', 'ценар', 'ценазакгшт', 'ценаза1кгшт', 'price', 'розничнаяцена'],
    'unit': ['ед', 'едизм', 'едизмер', 'единица', 'единицаизмерения', 'единицапродажи', 'unit'],
    'external_id': ['код', 'кодтовара', 'внешнийкод', 'артикул', 'артикулпоставщика', 'externalid', 'id'],
    'sku': ['внутреннийартикул', 'sku'], 'barcode': ['штрихкод', 'штриховойкод', 'barcode', 'gtin', 'ean'],
    'manufacturer': ['производитель', 'бренд', 'manufacturer', 'brand'],
    'package': ['фасовка', 'упаковка', 'package', 'pack'],
    'category': ['категория', 'группа', 'category'],
}


class ImportProblem(ValueError):
    pass


def clean_name(value):
    return ' '.join(unicodedata.normalize('NFKC', '' if value is None else str(value)).split())


def normalized(value):
    return clean_name(value).casefold()


def identity(row):
    return {key: normalized(row.get(key)) for key in ('name', 'manufacturer', 'package', 'unit')}


def parse_price(value):
    if value is None or isinstance(value, bool):
        raise ImportProblem('Цена отсутствует или неверна')
    text = re.sub(r'\s+', '', str(value)).replace(',', '.')
    text = re.sub(r'(?:₽|руб\.?|р\.)$', '', text, flags=re.I)
    try:
        price = Decimal(text)
        if not price.is_finite() or price < 0 or price > Decimal('9999999999.99'):
            raise InvalidOperation
        if price != price.quantize(Decimal('.01')):
            raise ImportProblem('У цены больше двух знаков после запятой')
        return format(price, '.2f')
    except (InvalidOperation, ValueError):
        raise ImportProblem('Некорректная или отрицательная цена') from None


def parse_barcode(value):
    if value in (None, ''):
        return ''
    if isinstance(value, bool) or isinstance(value, float) and not value.is_integer():
        raise ImportProblem('Штрихкод должен быть целым числом или текстом')
    text = str(int(value)) if isinstance(value, (int, float)) else clean_name(value)
    if not re.fullmatch(r'(?:\d{8}|\d{12,14})', text, flags=re.ASCII) or not int(text):
        raise ImportProblem('Нужен GTIN из 8, 12, 13 или 14 цифр; ведущие нули храните как текст')
    checksum = sum(int(digit) * (3 if index % 2 == 0 else 1)
                   for index, digit in enumerate(reversed(text[:-1])))
    if (10 - checksum % 10) % 10 != int(text[-1]):
        raise ImportProblem('Неверная контрольная цифра штрихкода')
    return text


def validate_mapping(mapping):
    if not isinstance(mapping, dict) or len(mapping) > 50:
        raise ImportProblem('Настройки: объект с именами листов или ключом *')
    for sheet, config in mapping.items():
        if not isinstance(sheet, str) or not isinstance(config, dict):
            raise ImportProblem('Неверные настройки листа')
        if set(config) - {'header_row', 'columns', 'default_unit'}:
            raise ImportProblem('Допустимы header_row, columns, default_unit')
        header = config.get('header_row', 1)
        if isinstance(header, bool) or not isinstance(header, int) or not 1 <= header <= 20:
            raise ImportProblem('Строка заголовков должна быть от 1 до 20')
        if config.get('default_unit', '') not in ('', 'kg', 'pcs'):
            raise ImportProblem('default_unit: kg или pcs')
        columns = config.get('columns', {})
        if not isinstance(columns, dict) or set(columns) - ALIASES.keys():
            raise ImportProblem('Неизвестное поле в columns')
        indices = []
        for value in columns.values():
            try:
                index = column_index_from_string(value.upper()) if isinstance(value, str) else value
                if isinstance(index, bool) or not isinstance(index, int) or not 1 <= index <= 64:
                    raise ValueError
                indices.append(index)
            except (ValueError, AttributeError):
                raise ImportProblem('Колонки: буквы A–BL или числа 1–64') from None
        if len(indices) != len(set(indices)):
            raise ImportProblem('Одна колонка не может означать два поля')
    return mapping


def read_excel(file, mapping=None):
    mapping = validate_mapping(mapping or {})
    file.seek(0, 2)
    if file.tell() > 10 * 1024 * 1024:
        raise ImportProblem('Максимальный размер файла — 10 МБ')
    file.seek(0)
    try:
        with ZipFile(file) as archive:
            members = archive.infolist()
            if len(members) > 2000 or sum(item.file_size for item in members) > 80 * 1024 * 1024:
                raise ImportProblem('Excel превышает допустимый распакованный размер')
            if any('..' in item.filename.split('/') or item.filename.startswith('/') or
                   'vbaproject' in item.filename.lower() or 'externallinks/' in item.filename.lower()
                   for item in members):
                raise ImportProblem('Макросы и внешние ссылки в прайсе не поддерживаются')
            # The installed openpyxl runtime has no defusedxml. Reject DTD/entity
            # declarations before its XML parser is reached; scan across chunks.
            for item in members:
                if item.filename.lower().endswith(('.xml', '.rels')):
                    tail = b''
                    with archive.open(item) as stream:
                        while chunk := stream.read(65536):
                            content = (tail + chunk).upper()
                            if b'\x00' in chunk or b'<!DOCTYPE' in content or b'<!ENTITY' in content:
                                raise ImportProblem('XML с DTD, сущностями или неподдерживаемой кодировкой запрещён')
                            tail = content[-16:]
    except BadZipFile:
        raise ImportProblem('Файл не является корректным XLSX') from None
    file.seek(0)
    workbook = load_workbook(file, read_only=True, data_only=False, keep_links=False)
    products, errors, sheets = [], [], []
    total = 0
    try:
        if len(workbook.worksheets) > 50:
            raise ImportProblem('В прайсе больше 50 листов')
        for sheet in workbook.worksheets:
            if sheet.max_row and sheet.max_row > 20020 or sheet.max_column and sheet.max_column > 64:
                raise ImportProblem(f'{sheet.title}: не более 20 000 строк и 64 колонок')
            # Some exporters under-report worksheet dimensions. Read the actual
            # XML rows so a truncated preview cannot propose false absences.
            sheet.reset_dimensions()
            config = mapping.get(sheet.title, mapping.get('*', {}))
            explicit = config.get('columns')
            columns, header, column_error = {}, config.get('header_row', 0), ''
            iterator = sheet.iter_rows(max_col=64, values_only=True)
            for number, cells in enumerate(iterator, 1):
                if number > 20 and not columns:
                    break
                if explicit:
                    if number != (header or 1):
                        continue
                    columns = {key: (column_index_from_string(value.upper()) if isinstance(value, str) else value) - 1
                               for key, value in explicit.items()}
                    header = number
                    break
                tokens = [re.sub(r'[^\w]', '', normalized(cell)) for cell in cells]
                matches = {key: [index for index, token in enumerate(tokens) if token in aliases]
                           for key, aliases in ALIASES.items()}
                detected = {key: indices[0] for key, indices in matches.items() if indices}
                if 'name' in detected and 'price' in detected and (not header or header == number):
                    if any(len(indices) > 1 for indices in matches.values()):
                        column_error = 'Несколько колонок с одним назначением. Явно задайте нужные колонки.'
                        break
                    columns, header = detected, number
                    break
            default_unit = config.get('default_unit') or ('pcs' if sheet.title == 'Вода' else '')
            if not {'name', 'price'} <= columns.keys() or not ('unit' in columns or default_unit):
                errors.append({'sheet': sheet.title, 'row': 0, 'name': '',
                               'error': column_error or 'Не найдены колонки названия, цены и единицы. Настройте колонки листа.'})
                continue
            sheets.append({'name': sheet.title, 'header_row': header,
                           'columns': {key: value + 1 for key, value in columns.items()}, 'default_unit': default_unit})
            for number, cells in enumerate(iterator, header + 1):
                if number > 20020:
                    raise ImportProblem(f'{sheet.title}: строки выходят за предел 20 020')
                if not any(value not in (None, '') for value in cells):
                    continue
                total += 1
                if total > 20000:
                    raise ImportProblem('Во всём файле больше 20 000 строк товаров')
                raw = {key: cells[index] for key, index in columns.items()}
                try:
                    if any(isinstance(value, str) and value.lstrip().startswith('=') for value in raw.values()):
                        raise ImportProblem('Формулы запрещены: загрузите значения ячеек')
                    name = clean_name(raw.get('name'))
                    if not name or len(name) > 255:
                        raise ImportProblem('Название отсутствует или длиннее 255 символов')
                    unit = normalized(raw.get('unit') or default_unit)
                    unit = {'кг': 'kg', 'kg': 'kg', 'шт': 'pcs', 'шт.': 'pcs', 'pcs': 'pcs'}.get(unit)
                    if not unit:
                        raise ImportProblem('Единица продажи: кг или шт; фасовка не является единицей продажи')
                    data = {key: clean_name(raw.get(key)) for key in ('external_id', 'sku', 'manufacturer', 'package')}
                    if any(len(value) > 100 for value in data.values()):
                        raise ImportProblem('Код, производитель и фасовка: не более 100 символов')
                    category = clean_name(raw.get('category')) or CATEGORY_NAMES.get(sheet.title, sheet.title)
                    if len(category) > 150:
                        raise ImportProblem('Категория длиннее 150 символов')
                    products.append({**data, 'name': name, 'price': parse_price(raw.get('price')), 'unit': unit,
                                     'barcode': parse_barcode(raw.get('barcode')), 'categories': [category],
                                     'sheet': sheet.title, 'row': number})
                except ImportProblem as exc:
                    errors.append({'sheet': sheet.title, 'row': number,
                                   'name': clean_name(raw.get('name'))[:255], 'error': str(exc)})
    finally:
        workbook.close()
    return {'products': products, 'errors': errors, 'sheets': sheets, 'total': total}
