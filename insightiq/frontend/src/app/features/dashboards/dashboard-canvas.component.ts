import { CommonModule } from '@angular/common';
import { Component, OnDestroy, OnInit, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { GridsterConfig, GridsterItem, GridsterModule, DisplayGrid, GridType } from 'angular-gridster2';
import { Subscription, interval } from 'rxjs';

import { DashboardCard, DashboardDetail, DashboardService } from '../../core/dashboard.service';
import { ExportService } from '../../core/export.service';
import { ReportService } from '../../core/report.service';
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
          <a routerLink="/dashboards" class="back">← Dashboards</a>
          <h1>{{ dashboard?.name }}</h1>
        </div>
        <div class="actions">
          <button type="button" class="btn btn-secondary btn-sm" (click)="refreshLiveCards()">Refresh live</button>
          <button type="button" class="btn btn-ghost btn-sm" (click)="exportDashboard('pdf')">Export PDF</button>
          <button type="button" class="btn btn-ghost btn-sm" (click)="exportDashboard('pptx')">Export PPT</button>
          <button type="button" class="btn btn-ghost btn-sm" (click)="scheduleReport()">Schedule email</button>
          <button type="button" class="btn btn-primary btn-sm" (click)="share()">Share</button>
        </div>
      </header>

      <form class="filters" [formGroup]="filterForm" (ngSubmit)="applyFilters()">
        <input class="input" formControlName="region" placeholder="Filter: region" />
        <input class="input" formControlName="date_from" type="date" />
        <input class="input" formControlName="date_to" type="date" />
        <button type="submit" class="btn btn-secondary">Apply filters</button>
      </form>

      @if (shareUrl) {
        <p class="share">Share link: <code>{{ shareUrl }}</code></p>
      }

      <div class="canvas-shell">
        <gridster [options]="options">
          @for (item of gridItems; track item.card.id) {
            <gridster-item [item]="item.grid">
              <app-dashboard-card
                [title]="item.card.title"
                [refreshMode]="item.card.refresh_mode"
                [payload]="item.payload"
                [removable]="true"
                [editable]="true"
                (remove)="removeCard(item)"
                (titleChange)="renameCard(item, $event)"
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
        height: calc(100vh - var(--space-8) - var(--space-12));
      }
      .page {
        display: flex;
        flex-direction: column;
        height: 100%;
        max-width: none;
        width: 100%;
      }
      header {
        display: flex;
        justify-content: space-between;
        align-items: flex-start;
        gap: var(--space-4);
        margin-bottom: var(--space-4);
        flex-wrap: wrap;
        flex-shrink: 0;
      }
      h1 {
        margin: 6px 0 0;
        font-size: var(--text-xl);
      }
      .back {
        color: var(--text-muted);
        text-decoration: none;
        font-size: var(--text-sm);
      }
      .back:hover { color: var(--primary-text); }
      .actions {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
      }
      .filters {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
        margin-bottom: var(--space-4);
        flex-shrink: 0;
      }
      .filters .input { width: auto; min-width: 160px; }
      .share {
        font-size: var(--text-sm);
        color: var(--text-2);
        flex-shrink: 0;
        margin-bottom: var(--space-3);
      }
      .share code {
        color: var(--primary-text);
        background: var(--surface-2);
        padding: 2px 8px;
        border-radius: var(--radius-sm);
        font-family: var(--font-mono);
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
export class DashboardCanvasComponent implements OnInit, OnDestroy {
  private readonly route = inject(ActivatedRoute);
  private readonly dashboards = inject(DashboardService);
  private readonly exportService = inject(ExportService);
  private readonly reports = inject(ReportService);
  private readonly fb = inject(FormBuilder);

  dashboard: DashboardDetail | null = null;
  gridItems: { card: DashboardCard; grid: GridsterItem; payload: { response_type: string; data: Record<string, unknown> } }[] = [];
  shareUrl = '';
  private refreshSub?: Subscription;
  private dashboardId = '';

  options: GridsterConfig = {
    gridType: GridType.Fit,
    displayGrid: DisplayGrid.None,
    setGridSize: true,
    draggable: { enabled: true, dragHandleClass: 'dcard-drag-handle', ignoreContent: true },
    resizable: { enabled: true },
    pushItems: true,
    margin: 12,
    outerMargin: true,
    minCols: 12,
    maxCols: 12,
    minRows: 4,
    itemChangeCallback: (item) => this.onGridItemChange(item),
  };

  readonly filterForm = this.fb.group({
    region: [''],
    date_from: [''],
    date_to: [''],
  });

  ngOnInit(): void {
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
          grid: this.toGridItem(card),
          payload: card.snapshot_response_json as { response_type: string; data: Record<string, unknown> },
        }));
        const maxRow = d.cards.reduce((max, card) => {
          const layout = card.layout_json ?? {};
          const y = Number(layout['y'] ?? 0);
          const rows = Number(layout['rows'] ?? 3);
          return Math.max(max, y + rows);
        }, 0);
        this.options = {
          ...this.options,
          minRows: Math.max(maxRow, 4),
        };
        setTimeout(() => this.refreshGrid(), 0);
        this.setupAutoRefresh(d.cards);
      },
    });
  }

  private toGridItem(card: DashboardCard): GridsterItem & { cardId: string } {
    const layout = card.layout_json ?? {};
    return {
      x: Number(layout['x'] ?? 0),
      y: Number(layout['y'] ?? 0),
      cols: Number(layout['cols'] ?? 4),
      rows: Math.max(Number(layout['rows'] ?? 3), 2),
      cardId: card.id,
    };
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
    const layout = {
      x: item.x ?? 0,
      y: item.y ?? 0,
      cols: item.cols ?? 4,
      rows: Math.max(item.rows ?? 3, 2),
    };
    this.dashboards.updateLayout(this.dashboardId, cardId, layout).subscribe();
  }

  private refreshGrid(): void {
    this.options.api?.optionsChanged?.();
    this.options.api?.resize?.();
  }

  applyFilters(): void {
    this.dashboards.updateFilters(this.dashboardId, this.filterForm.getRawValue()).subscribe();
  }

  removeCard(item: { card: DashboardCard; grid: GridsterItem; payload: { response_type: string; data: Record<string, unknown> } }): void {
    const label = item.card.title || 'this pinned item';
    if (!confirm(`Remove "${label}" from this dashboard?`)) return;

    this.dashboards.removeCard(this.dashboardId, item.card.id).subscribe({
      next: () => {
        this.gridItems = this.gridItems.filter((entry) => entry.card.id !== item.card.id);
        const maxRow = this.gridItems.reduce((max, entry) => {
          const layout = entry.card.layout_json ?? {};
          const y = Number(layout['y'] ?? 0);
          const rows = Number(layout['rows'] ?? 3);
          return Math.max(max, y + rows);
        }, 0);
        this.options = { ...this.options, minRows: Math.max(maxRow, 4) };
        setTimeout(() => this.refreshGrid(), 0);
      },
    });
  }

  renameCard(
    item: { card: DashboardCard; grid: GridsterItem; payload: { response_type: string; data: Record<string, unknown> } },
    title: string,
  ): void {
    this.dashboards.updateCard(this.dashboardId, item.card.id, { title }).subscribe({
      next: (card) => {
        item.card = card;
      },
    });
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

  exportDashboard(format: 'pdf' | 'pptx'): void {
    this.exportService.exportDashboard(this.dashboardId, format).subscribe({
      next: (res) => this.exportService.downloadBlob(res, `dashboard.${format}`),
    });
  }

  scheduleReport(): void {
    const email = window.prompt('Recipient email for scheduled PDF report?');
    if (!email) return;
    this.reports
      .create({
        dashboard_id: this.dashboardId,
        recipient_email: email,
        interval_seconds: 3600,
        export_format: 'pdf',
      })
      .subscribe({
        next: () => window.alert('Report scheduled (hourly). Check backend logs for dev email delivery.'),
      });
  }
}
