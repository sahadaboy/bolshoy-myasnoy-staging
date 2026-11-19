import { useEffect, useState } from 'react';
import { ShoppingBasket } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { useProduct } from '../hooks/useCatalog';
import { useCart } from '../context/CartContext';
import {
  formatMoney,
  lineTotal,
  minQuantity,
  normalizeQuantity,
  priceKopecks,
  stepQuantity,
} from '../lib/quantity';
import { ProductImage } from '../components/ProductImage';
import { QuantityControl } from '../components/QuantityControl';
import { ErrorState, LoadingGrid } from '../components/States';
import { BackLink } from '../components/Retail';

export function ProductPage() {
  const { id } = useParams();
  const { product, loading, error, retry } = useProduct(id);
  const cart = useCart();
  const { syncProducts } = cart;
  const [draft, setDraft] = useState(0);
  const [notice, setNotice] = useState('');
  useEffect(() => {
    if (product) {
      setDraft(minQuantity(product));
      syncProducts([product]);
    }
  }, [product, syncProducts]);
  const inCart = product ? cart.getQuantity(product.id) : 0;
  return (
    <>
      <BackLink />
      {loading ? (
        <LoadingGrid count={2} />
      ) : error || !product ? (
        <ErrorState retry={retry} message={error || 'Товар не найден.'} />
      ) : (
        <article className="retail-product-detail">
          <ProductImage product={product} large />
          <div className="retail-chips">
            {product.categories.map((category) => (
              <Link key={category.id} to={`/catalog?category=${category.id}`}>
                {category.name}
              </Link>
            ))}
          </div>
          <h1>{product.name}</h1>
          <p className="retail-subtitle">{product.is_available ? 'В каталоге · наличие подтвердит сотрудник' : 'Недоступен для заявки'}</p>
          <p className="retail-detail-price">
            {formatMoney(priceKopecks(product))}
            <span>/{product.unit === 'kg' ? 'кг' : 'шт'}</span>
          </p>
          {product.is_available && minQuantity(product) > 0 ? (
            <>
              <div className="retail-detail-quantity">
                <span>{inCart ? 'В корзине' : product.unit === 'kg' ? 'Вес' : 'Количество'}</span>
                <QuantityControl
                  product={product}
                  quantity={inCart || draft}
                  removable={!!inCart}
                  onDecrease={() =>
                    inCart
                      ? cart.decrease(product)
                      : setDraft((value) =>
                          normalizeQuantity(product, value - stepQuantity(product)),
                        )
                  }
                  onIncrease={() =>
                    inCart
                      ? cart.increase(product)
                      : setDraft((value) =>
                          normalizeQuantity(product, value + stepQuantity(product)),
                        )
                  }
                />
              </div>
              {inCart ? (
                <Link className="button button-primary" to="/cart">
                  Перейти в корзину <ShoppingBasket size={19} />
                </Link>
              ) : (
                <button
                  className="button button-primary retail-detail-add"
                  onClick={() => {
                    if (!cart.add(product, draft))
                      setNotice(
                        'Не удалось добавить выбранное количество. Измените количество и попробуйте снова.',
                      );
                  }}
                >
                  <ShoppingBasket size={19} />В корзину
                  <strong>{formatMoney(lineTotal(product, draft))}</strong>
                </button>
              )}
            </>
          ) : (
            <p className="inline-notice">
              {product.is_available
                ? 'Количество этого товара уточняется в магазине.'
                : 'Товар временно недоступен для заказа.'}
            </p>
          )}
          {notice && (
            <p role="alert" className="inline-notice">
              {notice}
            </p>
          )}
          {product.description && (
            <section>
              <h2>О товаре</h2>
              <p>{product.description}</p>
            </section>
          )}
          <p className="retail-sku">Артикул {product.sku}</p>
        </article>
      )}
    </>
  );
}
