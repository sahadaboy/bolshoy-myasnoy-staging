from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
import re

CENT = Decimal('0.01')


def valid_quantity(product, quantity):
    try:
        q = Decimal(str(quantity))
        return q.is_finite() and 0 < q <= Decimal('999999.999') and q.as_tuple().exponent >= -3 and product.min_quantity > 0 and product.quantity_step > 0 and q >= product.min_quantity and (q - product.min_quantity) % product.quantity_step == 0 and (product.unit == 'kg' or product.unit == 'pcs' and q == q.to_integral_value())
    except (InvalidOperation, ValueError, TypeError):
        return False


def line_total(price, quantity):
    return (price * quantity).quantize(CENT, rounding=ROUND_HALF_UP)
