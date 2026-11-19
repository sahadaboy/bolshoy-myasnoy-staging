import { ImageOff } from 'lucide-react';
import { Link } from 'react-router-dom';
import { useState } from 'react';
import { productImageUrl } from '../lib/api';
import type { ArticleCard } from '../types';

export function EditorialImage({ article }: { article: ArticleCard }) {
  const [failed, setFailed] = useState(false);
  const image = productImageUrl(article.image);
  return image && !failed ? (
    <img
      src={image}
      alt={article.title}
      width="720"
      height="430"
      loading="lazy"
      onError={() => setFailed(true)}
    />
  ) : (
    <span className="retail-editorial-placeholder">
      <ImageOff size={30} strokeWidth={1.3} />
    </span>
  );
}

export function RecipeCard({
  article,
  variant = 'recipe',
}: {
  article: ArticleCard;
  variant?: 'recipe' | 'topic' | 'feature';
}) {
  if (article.is_demo) return null;
  return (
    <Link
      className={`rp-${variant}${article.image ? '' : ' retail-text-recipe'}`}
      to={`/ideas/article/${article.slug}`}
    >
      {article.image && <EditorialImage article={article} />}
      {variant === 'feature' ? (
        <span className="rp-feature-copy">
          <span className="rp-feature-kind">
            {article.kind === 'recipe' ? 'Готовим дома' : 'Подборка'}
          </span>
          <strong>{article.title}</strong>
          <span>{article.description}</span>
          <span className="rp-feature-arrow">›</span>
        </span>
      ) : variant === 'topic' ? (
        <span>{article.title}</span>
      ) : (
        <>
          <strong>{article.title}</strong>
          <span>{article.description}</span>
          {article.duration_minutes && <span>{article.duration_minutes} мин</span>}
        </>
      )}
    </Link>
  );
}
