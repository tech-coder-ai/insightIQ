import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { DashboardService } from '../../core/dashboard.service';
import { API_BASE } from '../../core/api.config';
import { ResponseRendererComponent } from '../../shared/response-renderer.component';
import { SchemaTreeComponent } from '../../shared/schema-tree.component';

type DataSource = { id: string; name: string; db_type: string; description?: string; metadata_status?: string };
type Schema = { tables: { name: string; columns: { name: string; data_type: string }[] }[] };
type ResponsePayload = { response_type: string; title?: string; data: Record<string, unknown> };
type AskResponse = { conversation_id: string; sql: string; response: ResponsePayload };
type Message = { role: 'user' | 'assistant'; question?: string; sql?: string; response?: ResponsePayload; error?: string };

@Component({
  standalone: true,
  imports: [ReactiveFormsModule, ResponseRendererComponent, SchemaTreeComponent, RouterLink],
  template: `
    <div class="page">
      <div class="page-header">
        <div>
          <h1>Talk to Data</h1>
          <p>Ask questions in plain English. InsightIQ generates SQL and visualizes the result.</p>
        </div>
        @if (sources().length === 0) {
          <a routerLink="/datasources" class="btn-primary">+ Add datasource</a>
        }
      </div>

      @if (sources().length === 0) {
        <div class="empty">
          <div class="empty-icon">📊</div>
          <p>No datasources connected yet.</p>
          <a routerLink="/datasources" class="btn-primary">Go to Datasources →</a>
        </div>
      } @else {
        <div class="workspace">
          <!-- ── Left: datasource selector + schema ── -->
          <aside class="side-panel">
            <div class="panel-section">
              <div class="panel-label">Datasource</div>
              <select [value]="selectedSourceId()" (change)="onSourceChange($any($event.target).value)">
                <option value="">Select a datasource…</option>
                @for (ds of sources(); track ds.id) {
                  <option [value]="ds.id">{{ ds.name }}</option>
                }
              </select>
            </div>

            @if (selectedSource(); as src) {
              @if (src.description) {
                <div class="purpose-card">
                  <div class="purpose-label">Purpose</div>
                  <p>{{ src.description }}</p>
                </div>
              }
            }

            @if (selectedSourceId()) {
              <div class="panel-section schema-section">
                <div class="panel-label">
                  Schema
                  <button class="btn-ghost tiny" (click)="loadSchema(true)">↻</button>
                </div>
                <app-schema-tree [schema]="schema()" />
              </div>
            }
          </aside>

          <!-- ── Right: chat ── -->
          <div class="chat-area">
            @if (messages().length === 0) {
              <div class="chat-empty">
                <p>Select a datasource on the left, then ask a question below.</p>
                <div class="suggestions">
                  @for (s of suggestions; track s) {
                    <button class="suggestion" (click)="quickAsk(s)">{{ s }}</button>
                  }
                </div>
              </div>
            }

            <div class="messages">
              @for (msg of messages(); track $index) {
                @if (msg.role === 'user') {
                  <div class="msg user-msg">{{ msg.question }}</div>
                } @else {
                  <div class="msg assistant-msg">
                    @if (msg.error) {
                      <div class="error">{{ msg.error }}</div>
                    } @else {
                      @if (msg.sql) {
                        <details class="sql-details">
                          <summary>Generated SQL</summary>
                          <pre>{{ msg.sql }}</pre>
                        </details>
                      }
                      <app-response-renderer [payload]="msg.response ?? null" />
                      <div class="msg-actions">
                        <button class="btn-ghost tiny" (click)="pinToDashboard(msg)">📌 Pin to dashboard</button>
                      </div>
                    }
                  </div>
                }
              }

              @if (loading()) {
                <div class="msg assistant-msg thinking">
                  <span></span><span></span><span></span>
                </div>
              }
            </div>

            <form class="input-bar" [formGroup]="askForm" (ngSubmit)="ask()">
              <input
                formControlName="question"
                placeholder="e.g. Show monthly revenue by region as a bar chart"
                autocomplete="off"
              />
              <button type="submit" class="btn-primary" [disabled]="askForm.invalid || loading() || !selectedSourceId()">
                Ask
              </button>
            </form>
          </div>
        </div>
      }
    </div>
  `,
  styles: [`
    .page { max-width: 1140px; }

    .btn-primary {
      padding: 9px 16px; border-radius: var(--radius-md); border: none;
      background: var(--primary); color: var(--on-primary); font-size: var(--text-base);
      font-weight: 550; cursor: pointer; text-decoration: none; display: inline-flex; align-items: center;
      font-family: inherit; transition: background var(--dur-fast) var(--ease);
    }
    .btn-primary:hover:not(:disabled) { background: var(--primary-hover); }
    .btn-primary:disabled { opacity: 0.5; cursor: default; }
    .btn-ghost {
      padding: 5px 10px; border-radius: var(--radius-sm);
      border: 1px solid var(--border-strong);
      background: transparent; color: var(--text-2); cursor: pointer; font-size: var(--text-sm);
      font-family: inherit; transition: all var(--dur-fast) var(--ease);
    }
    .btn-ghost.tiny { padding: 3px 8px; font-size: var(--text-xs); }
    .btn-ghost:hover { background: var(--surface-2); color: var(--text); }

    .empty {
      text-align: center; padding: var(--space-12) var(--space-6);
      border: 1px dashed var(--border-strong); border-radius: var(--radius-lg);
      display: flex; flex-direction: column; align-items: center; gap: var(--space-4);
      color: var(--text-2);
    }
    .empty-icon { font-size: 48px; }

    /* ── Workspace ── */
    .workspace {
      display: grid;
      grid-template-columns: 272px 1fr;
      gap: 20px;
      height: calc(100vh - 200px);
      min-height: 520px;
    }

    /* ── Side panel ── */
    .side-panel {
      display: flex; flex-direction: column; gap: var(--space-4);
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: var(--space-4);
      overflow-y: auto;
      box-shadow: var(--shadow-sm);
    }
    .panel-section { display: flex; flex-direction: column; gap: 8px; }
    .panel-label {
      font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em;
      color: var(--text-muted); font-weight: 700; display: flex; align-items: center; gap: 6px;
    }
    .schema-section { flex: 1; overflow: hidden; display: flex; flex-direction: column; }
    select {
      padding: 9px 11px; border-radius: var(--radius-md);
      border: 1px solid var(--border-strong);
      background: var(--input-bg); color: var(--text); font-size: var(--text-base); font-family: inherit;
    }
    select:focus { outline: none; border-color: var(--border-focus); box-shadow: 0 0 0 3px var(--primary-soft); }

    /* ── Chat ── */
    .chat-area {
      display: flex; flex-direction: column;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      overflow: hidden;
      box-shadow: var(--shadow-sm);
    }
    .chat-empty {
      flex: 1; display: flex; flex-direction: column;
      align-items: center; justify-content: center;
      gap: var(--space-5); padding: var(--space-10); text-align: center; color: var(--text-2);
    }
    .suggestions { display: flex; flex-wrap: wrap; gap: 8px; justify-content: center; }
    .suggestion {
      padding: 7px 14px; border-radius: var(--radius-pill);
      border: 1px solid var(--border-strong);
      background: var(--surface-2);
      color: var(--text-2); cursor: pointer; font-size: var(--text-sm); font-family: inherit;
      transition: all var(--dur-fast) var(--ease);
    }
    .suggestion:hover { background: var(--primary-soft); color: var(--primary-text); border-color: var(--primary); }

    .messages {
      flex: 1; overflow-y: auto; padding: var(--space-5);
      display: flex; flex-direction: column; gap: var(--space-4);
    }
    .msg { max-width: 92%; }
    .user-msg {
      align-self: flex-end;
      background: var(--primary); color: var(--on-primary);
      border-radius: 14px 14px 3px 14px;
      padding: 10px 14px; font-size: var(--text-base);
    }
    .assistant-msg {
      align-self: flex-start;
      background: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: 3px 14px 14px 14px;
      padding: 14px; font-size: var(--text-base);
      display: flex; flex-direction: column; gap: 10px;
    }
    .sql-details summary { cursor: pointer; font-size: var(--text-xs); color: var(--text-muted); }
    .sql-details pre {
      margin: 6px 0 0; padding: 10px; border-radius: var(--radius-md);
      background: var(--bg); border: 1px solid var(--border); font-size: var(--text-xs);
      overflow-x: auto; font-family: var(--font-mono);
    }
    .msg-actions { display: flex; gap: 8px; }
    .error { color: var(--danger); font-size: var(--text-sm); }

    /* thinking animation */
    .thinking { padding: 16px !important; flex-direction: row !important; }
    .thinking span {
      display: inline-block; width: 7px; height: 7px;
      border-radius: 50%; background: var(--primary-text); margin: 0 2px;
      animation: bounce 1.2s infinite;
    }
    .thinking span:nth-child(2) { animation-delay: 0.2s; }
    .thinking span:nth-child(3) { animation-delay: 0.4s; }
    @keyframes bounce { 0%,80%,100%{transform:translateY(0)} 40%{transform:translateY(-6px)} }

    .input-bar {
      display: flex; gap: 10px; padding: var(--space-4);
      border-top: 1px solid var(--border);
      background: var(--surface-2);
    }
    .input-bar input {
      flex: 1; padding: 10px 14px; border-radius: var(--radius-md);
      border: 1px solid var(--border-strong);
      background: var(--input-bg); color: var(--text); font-size: var(--text-base); font-family: inherit;
      transition: border-color var(--dur-fast) var(--ease), box-shadow var(--dur-fast) var(--ease);
    }
    .input-bar input:focus { outline: none; border-color: var(--border-focus); box-shadow: 0 0 0 3px var(--primary-soft); }
    .purpose-card { margin-top: 12px; padding: 12px 14px; background: var(--primary-soft); border: 1px solid var(--primary-soft-2); border-radius: var(--radius-md); }
    .purpose-label { font-size: 10px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; color: var(--primary); margin-bottom: 4px; }
    .purpose-card p { margin: 0; font-size: var(--text-sm); color: var(--text-2); line-height: 1.5; }
  `],
})
export class TalkToDataComponent implements OnInit {
  private readonly dashboardService = inject(DashboardService);
  private readonly http = inject(HttpClient);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);

  readonly sources = signal<DataSource[]>([]);
  readonly selectedSourceId = signal('');
  readonly schema = signal<Schema | null>(null);
  readonly messages = signal<Message[]>([]);
  readonly loading = signal(false);

  readonly selectedSource = computed(() =>
    this.sources().find((s) => s.id === this.selectedSourceId()) ?? null,
  );

  private conversationId: string | null = null;

  readonly askForm = this.fb.group({
    question: ['', Validators.required],
  });

  readonly suggestions = [
    'Show top 10 rows',
    'Row count by status',
    'Monthly trend as a line chart',
    'Show schema summary',
  ];

  ngOnInit(): void { this.loadSources(); }

  loadSources(): void {
    this.http.get<DataSource[]>(`${API_BASE}/talk-to-data/sources`).subscribe({
      next: (s) => {
        this.sources.set(s);
        const preselect = this.route.snapshot.queryParamMap.get('source');
        if (preselect && !this.selectedSourceId() && s.some((d) => d.id === preselect)) {
          this.onSourceChange(preselect);
        }
      },
    });
  }

  onSourceChange(id: string): void {
    this.selectedSourceId.set(id);
    this.schema.set(null);
    this.messages.set([]);
    this.conversationId = null;
    if (id) this.loadSchema(false);
  }

  loadSchema(refresh: boolean): void {
    const id = this.selectedSourceId();
    if (!id) return;
    this.http.get<Schema>(`${API_BASE}/talk-to-data/sources/${id}/schema?refresh=${refresh}`).subscribe({
      next: (s) => this.schema.set(s),
    });
  }

  quickAsk(q: string): void {
    this.askForm.patchValue({ question: q });
    this.ask();
  }

  ask(): void {
    const v = this.askForm.getRawValue();
    if (!v.question || !this.selectedSourceId()) return;

    this.messages.update((m) => [...m, { role: 'user', question: v.question! }]);
    this.askForm.reset();
    this.loading.set(true);

    this.http.post<AskResponse>(`${API_BASE}/talk-to-data/ask`, {
      datasource_id: this.selectedSourceId(),
      question: v.question,
      conversation_id: this.conversationId,
    }).subscribe({
      next: (res) => {
        this.conversationId = res.conversation_id;
        this.loading.set(false);
        this.messages.update((m) => [...m, {
          role: 'assistant',
          sql: res.sql,
          response: res.response,
        }]);
      },
      error: (err: { error?: { detail?: string } }) => {
        this.loading.set(false);
        this.messages.update((m) => [...m, {
          role: 'assistant',
          error: err?.error?.detail ?? 'Query failed. Please try again.',
        }]);
      },
    });
  }

  pinToDashboard(msg: Message): void {
    if (!msg.response) return;
    const question = msg.question ?? 'Pinned result';
    this.dashboardService.list().subscribe({
      next: (dashboards) => {
        const doPın = (dashboardId: string) => {
          this.dashboardService.pinCard(dashboardId, {
            title: question,
            card_type: msg.response!.response_type,
            response: msg.response! as unknown as Record<string, unknown>,
            source_type: 'sql',
            source_config: {
              datasource_id: this.selectedSourceId(),
              sql: msg.sql,
              question,
            },
            refresh_mode: 'live',
          }).subscribe({ next: () => alert('Pinned to dashboard!') });
        };
        if (dashboards.length) {
          doPın(dashboards[0].id);
        } else {
          this.dashboardService.create('My Dashboard').subscribe({ next: (d) => doPın(d.id) });
        }
      },
    });
  }
}
