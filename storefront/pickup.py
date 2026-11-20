"""Store-local calendar; the device's timezone is never an input."""
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
import re
from django.utils import timezone
from rest_framework.exceptions import ValidationError
from .models import StoreProfile

MOSCOW = ZoneInfo('Europe/Moscow')
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


def opening_text(profile):
    if not profile.schedule_configured: return profile.opening_hours
    intervals=list(profile.opening_intervals.all())
    return '\n'.join(f'{name}: '+(', '.join(f'{r.opens:%H:%M}–{r.closes:%H:%M}' for r in intervals if r.weekday==day) or 'Закрыто') for day,name in enumerate(DAYS))


def slots(profile=None, *, now=None):
    now=(now or timezone.now()).astimezone(MOSCOW)
    profile=profile or StoreProfile.objects.filter(pk=1).first()
    configured=bool(profile and profile.schedule_configured)
    minimum=now+timedelta(minutes=profile.preparation_minutes if profile else 60)
    rows=list(profile.opening_intervals.all()) if configured else []
    dates=[]
    for n in range(8):
        day=now.date()+timedelta(days=n); values=[]
        for row in rows:
            if row.weekday!=day.weekday(): continue
            moment=datetime.combine(day,row.opens,MOSCOW)
            # Global half-hour grid even if opening is at 08:15.
            moment=moment.replace(minute=(moment.minute//30)*30,second=0,microsecond=0)
            if moment.time()<row.opens: moment+=timedelta(minutes=30)
            close=datetime.combine(day,row.closes,MOSCOW)
            while moment<close:
                values.append({'at':moment.isoformat(),'time':moment.strftime('%H:%M'),'available':moment>=minimum})
                moment+=timedelta(minutes=30)
        dates.append({'date':day.isoformat(),'weekday':DAYS[day.weekday()],'slots':values})
    return {'timezone':'Europe/Moscow','generated_at':now.isoformat(),'preparation_minutes':profile.preparation_minutes if profile else 60,'configured':configured,'days':dates}


def validate_pickup(value, profile, *, now=None):
    if value is None:
        raise ValidationError({'pickup_at':'Обновите страницу оформления и выберите желаемую дату и время самовывоза.'})
    if timezone.is_naive(value): raise ValidationError({'pickup_at':'Укажите часовой пояс времени самовывоза.'})
    current=slots(profile,now=now)
    if not any(item['available'] and datetime.fromisoformat(item['at'])==value for day in current['days'] for item in day['slots']):
        raise ValidationError({'pickup_at':'Это время уже недоступно. Выберите другой интервал самовывоза.'})
    return value
