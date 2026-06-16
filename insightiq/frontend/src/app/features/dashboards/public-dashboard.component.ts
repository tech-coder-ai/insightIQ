import { Component, OnInit, inject } from '@angular/core';
import { ActivatedRoute } from '@angular/router';
import { GridsterItem, GridsterModule } from 'angular-gridster2';

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
  `,
  styles: [
    `
      .page {
        padding: var(--space-8);
        max-width: 1200px;
        margin: 0 auto;
      }
      header {
        display: flex;
        align-items: center;
        gap: 12px;
        margin-bottom: var(--space-6);
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
      gridster {
        background: var(--surface-2);
        border: 1px solid var(--border);
        border-radius: var(--radius-lg);
      }
      gridster-item {
        background: transparent;
        border: none;
        border-radius: var(--radius-md);
        overflow: hidden;
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
    gridType: 'fit' as const,
    draggable: { enabled: false },
    resizable: { enabled: false },
    margin: 10,
    minCols: 12,
    maxCols: 12,
  };

  ngOnInit(): void {
    const token = this.route.snapshot.paramMap.get('token') ?? '';
    this.dashboards.getPublic(token).subscribe({
      next: (d) => {
        this.dashboard = d;
        this.gridItems = d.cards.map((card) => ({
          card,
          grid: card.layout_json as GridsterItem,
          payload: card.snapshot_response_json as { response_type: string; data: Record<string, unknown> },
        }));
      },
    });
  }
}
