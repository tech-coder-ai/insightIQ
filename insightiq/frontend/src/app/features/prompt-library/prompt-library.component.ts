import { Component, OnInit, inject, signal } from '@angular/core';
import { RouterLink } from '@angular/router';

import {
  PromptBindings,
  PromptListParams,
  PromptStudioService,
  PromptTemplate,
} from '../../core/prompt-studio.service';
import { IconComponent } from '../../shared/icon.component';

@Component({
  standalone: true,
  imports: [RouterLink, IconComponent],
  template: `
    <div class="page">
      <header class="head">
        <div>
          <h1>Prompt Library</h1>
          <p class="subtitle">All prompt templates you own or that are shared with your team.</p>
        </div>
        <a routerLink="/prompt-studio" class="btn btn-primary"><app-icon name="plus" [size]="14" /> Create in Studio</a>
      </header>

      <div class="toolbar">
        <div class="tabs">
          @for (tab of scopeTabs; track tab.value) {
            <button type="button" [class.active]="scope() === tab.value" (click)="setScope(tab.value)">
              {{ tab.label }}
            </button>
          }
        </div>
        <select [value]="binding()" (change)="setBinding($any($event.target).value)">
          <option value="">All bindings</option>
          <option value="none">Variables only</option>
          <option value="sql">SQL / Datasource</option>
          <option value="rag">RAG / Documents</option>
          <option value="file">Uploaded file</option>
        </select>
      </div>

      @if (loading()) {
        <div class="grid" aria-hidden="true">
          @for (i of [1, 2, 3, 4, 5, 6]; track i) {
            <article class="card">
              <div class="skeleton" style="width: 60%; height: 16px; margin-bottom: 10px;"></div>
              <div class="skeleton" style="width: 90%; height: 12px; margin-bottom: 8px;"></div>
              <div class="skeleton" style="width: 70%; height: 12px; margin-bottom: 14px;"></div>
              <div class="skeleton" style="width: 40%; height: 30px; border-radius: var(--radius-md);"></div>
            </article>
          }
        </div>
      } @else if (templates().length === 0) {
        <div class="empty">
          <p>No prompts match these filters.</p>
          <a routerLink="/prompt-studio" class="btn btn-secondary">Create your first prompt</a>
        </div>
      } @else {
        <div class="grid">
          @for (t of templates(); track t.id) {
            <article class="card">
              <div class="card-head">
                <h2>{{ t.name }}</h2>
                <div class="tags">
                  <span class="tag">{{ bindingLabel(t.bindings_json) }}</span>
                  @if (t.is_shared) { <span class="tag shared">Shared</span> }
                  @if (t.is_mine) { <span class="tag mine">Mine</span> }
                </div>
              </div>
              @if (t.description) {
                <p class="desc">{{ t.description }}</p>
              } @else {
                <p class="desc muted">No description</p>
              }
              <p class="meta">Version {{ t.latest_version ?? 1 }}</p>
              <div class="actions">
                <a class="btn btn-secondary" [routerLink]="['/prompt-studio']" [queryParams]="{ template: t.id }">
                  Open in Studio
                </a>
              </div>
            </article>
          }
        </div>
      }
    </div>
  `,
  styles: [`
    .page { max-width: 1100px; margin: 0 auto; }
    .head { display: flex; justify-content: space-between; gap: 16px; align-items: flex-start; margin-bottom: var(--space-6); }
    h1 { margin: 0 0 6px; font-size: var(--text-xl); }
    .subtitle, .muted { color: var(--text-muted); margin: 0; }
    .toolbar { display: flex; flex-wrap: wrap; gap: 12px; align-items: center; margin-bottom: var(--space-5); }
    .tabs { display: flex; gap: 6px; flex-wrap: wrap; }
    .tabs button, select {
      padding: 8px 12px; border-radius: var(--radius-md); border: 1px solid var(--border-strong);
      background: var(--surface); color: var(--text); font-family: inherit; cursor: pointer;
    }
    .tabs button.active { background: var(--primary-soft); color: var(--primary-text); border-color: var(--primary); }
    select { min-width: 180px; }
    .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: var(--space-4); }
    .card {
      background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
      padding: var(--space-5); box-shadow: var(--shadow-sm); display: grid; gap: 10px;
    }
    .card-head h2 { margin: 0; font-size: var(--text-lg); }
    .tags { display: flex; gap: 6px; flex-wrap: wrap; margin-top: 8px; }
    .tag {
      font-size: 10px; padding: 2px 8px; border-radius: var(--radius-pill);
      background: var(--surface-3); color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.04em;
    }
    .tag.shared { background: var(--primary-soft); color: var(--primary-text); }
    .tag.mine { background: var(--surface-2); }
    .desc { margin: 0; color: var(--text-2); font-size: var(--text-sm); line-height: 1.5; }
    .meta { margin: 0; font-size: var(--text-xs); color: var(--text-muted); }
    .actions { display: flex; gap: 8px; margin-top: 4px; }
    .empty {
      padding: var(--space-8); text-align: center; border: 1px dashed var(--border-strong);
      border-radius: var(--radius-lg); background: var(--surface);
    }
  `],
})
export class PromptLibraryComponent implements OnInit {
  private readonly promptService = inject(PromptStudioService);

  readonly scope = signal<PromptListParams['scope']>('all');
  readonly binding = signal<PromptListParams['binding'] | ''>('');
  readonly templates = signal<PromptTemplate[]>([]);
  readonly loading = signal(true);

  readonly scopeTabs = [
    { value: 'all' as const, label: 'All' },
    { value: 'mine' as const, label: 'Mine' },
    { value: 'shared' as const, label: 'Shared' },
  ];

  ngOnInit(): void {
    this.load();
  }

  setScope(scope: PromptListParams['scope']): void {
    this.scope.set(scope);
    this.load();
  }

  setBinding(value: string): void {
    this.binding.set((value || '') as PromptListParams['binding'] | '');
    this.load();
  }

  bindingLabel(bindings: PromptBindings | undefined): string {
    return this.promptService.bindingLabel(bindings);
  }

  load(): void {
    this.loading.set(true);
    const params: PromptListParams = { scope: this.scope() };
    const binding = this.binding();
    if (binding) params.binding = binding;
    this.promptService.listTemplates(params).subscribe({
      next: (items) => {
        this.templates.set(items);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }
}
