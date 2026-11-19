import { useRef, useState } from 'react';
import { Link } from 'react-router-dom';
import { productImageUrl } from '../lib/api';
import type { Banner } from '../types';

/** Admin records take precedence; unfilled slots reuse the first image. */
export function bannerSlides(banners: Banner[]): Banner[] {
  return banners.length
    ? Array.from({ length: 3 }, (_, position) => banners[position] || banners[0])
    : [];
}

export function BannerCarousel({ banners }: { banners: Banner[] }) {
  const slides = bannerSlides(banners);
  const [index, setIndex] = useState(0);
  const track = useRef<HTMLDivElement>(null);
  function goTo(position: number) {
    const element = track.current;
    const slide = element?.children[position] as HTMLElement | undefined;
    if (!element || !slide) return;
    const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    element.scrollTo({
      left:
        slide.getBoundingClientRect().left -
        element.getBoundingClientRect().left +
        element.scrollLeft,
      behavior: reduceMotion ? 'instant' : 'smooth',
    });
  }
  if (!slides.length) return null;
  return (
    <section
      className="retail-banner-carousel"
      aria-label="Витрина магазина"
      aria-roledescription="карусель"
    >
      <div
        className="retail-banners"
        ref={track}
        onScroll={() => {
          const element = track.current;
          if (!element?.firstElementChild) return;
          const first = element.firstElementChild as HTMLElement;
          const second = element.children[1] as HTMLElement;
          const step = second.offsetLeft - first.offsetLeft;
          if (step) setIndex(Math.max(0, Math.min(2, Math.round(element.scrollLeft / step))));
        }}
      >
        {slides.map((banner, position) => (
          <Link
            key={`${banner.id}-${position}`}
            to={banner.target_url}
            className="rp-promo"
            aria-label={`${banner.alt_text || 'Предложение магазина'} · слайд ${position + 1} из 3`}
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
      <div className="retail-banner-dots" role="group" aria-label="Слайды баннера">
        {slides.map((_, position) => (
          <button
            type="button"
            key={position}
            aria-label={`Слайд ${position + 1} из 3`}
            aria-pressed={index === position}
            onClick={() => goTo(position)}
          >
            <span />
          </button>
        ))}
      </div>
    </section>
  );
}
