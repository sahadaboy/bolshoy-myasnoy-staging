import { useRef, useState } from 'react';
import { ChevronRight, Clock3, MapPin, Phone } from 'lucide-react';
import { Link } from 'react-router-dom';
import { BackLink } from '../components/Retail';
import { ErrorState, LoadingGrid } from '../components/States';
import { fetchStoreProfile, productImageUrl } from '../lib/api';
import { useResource } from '../hooks/useResource';

export default function AboutPage() {
  const { data, loading, error, retry } = useResource(fetchStoreProfile);
  const gallery = useRef<HTMLDivElement>(null);
  const [index, setIndex] = useState(0);
  const phone = data?.phone.replace(/^(\+7)(\d{3})(\d{3})(\d{2})(\d{2})$/, '$1 $2 $3 $4 $5');
  function move(next: number) {
    const first = gallery.current?.firstElementChild as HTMLElement | null;
    if (!gallery.current || !first) return;
    gallery.current.scrollTo({
      left: (first.offsetWidth + 12) * next,
      behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches
        ? 'instant'
        : 'smooth',
    });
  }
  return (
    <>
      <BackLink fallback="/profile" />
      <div className="page-intro">
        <h1>О нас</h1>
      </div>
      {loading ? (
        <LoadingGrid count={2} />
      ) : error || !data ? (
        <ErrorState retry={retry} message={error || 'Не удалось открыть информацию о магазине.'} />
      ) : (
        <article className="retail-about">
          {data.photos.length > 0 && (
            <section className="store-gallery" aria-label="Фотографии магазина">
              <div
                className="store-gallery-track"
                ref={gallery}
                onScroll={(event) => {
                  const first = event.currentTarget.firstElementChild as HTMLElement | null;
                  if (first)
                    setIndex(
                      Math.min(
                        data.photos.length - 1,
                        Math.max(
                          0,
                          Math.round(event.currentTarget.scrollLeft / (first.offsetWidth + 12)),
                        ),
                      ),
                    );
                }}
              >
                {data.photos.map((photo, position) => (
                  <figure key={photo.id}>
                    <img
                      src={productImageUrl(photo.image) || ''}
                      alt={photo.alt_text || data.name}
                      width="1600"
                      height="1200"
                      loading={position ? 'lazy' : 'eager'}
                    />
                  </figure>
                ))}
              </div>
              {data.photos.length > 1 && (
                <div className="store-gallery-dots" aria-label="Выбор фотографии">
                  {data.photos.map((photo, position) => (
                    <button
                      key={photo.id}
                      aria-label={`Фото ${position + 1} из ${data.photos.length}`}
                      aria-pressed={index === position}
                      onClick={() => move(position)}
                    >
                      <span />
                    </button>
                  ))}
                </div>
              )}
            </section>
          )}
          <h2>{data.name}</h2>
          <div className="store-description">
            {data.description
              .split(/\n\s*\n/)
              .filter(Boolean)
              .map((text, position) => (
                <p key={position}>{text}</p>
              ))}
          </div>
          <section className="retail-about-section">
            <h2>
              <MapPin size={21} /> Ждём вас в магазине
            </h2>
            <p>{data.address}</p>
            {data.map_embed_url && (
              <Link className="retail-text-link" to="/about/map">
                Открыть на карте <ChevronRight size={16} />
              </Link>
            )}
          </section>
          {data.opening_hours && (
            <section className="retail-about-section">
              <h2>
                <Clock3 size={21} /> График работы
              </h2>
              <dl className="retail-hours">
                {data.opening_hours
                  .split('\n')
                  .filter(Boolean)
                  .map((line, position) => {
                    const separator = line.indexOf(': ');
                    return separator > -1 ? (
                      <div key={position}>
                        <dt>{line.slice(0, separator)}</dt>
                        <dd>{line.slice(separator + 2)}</dd>
                      </div>
                    ) : (
                      <div key={position}>
                        <dt>{line}</dt>
                      </div>
                    );
                  })}
              </dl>
            </section>
          )}
          <section className="retail-about-section">
            <h2>Всегда на связи</h2>
            {data.phone && (
              <a className="store-contact-phone" href={`tel:${data.phone.replace(/[^+\d]/g, '')}`}>
                <Phone size={19} />
                {phone}
              </a>
            )}
            <div className="store-socials">
              {data.telegram_url && (
                <a href={data.telegram_url} target="_blank" rel="noopener noreferrer">
                  <img src="/brand/telegram.svg" alt="" width="24" height="24" />
                  <span>Написать нам в Telegram</span>
                  <ChevronRight size={17} />
                </a>
              )}
              {data.vk_url && (
                <a href={data.vk_url} target="_blank" rel="noopener noreferrer">
                  <img src="/brand/vk.svg" alt="" width="24" height="24" />
                  <span>Мы ВКонтакте</span>
                  <ChevronRight size={17} />
                </a>
              )}
            </div>
            {data.email && (
              <a className="retail-text-link" href={`mailto:${data.email}`}>
                {data.email}
              </a>
            )}
          </section>
        </article>
      )}
    </>
  );
}
