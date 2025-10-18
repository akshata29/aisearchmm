import { createRoot } from 'react-dom/client';
import { StrictMode } from 'react';
import App from './App';
import './styles/app.css';

const rootEl = document.getElementById('root');

if (!rootEl) {
  throw new Error('Failed to find root element for Teams tab');
}

createRoot(rootEl).render(
  <StrictMode>
    <App />
  </StrictMode>
);
