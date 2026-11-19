import React from 'react';
import ReactDOM from 'react-dom/client';
import { BrowserRouter } from 'react-router-dom';
import { CartProvider } from './context/CartContext';
import { SessionProvider } from './context/SessionContext';
import App from './App';
import { loadTelegramWebApp } from './lib/telegram';
import '@fontsource-variable/manrope';
import './styles.css';

// Initialize the SDK before Router can remove Telegram's launch fragment.
// Plain browsers skip the network request and render immediately.
void loadTelegramWebApp().then(() =>
  ReactDOM.createRoot(document.getElementById('root')!).render(
    <React.StrictMode>
      <BrowserRouter>
        <CartProvider>
          <SessionProvider>
            <App />
          </SessionProvider>
        </CartProvider>
      </BrowserRouter>
    </React.StrictMode>,
  ),
);
