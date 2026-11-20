"""Bounded HTML fragments. Stored payloads are immutable after delivery starts."""
from html import escape
from zoneinfo import ZoneInfo

MOSCOW=ZoneInfo('Europe/Moscow')
def money(value): return f'{value:,.2f}'.replace(',',' ').replace('.',',')+' ₽'
def units(text): return len(text.encode('utf-16-le'))//2

def message_parts(order):
    number=escape(order.number)
    blocks=[f'🛒 <b>НОВЫЙ ЗАКАЗ</b>\n№ {number}\n\n',
        f'📅 <b>Забрать: {order.pickup_at.astimezone(MOSCOW):%d.%m.%Y в %H:%M}</b>\n\n' if order.pickup_at else '📅 Желаемое время: не указано\n\n',
        f'👤 <b>Покупатель:</b> {escape(order.buyer_name)}\n📞 <b>Телефон:</b> {escape(order.phone)}\n\n📦 <b>Состав заказа</b>\n']
    for item in order.items.all():
        quantity=f'{item.quantity.normalize():f}'.replace('.',',')
        blocks.append(f'• {escape(item.product_name)} — {quantity} {"кг" if item.unit=="kg" else "шт."} — {money(item.subtotal)}\n')
    blocks.append(f'\n💰 <b>Итого: {money(order.total)}</b>\n')
    if order.weight_estimate: blocks.append('Стоимость уточняется после фактического взвешивания.\n')
    if order.comment:
        blocks.append('\n<b>Комментарий:</b>\n')
        blocks.extend(escape(order.comment[i:i+300])+'\n' for i in range(0,len(order.comment),300))
    blocks.append(f'\n🕒 Заказ оформлен: {order.created_at.astimezone(MOSCOW):%d.%m.%Y в %H:%M}')
    parts=[]; current=''
    for block in blocks:
        if units(current+block)>3500:
            parts.append(current); current=f'ЗАКАЗ №{number} · продолжение\n\n'
        current+=block
    if current: parts.append(current)
    return parts
