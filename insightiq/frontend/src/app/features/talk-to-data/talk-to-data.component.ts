import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormBuilder, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { DashboardService, Dashboard } from '../../core/dashboard.service';
import { API_BASE } from '../../core/api.config';
import { ResponseRendererComponent } from '../../shared/response-renderer.component';
import { SchemaTreeComponent } from '../../shared/schema-tree.component';

type DataSource = { id: string; name: string; db_type: string; description?: string; metadata_status?: string };
type Schema = { tables: { name: string; columns: { name: string; data_type: string }[] }[] };
type ResponsePayload = { response_type: string; title?: string; data: Record<string, unknown> };
type AskResponse = { conversation_id: string; sql: string; response: ResponsePayload };
type Message = {
  role: 'user' | 'assistant';
  question?: string;
  sql?: string;
  response?: ResponsePayload;
  error?: string;
};
type Conversation = { id: string; title: string; starred: boolean; updated_at: string; datasource_id: string | null };
type ChatMessageDto = {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  metadata_json: { response?: ResponsePayload; datasource_id?: string };
  created_at: string;
};

@Component({
  standalone: true,
  imports: [ReactiveFormsModule, FormsModule, ResponseRendererComponent, SchemaTreeComponent, RouterLink],
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

              <div class="history">
                <div class="hist-head">
                  <div class="panel-label">Conversations</div>
                  <button class="new-chat" (click)="newChat()">+ New chat</button>
                </div>
                @if (conversations().length === 0) {
                  <div class="hist-empty">No conversations yet. Ask a question to start one.</div>
                } @else {
                  <div class="conv-list">
                    @for (cv of conversations(); track cv.id) {
                      <div class="conv-item" [class.active]="activeConversationId() === cv.id">
                        @if (renamingId() === cv.id) {
                          <input class="rename-input" [(ngModel)]="renameDraft"
                            (keydown.enter)="saveRename(cv)" (keydown.escape)="renamingId.set(null)" (blur)="saveRename(cv)" />
                        } @else {
                          <button class="conv-main" (click)="openConversation(cv)">
                            @if (cv.starred) { <span class="conv-star">★</span> }
                            <span class="conv-title">{{ cv.title }}</span>
                          </button>
                          <div class="conv-actions">
                            <button class="icon-btn xs" [title]="cv.starred ? 'Unstar' : 'Star'" (click)="toggleStar(cv, $event)">{{ cv.starred ? '★' : '☆' }}</button>
                            <button class="icon-btn xs" title="Rename" (click)="startRename(cv, $event)">✎</button>
                            <button class="icon-btn xs danger" title="Delete" (click)="deleteConversation(cv, $event)">✕</button>
                          </div>
                        }
                      </div>
                    }
                  </div>
                }
              </div>
            }
          </aside>

          <div class="chat-area">
            @if (!selectedSourceId()) {
              <div class="chat-empty">
                <p>Select a datasource on the left, then ask a question below.</p>
              </div>
            } @else {
              @if (messages().length === 0) {
                <div class="chat-empty-inner">
                  <p>Ask anything about your data — results appear as tables or charts.</p>
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
                    <div class="msg-row user">
                      @if (editingIndex() === $index) {
                        <div class="edit-box">
                          <textarea [(ngModel)]="editDraft" rows="2" (keydown.enter)="$event.preventDefault(); saveEdit($index)"></textarea>
                          <div class="edit-actions">
                            <button class="btn-ghost sm" (click)="cancelEdit()">Cancel</button>
                            <button class="btn-primary sm" (click)="saveEdit($index)">Save &amp; resend</button>
                          </div>
                        </div>
                      } @else {
                        <div class="msg user-msg">{{ msg.question }}</div>
                        <div class="msg-actions">
                          <button class="icon-btn" title="Edit" (click)="startEdit($index, msg.question || '')">✎</button>
                          <button class="icon-btn" title="Copy" (click)="copy(msg.question || '', 'u' + $index)">
                            {{ copied() === 'u' + $index ? '✓' : '⧉' }}
                          </button>
                        </div>
                      }
                    </div>
                  } @else {
                    <div class="msg-row assistant">
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
                        }
                      </div>
                      @if (!msg.error) {
                        <div class="msg-actions">
                          @if (msg.sql) {
                            <button class="icon-btn" title="Copy SQL" (click)="copy(msg.sql || '', 's' + $index)">
                              {{ copied() === 's' + $index ? '✓ Copied' : '⧉ SQL' }}
                            </button>
                          }
                          <button class="icon-btn" title="Pin to dashboard" (click)="openPinModal(msg)" [disabled]="pinning()">
                            📌 Pin
                          </button>
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
            }
          </div>
        </div>
      }
    </div>

    @if (pinModalOpen()) {
      <div class="modal-backdrop" (click)="closePinModal()">
        <div class="modal" (click)="$event.stopPropagation()">
          <div class="modal-head">
            <h2>Pin to dashboard</h2>
            <button class="icon-btn" (click)="closePinModal()">✕</button>
          </div>
          <p class="modal-sub">{{ pinMsg()?.question ?? 'Query result' }}</p>

          @if (pinError()) {
            <div class="modal-err">{{ pinError() }}</div>
          }

          @if (pinDashboards().length === 0) {
            <p class="modal-hint">No dashboards yet. Create one to save this chart.</p>
            <label class="modal-field">
              <span>Dashboard name</span>
              <input [(ngModel)]="pinNewDashboardName" placeholder="My Dashboard" />
            </label>
            <div class="modal-actions">
              <button class="btn-ghost" (click)="closePinModal()">Cancel</button>
              <button class="btn-primary" (click)="confirmPin()" [disabled]="pinning() || !pinNewDashboardName.trim()">
                {{ pinning() ? 'Working…' : 'Create & pin' }}
              </button>
            </div>
          } @else {
            <label class="modal-field">
              <span>Choose dashboard</span>
              <select [(ngModel)]="pinSelectedDashboardId">
                @for (d of pinDashboards(); track d.id) {
                  <option [value]="d.id">{{ d.name }}</option>
                }
              </select>
            </label>
            @if (pinCreateMode()) {
              <label class="modal-field">
                <span>New dashboard name</span>
                <input [(ngModel)]="pinNewDashboardName" placeholder="Sales overview" />
              </label>
            } @else {
              <button class="link-btn" type="button" (click)="pinCreateMode.set(true)">+ Create new dashboard instead</button>
            }
            <div class="modal-actions">
              <button class="btn-ghost" (click)="closePinModal()">Cancel</button>
              <button class="btn-primary" (click)="confirmPin()" [disabled]="pinning() || !canConfirmPin()">
                {{ pinning() ? 'Working…' : (pinCreateMode() ? 'Create & pin' : 'Pin to dashboard') }}
              </button>
            </div>
          }
        </div>
      </div>
    }
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
    .btn-primary.sm { padding: 5px 12px; font-size: var(--text-xs); }
    .btn-ghost {
      padding: 5px 10px; border-radius: var(--radius-sm);
      border: 1px solid var(--border-strong);
      background: transparent; color: var(--text-2); cursor: pointer; font-size: var(--text-sm);
      font-family: inherit; transition: all var(--dur-fast) var(--ease);
    }
    .btn-ghost.tiny { padding: 3px 8px; font-size: var(--text-xs); }
    .btn-ghost.sm { padding: 5px 12px; font-size: var(--text-xs); }
    .btn-ghost:hover { background: var(--surface-2); color: var(--text); }

    .empty {
      text-align: center; padding: var(--space-12) var(--space-6);
      border: 1px dashed var(--border-strong); border-radius: var(--radius-lg);
      display: flex; flex-direction: column; align-items: center; gap: var(--space-4);
      color: var(--text-2);
    }
    .empty-icon { font-size: 48px; }

    .workspace {
      display: grid;
      grid-template-columns: 272px 1fr;
      gap: 20px;
      height: calc(100vh - 200px);
      min-height: 520px;
    }

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
    .schema-section { flex: 1; min-height: 120px; overflow: hidden; display: flex; flex-direction: column; }
    select {
      padding: 9px 11px; border-radius: var(--radius-md);
      border: 1px solid var(--border-strong);
      background: var(--input-bg); color: var(--text); font-size: var(--text-base); font-family: inherit;
    }
    select:focus { outline: none; border-color: var(--border-focus); box-shadow: 0 0 0 3px var(--primary-soft); }

    .purpose-card { padding: 12px 14px; background: var(--primary-soft); border: 1px solid var(--primary-soft-2); border-radius: var(--radius-md); }
    .purpose-label { font-size: 10px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; color: var(--primary); margin-bottom: 4px; }
    .purpose-card p { margin: 0; font-size: var(--text-sm); color: var(--text-2); line-height: 1.5; }

    .history { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; padding-top: 12px; border-top: 1px solid var(--border); }
    .hist-head { display: flex; align-items: center; justify-content: space-between; }
    .new-chat {
      padding: 4px 10px; border-radius: var(--radius-pill);
      border: 1px solid var(--border-strong); background: var(--surface-2);
      color: var(--text-2); cursor: pointer; font-size: var(--text-xs); font-weight: 600; font-family: inherit;
    }
    .new-chat:hover { background: var(--primary-soft); color: var(--primary-text); border-color: var(--primary); }
    .hist-empty { font-size: var(--text-xs); color: var(--text-muted); padding: 4px 2px; line-height: 1.5; }
    .conv-list { display: flex; flex-direction: column; gap: 2px; max-height: 200px; overflow-y: auto; }
    .conv-item {
      display: flex; align-items: center; gap: 2px; border-radius: var(--radius-md);
      border: 1px solid transparent; padding-right: 2px;
    }
    .conv-item:hover { background: var(--surface-2); }
    .conv-item.active { border-color: var(--primary); background: var(--primary-soft); }
    .conv-main {
      flex: 1; min-width: 0; display: flex; align-items: center; gap: 6px;
      text-align: left; padding: 7px 9px; border: none; background: transparent;
      color: inherit; cursor: pointer; font-family: inherit;
    }
    .conv-star { color: var(--warning, #d29922); font-size: 11px; }
    .conv-title { font-size: var(--text-sm); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .conv-actions { display: flex; gap: 2px; opacity: 0; flex-shrink: 0; }
    .conv-item:hover .conv-actions, .conv-item.active .conv-actions { opacity: 1; }
    .rename-input {
      flex: 1; min-width: 0; padding: 5px 8px; border-radius: var(--radius-sm);
      border: 1px solid var(--border-focus); background: var(--input-bg); color: var(--text);
      font-size: var(--text-sm); font-family: inherit;
    }

    .chat-area {
      display: flex; flex-direction: column;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      overflow: hidden;
      box-shadow: var(--shadow-sm);
    }
    .chat-empty, .chat-empty-inner {
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
    }
    .suggestion:hover { background: var(--primary-soft); color: var(--primary-text); border-color: var(--primary); }

    .messages {
      flex: 1; overflow-y: auto; padding: var(--space-5);
      display: flex; flex-direction: column; gap: var(--space-4);
    }
    .msg-row { display: flex; flex-direction: column; gap: 4px; max-width: 92%; }
    .msg-row.user { align-self: flex-end; align-items: flex-end; }
    .msg-row.assistant { align-self: flex-start; align-items: stretch; max-width: 94%; }
    .msg { max-width: 100%; }
    .user-msg {
      background: var(--primary); color: var(--on-primary);
      border-radius: 14px 14px 3px 14px;
      padding: 10px 14px; font-size: var(--text-base);
    }
    .assistant-msg {
      background: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: 3px 14px 14px 14px;
      padding: 14px; font-size: var(--text-base);
      display: flex; flex-direction: column; gap: 10px;
    }
    .msg-actions { display: flex; gap: 4px; opacity: 0; transition: opacity var(--dur-fast) var(--ease); }
    .msg-row:hover .msg-actions { opacity: 1; }
    .icon-btn {
      display: inline-flex; align-items: center; gap: 4px;
      padding: 3px 8px; border-radius: var(--radius-sm);
      border: 1px solid var(--border); background: var(--surface-2);
      color: var(--text-muted); cursor: pointer; font-size: var(--text-xs); font-family: inherit;
    }
    .icon-btn:hover { color: var(--text); border-color: var(--border-strong); background: var(--surface-3); }
    .icon-btn:disabled { opacity: 0.5; cursor: default; }
    .icon-btn.xs { padding: 2px 5px; font-size: 11px; }
    .icon-btn.xs.danger:hover { background: var(--danger); color: #fff; border-color: var(--danger); }

    .edit-box { display: flex; flex-direction: column; gap: 8px; width: 420px; max-width: 100%; }
    .edit-box textarea {
      width: 100%; box-sizing: border-box; resize: vertical;
      padding: 10px 12px; border-radius: var(--radius-md);
      border: 1px solid var(--border-focus); background: var(--input-bg);
      color: var(--text); font-size: var(--text-base); font-family: inherit;
    }
    .edit-actions { display: flex; gap: 8px; justify-content: flex-end; }

    .sql-details summary { cursor: pointer; font-size: var(--text-xs); color: var(--text-muted); }
    .sql-details pre {
      margin: 6px 0 0; padding: 10px; border-radius: var(--radius-md);
      background: var(--bg); border: 1px solid var(--border); font-size: var(--text-xs);
      overflow-x: auto; font-family: var(--font-mono);
    }
    .error { color: var(--danger); font-size: var(--text-sm); }

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
    }
    .input-bar input:focus { outline: none; border-color: var(--border-focus); box-shadow: 0 0 0 3px var(--primary-soft); }

    .modal-backdrop {
      position: fixed; inset: 0; z-index: 1000;
      background: rgba(0, 0, 0, 0.45);
      display: flex; align-items: center; justify-content: center; padding: 20px;
    }
    .modal {
      width: min(440px, 100%); background: var(--surface);
      border: 1px solid var(--border); border-radius: var(--radius-lg);
      padding: var(--space-6); box-shadow: var(--shadow-lg);
    }
    .modal-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
    .modal-head h2 { margin: 0; font-size: var(--text-lg); }
    .modal-sub { margin: 0 0 16px; color: var(--text-2); font-size: var(--text-sm); }
    .modal-hint { margin: 0 0 12px; color: var(--text-2); font-size: var(--text-sm); }
    .modal-err { margin-bottom: 12px; color: var(--danger); font-size: var(--text-sm); }
    .modal-field { display: flex; flex-direction: column; gap: 6px; margin-bottom: 14px; font-size: var(--text-xs); color: var(--text-2); font-weight: 550; }
    .modal-field input, .modal-field select {
      padding: 9px 12px; border-radius: var(--radius-md);
      border: 1px solid var(--border-strong); background: var(--input-bg);
      color: var(--text); font-size: var(--text-base); font-family: inherit;
    }
    .modal-actions { display: flex; justify-content: flex-end; gap: 10px; margin-top: 8px; }
    .link-btn {
      border: none; background: none; padding: 0; margin-bottom: 12px;
      color: var(--primary-text); cursor: pointer; font-size: var(--text-sm); font-family: inherit;
    }
    .link-btn:hover { text-decoration: underline; }
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
  readonly pinning = signal(false);
  readonly copied = signal<string | null>(null);
  readonly pinModalOpen = signal(false);
  readonly pinDashboards = signal<Dashboard[]>([]);
  readonly pinMsg = signal<Message | null>(null);
  readonly pinCreateMode = signal(false);
  readonly pinError = signal('');
  pinSelectedDashboardId = '';
  pinNewDashboardName = 'My Dashboard';
  readonly conversations = signal<Conversation[]>([]);
  readonly activeConversationId = signal<string | null>(null);
  readonly renamingId = signal<string | null>(null);
  readonly editingIndex = signal<number | null>(null);
  editDraft = '';
  renameDraft = '';

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
    this.newChat();
    if (id) {
      this.loadSchema(false);
      this.loadConversations(id);
    } else {
      this.conversations.set([]);
    }
  }

  loadConversations(datasourceId: string): void {
    this.http.get<Conversation[]>(`${API_BASE}/chat/conversations?datasource_id=${datasourceId}`).subscribe({
      next: (c) => this.conversations.set(c),
      error: () => this.conversations.set([]),
    });
  }

  newChat(): void {
    this.messages.set([]);
    this.conversationId = null;
    this.activeConversationId.set(null);
    this.editingIndex.set(null);
  }

  openConversation(cv: Conversation): void {
    this.activeConversationId.set(cv.id);
    this.conversationId = cv.id;
    this.messages.set([]);
    this.loading.set(true);
    this.http.get<ChatMessageDto[]>(`${API_BASE}/chat/messages?conversation_id=${cv.id}`).subscribe({
      next: (msgs) => {
        this.loading.set(false);
        const out: Message[] = [];
        let lastQuestion = '';
        for (const m of msgs) {
          if (m.role === 'user') {
            lastQuestion = m.content;
            out.push({ role: 'user', question: m.content });
          } else if (m.role === 'assistant') {
            const response = m.metadata_json?.response;
            if (response) {
              out.push({ role: 'assistant', sql: m.content, response, question: lastQuestion });
            } else {
              out.push({ role: 'assistant', error: m.content });
            }
          }
        }
        this.messages.set(out);
      },
      error: () => this.loading.set(false),
    });
  }

  startRename(cv: Conversation, ev: Event): void {
    ev.stopPropagation();
    this.renamingId.set(cv.id);
    this.renameDraft = cv.title;
  }

  saveRename(cv: Conversation): void {
    const title = this.renameDraft.trim();
    this.renamingId.set(null);
    if (!title || title === cv.title) return;
    this.http.patch<Conversation>(`${API_BASE}/chat/conversations/${cv.id}`, { title }).subscribe({
      next: () => this.reloadConversations(),
    });
  }

  toggleStar(cv: Conversation, ev: Event): void {
    ev.stopPropagation();
    this.http.patch<Conversation>(`${API_BASE}/chat/conversations/${cv.id}`, { starred: !cv.starred }).subscribe({
      next: () => this.reloadConversations(),
    });
  }

  deleteConversation(cv: Conversation, ev: Event): void {
    ev.stopPropagation();
    if (!confirm(`Delete conversation "${cv.title}"? This cannot be undone.`)) return;
    this.http.delete(`${API_BASE}/chat/conversations/${cv.id}`).subscribe({
      next: () => {
        if (this.activeConversationId() === cv.id) this.newChat();
        this.reloadConversations();
      },
    });
  }

  private reloadConversations(): void {
    const id = this.selectedSourceId();
    if (id) this.loadConversations(id);
  }

  loadSchema(refresh: boolean): void {
    const id = this.selectedSourceId();
    if (!id) return;
    this.http.get<Schema>(`${API_BASE}/talk-to-data/sources/${id}/schema?refresh=${refresh}`).subscribe({
      next: (s) => this.schema.set(s),
    });
  }

  quickAsk(q: string): void {
    this.ask(q);
  }

  ask(override?: string): void {
    const q = (override ?? this.askForm.getRawValue().question ?? '').trim();
    if (!q || !this.selectedSourceId() || this.loading()) return;

    this.messages.update((m) => [...m, { role: 'user', question: q }]);
    if (override === undefined) this.askForm.reset();
    this.loading.set(true);

    this.http.post<AskResponse>(`${API_BASE}/talk-to-data/ask`, {
      datasource_id: this.selectedSourceId(),
      question: q,
      conversation_id: this.conversationId,
    }).subscribe({
      next: (res) => {
        const wasNew = this.activeConversationId() !== res.conversation_id;
        this.conversationId = res.conversation_id;
        this.activeConversationId.set(res.conversation_id);
        this.loading.set(false);
        this.messages.update((m) => [...m, {
          role: 'assistant',
          sql: res.sql,
          response: res.response,
          question: q,
        }]);
        if (wasNew) this.reloadConversations();
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

  startEdit(index: number, question: string): void {
    this.editingIndex.set(index);
    this.editDraft = question;
  }

  cancelEdit(): void {
    this.editingIndex.set(null);
    this.editDraft = '';
  }

  saveEdit(index: number): void {
    const q = this.editDraft.trim();
    this.editingIndex.set(null);
    if (!q) return;
    this.messages.update((m) => m.slice(0, index));
    this.ask(q);
  }

  copy(text: string, key: string): void {
    navigator.clipboard?.writeText(text).then(() => {
      this.copied.set(key);
      setTimeout(() => { if (this.copied() === key) this.copied.set(null); }, 1500);
    });
  }

  openPinModal(msg: Message): void {
    if (!msg.response || this.pinning()) return;
    this.pinMsg.set(msg);
    this.pinError.set('');
    this.pinCreateMode.set(false);
    this.pinNewDashboardName = 'My Dashboard';
    this.pinning.set(true);
    this.dashboardService.list().subscribe({
      next: (dashboards) => {
        this.pinning.set(false);
        this.pinDashboards.set(dashboards);
        this.pinSelectedDashboardId = dashboards[0]?.id ?? '';
        this.pinModalOpen.set(true);
      },
      error: (err: { error?: { detail?: string } }) => {
        this.pinning.set(false);
        this.pinError.set(err?.error?.detail ?? 'Could not load dashboards.');
        this.pinDashboards.set([]);
        this.pinModalOpen.set(true);
      },
    });
  }

  closePinModal(): void {
    this.pinModalOpen.set(false);
    this.pinMsg.set(null);
    this.pinCreateMode.set(false);
    this.pinError.set('');
  }

  canConfirmPin(): boolean {
    if (this.pinCreateMode() || this.pinDashboards().length === 0) {
      return !!this.pinNewDashboardName.trim();
    }
    return !!this.pinSelectedDashboardId;
  }

  confirmPin(): void {
    const msg = this.pinMsg();
    if (!msg?.response || !this.canConfirmPin() || this.pinning()) return;

    const createNew = this.pinDashboards().length === 0 || this.pinCreateMode();
    if (createNew) {
      const name = this.pinNewDashboardName.trim();
      if (!name) return;
      this.pinning.set(true);
      this.pinError.set('');
      this.dashboardService.create(name).subscribe({
        next: (d) => this.pinToDashboardId(d.id, msg),
        error: (err: { error?: { detail?: string } }) => {
          this.pinning.set(false);
          this.pinError.set(err?.error?.detail ?? 'Could not create dashboard.');
        },
      });
      return;
    }

    this.pinToDashboardId(this.pinSelectedDashboardId, msg);
  }

  private pinToDashboardId(dashboardId: string, msg: Message): void {
    const sourceId = this.selectedSourceId();
    if (!sourceId || !msg.response) return;

    this.pinning.set(true);
    this.pinError.set('');
    this.dashboardService.pinCard(dashboardId, {
      title: msg.question ?? 'Pinned result',
      card_type: msg.response.response_type,
      response: JSON.parse(JSON.stringify(msg.response)) as Record<string, unknown>,
      source_type: 'sql',
      source_config: {
        datasource_id: sourceId,
        sql: msg.sql ?? '',
        question: msg.question ?? '',
      },
      refresh_mode: 'live',
    }).subscribe({
      next: () => {
        this.pinning.set(false);
        this.closePinModal();
        alert('Pinned to dashboard!');
      },
      error: (err: { error?: { detail?: string } }) => {
        this.pinning.set(false);
        this.pinError.set(err?.error?.detail ?? 'Could not pin to dashboard.');
      },
    });
  }
}
