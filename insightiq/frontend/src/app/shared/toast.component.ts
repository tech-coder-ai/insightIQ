import { Component, inject } from '@angular/core';

import { ToastService } from '../core/toast.service';
import { IconComponent } from './icon.component';

@Component({
  selector: 'app-toast-container',
  standalone: true,
  imports: [IconComponent],
  template: `
    <div class="toast-stack" aria-live="polite" role="status">
      @for (toast of toasts.toasts(); track toast.id) {
        <div class="toast" [class]="toast.kind">
          <app-icon [name]="iconFor(toast.kind)" [size]="18" />
          <span class="toast-msg">{{ toast.message }}</span>
          <button type="button" class="toast-close" aria-label="Dismiss" (click)="toasts.dismiss(toast.id)">
            <app-icon name="close" [size]="14" />
          </button>
        </div>
      }
    </div>
  `,
  styles: [
    `
      .toast-stack {
        position: fixed;
        bottom: var(--space-5);
        right: var(--space-5);
        z-index: 1400;
        display: flex;
        flex-direction: column;
        gap: 10px;
        max-width: min(380px, calc(100vw - var(--space-5) * 2));
      }
      .toast {
        display: flex;
        align-items: flex-start;
        gap: 10px;
        padding: 12px 14px;
        border-radius: var(--radius-lg);
        background: var(--surface);
        border: 1px solid var(--border-strong);
        box-shadow: var(--shadow-lg);
        color: var(--text);
        font-size: var(--text-sm);
        animation: toast-in var(--dur) var(--ease-out);
      }
      .toast.success { border-left: 3px solid var(--success, #22c55e); }
      .toast.success app-icon { color: var(--success, #22c55e); }
      .toast.error { border-left: 3px solid var(--danger); }
      .toast.error app-icon { color: var(--danger); }
      .toast.info { border-left: 3px solid var(--primary); }
      .toast.info app-icon { color: var(--primary-text); }
      .toast-msg { flex: 1; line-height: 1.45; word-break: break-word; }
      .toast-close {
        border: none;
        background: none;
        color: var(--text-muted);
        cursor: pointer;
        padding: 2px;
        display: inline-flex;
        flex-shrink: 0;
      }
      .toast-close:hover { color: var(--text); }
      @keyframes toast-in {
        from { opacity: 0; transform: translateY(8px); }
        to { opacity: 1; transform: translateY(0); }
      }
    `,
  ],
})
export class ToastContainerComponent {
  readonly toasts = inject(ToastService);

  iconFor(kind: string): string {
    if (kind === 'success') return 'check-circle';
    if (kind === 'error') return 'alert-circle';
    return 'info';
  }
}
