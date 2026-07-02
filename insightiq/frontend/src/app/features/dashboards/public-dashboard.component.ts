import { Component, OnInit, inject, signal } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { GridsterItem, GridsterModule, DisplayGrid, GridType } from 'angular-gridster2';

import { DashboardDetail, DashboardService } from '../../core/dashboard.service';
import { DashboardCardComponent } from '../../shared/dashboard-card.component';
import { IconComponent } from '../../shared/icon.component';

@Component({
  standalone: true,
  imports: [GridsterModule, DashboardCardComponent, IconComponent],
  template: `
    <div class="page">
      @if (loading()) {
        <header>
          <div class="skeleton" style="width: 32px; height: 32px; border-radius: 9px;"></div>
          <div class="skeleton" style="width: 200px; height: 22px;"></div>
        </header>
        <div class="skeleton-grid" aria-hidden="true">
          @for (i of [1, 2, 3, 4]; track i) {
            <div class="skeleton" style="height: 180px; border-radius: var(--radius-md);"></div>
          }
        </div>
      } @else if (loadError()) {
        <div class="state-banner error">
          <p>{{ loadError() }}</p>
        </div>
      } @else {
        <header>
          <span class="brand-mark">IQ</span>
          <h1>{{ dashboard?.name }}</h1>
          <span class="badge">Read-only</span>
        </header>

        @if (gridItems.length === 0) {
          <div class="empty-state">
            <div class="icon"><app-icon name="grid" [size]="28" /></div>
            <p>This dashboard has no cards yet.</p>
          </div>
        } @else {
          <div class="canvas-shell">
            <gridster [options]="options">
              @for (item of gridItems; track item.card.id) {
                <gridster-item [item]="item.grid">
                  <app-dashboard-card
                    [title]="item.card.title"
                    [refreshMode]="item.card.refresh_mode"
                    [payload]="item.payload"
                  />
                </gridster-item>
              }
            </gridster>
          </div>
        }
      }
    </div>
  `,
  styles: [
    `
      :host {
        display: block;
        min-height: 100vh;
      }
      .page {
        display: flex;
        flex-direction: column;
        min-height: 100vh;
        padding: var(--space-8);
        max-width: none;
        width: 100%;
        box-sizing: border-box;
      }
      header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: var(--space-4);
        flex-shrink: 0;
      }
      h1 { font-size: var(--text-xl); }
      .brand-mark {
        width: 32px; height: 32px; border-radius: 9px;
        display: grid; place-items: center;
        background: linear-gradient(135deg, var(--primary), var(--primary-hover));
        color: #fff; font-weight: 700; font-size: 13px;
      }
      .badge {
        font-size: var(--text-xs);
        padding: 3px 10px;
        border-radius: var(--radius-pill);
        background: var(--surface-3);
        color: var(--text-2);
      }
      .canvas-shell {
        width: 100%;
      }
      :host ::ng-deep gridster {
        display: block;
        width: 100%;
        background: transparent;
      }
      :host ::ng-deep gridster-item {
        background: transparent !important;
      }
      :host ::ng-deep gridster .gridster-column,
      :host ::ng-deep gridster .gridster-row {
        display: none !important;
      }
      :host ::ng-deep gridster-item app-dashboard-card {
        display: block;
        height: 100%;
      }
      .skeleton-grid {
        display: grid;
        grid-template-columns: repeat(auto-fill, minmax(280px, 1fr));
        gap: var(--space-4);
      }
      .state-banner {
        padding: var(--space-8);
        text-align: center;
        border-radius: var(--radius-lg);
        border: 1px solid var(--border);
        background: var(--surface);
        color: var(--text-2);
      }
      .state-banner.error { color: var(--danger); border-color: var(--danger-soft); background: var(--danger-soft); }
      .empty-state {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 10px;
        padding: var(--space-10);
        border-radius: var(--radius-lg);
        border: 1px dashed var(--border-strong);
        color: var(--text-muted);
      }
    `,
  ],
})
export class PublicDashboardComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly dashboards = inject(DashboardService);

  readonly loading = signal(true);
  readonly loadError = signal('');

  dashboard: DashboardDetail | null = null;
  gridItems: { card: { id: string; title: string; refresh_mode: string }; grid: GridsterItem; payload: { response_type: string; data: Record<string, unknown> } }[] = [];

  readonly fixedRowHeight = 100;

  options = {
    gridType: GridType.ScrollVertical,
    fixedRowHeight: this.fixedRowHeight,
    displayGrid: DisplayGrid.None,
    draggable: { enabled: false },
    resizable: { enabled: false },
    margin: 12,
    outerMargin: true,
    minCols: 12,
    maxCols: 12,
    minRows: 4,
  };

  ngOnInit(): void {
    const token = this.route.snapshot.paramMap.get('token') ?? '';
    this.dashboards.getPublic(token).subscribe({
      next: (d) => {
        this.dashboard = d;
        const maxRow = d.cards.reduce((max, card) => {
          const y = Number(card.layout_json?.['y'] ?? 0);
          const rows = Number(card.layout_json?.['rows'] ?? 3);
          return Math.max(max, y + rows);
        }, 0);
        this.options = { ...this.options, fixedRowHeight: this.fixedRowHeight, minRows: Math.max(maxRow, 4) };
        this.gridItems = d.cards.map((card) => ({
          card,
          grid: {
            x: Number(card.layout_json?.['x'] ?? 0),
            y: Number(card.layout_json?.['y'] ?? 0),
            cols: Number(card.layout_json?.['cols'] ?? 4),
            rows: Math.max(Number(card.layout_json?.['rows'] ?? 3), 2),
          } as GridsterItem,
          payload: card.snapshot_response_json as { response_type: string; data: Record<string, unknown> },
        }));
        this.loading.set(false);
      },
      error: (err: { error?: { detail?: string } }) => {
        this.loading.set(false);
        this.loadError.set(err?.error?.detail ?? 'This dashboard link is invalid or no longer shared.');
      },
    });
  }
}
