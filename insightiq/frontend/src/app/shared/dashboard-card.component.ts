import { afterNextRender, Component, ElementRef, EventEmitter, inject, Injector, Input, Output, ViewChild } from '@angular/core';

import { IconComponent } from './icon.component';
import { ResponseRendererComponent } from './response-renderer.component';

@Component({
  selector: 'app-dashboard-card',
  standalone: true,
  imports: [ResponseRendererComponent, IconComponent],
  template: `
    <div class="dcard" [class.dcard-highlight]="highlighted">
      <div class="drag-bar dcard-drag-handle" title="Drag to reposition"><app-icon name="more-horizontal" [size]="14" /></div>
      <div class="head">
        <div class="title-wrap">
          @if (editing) {
            <input
              #titleInput
              class="title-input"
              [value]="draft"
              (input)="draft = $any($event.target).value"
              (mousedown)="$event.stopPropagation()"
              (blur)="onInputBlur()"
              (keydown.enter)="commitEdit()"
              (keydown.escape)="cancelEdit()"
            />
          } @else {
            <h3 [title]="title">{{ title }}</h3>
            @if (editable) {
              <button
                type="button"
                class="rename-btn"
                title="Rename card"
                aria-label="Rename card"
                (mousedown)="$event.stopPropagation()"
                (click)="startEdit($event)"
              >
                <app-icon name="edit" [size]="12" />
              </button>
            }
          }
        </div>
        <div class="head-actions">
          @if (editable) {
            <select
              class="mode-select"
              [value]="refreshMode"
              (mousedown)="$event.stopPropagation()"
              (change)="onRefreshModeChange($event)"
              [title]="refreshMode === 'live' ? 'Re-runs query on refresh' : 'Frozen at pin time'"
            >
              <option value="snapshot">Snapshot</option>
              <option value="live">Live</option>
            </select>
            @if (refreshMode === 'live') {
              <button
                type="button"
                class="refresh-btn"
                title="Refresh now"
                aria-label="Refresh now"
                (mousedown)="$event.stopPropagation()"
                (click)="onRefresh($event)"
              >
                <app-icon name="refresh" [size]="12" />
              </button>
            }
          } @else {
            <span class="mode" [class.mode-live]="refreshMode === 'live'">{{ refreshMode }}</span>
          }
          @if (removable) {
            <button
              type="button"
              class="remove-btn"
              title="Remove from dashboard"
              aria-label="Remove from dashboard"
              (mousedown)="$event.stopPropagation()"
              (click)="onRemove($event)"
            >
              <app-icon name="close" [size]="12" />
            </button>
          }
        </div>
      </div>
      <div class="body">
        <app-response-renderer [payload]="payload" [showTitle]="false" />
      </div>
    </div>
  `,
  styles: [
    `
      .dcard {
        height: 100%;
        display: flex;
        flex-direction: column;
        padding: 14px;
        padding-top: 8px;
        box-sizing: border-box;
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius-md);
        box-shadow: var(--shadow-sm);
        overflow: hidden;
        transition: box-shadow var(--dur) var(--ease), border-color var(--dur) var(--ease);
      }
      .dcard.dcard-highlight {
        border-color: var(--primary);
        box-shadow: 0 0 0 3px var(--primary-soft), var(--shadow-md);
      }
      .drag-bar {
        align-self: center;
        width: 36px;
        height: 18px;
        margin-bottom: 6px;
        border-radius: var(--radius-pill);
        display: grid;
        place-items: center;
        color: var(--text-muted);
        font-size: 11px;
        letter-spacing: 2px;
        cursor: move;
        user-select: none;
      }
      .drag-bar:hover { background: var(--surface-3); color: var(--text-2); }
      .head {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 8px;
        margin-bottom: 10px;
        flex-shrink: 0;
      }
      .title-wrap {
        display: flex;
        align-items: center;
        gap: 6px;
        min-width: 0;
        flex: 1;
      }
      .head-actions {
        display: flex;
        align-items: center;
        gap: 8px;
        flex-shrink: 0;
      }
      .body {
        flex: 1;
        min-height: 0;
        overflow: auto;
      }
      h3 {
        margin: 0;
        font-size: var(--text-base);
        color: var(--text);
        min-width: 0;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
      .title-input {
        width: 100%;
        min-width: 0;
        padding: 4px 8px;
        border-radius: var(--radius-sm);
        border: 1px solid var(--border-focus);
        background: var(--input-bg);
        color: var(--text);
        font-size: var(--text-base);
        font-family: inherit;
      }
      .title-input:focus {
        outline: none;
        box-shadow: 0 0 0 3px var(--primary-soft);
      }
      .rename-btn,
      .remove-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 24px;
        height: 24px;
        padding: 0;
        border-radius: var(--radius-sm);
        border: 1px solid var(--border);
        background: var(--surface-2);
        color: var(--text-muted);
        cursor: pointer;
        font-size: 12px;
        line-height: 1;
        flex-shrink: 0;
        transition: background var(--dur-fast) var(--ease), color var(--dur-fast) var(--ease), border-color var(--dur-fast) var(--ease);
      }
      .rename-btn:hover {
        color: var(--text);
        border-color: var(--border-strong);
        background: var(--surface-3);
      }
      .remove-btn:hover {
        background: var(--danger-soft);
        border-color: var(--danger);
        color: var(--danger);
      }
      .mode {
        font-size: var(--text-xs);
        color: var(--text-muted);
        text-transform: uppercase;
        letter-spacing: 0.05em;
      }
      .mode-live {
        color: var(--primary-text);
      }
      .mode-select {
        padding: 2px 6px;
        border-radius: var(--radius-sm);
        border: 1px solid var(--border);
        background: var(--surface-2);
        color: var(--text-2);
        font-size: var(--text-xs);
        font-family: inherit;
        text-transform: uppercase;
        letter-spacing: 0.04em;
        cursor: pointer;
      }
      .mode-select:focus {
        outline: none;
        border-color: var(--border-focus);
      }
      .refresh-btn {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        width: 24px;
        height: 24px;
        padding: 0;
        border-radius: var(--radius-sm);
        border: 1px solid var(--border);
        background: var(--surface-2);
        color: var(--primary-text);
        cursor: pointer;
        font-size: 14px;
        line-height: 1;
        flex-shrink: 0;
      }
      .refresh-btn:hover {
        background: var(--primary-soft);
        border-color: var(--primary-soft-2);
      }
    `,
  ],
})
export class DashboardCardComponent {
  private readonly injector = inject(Injector);

  @ViewChild('titleInput') titleInput?: ElementRef<HTMLInputElement>;

  @Input() title = '';
  @Input() refreshMode = 'snapshot';
  @Input() highlighted = false;
  @Input() removable = false;
  @Input() editable = false;
  @Input() payload: { response_type: string; title?: string; data: Record<string, unknown> } | null = null;
  @Output() remove = new EventEmitter<void>();
  @Output() titleChange = new EventEmitter<string>();
  @Output() refreshModeChange = new EventEmitter<{ mode: string; autoRefreshSeconds: number | null }>();
  @Output() refresh = new EventEmitter<void>();

  editing = false;
  draft = '';
  private skipBlurCommit = false;

  onRemove(event: Event): void {
    event.stopPropagation();
    this.remove.emit();
  }

  onRefreshModeChange(event: Event): void {
    const mode = (event.target as HTMLSelectElement).value;
    this.refreshModeChange.emit({
      mode,
      autoRefreshSeconds: null,
    });
  }

  onRefresh(event: Event): void {
    event.stopPropagation();
    this.refresh.emit();
  }

  startEdit(event: Event): void {
    event.preventDefault();
    event.stopPropagation();
    this.skipBlurCommit = true;
    this.editing = true;
    this.draft = this.title;
    afterNextRender(
      () => {
        const el = this.titleInput?.nativeElement;
        el?.focus();
        el?.select();
        this.skipBlurCommit = false;
      },
      { injector: this.injector },
    );
  }

  onInputBlur(): void {
    if (this.skipBlurCommit) return;
    this.commitEdit();
  }

  commitEdit(): void {
    if (!this.editing) return;
    this.editing = false;
    const next = this.draft.trim();
    if (next && next !== this.title) {
      this.titleChange.emit(next);
    } else {
      this.draft = this.title;
    }
  }

  cancelEdit(): void {
    this.skipBlurCommit = false;
    this.editing = false;
    this.draft = this.title;
  }
}
