import { AfterViewInit, Component, ElementRef, HostListener, OnDestroy, OnInit, ViewChild, inject, signal } from '@angular/core';
import { FormBuilder, FormsModule, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { GridsterConfig, GridsterItem, GridsterModule, DisplayGrid, GridType } from 'angular-gridster2';
import { Subscription, combineLatest, interval } from 'rxjs';

import { ConfirmService } from '../../core/confirm.service';
import { DashboardCard, DashboardDetail, DashboardService } from '../../core/dashboard.service';
import { ExportService } from '../../core/export.service';
import { ReportService } from '../../core/report.service';
import { ToastService } from '../../core/toast.service';
import { DashboardCardComponent } from '../../shared/dashboard-card.component';
import { IconComponent } from '../../shared/icon.component';

@Component({
  standalone: true,
  imports: [
    ReactiveFormsModule,
    FormsModule,
    RouterLink,
    GridsterModule,
    DashboardCardComponent,
    IconComponent,
  ],
  template: `
    <div class="page">
      @if (loading) {
        <div class="state-banner">Loading dashboard…</div>
      } @else if (loadError) {
        <div class="state-banner error">
          <p>{{ loadError }}</p>
          <a routerLink="/dashboards" class="back">← Back to dashboards</a>
        </div>
      } @else {
      <header>
        <div>
          <a routerLink="/dashboards" class="back">← Dashboards</a>
          <h1>{{ dashboard?.name || 'Dashboard' }}</h1>
        </div>
        <div class="actions">
          <button type="button" class="btn btn-secondary btn-sm" (click)="refreshLiveCards()">Refresh live</button>
          <button type="button" class="btn btn-ghost btn-sm" (click)="openExportModal()">Export…</button>
          <button type="button" class="btn btn-ghost btn-sm" (click)="openScheduleModal()">Schedule email</button>
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

      @if (exportModalOpen()) {
        <div class="modal-backdrop" (click)="closeExportModal()">
          <div class="modal" role="dialog" aria-modal="true" aria-label="Export dashboard" (click)="$event.stopPropagation()">
            <div class="modal-head">
              <h2>Export dashboard</h2>
              <button type="button" class="icon-btn" aria-label="Close" (click)="closeExportModal()"><app-icon name="close" [size]="14" /></button>
            </div>
            <label class="modal-field">
              <span>Format</span>
              <select [(ngModel)]="exportFormat">
                <option value="pdf">PDF document</option>
                <option value="pptx">PowerPoint deck</option>
              </select>
            </label>
            <label class="modal-checkbox">
              <input type="checkbox" [(ngModel)]="exportIncludeFilters" />
              <span>Include currently applied filters</span>
            </label>
            <div class="modal-actions">
              <button type="button" class="btn btn-ghost" (click)="closeExportModal()">Cancel</button>
              <button type="button" class="btn btn-primary" [disabled]="exporting()" (click)="confirmExport()">
                {{ exporting() ? 'Exporting…' : 'Export' }}
              </button>
            </div>
          </div>
        </div>
      }

      @if (scheduleModalOpen()) {
        <div class="modal-backdrop" (click)="closeScheduleModal()">
          <div class="modal" role="dialog" aria-modal="true" aria-label="Schedule email report" (click)="$event.stopPropagation()">
            <div class="modal-head">
              <h2>Schedule email report</h2>
              <button type="button" class="icon-btn" aria-label="Close" (click)="closeScheduleModal()"><app-icon name="close" [size]="14" /></button>
            </div>
            @if (scheduleError()) {
              <div class="modal-err">{{ scheduleError() }}</div>
            }
            <label class="modal-field">
              <span>Recipient email</span>
              <input class="input" type="email" [(ngModel)]="scheduleEmail" placeholder="you@company.com" />
            </label>
            <label class="modal-field">
              <span>Format</span>
              <select [(ngModel)]="scheduleFormat">
                <option value="pdf">PDF document</option>
                <option value="pptx">PowerPoint deck</option>
              </select>
            </label>
            <label class="modal-field">
              <span>Frequency</span>
              <select [(ngModel)]="scheduleIntervalSeconds">
                <option [ngValue]="3600">Hourly</option>
                <option [ngValue]="86400">Daily</option>
                <option [ngValue]="604800">Weekly</option>
              </select>
            </label>
            <div class="modal-actions">
              <button type="button" class="btn btn-ghost" (click)="closeScheduleModal()">Cancel</button>
              <button type="button" class="btn btn-primary" [disabled]="scheduling()" (click)="confirmSchedule()">
                {{ scheduling() ? 'Scheduling…' : 'Schedule' }}
              </button>
            </div>
          </div>
        </div>
      }

      @if (gridItems.length === 0) {
        <div class="empty-state">
          <div class="icon"><app-icon name="chart" [size]="28" /></div>
          <p>This dashboard has no cards yet.</p>
          <p class="hint">Pin a query result from <a routerLink="/talk-to-data">Talk to Data</a> to get started.</p>
        </div>
      } @else {
      <div class="canvas-shell" #canvasShell>
        <gridster [options]="options">
          @for (item of gridItems; track item.card.id) {
            <gridster-item [item]="item.grid">
              <app-dashboard-card
                [title]="item.card.title"
                [refreshMode]="item.card.refresh_mode"
                [highlighted]="highlightedCardId() === item.card.id"
                [payload]="item.payload"
                [removable]="true"
                [editable]="true"
                (remove)="removeCard(item)"
                (titleChange)="renameCard(item, $event)"
                (refreshModeChange)="setRefreshMode(item, $event)"
                (refresh)="refreshOneCard(item)"
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
        display: flex;
        flex-direction: column;
        flex: 1;
        min-height: 0;
        width: 100%;
      }
      .page {
        display: flex;
        flex-direction: column;
        width: 100%;
        flex: 1;
        min-height: 0;
        max-width: none;
      }
      .state-banner {
        padding: var(--space-8);
        color: var(--text-2);
        font-size: var(--text-base);
      }
      .state-banner.error {
        color: var(--danger);
      }
      .state-banner .back {
        display: inline-block;
        margin-top: var(--space-3);
        color: var(--text-muted);
        text-decoration: none;
      }
      .empty-state {
        flex: 1;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        min-height: 0;
        margin-top: var(--space-4);
        padding: var(--space-8);
        text-align: center;
        border: 1px dashed var(--border-strong);
        border-radius: var(--radius-md);
        background: var(--surface-2);
      }
      .empty-state .icon { font-size: 28px; margin-bottom: var(--space-3); }
      .empty-state p { margin: 0 0 var(--space-2); color: var(--text-2); }
      .empty-state .hint { font-size: var(--text-sm); color: var(--text-muted); }
      .empty-state a { color: var(--primary-text); }
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
        overflow: auto;
        border: 1px solid var(--border);
        border-radius: var(--radius-md);
        background: var(--surface-2);
      }
      :host ::ng-deep gridster {
        display: block;
        width: 100%;
        height: 100% !important;
        min-height: 100%;
        background: transparent;
      }
      :host ::ng-deep gridster .gridster-column,
      :host ::ng-deep gridster .gridster-row {
        display: none !important;
      }
      :host ::ng-deep gridster-item {
        background: transparent !important;
        overflow: visible;
      }
      :host ::ng-deep gridster-item app-dashboard-card {
        display: block;
        height: 100%;
        min-height: 0;
      }
      .modal-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--space-4); }
      .modal-head h2 { margin: 0; font-size: var(--text-lg); }
      .modal-err { margin-bottom: 12px; color: var(--danger); font-size: var(--text-sm); }
      .modal-field {
        display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px;
        font-size: var(--text-xs); color: var(--text-2); font-weight: 550;
      }
      .modal-field input, .modal-field select {
        padding: 9px 12px; border-radius: var(--radius-md);
        border: 1px solid var(--border-strong); background: var(--input-bg);
        color: var(--text); font-size: var(--text-base); font-family: inherit;
      }
      .modal-checkbox {
        display: flex; align-items: center; gap: 8px; margin-bottom: 16px;
        font-size: var(--text-sm); color: var(--text-2); cursor: pointer;
      }
      .modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 8px; }

      @media (max-width: 640px) {
        header { flex-direction: column; align-items: stretch; }
        .actions { width: 100%; }
        .actions .btn { flex: 1; }
        .filters { flex-direction: column; align-items: stretch; }
        .filters .input { width: 100%; min-width: 0; }
      }
    `,
  ],
})
export class DashboardCanvasComponent implements OnInit, AfterViewInit, OnDestroy {
  private readonly route = inject(ActivatedRoute);
  private readonly dashboards = inject(DashboardService);
  private readonly exportService = inject(ExportService);
  private readonly reports = inject(ReportService);
  private readonly fb = inject(FormBuilder);
  private readonly confirmDialog = inject(ConfirmService);
  private readonly toast = inject(ToastService);

  @ViewChild('canvasShell') canvasShell?: ElementRef<HTMLElement>;

  dashboard: DashboardDetail | null = null;
  gridItems: { card: DashboardCard; grid: GridsterItem; payload: { response_type: string; data: Record<string, unknown> } }[] = [];
  shareUrl = '';
  loading = true;
  loadError = '';
  readonly highlightedCardId = signal<string | null>(null);
  private focusCardId: string | null = null;
  private refreshSub?: Subscription;
  private routeSub?: Subscription;
  private resizeObserver?: ResizeObserver;
  private dashboardId = '';

  readonly fixedRowHeight = 100;

  options: GridsterConfig = {
    gridType: GridType.VerticalFixed,
    fixedRowHeight: this.fixedRowHeight,
    displayGrid: DisplayGrid.None,
    setGridSize: true,
    draggable: { enabled: true, dragHandleClass: 'dcard-drag-handle', ignoreContent: true },
    resizable: { enabled: true },
    pushItems: true,
    margin: 12,
    outerMargin: true,
    minCols: 12,
    maxCols: 12,
    minRows: 6,
    itemChangeCallback: (item) => this.onGridItemChange(item),
  };

  readonly filterForm = this.fb.group({
    region: [''],
    date_from: [''],
    date_to: [''],
  });

  readonly exportModalOpen = signal(false);
  readonly exporting = signal(false);
  exportFormat: 'pdf' | 'pptx' = 'pdf';
  exportIncludeFilters = true;

  readonly scheduleModalOpen = signal(false);
  readonly scheduling = signal(false);
  readonly scheduleError = signal('');
  scheduleEmail = '';
  scheduleFormat: 'pdf' | 'pptx' = 'pdf';
  scheduleIntervalSeconds = 3600;

  ngOnInit(): void {
    this.routeSub = combineLatest([this.route.paramMap, this.route.queryParamMap]).subscribe(([params, query]) => {
      this.dashboardId = params.get('id') ?? '';
      this.focusCardId = query.get('card');
      this.shareUrl = '';
      this.load();
    });
  }

  ngAfterViewInit(): void {
    this.resizeObserver = new ResizeObserver(() => this.syncGridToViewport());
    this.observeCanvas();
  }

  private observeCanvas(): void {
    if (!this.resizeObserver) return;
    this.resizeObserver.disconnect();
    const el = this.canvasShell?.nativeElement;
    if (el) this.resizeObserver.observe(el);
  }

  ngOnDestroy(): void {
    this.refreshSub?.unsubscribe();
    this.routeSub?.unsubscribe();
    this.resizeObserver?.disconnect();
  }

  load(): void {
    if (!this.dashboardId) {
      this.loading = false;
      this.loadError = 'Dashboard not found.';
      return;
    }

    this.loading = true;
    this.loadError = '';
    this.dashboards.get(this.dashboardId).subscribe({
      next: (d) => {
        this.dashboard = d;
        this.filterForm.patchValue((d.global_filters_json ?? {}) as Record<string, string>);
        this.gridItems = d.cards.map((card) => ({
          card,
          grid: this.toGridItem(card),
          payload: this.normalizePayload(card.snapshot_response_json),
        }));
        this.loading = false;
        setTimeout(() => {
          this.observeCanvas();
          this.syncGridToViewport();
          if (this.focusCardId) this.focusCard(this.focusCardId);
        }, 0);
        this.setupAutoRefresh(d.cards);
      },
      error: (err: { status?: number; error?: { detail?: string } }) => {
        this.loading = false;
        this.dashboard = null;
        this.gridItems = [];
        if (err.status === 404) {
          this.loadError = 'Dashboard not found or you do not have access.';
        } else {
          this.loadError = err.error?.detail ?? 'Could not load dashboard. Is the backend running?';
        }
      },
    });
  }

  private normalizePayload(raw: Record<string, unknown>): { response_type: string; data: Record<string, unknown> } {
    if (raw['response_type'] && raw['data']) {
      return raw as { response_type: string; data: Record<string, unknown> };
    }
    return { response_type: 'explanation', data: { output: JSON.stringify(raw, null, 2) } };
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

  private focusCard(cardId: string): void {
    const item = this.gridItems.find((entry) => entry.card.id === cardId);
    if (!item) return;

    this.highlightedCardId.set(cardId);
    const shell = this.canvasShell?.nativeElement;
    if (shell) {
      const margin = this.options.margin ?? 12;
      const rowUnit = this.fixedRowHeight + margin;
      const top = Math.max(0, Number(item.grid.y ?? 0) * rowUnit - margin);
      shell.scrollTo({ top, behavior: 'smooth' });
    }

    window.setTimeout(() => this.highlightedCardId.set(null), 3500);
  }

  private syncGridToViewport(): void {
    const shell = this.canvasShell?.nativeElement;
    const height = shell?.clientHeight ?? 480;
    const margin = this.options.margin ?? 12;
    const rowUnit = this.fixedRowHeight + margin;
    const rowsForViewport = Math.max(4, Math.floor((height + margin) / rowUnit));
    const maxCardRow = this.gridItems.reduce((max, entry) => {
      const y = Number(entry.grid.y ?? 0);
      const rows = Number(entry.grid.rows ?? 3);
      return Math.max(max, y + rows);
    }, 0);

    this.options = {
      ...this.options,
      fixedRowHeight: this.fixedRowHeight,
      minRows: Math.max(maxCardRow, rowsForViewport),
    };
    this.refreshGrid();
  }

  applyFilters(): void {
    this.dashboards.updateFilters(this.dashboardId, this.filterForm.getRawValue()).subscribe();
  }

  async removeCard(item: { card: DashboardCard; grid: GridsterItem; payload: { response_type: string; data: Record<string, unknown> } }): Promise<void> {
    const label = item.card.title || 'this pinned item';
    const ok = await this.confirmDialog.ask({
      title: `Remove "${label}"?`,
      message: 'This removes the card from this dashboard.',
      confirmLabel: 'Remove',
      danger: true,
    });
    if (!ok) return;

    this.dashboards.removeCard(this.dashboardId, item.card.id).subscribe({
      next: () => {
        this.gridItems = this.gridItems.filter((entry) => entry.card.id !== item.card.id);
        setTimeout(() => this.syncGridToViewport(), 0);
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

  setRefreshMode(
    item: { card: DashboardCard; grid: GridsterItem; payload: { response_type: string; data: Record<string, unknown> } },
    change: { mode: string; autoRefreshSeconds: number | null },
  ): void {
    this.dashboards.updateCard(this.dashboardId, item.card.id, {
      refresh_mode: change.mode,
      auto_refresh_seconds: change.autoRefreshSeconds,
    }).subscribe({
      next: (card) => {
        item.card = card;
        this.setupAutoRefresh(this.gridItems.map((entry) => entry.card));
        if (card.refresh_mode === 'live') {
          this.refreshOneCard(item);
        }
      },
    });
  }

  refreshOneCard(
    item: { card: DashboardCard; grid: GridsterItem; payload: { response_type: string; data: Record<string, unknown> } },
  ): void {
    if (item.card.refresh_mode !== 'live') return;
    this.dashboards.refreshCard(this.dashboardId, item.card.id).subscribe({
      next: (card) => {
        item.card = card;
        item.payload = this.normalizePayload(card.snapshot_response_json);
      },
    });
  }

  refreshLiveCards(): void {
    const live = this.gridItems.filter((i) => i.card.refresh_mode === 'live');
    for (const item of live) {
      this.refreshOneCard(item);
    }
  }

  share(): void {
    this.dashboards.share(this.dashboardId).subscribe({
      next: (res) => {
        this.shareUrl = `${window.location.origin}${res.url_path}`;
      },
    });
  }

  @HostListener('document:keydown.escape')
  onEscape(): void {
    if (this.exportModalOpen()) this.closeExportModal();
    if (this.scheduleModalOpen()) this.closeScheduleModal();
  }

  openExportModal(): void {
    this.exportModalOpen.set(true);
  }

  closeExportModal(): void {
    if (this.exporting()) return;
    this.exportModalOpen.set(false);
  }

  confirmExport(): void {
    this.exporting.set(true);
    this.exportService.exportDashboard(this.dashboardId, this.exportFormat, this.exportIncludeFilters).subscribe({
      next: (res) => {
        this.exportService.downloadBlob(res, `dashboard.${this.exportFormat}`);
        this.exporting.set(false);
        this.exportModalOpen.set(false);
      },
      error: () => {
        this.exporting.set(false);
        this.toast.error('Could not export dashboard.');
      },
    });
  }

  openScheduleModal(): void {
    this.scheduleError.set('');
    this.scheduleModalOpen.set(true);
  }

  closeScheduleModal(): void {
    if (this.scheduling()) return;
    this.scheduleModalOpen.set(false);
  }

  confirmSchedule(): void {
    const email = this.scheduleEmail.trim();
    if (!email) {
      this.scheduleError.set('Recipient email is required.');
      return;
    }
    this.scheduling.set(true);
    this.scheduleError.set('');
    this.reports
      .create({
        dashboard_id: this.dashboardId,
        recipient_email: email,
        interval_seconds: this.scheduleIntervalSeconds,
        export_format: this.scheduleFormat,
      })
      .subscribe({
        next: () => {
          this.scheduling.set(false);
          this.scheduleModalOpen.set(false);
          this.scheduleEmail = '';
        },
        error: () => {
          this.scheduling.set(false);
          this.scheduleError.set('Could not schedule the report. Please try again.');
        },
      });
  }
}
