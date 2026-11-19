import { X } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { fetchStoreProfile } from '../lib/api';
import { useResource } from '../hooks/useResource';
import { ErrorState, LoadingGrid } from '../components/States';

export default function StoreMapPage() {
  const { data, loading, error, retry } = useResource(fetchStoreProfile);
  const navigate = useNavigate();
  return (
    <section className="store-map-page">
      <div className="dialog-heading">
        <h1>Как нас найти</h1>
        <button
          className="icon-button"
          aria-label="Закрыть карту"
          onClick={() =>
            window.history.state?.idx > 0 ? navigate(-1) : navigate('/about', { replace: true })
          }
        >
          <X size={22} />
        </button>
      </div>
      <p>{data?.address}</p>
      {loading ? (
        <LoadingGrid count={1} />
      ) : error ? (
        <ErrorState retry={retry} message={error} />
      ) : data?.map_embed_url ? (
        <iframe
          src={data.map_embed_url}
          title="Карта расположения Большого Мясного"
          referrerPolicy="no-referrer"
          allowFullScreen
        />
      ) : (
        <p>Карта сейчас недоступна.</p>
      )}
    </section>
  );
}
