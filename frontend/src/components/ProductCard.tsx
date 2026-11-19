import { memo } from 'react';
import { Plus } from 'lucide-react';
import { Link, useLocation } from 'react-router-dom';
import { useCart } from '../context/CartContext';
import { formatMoney, minQuantity, priceKopecks } from '../lib/quantity';
import { ProductImage } from './ProductImage';
import { QuantityControl } from './QuantityControl';
import type { Product } from '../types';

const CardView = memo(function CardView({
  product,
  quantity,
  add,
  increase,
  decrease,
  from,
}: {
  product: Product;
  quantity: number;
  add: (p: Product) => boolean;
  increase: (p: Product) => boolean;
  decrease: (p: Product) => boolean;
  from: string;
}) {
  const available = product.is_available && minQuantity(product) > 0;
  return (
    <article className="rp-product">
      <Link
        to={`/product/${product.id}`}
        state={{ from }}
        className="rp-product-photo"
        aria-label={`Подробнее: ${product.name}`}
      >
        <ProductImage product={product} />
      </Link>
      <div className={`rp-product-purchase${quantity > 0 ? ' has-quantity' : ''}`}>
        <p className="rp-price">
          {formatMoney(priceKopecks(product))}
          <span>/{product.unit === 'kg' ? 'кг' : 'шт'}</span>
        </p>
        {available ? (
          quantity > 0 ? (
            <QuantityControl
              product={product}
              quantity={quantity}
              onDecrease={() => decrease(product)}
              onIncrease={() => increase(product)}
            />
          ) : (
            <button
              className="rp-add"
              aria-label={`В корзину: ${product.name}`}
              onClick={() => add(product)}
            >
              <Plus size={22} strokeWidth={1.7} />
            </button>
          )
        ) : (
          <span className="retail-unavailable">
            {product.is_available ? 'Уточните в магазине' : 'Нет в наличии'}
          </span>
        )}
      </div>
      <Link to={`/product/${product.id}`} state={{ from }} className="rp-product-name">
        {product.name}
      </Link>
    </article>
  );
});

export function ProductCard({ product }: { product: Product }) {
  const { getQuantity, add, increase, decrease } = useCart();
  const location = useLocation();
  return (
    <CardView
      product={product}
      quantity={getQuantity(product.id)}
      add={add}
      increase={increase}
      decrease={decrease}
      from={location.pathname + location.search}
    />
  );
}
