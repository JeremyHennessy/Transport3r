import React, { Component, useEffect, useState } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import ReactDOM from 'react-dom/client';
import CarrierRouteApp from './CarrierRouteApp';
import CarrierReport from './CarrierReport';
import FleetRouteApp from './FleetRouteApp';
import WorkspaceApp from './WorkspaceApp';
import './workspace.css';
import './coverage.css';
import './insight.css';
import './completeData.css';
import './visualPolish.css';
import './visualPolishExtras.css';

type ErrorBoundaryState = { error: Error | null };

class AppErrorBoundary extends Component<{ children: ReactNode }, ErrorBoundaryState> {
  state: ErrorBoundaryState = { error: null };

  static getDerivedStateFromError(error: Error): ErrorBoundaryState {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Transport3r runtime error', error, info);
  }

  render() {
    if (!this.state.error) return this.props.children;
    return <div className="t3-runtime-fallback">
      <div className="t3-runtime-card">
        <div className="t3-eyebrow">Runtime recovery</div>
        <h1>Transport3r could not render this view.</h1>
        <p>The application shell is still available. This error is contained instead of leaving a blank page.</p>
        <pre>{this.state.error.message}</pre>
        <div className="t3-actions"><a className="t3-button primary" href="#/overview" onClick={() => this.setState({ error: null })}>Open overview</a><a className="t3-button secondary" href="#/carriers" onClick={() => this.setState({ error: null })}>Open carriers</a><button className="t3-button text" onClick={() => window.location.reload()}>Reload application</button></div>
      </div>
    </div>;
  }
}

function RootRouter() {
  const [hash, setHash] = useState(window.location.hash);

  useEffect(() => {
    const onHash = () => setHash(window.location.hash);
    window.addEventListener('hashchange', onHash);
    return () => window.removeEventListener('hashchange', onHash);
  }, []);

  // A new USDOT must never inherit another carrier's identity, counts or failed-request state.
  const carrierKey = hash.split('/')[2];
  if (/^#\/carrier\/\d+\/report(?:\?|$)/.test(hash)) return <CarrierReport key={hash.split('?')[0]+new URLSearchParams(hash.split('?')[1]??'').get('format')}/>;
  if (/^#\/carrier\/\d+\/fleet(?:\?|$)/.test(hash)) return <FleetRouteApp key={carrierKey} />;
  return hash.startsWith('#/carrier/') ? <CarrierRouteApp key={carrierKey} /> : <WorkspaceApp />;
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <AppErrorBoundary>
      <RootRouter />
    </AppErrorBoundary>
  </React.StrictMode>,
);
