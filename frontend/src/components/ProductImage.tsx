import { useState } from 'react';
import { ShoppingBasket } from 'lucide-react';
import { productImageUrl } from '../lib/api';
import type { Product } from '../types';

export function ProductImage({ product, large = false }: { product: Product; large?: boolean }) {
  const [failedImage, setFailedImage] = useState<string | null>(null);
  const source = product.image;
  const imageUrl = productImageUrl(source);
  return (
    <div className={`product-picture ${large ? 'large' : ''}`}>
      {imageUrl && failedImage !== source ? (
        <img
          src={imageUrl}
          alt={product.name}
          width="480"
          height="480"
          loading={large ? 'eager' : 'lazy'}
          onError={() => setFailedImage(source)}
        />
      ) : (
        <span className="product-placeholder" role="img" aria-label="Фотография отсутствует">
          <ShoppingBasket size={large ? 52 : 36} strokeWidth={1} aria-hidden="true" />
        </span>
      )}
    </div>
  );
}
