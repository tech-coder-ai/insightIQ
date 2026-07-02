import { Injectable, signal } from '@angular/core';

export type ConfirmOptions = {
  title: string;
  message?: string;
  confirmLabel?: string;
  cancelLabel?: string;
  danger?: boolean;
};

export type ConfirmRequest = ConfirmOptions & {
  resolve: (value: boolean) => void;
};

@Injectable({ providedIn: 'root' })
export class ConfirmService {
  readonly request = signal<ConfirmRequest | null>(null);

  ask(options: ConfirmOptions): Promise<boolean> {
    return new Promise<boolean>((resolve) => {
      this.request.set({ ...options, resolve });
    });
  }

  resolve(value: boolean): void {
    const current = this.request();
    if (!current) return;
    this.request.set(null);
    current.resolve(value);
  }
}
