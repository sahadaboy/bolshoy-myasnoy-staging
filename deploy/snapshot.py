"""Private, ID-preserving Django fixtures; includes automatic M2M row IDs."""
import hashlib
import json
from pathlib import Path, PurePosixPath
from django.apps import apps
from django.core import serializers
from django.core.management import call_command
from django.db import connections, transaction
from django.db.models import FileField


def sha256(path):
    with Path(path).open('rb') as source:
        return hashlib.file_digest(source, 'sha256').hexdigest()


def models():
    result = []
    for model in apps.get_models(include_auto_created=True):
        meta = model._meta
        owner = meta.auto_created if meta.auto_created else model
        if meta.app_label in ('shop', 'storefront') or (meta.app_label == 'auth' and owner._meta.model_name in ('user', 'group')):
            result.append(model)
    return sorted(result, key=lambda m: m._meta.label_lower)


def records(using='default'):
    result = []
    for model in models():
        # Explicit through objects below preserve PKs; never let the deserializer
        # silently recreate join rows from a normal M2M list.
        fields = [field.name for field in model._meta.concrete_fields if not field.primary_key]
        raw = serializers.serialize('json', model._default_manager.using(using).order_by('pk'),
                                    fields=fields, use_natural_foreign_keys=True)
        result.extend(json.loads(raw))
    return result


def digest(data):
    return hashlib.sha256(json.dumps(data, ensure_ascii=False, sort_keys=True, separators=(',', ':')).encode()).hexdigest()


def media_key(value):
    path = PurePosixPath(value)
    if (not value or '\\' in value or path.is_absolute() or len(path.parts) < 2
            or path.parts[0] not in ('products', 'storefront_uploads')
            or any(part.startswith('.') for part in path.parts)
            or path.suffix.lower() not in ('.png', '.jpg', '.jpeg', '.webp', '.avif')):
        raise ValueError('Unsafe or unsupported media key in snapshot.')
    return path.as_posix()


def write_snapshot(folder, media_root, using='default'):
    import shutil
    folder, media_root = Path(folder), Path(media_root).resolve()
    data = records(using)
    fixture = folder / 'data.json'
    fixture.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    counts = {m._meta.label_lower: m._default_manager.using(using).count() for m in models()}
    image_names = set()
    for model in models():
        for field in model._meta.concrete_fields:
            if isinstance(field, FileField):
                image_names.update(str(value) for value in model._default_manager.using(using).values_list(field.name, flat=True) if value)
    # Keep unused uploaded images too; a migration must not discard older media.
    for directory in ('products', 'storefront_uploads'):
        if (media_root / directory).is_dir():
            image_names.update(path.relative_to(media_root).as_posix() for path in (media_root / directory).rglob('*')
                               if path.is_file() and path.suffix.lower() in ('.png', '.jpg', '.jpeg', '.webp', '.avif'))
    media = []
    for name in sorted(image_names):
        key = media_key(name)
        source = (media_root / key).resolve()
        if not source.is_relative_to(media_root) or not source.is_file():
            raise ValueError('A referenced media file is missing. Nothing may be silently dropped.')
        from PIL import Image
        with Image.open(source) as image:
            image.verify()
        destination = folder / 'media' / key
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source, destination)
        media.append({'key': key, 'size': source.stat().st_size, 'sha256': sha256(source)})
    manifest = {'format': 1, 'fixture_sha256': sha256(fixture), 'records_sha256': digest(data), 'counts': counts, 'media': media}
    (folder / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding='utf-8')
    return manifest


def read_snapshot(folder):
    folder = Path(folder).resolve()
    manifest = json.loads((folder / 'manifest.json').read_text(encoding='utf-8'))
    if manifest.get('format') != 1 or sha256(folder / 'data.json') != manifest['fixture_sha256']:
        raise ValueError('Snapshot checksum or format is invalid.')
    data = json.loads((folder / 'data.json').read_text(encoding='utf-8'))
    allowed = {m._meta.label_lower for m in models()}
    if any(row.get('model') not in allowed for row in data) or digest(data) != manifest['records_sha256']:
        raise ValueError('Snapshot contains unexpected models or data.')
    counts = {name: 0 for name in allowed}
    for row in data:
        counts[row['model']] += 1
    if counts != manifest['counts']:
        raise ValueError('Snapshot model counts do not match.')
    for item in manifest['media']:
        key = media_key(item['key'])
        file = (folder / 'media' / key).resolve()
        if not file.is_relative_to(folder / 'media') or file.stat().st_size != item['size'] or sha256(file) != item['sha256']:
            raise ValueError('Media checksum does not match.')
    return manifest


def restore_snapshot(folder, using='default'):
    manifest = read_snapshot(folder)
    connection = connections[using]
    with transaction.atomic(using=using):
        if any(model._default_manager.using(using).exists() for model in models()):
            raise ValueError('Target contains application data or users. Refusing to overwrite it.')
        call_command('loaddata', str(Path(folder).resolve() / 'data.json'), database=using, verbosity=0)
        if digest(records(using)) != manifest['records_sha256']:
            raise ValueError('Verification failed. The database import is rolled back.')
        # Explicitly include auto-created through tables when repairing PG sequences.
        from django.core.management.color import no_style
        for sql in connection.ops.sequence_reset_sql(no_style(), models()):
            with connection.cursor() as cursor:
                cursor.execute(sql)
    return manifest
