import { Component, ElementRef, HostListener, Injector, afterNextRender, effect, inject, viewChild } from '@angular/core';

import { ConfirmService } from '../core/confirm.service';

@Component({
  selector: 'app-confirm-dialog',
  standalone: true,
  template: `
    @if (confirm.request(); as req) {
      <div class="modal-backdrop" (click)="confirm.resolve(false)">
        <div class="modal confirm-modal" role="alertdialog" aria-modal="true" [attr.aria-label]="req.title" (click)="$event.stopPropagation()">
          <h2>{{ req.title }}</h2>
          @if (req.message) {
            <p>{{ req.message }}</p>
          }
          <div class="confirm-actions">
            <button type="button" class="btn btn-ghost" (click)="confirm.resolve(false)">
              {{ req.cancelLabel ?? 'Cancel' }}
            </button>
            <button
              #confirmBtn
              type="button"
              class="btn"
              [class.btn-danger]="req.danger"
              [class.btn-primary]="!req.danger"
              (click)="confirm.resolve(true)"
            >
              {{ req.confirmLabel ?? 'Confirm' }}
            </button>
          </div>
        </div>
      </div>
    }
  `,
  styles: [
    `
      .confirm-modal { width: min(420px, 100%); }
      .confirm-modal h2 { margin: 0 0 10px; font-size: var(--text-lg); }
      .confirm-modal p { margin: 0 0 var(--space-5); color: var(--text-2); line-height: 1.55; }
      .confirm-actions { display: flex; justify-content: flex-end; gap: 10px; }
    `,
  ],
})
export class ConfirmDialogComponent {
  readonly confirm = inject(ConfirmService);
  private readonly injector = inject(Injector);
  private readonly confirmBtn = viewChild<ElementRef<HTMLButtonElement>>('confirmBtn');
  private previouslyFocused: HTMLElement | null = null;

  constructor() {
    effect(() => {
      if (this.confirm.request()) {
        this.previouslyFocused = document.activeElement as HTMLElement | null;
        afterNextRender(() => this.confirmBtn()?.nativeElement.focus(), { injector: this.injector });
      } else {
        this.previouslyFocused?.focus();
        this.previouslyFocused = null;
      }
    });
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.confirm.request()) this.confirm.resolve(false);
  }
}
