import { Injectable, signal } from '@angular/core';

export type ToastKind = 'success' | 'error' | 'info';

export type Toast = {
  id: number;
  kind: ToastKind;
  message: string;
};

const DEFAULT_DURATION_MS: Record<ToastKind, number> = {
  success: 4000,
  info: 4500,
  error: 6500,
};

@Injectable({ providedIn: 'root' })
export class ToastService {
  private nextId = 1;
  readonly toasts = signal<Toast[]>([]);

  success(message: string, durationMs?: number): void {
    this.push('success', message, durationMs);
  }

  error(message: string, durationMs?: number): void {
    this.push('error', message, durationMs);
  }

  info(message: string, durationMs?: number): void {
    this.push('info', message, durationMs);
  }

  dismiss(id: number): void {
    this.toasts.update((list) => list.filter((t) => t.id !== id));
  }

  private push(kind: ToastKind, message: string, durationMs?: number): void {
    const id = this.nextId++;
    this.toasts.update((list) => [...list, { id, kind, message }]);
    const duration = durationMs ?? DEFAULT_DURATION_MS[kind];
    setTimeout(() => this.dismiss(id), duration);
  }
}
