import { Minus, Plus, Trash2 } from 'lucide-react';
import { formatQuantity, minQuantity } from '../lib/quantity';
import type { Product } from '../types';

export function QuantityControl({
  product,
  quantity,
  onDecrease,
  onIncrease,
  removable = true,
  disabled = false,
}: {
  product: Product;
  quantity: number;
  onDecrease: () => void;
  onIncrease: () => void;
  removable?: boolean;
  disabled?: boolean;
}) {
  const atMinimum = quantity <= minQuantity(product);
  return (
    <div
      className={`quantity-control ${disabled ? 'disabled' : ''}`}
      aria-label={`Количество: ${product.name}`}
    >
      <button
        type="button"
        aria-label={
          atMinimum && removable
            ? `Удалить ${product.name} из корзины`
            : `Уменьшить количество ${product.name}`
        }
        onClick={onDecrease}
        disabled={disabled || (!removable && atMinimum)}
      >
        {atMinimum && removable ? (
          <Trash2 size={17} aria-hidden="true" />
        ) : (
          <Minus size={18} aria-hidden="true" />
        )}
      </button>
      <span key={quantity} className="quantity-value" aria-live="polite">
        {formatQuantity(quantity, product.unit)}
      </span>
      <button
        type="button"
        aria-label={`Увеличить количество ${product.name}`}
        onClick={onIncrease}
        disabled={disabled}
      >
        <Plus size={18} aria-hidden="true" />
      </button>
    </div>
  );
}
