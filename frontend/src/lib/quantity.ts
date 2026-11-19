import type { Product } from '../types';

const MAX_SAFE = BigInt(Number.MAX_SAFE_INTEGER);
const integerFormatter = new Intl.NumberFormat('ru-RU', { maximumFractionDigits: 0 });

/** Parse an API Decimal without converting its fractional part to a float. */
function scaledDecimal(value: string, precision: number): number {
  if (typeof value !== 'string' || !/^\d+(?:\.\d+)?$/.test(value)) return 0;
  const [whole, fraction = ''] = value.split('.');
  if (fraction.length > precision && /[1-9]/.test(fraction.slice(precision))) return 0;
  const scaled =
    BigInt(whole) * 10n ** BigInt(precision) +
    BigInt(fraction.slice(0, precision).padEnd(precision, '0'));
  return scaled <= MAX_SAFE ? Number(scaled) : 0;
}

export function priceKopecks(product: Pick<Product, 'price'>): number {
  return scaledDecimal(product.price, 2);
}

export function quantityThousandths(value: string): number {
  return scaledDecimal(value, 3);
}

function gcd(a: number, b: number): number {
  while (b !== 0) [a, b] = [b, a % b];
  return a;
}

function constraints(product: Product): { min: number; step: number } {
  const min = scaledDecimal(product.min_quantity, 3);
  const step = scaledDecimal(product.quantity_step, 3);
  if (min <= 0 || step <= 0) return { min: 0, step: 0 };
  if (product.unit === 'kg') return { min, step };
  if (product.unit !== 'pcs') return { min: 0, step: 0 };

  // A piece count must be an integer AND lie on the API's min + n × step lattice.
  const divisor = gcd(step, 1000);
  if (min % divisor !== 0) return { min: 0, step: 0 };
  const period = 1000 / divisor;
  for (let offset = 0; offset < period; offset += 1) {
    const candidate = BigInt(min) + BigInt(offset) * BigInt(step);
    if (candidate % 1000n === 0n) {
      const integerStep = BigInt(step) * BigInt(period);
      if (candidate > MAX_SAFE || integerStep > MAX_SAFE) return { min: 0, step: 0 };
      return { min: Number(candidate), step: Number(integerStep) };
    }
  }
  return { min: 0, step: 0 };
}

export function minQuantity(product: Product): number {
  return constraints(product).min;
}

export function stepQuantity(product: Product): number {
  return constraints(product).step;
}

/** Snap down to the valid lattice; positive values below the minimum become the minimum. */
export function normalizeQuantity(product: Product, quantity: number): number {
  if (!Number.isSafeInteger(quantity) || quantity <= 0) return 0;
  const { min, step } = constraints(product);
  if (!min || !step) return 0;
  const price = BigInt(priceKopecks(product));
  const maxForPrice = price > 0n ? (MAX_SAFE * 1000n) / price : MAX_SAFE;
  const limit = Number(maxForPrice < MAX_SAFE ? maxForPrice : MAX_SAFE);
  if (limit < min) return 0;
  const bounded = Math.min(Math.max(quantity, min), limit);
  return min + Math.floor((bounded - min) / step) * step;
}

/** Return 0 if adding two valid quantities cannot preserve the exact API lattice. */
export function addQuantities(product: Product, current: number, added: number): number {
  if (!Number.isSafeInteger(current) || current < 0 || !Number.isSafeInteger(added) || added <= 0)
    return 0;
  if (normalizeQuantity(product, added) !== added) return 0;
  if (current && normalizeQuantity(product, current) !== current) return 0;
  const combined = current + added;
  return Number.isSafeInteger(combined) && normalizeQuantity(product, combined) === combined
    ? combined
    : 0;
}

/** Round each line once, half up to a kopeck, as with Decimal.quantize('0.01'). */
export function lineTotal(product: Pick<Product, 'price'>, quantity: number): number {
  if (!Number.isSafeInteger(quantity) || quantity < 0) return 0;
  const kopecks = (BigInt(priceKopecks(product)) * BigInt(quantity) + 500n) / 1000n;
  if (kopecks > MAX_SAFE) throw new RangeError('Стоимость превышает безопасный диапазон');
  return Number(kopecks);
}

export function formatMoney(kopecks: number): string {
  if (!Number.isSafeInteger(kopecks) || kopecks < 0) return '0 ₽';
  const amount = BigInt(kopecks);
  const fraction = amount % 100n;
  return `${integerFormatter.format(amount / 100n)}${fraction ? `,${fraction.toString().padStart(2, '0')}` : ''} ₽`;
}

export function formatQuantity(quantity: number, unit?: Product['unit']): string {
  if (!Number.isSafeInteger(quantity) || quantity < 0)
    return unit ? `0 ${unit === 'kg' ? 'кг' : 'шт'}` : '0';
  const amount = BigInt(quantity);
  const fraction = (amount % 1000n).toString().padStart(3, '0').replace(/0+$/, '');
  const text = `${integerFormatter.format(amount / 1000n)}${fraction ? `,${fraction}` : ''}`;
  return `${text}${unit ? ` ${unit === 'kg' ? 'кг' : 'шт'}` : ''}`;
}
