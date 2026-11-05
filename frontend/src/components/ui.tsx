import type { ButtonHTMLAttributes, ReactNode } from 'react';
import { AlertCircle, ArrowRight, RefreshCw } from 'lucide-react';

export function Button({ variant = 'secondary', className = '', children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: 'primary' | 'secondary' | 'quiet'; children: ReactNode }) {
  return <button type="button" className={`button button--${variant} ${className}`} {...props}>{children}</button>;
}

export function ActionLink({ href, children, primary = false }: { href: string; children: ReactNode; primary?: boolean }) {
  return <a className={`button button--${primary ? 'primary' : 'secondary'}`} href={`#${href}`}>{children}<ArrowRight aria-hidden="true" /></a>;
}

export function PageHeading({ title, description, action }: { title: string; description?: string; action?: ReactNode }) {
  return <header className="page-heading"><div><h1 tabIndex={-1}>{title}</h1>{description && <p>{description}</p>}</div>{action}</header>;
}

export function ErrorNotice({ message, retry }: { message: string; retry?: () => void }) {
  return <div className="notice notice--error" role="alert"><AlertCircle aria-hidden="true" /><div><p>{message}</p>{retry && <Button onClick={retry}><RefreshCw aria-hidden="true" />Повторить</Button>}</div></div>;
}

export function EmptyState({ title, children, action }: { title: string; children: ReactNode; action?: ReactNode }) {
  return <div className="empty-state"><h2>{title}</h2><p>{children}</p>{action}</div>;
}

export function Loading({ label = 'Загружаем данные' }: { label?: string }) {
  return <div className="loading" role="status" aria-label={label}><span className="sr-only">{label}…</span><div className="skeleton skeleton--title" /><div className="skeleton" /><div className="skeleton skeleton--short" /><div className="skeleton skeleton--block" /></div>;
}

export function GuestNote({ compact = false }: { compact?: boolean }) {
  return <div className={`guest-note ${compact ? 'guest-note--compact' : ''}`}>
    <strong>Без регистрации. В этом браузере.</strong>
    <p>Анонимная история хранится на тестовом сервере. Доступ к ней даёт cookie этого браузера. Черновик дополнительно сохраняется на устройстве.</p>
    {!compact && <p>Очистка cookie лишит доступа к истории. Данные не переносятся между устройствами. Сохраните JSON в разделе «Прогресс».</p>}
    <a className="text-link" href="#/help">О данных и гостевом режиме</a>
  </div>;
}
