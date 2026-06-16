import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';
import { GridsterConfig, GridsterItem, GridsterModule } from 'angular-gridster2';
import { Subscription, interval } from 'rxjs';

import { DashboardCard, DashboardDetail, DashboardService } from '../../core/dashboard.service';
import { AuthService } from '../../core/auth.service';
import { DashboardCardComponent } from '../../shared/dashboard-card.component';

@Component({
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    RouterLink,
    GridsterModule,
    DashboardCardComponent,
  ],
  template: `
    <div class="page">
      <header>
        <div>
          <a routerLink="/dashboards">← Dashboards</a>
          <h1>{{ dashboard?.name }}</h1>
        </div>
        <div class="actions">
          <button type="button" (click)="refreshLiveCards()">Refresh live</button>
          <button type="button" (click)="share()">Share</button>
          <button type="button" (click)="logout()">Logout</button>
        </div>
      </header>

      <form class="filters" [formGroup]="filterForm" (ngSubmit)="applyFilters()">
        <input formControlName="region" placeholder="Filter: region" />
        <input formControlName="date_from" type="date" />
        <input formControlName="date_to" type="date" />
        <button type="submit">Apply filters</button>
      </form>

      @if (shareUrl) {
        <p class="share">Share link: <code>{{ shareUrl }}</code></p>
      }

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
        min-height: 100vh;
      }
      header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        margin-bottom: 16px;
      }
      h1 {
        margin: 8px 0 0;
      }
      .actions {
        display: flex;
        gap: 8px;
      }
      .filters {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-bottom: 16px;
      }
      input,
      button {
        padding: 8px 10px;
        border-radius: 8px;
        border: 1px solid rgba(255, 255, 255, 0.12);
        background: rgba(0, 0, 0, 0.25);
        color: inherit;
      }
      gridster {
        background: rgba(255, 255, 255, 0.02);
        border-radius: 12px;
      }
      gridster-item {
        background: rgba(255, 255, 255, 0.04);
        border: 1px solid rgba(255, 255, 255, 0.08);
        border-radius: 12px;
      }
      .share code {
        color: #8ec5ff;
      }
      a {
        color: #8ec5ff;
        text-decoration: none;
      }
    `,
  ],
})
export class DashboardCanvasComponent implements OnInit, OnDestroy {
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly dashboards = inject(DashboardService);
  private readonly auth = inject(AuthService);
  private readonly fb = inject(FormBuilder);

  dashboard: DashboardDetail | null = null;
  gridItems: { card: DashboardCard; grid: GridsterItem; payload: { response_type: string; data: Record<string, unknown> } }[] = [];
  shareUrl = '';
  private refreshSub?: Subscription;
  private dashboardId = '';

  options: GridsterConfig = {
    gridType: 'fit',
    draggable: { enabled: true },
    resizable: { enabled: true },
    pushItems: true,
    margin: 10,
    minCols: 12,
    maxCols: 12,
    minRows: 1,
    itemChangeCallback: (item) => this.onGridItemChange(item),
  };

  readonly filterForm = this.fb.group({
    region: [''],
    date_from: [''],
    date_to: [''],
  });

  ngOnInit(): void {
    if (!this.auth.isAuthenticated()) {
      this.router.navigate(['/login']);
      return;
    }
    this.dashboardId = this.route.snapshot.paramMap.get('id') ?? '';
    this.load();
  }

  ngOnDestroy(): void {
    this.refreshSub?.unsubscribe();
  }

  load(): void {
    this.dashboards.get(this.dashboardId).subscribe({
      next: (d) => {
        this.dashboard = d;
        this.filterForm.patchValue(d.global_filters_json as Record<string, string>);
        this.gridItems = d.cards.map((card) => ({
          card,
          grid: { ...card.layout_json, cardId: card.id },
          payload: card.snapshot_response_json as { response_type: string; data: Record<string, unknown> },
        }));
        this.setupAutoRefresh(d.cards);
      },
    });
  }

  setupAutoRefresh(cards: DashboardCard[]): void {
    this.refreshSub?.unsubscribe();
    const live = cards.filter((c) => c.refresh_mode === 'live' && c.auto_refresh_seconds);
    if (!live.length) return;
    const seconds = Math.min(...live.map((c) => c.auto_refresh_seconds ?? 60));
    this.refreshSub = interval(seconds * 1000).subscribe(() => this.refreshLiveCards());
  }

  onGridItemChange(item: GridsterItem): void {
    const cardId = (item as GridsterItem & { cardId?: string }).cardId;
    if (!cardId) return;
    const layout = { x: item.x ?? 0, y: item.y ?? 0, cols: item.cols ?? 4, rows: item.rows ?? 3 };
    this.dashboards.updateLayout(this.dashboardId, cardId, layout).subscribe();
  }

  applyFilters(): void {
    this.dashboards.updateFilters(this.dashboardId, this.filterForm.getRawValue()).subscribe();
  }

  refreshLiveCards(): void {
    const live = this.gridItems.filter((i) => i.card.refresh_mode === 'live');
    for (const item of live) {
      this.dashboards.refreshCard(this.dashboardId, item.card.id).subscribe({
        next: (card) => {
          item.card = card;
          item.payload = card.snapshot_response_json as { response_type: string; data: Record<string, unknown> };
        },
      });
    }
  }

  share(): void {
    this.dashboards.share(this.dashboardId).subscribe({
      next: (res) => {
        this.shareUrl = `${window.location.origin}${res.url_path}`;
      },
    });
  }

  logout(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
  }
}
