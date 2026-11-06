import { Component, StrictMode } from 'react';
import type { ErrorInfo, ReactNode } from 'react';
import { createRoot } from 'react-dom/client';
import { Button } from '../components/ui';
import OfflineApp from './app';

class OfflineErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };

  static getDerivedStateFromError() {
    return { failed: true };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('Не удалось отобразить автономный интерфейс.', error, info.componentStack);
  }

  render() {
    if (this.state.failed) {
      return <main className="offline-boot">
        <h1>Не удалось открыть экран</h1>
        <p>Сохранённая история не удалялась. Перезапустите экран, чтобы снова прочитать данные на устройстве.</p>
        <Button variant="primary" onClick={() => window.location.reload()}>Открыть снова</Button>
      </main>;
    }
    return this.props.children;
  }
}

const root = document.getElementById('root');
if (!root) throw new Error('Корневой элемент автономного приложения не найден.');
if (document.documentElement.dataset.offlineSupported === 'true') {
  createRoot(root).render(<StrictMode><OfflineErrorBoundary><OfflineApp /></OfflineErrorBoundary></StrictMode>);
}
