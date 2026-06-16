import { JsonPipe, SlicePipe } from '@angular/common';
import { Component, OnInit, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { AuthService } from '../../core/auth.service';
import { DashboardService } from '../../core/dashboard.service';
import { PromptRun, PromptStudioService, PromptTemplate } from '../../core/prompt-studio.service';
import { ResponseRendererComponent } from '../../shared/response-renderer.component';

@Component({
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink, ResponseRendererComponent, JsonPipe, SlicePipe],
  template: `
    <div class="page">
      <header>
        <h1>Prompt Studio</h1>
        <a routerLink="/">Home</a>
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
        padding: 24px;
        max-width: 1100px;
        margin: 0 auto;
      }
      header {
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      .layout {
        display: grid;
        grid-template-columns: 280px 1fr;
        gap: 24px;
        margin-top: 20px;
      }
      aside ul {
        list-style: none;
        padding: 0;
        display: grid;
        gap: 4px;
      }
      aside button {
        width: 100%;
        text-align: left;
        padding: 8px 10px;
        border-radius: 8px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        background: transparent;
        color: inherit;
        cursor: pointer;
      }
      aside button.active {
        background: rgba(88, 166, 255, 0.2);
      }
      .badge {
        font-size: 10px;
        margin-left: 6px;
        opacity: 0.7;
      }
      input,
      textarea,
      select,
      button {
        width: 100%;
        padding: 10px 12px;
        border-radius: 10px;
        border: 1px solid rgba(255, 255, 255, 0.12);
        background: rgba(0, 0, 0, 0.25);
        color: inherit;
        margin-bottom: 8px;
        box-sizing: border-box;
      }
      .primary {
        background: rgba(88, 166, 255, 0.25);
      }
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
      .muted {
        opacity: 0.7;
      }
      .scores {
        display: flex;
        gap: 16px;
        margin-top: 12px;
        font-size: 13px;
      }
      .run-item {
        padding: 10px;
        border-radius: 8px;
        border: 1px solid rgba(255, 255, 255, 0.08);
        margin-bottom: 8px;
        display: flex;
        justify-content: space-between;
        gap: 12px;
      }
      pre {
        white-space: pre-wrap;
        font-size: 12px;
      }
    `,
  ],
})
export class PromptStudioComponent implements OnInit {
  private readonly promptService = inject(PromptStudioService);
  private readonly dashboardService = inject(DashboardService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
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
    if (!this.auth.isAuthenticated()) {
      this.router.navigate(['/login']);
      return;
    }
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
