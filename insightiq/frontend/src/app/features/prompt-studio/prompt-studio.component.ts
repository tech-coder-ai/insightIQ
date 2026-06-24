import { SlicePipe } from '@angular/common';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { HttpClient } from '@angular/common/http';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { API_BASE } from '../../core/api.config';
import { DashboardService } from '../../core/dashboard.service';
import {
  PromptBindings,
  PromptRun,
  PromptStudioService,
  PromptTemplate,
  PromptTemplateDetail,
  PromptVersion,
} from '../../core/prompt-studio.service';
import { ResponseRendererComponent } from '../../shared/response-renderer.component';

type DataSourceOption = { id: string; name: string; db_type: string };
type CollectionOption = { id: string; name: string };
type DocumentOption = { id: string; filename: string; has_content: boolean };

@Component({
  standalone: true,
  imports: [ReactiveFormsModule, ResponseRendererComponent, SlicePipe, RouterLink],
  template: `
    <div class="page">
      <header>
        <h1>Prompt Studio</h1>
        <p class="subtitle">Create, test, refine, version and share prompt templates. Browse all prompts in <a routerLink="/prompt-library">Prompt Library</a>.</p>
      </header>

      <div class="layout">
        <aside>
          <h2>Library</h2>
          <ul>
            @for (t of templates; track t.id) {
              <li>
                <button type="button" [class.active]="selected?.id === t.id" (click)="select(t)">
                  <span class="tpl-name">{{ t.name }}</span>
                  <span class="tpl-meta">
                    @if (bindingLabel(t.bindings_json); as label) {
                      <span class="bind-tag">{{ label }}</span>
                    }
                    @if (t.is_shared) { <span class="badge">shared</span> }
                  </span>
                </button>
              </li>
            }
          </ul>

          <h3>New template</h3>
          <form [formGroup]="createForm" (ngSubmit)="createTemplate()">
            <input formControlName="name" placeholder="Template name" />
            <textarea formControlName="template_body" rows="4" placeholder="Summarize {{ '{{' }} metric {{ '}}' }} for {{ '{{' }} region {{ '}}' }}."></textarea>
            <button type="submit" class="primary">Create</button>
          </form>
        </aside>

        <main>
          @if (selectedDetail) {
            <div class="editor">
              <div class="head-row">
                <div class="title-block">
                  <input
                    class="title-input"
                    [value]="selectedDetail.name"
                    (change)="renameTemplate($any($event.target).value)"
                  />
                  <p class="muted">Version {{ selectedVersion?.version_number ?? selectedDetail.latest_version ?? 1 }}</p>
                </div>
                <div class="head-actions">
                  <button type="button" (click)="share()">{{ selectedDetail.is_shared ? 'Unshare' : 'Share to library' }}</button>
                </div>
              </div>

              <section class="panel">
                <div class="label-row">
                  <h3>Data binding</h3>
                  <button
                    type="button"
                    class="info-btn"
                    [attr.aria-expanded]="showBindingHelp"
                    aria-label="What is data binding?"
                    title="What is data binding?"
                    (click)="showBindingHelp = !showBindingHelp"
                  >
                    ⓘ
                  </button>
                </div>
                @if (showBindingHelp) {
                  <div class="info-tip">
                    Attach SQL, documents, or a file so each run has real data behind it.
                    Retrieved content is available as <code>{{ '{{' }} context {{ '}}' }}</code> in your template body.
                  </div>
                }
                <p class="hint">Attach a datasource query, RAG collection, or uploaded file. Bound context is injected as <code>{{ '{{' }} context {{ '}}' }}</code> in your template.</p>
                @if (datasources.length === 0 && bindingForm.value.type === 'sql') {
                  <p class="warn">No datasources yet. <a routerLink="/datasources">Register one</a> first.</p>
                }
                @if (collections.length === 0 && (bindingForm.value.type === 'rag' || bindingForm.value.type === 'file')) {
                  <p class="warn">No document collections yet. <a routerLink="/talk-to-docs">Create one in Talk to Docs</a>.</p>
                }
                <form [formGroup]="bindingForm" (ngSubmit)="saveBindings()">
                  <label>Source type</label>
                  <select formControlName="type" (change)="onBindingTypeChange()">
                    <option value="none">None (variables only)</option>
                    <option value="sql">Datasource (SQL)</option>
                    <option value="rag">Document collection (RAG)</option>
                    <option value="file">Uploaded file</option>
                  </select>

                  @if (bindingForm.value.type === 'sql') {
                    <label>Datasource</label>
                    <select formControlName="datasource_id">
                      <option value="">Select datasource…</option>
                      @for (ds of datasources; track ds.id) {
                        <option [value]="ds.id">{{ ds.name }} ({{ ds.db_type }})</option>
                      }
                    </select>
                    <label>SQL (Jinja supported)</label>
                    <textarea formControlName="sql" rows="3" placeholder="SELECT status, COUNT(*) AS row_count FROM customers GROUP BY status"></textarea>
                  }

                  @if (bindingForm.value.type === 'rag') {
                    <label>Document collection</label>
                    <select formControlName="collection_id" (change)="loadDocuments()">
                      <option value="">Select collection…</option>
                      @for (c of collections; track c.id) {
                        <option [value]="c.id">{{ c.name }}</option>
                      }
                    </select>
                    <label>Question variable name</label>
                    <input formControlName="query_variable" placeholder="question" />
                    <p class="hint">Run variables must include this key, e.g. {{ '{' }}"question": "What are the key risks?"{{ '}' }}</p>
                  }

                  @if (bindingForm.value.type === 'file') {
                    <label>Collection</label>
                    <select formControlName="collection_id" (change)="loadDocuments()">
                      <option value="">Select collection…</option>
                      @for (c of collections; track c.id) {
                        <option [value]="c.id">{{ c.name }}</option>
                      }
                    </select>
                    <label>Uploaded file</label>
                    <select formControlName="document_id">
                      <option value="">Select file…</option>
                      @for (d of documents; track d.id) {
                        <option [value]="d.id" [disabled]="!d.has_content">{{ d.filename }}{{ d.has_content ? '' : ' (processing)' }}</option>
                      }
                    </select>
                    <label class="file-upload">
                      Upload file to this collection
                      <input type="file" (change)="uploadFile($event)" accept=".pdf,.docx,.txt,.csv,.pptx,.md" />
                    </label>
                  }

                  <button type="submit" class="secondary">Save binding</button>
                </form>
              </section>

              <section class="panel">
                <h3>Template editor</h3>
                <form [formGroup]="editorForm">
                  <label>Description</label>
                  <input formControlName="description" placeholder="What this prompt is for" (blur)="saveMeta()" />
                  <label>System prompt</label>
                  <textarea formControlName="system_prompt" rows="2"></textarea>
                  <label>Template body (Jinja)</label>
                  <textarea formControlName="template_body" rows="6" placeholder="Summarize the following for {{ '{{' }} region {{ '}}' }}:\n\n{{ '{{' }} context {{ '}}' }}"></textarea>
                  <div class="actions">
                    <label class="inline">Version
                      <select formControlName="version_id" (change)="loadSelectedVersion()">
                        @for (v of versions; track v.id) {
                          <option [value]="v.id">v{{ v.version_number }} · {{ v.created_at | slice:0:10 }}</option>
                        }
                      </select>
                    </label>
                    <button type="button" class="secondary" (click)="saveNewVersion()">Save as new version</button>
                  </div>
                </form>
              </section>

              <section class="panel">
                <h3>Test run</h3>
                <form [formGroup]="runForm" (ngSubmit)="run()">
                  <div class="label-row">
                    <label>Variables (JSON)</label>
                    <button
                      type="button"
                      class="info-btn"
                      [attr.aria-expanded]="showVariablesHelp"
                      aria-label="What are run variables?"
                      title="What are run variables?"
                      (click)="showVariablesHelp = !showVariablesHelp"
                    >
                      ⓘ
                    </button>
                  </div>
                  @if (showVariablesHelp) {
                    <div class="info-tip">
                      The template above is reusable — placeholders like <code>{{ '{{' }} region {{ '}}' }}</code> are filled in at run time.
                      Use this JSON to supply those values for <strong>this test only</strong>.
                      Data binding injects <code>{{ '{{' }} context {{ '}}' }}</code> automatically; you usually do not put context here.
                      Use <code>{{ '{' }}{{ '}' }}</code> when the prompt is fully static.
                      RAG bindings need a question key, e.g. <code>{{ '{' }}"question": "What are the risks?"{{ '}' }}</code>.
                    </div>
                  }
                  <textarea formControlName="variablesJson" rows="4"></textarea>
                  @if (running()) {
                    <div class="run-progress" role="status" aria-live="polite" aria-label="Running prompt">
                      <div class="run-progress-track">
                        <div class="run-progress-bar"></div>
                      </div>
                      <span class="run-progress-label">Running prompt…</span>
                    </div>
                  }
                  <div class="actions">
                    <button type="submit" class="primary" [disabled]="running()">
                      {{ running() ? 'Running…' : 'Run prompt' }}
                    </button>
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
              </section>

              @if (lastRun) {
                <section class="panel output">
                  <h3>Latest output</h3>
                  <app-response-renderer [payload]="$any(lastRun.response)" [showTitle]="false" />
                  <div class="scores">
                    <span>Faithfulness: {{ lastRun.eval_scores.faithfulness }}</span>
                    <span>Relevancy: {{ lastRun.eval_scores.relevancy }}</span>
                    <span>Overall: {{ lastRun.eval_scores.overall }}</span>
                  </div>
                  @if (lastRun.context_preview) {
                    <details>
                      <summary>Context preview</summary>
                      <pre>{{ lastRun.context_preview }}</pre>
                    </details>
                  }
                  <details>
                    <summary>Rendered prompt</summary>
                    <pre>{{ lastRun.rendered_prompt }}</pre>
                  </details>
                </section>
              }

              <section class="panel">
                <div class="run-history-head">
                  <h3>Run history</h3>
                  @if (runs.length && selectedDetail?.is_mine) {
                    <button type="button" class="danger-link" (click)="clearAllRuns()">Clear all</button>
                  }
                </div>
                @if (runs.length === 0) {
                  <p class="muted">No runs yet. Use <strong>Run prompt</strong> above to test this template.</p>
                }
                @for (r of runs; track r.run_id) {
                  <div class="run-item">
                    <button type="button" class="run-open" (click)="openRun(r)">
                      <pre>{{ r.output.slice(0, 140) }}{{ r.output.length > 140 ? '…' : '' }}</pre>
                      <span class="muted">score {{ r.eval_scores.overall }}</span>
                    </button>
                    <button
                      type="button"
                      class="run-delete"
                      title="Delete run"
                      aria-label="Delete run"
                      (click)="deleteRun(r, $event)"
                    >
                      ✕
                    </button>
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
      .page { max-width: 1200px; margin: 0 auto; }
      header { margin-bottom: var(--space-6); }
      h1 { margin: 0 0 4px; font-size: var(--text-xl); }
      h2 { margin: 0; font-size: var(--text-lg); }
      h3 { margin: 0 0 10px; font-size: var(--text-base); color: var(--text); }
      .subtitle, .muted, .hint { color: var(--text-muted); font-size: var(--text-sm); }
      .subtitle { margin: 0; font-size: var(--text-base); color: var(--text-2); }
      .hint { margin: 0 0 10px; }
      .label-row { display: flex; align-items: center; gap: 8px; margin-bottom: 8px; }
      .label-row h3, .label-row label { margin: 0; }
      .info-btn {
        width: 22px; height: 22px; border-radius: 50%; border: 1px solid var(--border-strong);
        background: var(--surface-2); color: var(--text-2); cursor: pointer; font-size: 12px;
        line-height: 1; padding: 0; font-family: inherit;
      }
      .info-btn:hover { border-color: var(--primary); color: var(--primary-text); background: var(--primary-soft); }
      .info-tip {
        margin: 0 0 10px; padding: 10px 12px; border-radius: var(--radius-md);
        border: 1px solid var(--border); background: var(--surface-2); color: var(--text-2);
        font-size: var(--text-sm); line-height: 1.5;
      }
      .info-tip code { font-family: var(--font-mono); font-size: var(--text-xs); }
      .layout { display: grid; grid-template-columns: 280px 1fr; gap: var(--space-6); align-items: start; }
      aside, main, .panel {
        background: var(--surface);
        border: 1px solid var(--border);
        border-radius: var(--radius-lg);
        box-shadow: var(--shadow-sm);
      }
      aside { padding: var(--space-5); }
      main { padding: var(--space-6); }
      aside ul { list-style: none; padding: 0; margin: 0 0 var(--space-5); display: grid; gap: 4px; }
      aside ul button {
        width: 100%; text-align: left; padding: 9px 11px; border-radius: var(--radius-md);
        border: 1px solid transparent; background: transparent; color: inherit; cursor: pointer; font-family: inherit;
        display: flex; flex-direction: column; gap: 4px; align-items: flex-start;
      }
      .tpl-name { font-weight: 550; }
      .tpl-meta { display: flex; gap: 6px; flex-wrap: wrap; }
      .bind-tag {
        font-size: 10px; padding: 2px 7px; border-radius: var(--radius-pill);
        background: var(--surface-3); color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.04em;
      }
      aside ul button.active { background: var(--primary-soft); color: var(--primary-text); border-color: var(--primary); }
      .badge { font-size: var(--text-xs); margin-left: 6px; padding: 2px 7px; border-radius: var(--radius-pill); background: var(--primary-soft); color: var(--primary-text); }
      .panel { padding: var(--space-5); margin-top: var(--space-4); }
      .head-row { display: flex; justify-content: space-between; gap: 12px; align-items: flex-start; }
      .title-block { flex: 1; min-width: 0; }
      .title-input {
        width: 100%; padding: 8px 10px; border-radius: var(--radius-md); border: 1px solid var(--border-strong);
        background: var(--input-bg); color: var(--text); font-size: var(--text-lg); font-weight: 650; font-family: inherit;
        box-sizing: border-box; margin-bottom: 4px;
      }
      .warn { color: var(--warning, #b45309); font-size: var(--text-sm); margin: 0 0 10px; }
      .warn a { color: var(--primary-text); }
      code { font-family: var(--font-mono); font-size: 0.92em; }
      .file-upload input[type='file'] { margin-top: 6px; padding: 8px; }
      label { display: block; margin: 10px 0 6px; font-size: var(--text-xs); color: var(--text-2); font-weight: 600; }
      label.inline { display: flex; align-items: center; gap: 8px; margin: 0; font-size: var(--text-sm); }
      input, textarea, select, button {
        width: 100%; padding: 9px 12px; border-radius: var(--radius-md); border: 1px solid var(--border-strong);
        background: var(--input-bg); color: var(--text); box-sizing: border-box; font-family: inherit; font-size: var(--text-base);
      }
      textarea { font-family: var(--font-mono); font-size: var(--text-sm); resize: vertical; }
      button { cursor: pointer; font-weight: 550; }
      .primary { background: var(--primary); color: var(--on-primary); border-color: transparent; }
      .secondary { background: var(--surface-2); }
      .actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 12px; align-items: center; }
      .actions button, .actions select, label.inline select { width: auto; min-width: 160px; flex: 1; }
      .run-progress { margin-top: 12px; display: grid; gap: 8px; }
      .run-progress-track {
        height: 6px; border-radius: var(--radius-pill); background: var(--surface-3);
        overflow: hidden; position: relative;
      }
      .run-progress-bar {
        position: absolute; inset: 0 auto 0 0; width: 40%; border-radius: inherit;
        background: linear-gradient(90deg, var(--primary), color-mix(in srgb, var(--primary) 70%, white));
        animation: run-progress-slide 1.1s ease-in-out infinite;
      }
      .run-progress-label { font-size: var(--text-sm); color: var(--text-2); }
      @keyframes run-progress-slide {
        0% { transform: translateX(-100%); }
        100% { transform: translateX(350%); }
      }
      .scores { display: flex; gap: 16px; margin-top: 12px; font-size: var(--text-sm); color: var(--text-2); }
      .run-history-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 10px; }
      .run-history-head h3 { margin: 0; }
      .danger-link {
        border: none; background: transparent; color: var(--danger, #cf222e); cursor: pointer;
        font-size: var(--text-sm); font-family: inherit; padding: 0;
      }
      .danger-link:hover { text-decoration: underline; }
      .run-item {
        display: flex; justify-content: space-between; gap: 8px; align-items: stretch;
        margin-bottom: 8px;
      }
      .run-open {
        flex: 1; display: flex; justify-content: space-between; gap: 12px; align-items: flex-start;
        text-align: left; background: var(--surface-2); border: 1px solid var(--border);
        border-radius: var(--radius-md); padding: 10px 12px; cursor: pointer; color: inherit;
        font-family: inherit;
      }
      .run-open:hover { background: var(--surface-3); }
      .run-delete {
        width: 36px; flex-shrink: 0; border: 1px solid var(--border-strong);
        border-radius: var(--radius-md); background: var(--surface-2); color: var(--text-muted);
        cursor: pointer; font-family: inherit;
      }
      .run-delete:hover { color: var(--danger, #cf222e); border-color: var(--danger, #cf222e); background: var(--danger-soft, #ffebe9); }
      .run-item pre { margin: 0; white-space: pre-wrap; font-size: var(--text-xs); font-family: var(--font-mono); flex: 1; }
      pre { white-space: pre-wrap; font-size: var(--text-xs); font-family: var(--font-mono); }
      details summary { cursor: pointer; color: var(--text-2); font-size: var(--text-sm); margin-top: 8px; }
    `,
  ],
})
export class PromptStudioComponent implements OnInit {
  private readonly promptService = inject(PromptStudioService);
  private readonly dashboardService = inject(DashboardService);
  private readonly http = inject(HttpClient);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);

  templates: PromptTemplate[] = [];
  selected: PromptTemplate | null = null;
  selectedDetail: PromptTemplateDetail | null = null;
  selectedVersion: PromptVersion | null = null;
  versions: PromptVersion[] = [];
  runs: PromptRun[] = [];
  lastRun: PromptRun | null = null;
  dashboards: { id: string; name: string }[] = [];
  datasources: DataSourceOption[] = [];
  collections: CollectionOption[] = [];
  documents: DocumentOption[] = [];
  showVariablesHelp = false;
  showBindingHelp = false;
  readonly running = signal(false);

  readonly createForm = this.fb.group({
    name: ['Revenue summary', Validators.required],
    template_body: ['Summarize the following data for {{ region }}:\n\n{{ context }}', Validators.required],
  });

  readonly bindingForm = this.fb.group({
    type: ['none' as PromptBindings['type']],
    datasource_id: [''],
    sql: ['SELECT * FROM customers LIMIT 20'],
    collection_id: [''],
    query_variable: ['question'],
    document_id: [''],
  });

  readonly editorForm = this.fb.group({
    description: [''],
    system_prompt: ['You are a helpful analyst.'],
    template_body: ['', Validators.required],
    version_id: [''],
  });

  readonly runForm = this.fb.group({
    variablesJson: ['{"region": "EMEA", "question": "What are the main trends?"}', Validators.required],
  });

  ngOnInit(): void {
    this.loadTemplates();
    this.dashboardService.list().subscribe({ next: (d) => (this.dashboards = d) });
    this.http.get<DataSourceOption[]>(`${API_BASE}/talk-to-data/sources`).subscribe({
      next: (items) => (this.datasources = items),
    });
    this.http.get<CollectionOption[]>(`${API_BASE}/talk-to-docs/collections`).subscribe({
      next: (items) => (this.collections = items),
    });
    this.route.queryParamMap.subscribe((params) => {
      const templateId = params.get('template');
      if (templateId && this.templates.some((t) => t.id === templateId)) {
        const match = this.templates.find((t) => t.id === templateId);
        if (match) this.select(match);
      }
    });
  }

  loadTemplates(): void {
    this.promptService.listTemplates({ scope: 'all' }).subscribe({
      next: (items) => {
        this.templates = items;
        const templateId = this.route.snapshot.queryParamMap.get('template');
        if (templateId) {
          const match = items.find((t) => t.id === templateId);
          if (match) {
            this.select(match);
            return;
          }
        }
        if (!this.selected && items.length) this.select(items[0]);
      },
    });
  }

  select(t: PromptTemplate): void {
    this.selected = t;
    this.lastRun = null;
    this.promptService.getTemplate(t.id).subscribe({
      next: (detail) => {
        this.selectedDetail = detail;
        this.patchBindingForm(detail.bindings_json || {});
        this.editorForm.patchValue({
          description: detail.description,
          system_prompt: detail.system_prompt,
          template_body: detail.template_body,
          version_id: detail.latest_version_id ?? '',
        });
        if (detail.bindings_json?.collection_id || detail.bindings_json?.type === 'file') {
          this.loadDocuments();
        }
      },
    });
    this.promptService.listVersions(t.id).subscribe({
      next: (versions) => {
        this.versions = versions;
        this.selectedVersion = versions[0] ?? null;
      },
    });
    this.promptService.listRuns(t.id).subscribe({ next: (r) => (this.runs = r) });
  }

  patchBindingForm(bindings: PromptBindings): void {
    this.bindingForm.patchValue({
      type: bindings.type ?? 'none',
      datasource_id: bindings.datasource_id ?? '',
      sql: bindings.sql ?? '',
      collection_id: bindings.collection_id ?? '',
      query_variable: bindings.query_variable ?? 'question',
      document_id: bindings.document_id ?? '',
    });
  }

  bindingsFromForm(): PromptBindings {
    const v = this.bindingForm.getRawValue();
    const type = v.type ?? 'none';
    if (type === 'sql') {
      return { type, datasource_id: v.datasource_id || undefined, sql: v.sql || undefined };
    }
    if (type === 'rag') {
      return {
        type,
        collection_id: v.collection_id || undefined,
        query_variable: v.query_variable || 'question',
      };
    }
    if (type === 'file') {
      return {
        type,
        collection_id: v.collection_id || undefined,
        document_id: v.document_id || undefined,
      };
    }
    return { type: 'none' };
  }

  bindingLabel(bindings: PromptBindings | undefined): string | null {
    const label = this.promptService.bindingLabel(bindings);
    return label === 'Variables only' ? null : label;
  }

  renameTemplate(name: string): void {
    if (!this.selectedDetail) return;
    const trimmed = name.trim();
    if (!trimmed || trimmed === this.selectedDetail.name) return;
    this.promptService.updateTemplate(this.selectedDetail.id, { name: trimmed }).subscribe({
      next: (t) => {
        this.selectedDetail = { ...this.selectedDetail!, name: t.name };
        if (this.selected) this.selected = { ...this.selected, name: t.name };
        this.templates = this.templates.map((x) => (x.id === t.id ? { ...x, name: t.name } : x));
      },
    });
  }

  uploadFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    const collectionId = this.bindingForm.value.collection_id;
    if (!file || !collectionId) return;

    const body = new FormData();
    body.append('file', file);
    this.http.post(`${API_BASE}/talk-to-docs/collections/${collectionId}/upload`, body).subscribe({
      next: () => {
        window.setTimeout(() => this.loadDocuments(), 2500);
        alert('File uploaded. Wait for processing, then pick it from the list.');
      },
      error: () => alert('Upload failed'),
    });
    input.value = '';
  }

  onBindingTypeChange(): void {
    this.documents = [];
    const type = this.bindingForm.value.type;
    if (type === 'rag') {
      this.runForm.patchValue({ variablesJson: '{"question": "What are the key risks?"}' });
    } else if (type === 'sql') {
      this.runForm.patchValue({ variablesJson: '{"region": "EMEA"}' });
    } else {
      this.runForm.patchValue({ variablesJson: '{}' });
    }
  }

  loadDocuments(): void {
    const collectionId = this.bindingForm.value.collection_id;
    if (!collectionId) {
      this.documents = [];
      return;
    }
    this.http.get<DocumentOption[]>(`${API_BASE}/talk-to-docs/collections/${collectionId}/documents`).subscribe({
      next: (items) => (this.documents = items),
    });
  }

  saveBindings(): void {
    if (!this.selectedDetail) return;
    this.promptService.updateTemplate(this.selectedDetail.id, { bindings_json: this.bindingsFromForm() }).subscribe({
      next: (t) => {
        this.selectedDetail = { ...this.selectedDetail!, ...t };
        this.templates = this.templates.map((x) => (x.id === t.id ? { ...x, ...t } : x));
      },
    });
  }

  saveMeta(): void {
    if (!this.selectedDetail) return;
    const description = this.editorForm.value.description ?? '';
    if (description === this.selectedDetail.description) return;
    this.promptService.updateTemplate(this.selectedDetail.id, { description }).subscribe({
      next: (t) => {
        this.selectedDetail = { ...this.selectedDetail!, description: t.description };
      },
    });
  }

  loadSelectedVersion(): void {
    const versionId = this.editorForm.value.version_id;
    const version = this.versions.find((v) => v.id === versionId);
    if (!version) return;
    this.selectedVersion = version;
    this.editorForm.patchValue({
      system_prompt: version.system_prompt,
      template_body: version.template_body,
    });
  }

  saveNewVersion(): void {
    if (!this.selectedDetail || this.editorForm.invalid) return;
    const v = this.editorForm.getRawValue();
    this.promptService
      .createVersion(this.selectedDetail.id, {
        template_body: v.template_body!,
        system_prompt: v.system_prompt || '',
      })
      .subscribe({
        next: (version) => {
          this.versions = [version, ...this.versions.filter((x) => x.id !== version.id)];
          this.selectedVersion = version;
          this.selectedDetail = {
            ...this.selectedDetail!,
            latest_version: version.version_number,
            latest_version_id: version.id,
          };
          this.editorForm.patchValue({ version_id: version.id });
          this.templates = this.templates.map((t) =>
            t.id === this.selectedDetail!.id ? { ...t, latest_version: version.version_number } : t,
          );
        },
      });
  }

  createTemplate(): void {
    if (this.createForm.invalid) return;
    const v = this.createForm.getRawValue();
    this.promptService
      .createTemplate({ name: v.name!, template_body: v.template_body!, system_prompt: 'You are a helpful analyst.' })
      .subscribe({
        next: (t) => {
          this.templates = [t, ...this.templates];
          this.select(t);
        },
      });
  }

  run(): void {
    if (!this.selectedDetail || this.runForm.invalid || this.running()) return;
    let variables: Record<string, unknown> = {};
    try {
      variables = JSON.parse(this.runForm.getRawValue().variablesJson!);
    } catch {
      return;
    }
    const versionId = this.editorForm.value.version_id || this.selectedDetail.latest_version_id || undefined;
    this.running.set(true);
    this.promptService.run(this.selectedDetail.id, variables, versionId).subscribe({
      next: (r) => {
        this.lastRun = r;
        this.runs = [r, ...this.runs];
        this.running.set(false);
      },
      error: (err: { error?: { detail?: string } }) => {
        this.running.set(false);
        alert(err?.error?.detail ?? 'Prompt run failed');
      },
    });
  }

  openRun(r: PromptRun): void {
    this.lastRun = r;
  }

  deleteRun(r: PromptRun, event?: Event): void {
    event?.stopPropagation();
    if (!confirm('Delete this run from history?')) return;
    this.promptService.deleteRun(r.run_id).subscribe({
      next: () => {
        this.runs = this.runs.filter((x) => x.run_id !== r.run_id);
        if (this.lastRun?.run_id === r.run_id) {
          this.lastRun = this.runs[0] ?? null;
        }
      },
      error: (err: { error?: { detail?: string } }) => alert(err?.error?.detail ?? 'Could not delete run'),
    });
  }

  clearAllRuns(): void {
    if (!this.selectedDetail) return;
    if (!confirm('Delete all run history for this template?')) return;
    this.promptService.deleteAllRuns(this.selectedDetail.id).subscribe({
      next: () => {
        this.runs = [];
        this.lastRun = null;
      },
      error: (err: { error?: { detail?: string } }) => alert(err?.error?.detail ?? 'Could not clear run history'),
    });
  }

  share(): void {
    if (!this.selectedDetail) return;
    this.promptService.share(this.selectedDetail.id, !this.selectedDetail.is_shared).subscribe({
      next: (t) => {
        this.selectedDetail = { ...this.selectedDetail!, is_shared: t.is_shared };
        this.templates = this.templates.map((x) => (x.id === t.id ? { ...x, is_shared: t.is_shared } : x));
      },
      error: (err: { error?: { detail?: string } }) => alert(err?.error?.detail ?? 'Could not update sharing'),
    });
  }

  pinToDashboard(dashboardId: string): void {
    if (!this.lastRun || !dashboardId) return;
    this.promptService.pinRun(this.lastRun.run_id, dashboardId, this.selectedDetail?.name).subscribe({
      next: () => alert('Pinned to dashboard'),
    });
  }
}
