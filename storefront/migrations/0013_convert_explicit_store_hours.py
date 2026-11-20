from datetime import time
import re
from django.db import migrations
DAYS = ['Понедельник','Вторник','Среда','Четверг','Пятница','Суббота','Воскресенье']

def parse_legacy_hours(text):
    """Only a complete, explicit, unambiguous seven-day schedule is importable."""
    result, seen = [], set()
    for line in text.strip().splitlines():
        parts = line.strip().split(':', 1)
        if len(parts)!=2 or parts[0].strip().capitalize() not in DAYS: return None
        day = DAYS.index(parts[0].strip().capitalize())
        if day in seen: return None
        seen.add(day); value=parts[1].strip()
        if value.lower() in ('выходной','закрыто'): continue
        for interval in value.split(','):
            match=re.fullmatch(r'\s*(\d{2}:\d{2})\s*[–—-]\s*(\d{2}:\d{2})\s*',interval)
            if not match: return None
            try: start,end=map(time.fromisoformat,match.groups())
            except ValueError: return None
            if start>=end or any(d==day and start<b and end>a for d,a,b in result): return None
            result.append((day,start,end))
    return result if len(seen)==7 else None


def convert(apps, schema_editor):
    Store=apps.get_model('storefront','StoreProfile')
    Interval=apps.get_model('storefront','StoreOpeningInterval')
    alias=schema_editor.connection.alias
    for store in Store.objects.using(alias).all():
        if store.schedule_configured or Interval.objects.using(alias).filter(store_id=store.pk).exists(): continue
        parsed=parse_legacy_hours(store.opening_hours)
        if parsed is None: continue  # Admin must explicitly configure ambiguous text.
        Interval.objects.using(alias).bulk_create([Interval(store_id=store.pk,weekday=day,opens=start,closes=end) for day,start,end in parsed])
        Store.objects.using(alias).filter(pk=store.pk).update(schedule_configured=True)

class Migration(migrations.Migration):
    dependencies=[('storefront','0012_pickup_schedule_and_acceptance')]
    operations=[migrations.RunPython(convert,migrations.RunPython.noop)]
