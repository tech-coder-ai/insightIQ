import { JsonPipe, SlicePipe } from '@angular/common';
import { Component, OnInit, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { DashboardService } from '../../core/dashboard.service';
import { PromptRun, PromptStudioService, PromptTemplate } from '../../core/prompt-studio.service';
import { ResponseRendererComponent } from '../../shared/response-renderer.component';

@Component({
  standalone: true,
  imports: [ReactiveFormsModule, ResponseRendererComponent, JsonPipe, SlicePipe],
  template: `
    <div class="page">
      <header>
        <h1>Prompt Studio</h1>
        <p class="subtitle">Build, version and evaluate prompt templates</p>
      </header>

      <div class="layout">
        <aside>
          <h2>Library</h2>
          <ul>
            @for (t of templates; track t.id) {
              <li>
                <button type="button" [class.active]="selected?.id === t.id" (click)="select(t)">
                  {{ t.name }}
                  @if (t.is_shared) {
                    <span class="badge">shared</span>
                  }
                </button>
              </li>
            }
          </ul>

          <h3>New template</h3>
          <form [formGroup]="createForm" (ngSubmit)="createTemplate()">
            <input formControlName="name" placeholder="Name" />
            <textarea formControlName="template_body" rows="4" placeholder="Hello {{ '{{' }} name {{ '}}' }}"></textarea>
            <textarea formControlName="system_prompt" rows="2" placeholder="System prompt (optional)"></textarea>
            <button type="submit" class="primary">Create</button>
          </form>
        </aside>

        <main>
          @if (selected) {
            <div class="editor">
              <h2>{{ selected.name }}</h2>
              <p class="muted">{{ selected.description || 'No description' }}</p>

              <form [formGroup]="runForm" (ngSubmit)="run()">
                <label>Variables (JSON)</label>
                <textarea formControlName="variablesJson" rows="3"></textarea>
                <div class="actions">
                  <button type="submit" class="primary">Run</button>
                  <button type="button" (click)="share()">{{ selected.is_shared ? 'Unshare' : 'Share' }}</button>
                  @if (lastRun) {
                    <select #dash (change)="pinToDashboard(dash.value)">
                      <option value="">Pin to dashboard…</option>
                      @for (d of dashboards; track d.id) {
                        <option [value]="d.id">{{ d.name }}</option>
                      }
                    </select>
                  }
                </div>
              </form>

              @if (lastRun) {
                <section class="output">
                  <h3>Output</h3>
                  <app-response-renderer [payload]="$any(lastRun.response)" />
                  <div class="scores">
                    <span>Faithfulness: {{ lastRun.eval_scores.faithfulness }}</span>
                    <span>Relevancy: {{ lastRun.eval_scores.relevancy }}</span>
                    <span>Overall: {{ lastRun.eval_scores.overall }}</span>
                  </div>
                  <details>
                    <summary>Rendered prompt</summary>
                    <pre>{{ lastRun.rendered_prompt }}</pre>
                  </details>
                </section>
              }

              <section>
                <h3>Run history</h3>
                @for (r of runs; track r.run_id) {
                  <div class="run-item">
                    <pre>{{ r.output | slice: 0 : 120 }}…</pre>
                    <span class="muted">score {{ r.eval_scores.overall }}</span>
                  </div>
                }
              </section>
            </div>
          } @else {
            <p class="muted">Select or create a template to get started.</p>
          }
        </main>
      </div>
    </div>
  `,
  styles: [
    `
      .page {
        max-width: 1140px;
        margin: 0 auto;
      }
      header {
        display: flex;
        flex-direction: column;
        gap: 4px;
        margin-bottom: var(--space-6);
      }
      h1 { margin: 0; font-size: var(--text-xl); }
      h2 { font-size: var(--text-lg); }
      h3 { font-size: var(--text-base); color: var(--text-2); }
      .subtitle { margin: 0; color: var(--text-2); font-size: var(--text-base); }
      .layout {
        display: grid;
        grid-template-columns: 290px 1fr;
        gap: var(--space-6);
      }
      aside {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius-lg);
        padding: var(--space-5);
        box-shadow: var(--shadow-sm);
        height: fit-content;
      }
      aside ul {
        list-style: none;
        padding: 0;
        display: grid;
        gap: 4px;
        margin: 0 0 var(--space-5);
      }
      aside ul button {
        width: 100%;
        text-align: left;
        padding: 9px 11px;
        border-radius: var(--radius-md);
        border: 1px solid transparent;
        background: transparent;
        color: inherit;
        cursor: pointer;
        font-family: inherit;
        font-size: var(--text-base);
        margin-bottom: 0;
        transition: background var(--dur-fast) var(--ease);
      }
      aside ul button:hover { background: var(--surface-2); }
      aside ul button.active {
        background: var(--primary-soft);
        color: var(--primary-text);
        border-color: var(--primary);
      }
      .badge {
        font-size: var(--text-xs);
        margin-left: 6px;
        padding: 2px 7px;
        border-radius: var(--radius-pill);
        background: var(--primary-soft);
        color: var(--primary-text);
      }
      main {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius-lg);
        padding: var(--space-6);
        box-shadow: var(--shadow-sm);
      }
      input,
      textarea,
      select,
      button {
        width: 100%;
        padding: 9px 12px;
        border-radius: var(--radius-md);
        border: 1px solid var(--border-strong);
        background: var(--input-bg);
        color: var(--text);
        margin-bottom: 8px;
        box-sizing: border-box;
        font-family: inherit;
        font-size: var(--text-base);
      }
      textarea { font-family: var(--font-mono); font-size: var(--text-sm); resize: vertical; }
      input:focus, textarea:focus, select:focus {
        outline: none; border-color: var(--border-focus); box-shadow: 0 0 0 3px var(--primary-soft);
      }
      button {
        cursor: pointer;
        font-weight: 550;
        transition: background var(--dur-fast) var(--ease);
      }
      .primary {
        background: var(--primary);
        color: var(--on-primary);
        border-color: transparent;
      }
      .primary:hover { background: var(--primary-hover); }
      .actions {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
      }
      .actions button,
      .actions select {
        width: auto;
        flex: 1;
        min-width: 120px;
      }
      .muted { color: var(--text-muted); }
      .output {
        margin-top: var(--space-5);
        padding-top: var(--space-5);
        border-top: 1px solid var(--border);
      }
      .scores {
        display: flex;
        gap: var(--space-4);
        margin-top: var(--space-3);
        font-size: var(--text-sm);
        color: var(--text-2);
      }
      .run-item {
        padding: 11px;
        border-radius: var(--radius-md);
        border: 1px solid var(--border);
        background: var(--surface-2);
        margin-bottom: 8px;
        display: flex;
        justify-content: space-between;
        gap: 12px;
      }
      pre {
        white-space: pre-wrap;
        font-size: var(--text-xs);
        font-family: var(--font-mono);
        margin: 0;
      }
      details summary { cursor: pointer; color: var(--text-2); font-size: var(--text-sm); }
    `,
  ],
})
export class PromptStudioComponent implements OnInit {
  private readonly promptService = inject(PromptStudioService);
  private readonly dashboardService = inject(DashboardService);
  private readonly fb = inject(FormBuilder);

  templates: PromptTemplate[] = [];
  selected: PromptTemplate | null = null;
  runs: PromptRun[] = [];
  lastRun: PromptRun | null = null;
  dashboards: { id: string; name: string }[] = [];

  readonly createForm = this.fb.group({
    name: ['Revenue summary', Validators.required],
    template_body: ['Summarize {{ metric }} for {{ region }}.', Validators.required],
    system_prompt: ['You are a financial analyst.'],
  });

  readonly runForm = this.fb.group({
    variablesJson: ['{"metric": "revenue", "region": "EMEA"}', Validators.required],
  });

  ngOnInit(): void {
    this.loadTemplates();
    this.dashboardService.list().subscribe({ next: (d) => (this.dashboards = d) });
  }

  loadTemplates(): void {
    this.promptService.listTemplates().subscribe({
      next: (items) => {
        this.templates = items;
        if (!this.selected && items.length) this.select(items[0]);
      },
    });
  }

  select(t: PromptTemplate): void {
    this.selected = t;
    this.lastRun = null;
    this.promptService.listRuns(t.id).subscribe({ next: (r) => (this.runs = r) });
  }

  createTemplate(): void {
    if (this.createForm.invalid) return;
    const v = this.createForm.getRawValue();
    this.promptService
      .createTemplate({
        name: v.name!,
        template_body: v.template_body!,
        system_prompt: v.system_prompt || '',
      })
      .subscribe({
        next: (t) => {
          this.templates = [t, ...this.templates];
          this.select(t);
        },
      });
  }

  run(): void {
    if (!this.selected || this.runForm.invalid) return;
    let variables: Record<string, unknown> = {};
    try {
      variables = JSON.parse(this.runForm.getRawValue().variablesJson!);
    } catch {
      return;
    }
    this.promptService.run(this.selected.id, variables).subscribe({
      next: (r) => {
        this.lastRun = r;
        this.runs = [r, ...this.runs];
      },
    });
  }

  share(): void {
    if (!this.selected) return;
    this.promptService.share(this.selected.id, !this.selected.is_shared).subscribe({
      next: (t) => {
        this.selected = t;
        this.templates = this.templates.map((x) => (x.id === t.id ? t : x));
      },
    });
  }

  pinToDashboard(dashboardId: string): void {
    if (!this.lastRun || !dashboardId) return;
    this.promptService.pinRun(this.lastRun.run_id, dashboardId, this.selected?.name).subscribe();
  }
}
