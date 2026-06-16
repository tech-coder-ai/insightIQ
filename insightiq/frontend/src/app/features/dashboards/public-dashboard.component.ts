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
        <h1>{{ dashboard?.name }} <span class="badge">read-only</span></h1>
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
        padding: 20px;
      }
      .badge {
        font-size: 12px;
        opacity: 0.6;
        font-weight: normal;
      }
      gridster-item {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
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
