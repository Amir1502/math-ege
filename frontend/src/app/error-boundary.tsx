import { Component, type ReactNode } from 'react';

export class ErrorBoundary extends Component<{ children: ReactNode }, { failed: boolean }> {
  state = { failed: false };
  static getDerivedStateFromError() { return { failed: true }; }
  render() {
    if (!this.state.failed) return this.props.children;
    return <main className="fatal-error"><h1>Не удалось открыть экран</h1><p>Сохранённые данные не удалены. Перезагрузите страницу, чтобы восстановить занятие.</p><button type="button" className="button button--primary" onClick={() => window.location.reload()}>Перезагрузить</button><a className="button button--secondary" href="#/" onClick={() => this.setState({ failed: false })}>К плану</a></main>;
  }
}
