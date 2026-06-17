import { Component, OnInit, inject } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { GridsterItem, GridsterModule, DisplayGrid, GridType } from 'angular-gridster2';

import { DashboardDetail, DashboardService } from '../../core/dashboard.service';
import { DashboardCardComponent } from '../../shared/dashboard-card.component';

@Component({
  standalone: true,
  imports: [GridsterModule, DashboardCardComponent],
  template: `
    <div class="page">
      <header>
        <span class="brand-mark">IQ</span>
        <h1>{{ dashboard?.name }}</h1>
        <span class="badge">Read-only</span>
      </header>

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
        flex: 1;
        min-height: 0;
        width: 100%;
      }
      .canvas-shell gridster {
        display: block;
        width: 100%;
        height: 100%;
        min-height: calc(100vh - 120px);
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
    `,
  ],
})
export class PublicDashboardComponent implements OnInit {
  private readonly route = inject(ActivatedRoute);
  private readonly dashboards = inject(DashboardService);

  dashboard: DashboardDetail | null = null;
  gridItems: { card: { id: string; title: string; refresh_mode: string }; grid: GridsterItem; payload: { response_type: string; data: Record<string, unknown> } }[] = [];

  options = {
    gridType: GridType.Fit,
    displayGrid: DisplayGrid.None,
    setGridSize: true,
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
        this.options = { ...this.options, minRows: Math.max(maxRow, 4) };
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
      },
    });
  }
}
