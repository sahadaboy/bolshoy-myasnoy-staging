import { useCart } from '../context/CartContext';
export function CartSyncNotice() {
  const cart = useCart();
  if (cart.syncStatus === 'guest') return null;
  const message =
    cart.syncStatus === 'synced'
      ? 'Корзина синхронизирована'
      : cart.syncStatus === 'loading'
        ? 'Загружаем корзину…'
        : cart.syncStatus === 'saving'
          ? 'Сохраняем корзину…'
          : cart.syncStatus === 'conflict'
            ? 'Корзина изменена на другом устройстве. Выберите, какие изменения сохранить.'
            : cart.syncStatus === 'auth-required'
              ? 'Для синхронизации восстановите вход через Telegram. Выбранные товары сохранены.'
              : cart.syncError || 'Нет соединения. Выбранные товары сохранены на устройстве.';
  return (
    <div className="inline-notice" role="status" aria-live="polite">
      <p>{message}</p>
      {cart.syncStatus === 'conflict' ? (
        <>
          <button className="button button-secondary" onClick={() => cart.resolveSync(true)}>
            Применить мои изменения
          </button>
          <button className="button button-secondary" onClick={() => cart.resolveSync(false)}>
            Загрузить с сервера
          </button>
        </>
      ) : cart.syncStatus === 'offline' ? (
        <button className="button button-secondary" onClick={cart.retrySync}>
          Повторить синхронизацию
        </button>
      ) : null}
    </div>
  );
}
