import React, { useEffect, useState } from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import CarrierRouteApp from './CarrierRouteApp';
import './styles.css';
import './carrier360.css';
import './carrierRoutes.css';

function RootRouter() {
  const [hash, setHash] = useState(window.location.hash);

  useEffect(() => {
    const onHash = () => setHash(window.location.hash);
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  useEffect(() => {
    const openCarrierRoute = (event: MouseEvent) => {
      const target = event.target as HTMLElement | null;
      const result = target?.closest<HTMLButtonElement>('button.carrier-result');
      if (!result) return;
      const match = result.textContent?.match(/USDOT\s+(\d+)/i);
      if (!match) return;
      event.preventDefault();
      event.stopPropagation();
      window.location.hash = `#/carrier/${match[1]}/summary`;
    };
    document.addEventListener('click', openCarrierRoute, true);
    return () => document.removeEventListener('click', openCarrierRoute, true);
  }, []);

  return hash.startsWith('#/carrier/') ? <CarrierRouteApp /> : <App />;
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <RootRouter />
  </React.StrictMode>,
);
