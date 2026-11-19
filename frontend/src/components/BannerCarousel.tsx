import { useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import { fetchBanners, productImageUrl } from '../lib/api';
import type { Banner } from '../types';

export function BannerCarousel() {
  const [banners, setBanners] = useState<Banner[]>([]);
  const [index, setIndex] = useState(0);
  const track = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const controller = new AbortController();
    fetchBanners(controller.signal)
      .then(setBanners)
      .catch(() => {
        /* Optional editorial content never blocks the catalogue. */
      });
    return () => controller.abort();
  }, []);
  function goTo(next: number) {
    const element = track.current;
    if (!element) return;
    const target = Math.max(0, Math.min(next, banners.length - 1));
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    element.scrollTo({
      left: target * element.clientWidth,
      behavior: reduceMotion ? 'instant' : 'smooth',
    });
  }
  if (!banners.length) return null;
  return (
    <section
      className="banner-carousel"
      aria-label="Предложения магазина"
      aria-roledescription="карусель"
    >
      <div
        className="banner-track"
        ref={track}
        onScroll={() => {
          const element = track.current;
          if (element?.clientWidth) setIndex(Math.round(element.scrollLeft / element.clientWidth));
        }}
      >
        {banners.map((banner, position) => (
          <Link
            key={banner.id}
            to={banner.target_url}
            className="banner-slide"
            aria-label={banner.alt_text || `Предложение магазина ${position + 1}`}
          >
            <img
              src={productImageUrl(banner.image) || banner.image}
              alt={banner.alt_text || ''}
              width="1100"
              height="500"
              loading={position ? 'lazy' : 'eager'}
              fetchPriority={position ? 'auto' : 'high'}
            />
          </Link>
        ))}
      </div>
      {banners.length > 1 && (
        <div className="banner-controls">
          <button
            className="icon-button"
            aria-label="Предыдущий баннер"
            disabled={index === 0}
            onClick={() => goTo(index - 1)}
          >
            <ChevronLeft size={18} aria-hidden="true" />
          </button>
          <div className="banner-dots">
            {banners.map((banner, position) => (
              <button
                key={banner.id}
                aria-label={`Баннер ${position + 1}`}
                aria-pressed={index === position}
                onClick={() => goTo(position)}
              >
                <span />
              </button>
            ))}
          </div>
          <button
            className="icon-button"
            aria-label="Следующий баннер"
            disabled={index === banners.length - 1}
            onClick={() => goTo(index + 1)}
          >
            <ChevronRight size={18} aria-hidden="true" />
          </button>
        </div>
      )}
    </section>
  );
}
