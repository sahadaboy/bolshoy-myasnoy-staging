// Independent of the application bundle: failed chunk/network loads still offer retry.
(() => {
  const boot = document.getElementById('app-boot');
  const fail = (event) => {
    if (event.type === 'error' && event.target !== window &&
        (event.target?.tagName !== 'SCRIPT' || event.target.id === 'telegram-webapp-sdk')) return;
    if (!boot?.isConnected || boot.dataset.ready) return;
    boot.querySelector('.boot-track').hidden = true;
    document.getElementById('boot-error').hidden = false;
    document.getElementById('boot-retry').hidden = false;
    window.Telegram?.WebApp?.ready?.();
  };
  document.getElementById('boot-retry')?.addEventListener('click', () => location.reload());
  window.addEventListener('error', fail, true);
  window.addEventListener('unhandledrejection', fail);
})();
