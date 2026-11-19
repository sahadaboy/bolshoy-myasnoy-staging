"""Small, reviewed navigation rules over existing category/name fields.

No product/category writes. Prefixes describe the product itself, not a flavour
mentioned later in its name (e.g. shrimp-flavoured peanuts are not shrimp).
"""
from dataclasses import dataclass
from django.db.models import Q


@dataclass(frozen=True)
class CatalogTag:
    slug: str
    label: str
    condition: Q


def starts(pattern):
    return Q(name__iregex=r'^(?:' + pattern + r')(?:\s|$)')


TAG_GROUPS = {
    'grocery': (
        CatalogTag('rice', 'Рис', starts('рис') | (starts('крупа') & Q(name__iregex=r'\sрис(?:\s|$)'))),
        CatalogTag('buckwheat', 'Гречка', starts('гречка|гречневая крупа') | (starts('крупа') & Q(name__iregex='греч'))),
        CatalogTag('oats', 'Овсянка', starts('хлопья|каша|крупа') & Q(name__iregex='овся')),
        CatalogTag('pasta', 'Макароны', starts('мак изд|макароны|макаронные изделия|спагетти|вермишель')),
        CatalogTag('bulgur', 'Булгур', starts('булгур') | (starts('крупа') & Q(name__iregex='булгур'))),
        CatalogTag('semolina', 'Манка', starts('манка') | (starts('крупа') & Q(name__iregex='манн'))),
    ),
    'seafood': (
        CatalogTag('shrimp', 'Креветки', Q(name__iregex=r'^креветк')),
        CatalogTag('mussels', 'Мидии', Q(name__iregex=r'^миди')),
        CatalogTag('squid', 'Кальмары', Q(name__iregex=r'^кальмар')),
        CatalogTag('fish', 'Рыба', starts('горбуша|сайра|сельдь|скумбрия|тунец|шпроты|бычки|килька|салака|анчоус|форель|сёмга|семга|лосось|сардина|сардины|сардинелла|ассорти рыб|ассорти рыбное')),
        CatalogTag('caviar', 'Икра', starts('икра|икорка')),
        CatalogTag('crab-sticks', 'Крабовые палочки', Q(name__iregex=r'^(?:краб\s+палоч|крабовые\s+палоч|палочки\s+краб)')),
    ),
    'dairy': (
        CatalogTag('milk', 'Молоко', starts('молоко') & ~Q(name__iregex=r'^молоко\s+сгущ')),
        CatalogTag('sour-cream', 'Сметана', Q(name__iregex=r'^сметан')),
        CatalogTag('cottage-cheese', 'Творог', starts('творог')),
        CatalogTag('kefir', 'Кефир', starts('кефир|биокефир')),
        CatalogTag('yogurt', 'Йогурты', Q(name__iregex=r'^(?:био)?йогурт')),
        CatalogTag('cream', 'Сливки', starts('сливки')),
    ),
}

CATEGORY_TAG_GROUPS = {
    'Бакалея': 'grocery', 'Крупы и бакалея': 'grocery',
    'Морепродукты': 'seafood', 'Рыба и морепродукты': 'seafood',
    'Молочная продукция': 'dairy',
}


def rules_for(category_name, group):
    # A concrete category takes precedence. Never add cheese/frozen fish from
    # another original category just to make a navigation chip nonempty.
    key = CATEGORY_TAG_GROUPS.get(category_name) if category_name is not None else group
    return TAG_GROUPS.get(key, ())
