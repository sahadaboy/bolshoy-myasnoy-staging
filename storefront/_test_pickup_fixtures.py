from .models import StoreProfile, StoreOpeningInterval
from .pickup import slots

def schedule():
    store,_=StoreProfile.objects.get_or_create(pk=1)
    store.schedule_configured=True;store.preparation_minutes=60;store.save()
    StoreOpeningInterval.objects.filter(store=store).delete()
    StoreOpeningInterval.objects.bulk_create([StoreOpeningInterval(store=store,weekday=d,opens='08:00',closes='19:00' if d==2 else '20:00') for d in range(7)])
    return store


def available_pickup():
    if not StoreOpeningInterval.objects.exists(): schedule()
    return next(s['at'] for s in slots()['days'][1]['slots'] if s['available'])
