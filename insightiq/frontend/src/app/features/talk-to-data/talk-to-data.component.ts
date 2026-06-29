import { HttpClient } from '@angular/common/http';
import { Component, ElementRef, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import { FormBuilder, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { DashboardService, Dashboard } from '../../core/dashboard.service';
import { API_BASE } from '../../core/api.config';
import { ResponseRendererComponent } from '../../shared/response-renderer.component';
import { SchemaTreeComponent } from '../../shared/schema-tree.component';
import { PromptPickerComponent } from '../../shared/prompt-picker.component';

type DataSource = { id: string; name: string; db_type: string; description?: string; metadata_status?: string };
type Schema = { tables: { name: string; columns: { name: string; data_type: string }[] }[] };
type ResponsePayload = { response_type: string; title?: string; data: Record<string, unknown> };
type AskResponse = {
  conversation_id: string;
  sql: string;
  response: ResponsePayload;
  clarification?: string;
  awaiting_confirmation?: boolean;
  proposed_sql?: string;
  interpretation?: string;
};
type Message = {
  role: 'user' | 'assistant';
  question?: string;
  sql?: string;
  response?: ResponsePayload;
  error?: string;
  awaitingConfirmation?: boolean;
  proposedSql?: string;
  interpretation?: string;
};
type Conversation = { id: string; title: string; starred: boolean; updated_at: string; datasource_id: string | null };
type ChatMessageMetadata = {
  response?: ResponsePayload;
  datasource_id?: string;
  sql?: string | null;
  awaiting_confirmation?: boolean;
  pending_sql?: string | null;
  pending_interpretation?: string | null;
  pending_original_question?: string | null;
};
type ChatMessageDto = {
  id: string;
  conversation_id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  metadata_json: ChatMessageMetadata;
  created_at: string;
};

@Component({
  standalone: true,
  imports: [ReactiveFormsModule, FormsModule, ResponseRendererComponent, SchemaTreeComponent, PromptPickerComponent, RouterLink],
  template: `
    <div class="page page-chat">
      <div class="page-header">
        <div>
          <span class="label-eyebrow">Analytics</span>
          <h1>Talk to Data</h1>
          <p>Ask questions in plain English. InsightIQ generates SQL and visualizes results.</p>
        </div>
        @if (sources().length === 0) {
          <a routerLink="/datasources" class="btn btn-primary">+ Add datasource</a>
        }
      </div>

      @if (sources().length === 0) {
        <div class="empty">
          <div class="empty-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="28" height="28"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5"/></svg>
          </div>
          <h3>No datasources connected</h3>
          <p>Connect a database to start asking questions in natural language.</p>
          <a routerLink="/datasources" class="btn btn-primary">Add datasource</a>
        </div>
      } @else {
        <div class="chat-workspace">
          <aside class="chat-side-panel side-panel">
            <div class="panel-section">
              <div class="panel-label">Datasource</div>
              <div class="source-row">
                <select [value]="selectedSourceId()" (change)="onSourceChange($any($event.target).value)">
                  <option value="">Select a datasource…</option>
                  @for (ds of sources(); track ds.id) {
                    <option [value]="ds.id">{{ ds.name }}</option>
                  }
                </select>
                @if (selectedSourceId()) {
                  <button
                    type="button"
                    class="icon-btn schema-btn"
                    title="View schema"
                    aria-label="View schema"
                    (click)="openSchemaPanel()"
                  >
                    🗂
                  </button>
                }
              </div>
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

          <div class="chat-panel">
            @if (!selectedSourceId()) {
              <div class="chat-welcome">
                <div class="icon-tile" aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><ellipse cx="12" cy="5" rx="8" ry="3"/><path d="M4 5v14c0 1.66 3.58 3 8 3s8-1.34 8-3V5"/></svg>
                </div>
                <h3>Select a datasource</h3>
                <p>Choose a connection on the left, then ask your first question.</p>
              </div>
            } @else {
              @if (messages().length === 0 && !loading()) {
                <div class="chat-messages">
                  <div class="chat-welcome">
                    <div class="icon-tile" aria-hidden="true">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                    </div>
                    <h3>Start a conversation</h3>
                    <p>Ask anything about your data — results appear as tables or charts.</p>
                    <div class="prompt-starters">
                      @for (s of suggestions; track s) {
                        <button type="button" class="prompt-starter" (click)="quickAsk(s)">{{ s }}</button>
                      }
                    </div>
                  </div>
                </div>
              } @else {
              <div class="chat-messages" #messagesPane>
                @for (msg of messages(); track $index) {
                  @if (msg.role === 'user') {
                    <div class="msg-row user">
                      <div class="msg-row-inner">
                        @if (editingIndex() === $index) {
                          <div class="msg-body">
                            <div class="edit-box">
                              <textarea [(ngModel)]="editDraft" rows="2" (keydown.enter)="$event.preventDefault(); saveEdit($index)"></textarea>
                              <div class="edit-actions">
                                <button class="btn-ghost sm" (click)="cancelEdit()">Cancel</button>
                                <button class="btn-primary sm" (click)="saveEdit($index)">Save &amp; resend</button>
                              </div>
                            </div>
                          </div>
                        } @else {
                          <div class="msg-body">
                            <div class="msg-bubble user">{{ msg.question }}</div>
                            <div class="msg-actions">
                              <button class="msg-icon-btn" title="Edit" (click)="startEdit($index, msg.question || '')">✎ Edit</button>
                              <button class="msg-icon-btn" title="Copy" (click)="copy(msg.question || '', 'u' + $index)">
                                {{ copied() === 'u' + $index ? '✓ Copied' : '⧉ Copy' }}
                              </button>
                            </div>
                          </div>
                          <div class="msg-avatar user" aria-hidden="true">You</div>
                        }
                      </div>
                    </div>
                  } @else {
                    <div class="msg-row assistant">
                      <div class="msg-row-inner">
                        <div class="msg-avatar bot" aria-hidden="true">IQ</div>
                        <div class="msg-body">
                          <div class="msg-bubble assistant">
                            @if (msg.error) {
                              <div class="error">{{ msg.error }}</div>
                            } @else {
                              @if (msg.awaitingConfirmation && msg.proposedSql) {
                                <details class="sql-details" open>
                                  <summary>Proposed SQL</summary>
                                  <pre>{{ msg.proposedSql }}</pre>
                                </details>
                              } @else if (msg.sql) {
                                <details class="sql-details">
                                  <summary>Generated SQL</summary>
                                  <pre>{{ msg.sql }}</pre>
                                </details>
                              }
                              <app-response-renderer [payload]="msg.response ?? null" />
                              @if (msg.awaitingConfirmation) {
                                <div class="confirm-actions">
                                  <button type="button" class="btn-primary sm" (click)="confirmProposal()" [disabled]="loading()">
                                    Yes, run it
                                  </button>
                                  <button type="button" class="btn-ghost sm" (click)="rejectProposal()" [disabled]="loading()">
                                    No, rephrase
                                  </button>
                                </div>
                              }
                            }
                          </div>
                          @if (!msg.error && !msg.awaitingConfirmation) {
                            <div class="msg-actions">
                              @if (msg.sql) {
                                <button class="msg-icon-btn" title="Copy SQL" (click)="copy(msg.sql || '', 's' + $index)">
                                  {{ copied() === 's' + $index ? '✓ Copied' : '⧉ SQL' }}
                                </button>
                              }
                              <button class="msg-icon-btn" title="Pin to dashboard" (click)="openPinModal(msg)" [disabled]="pinning()">
                                📌 Pin
                              </button>
                            </div>
                          }
                        </div>
                      </div>
                    </div>
                  }
                }

                @if (loading()) {
                  <div class="msg-row assistant">
                    <div class="msg-row-inner">
                      <div class="msg-avatar bot" aria-hidden="true">IQ</div>
                      <div class="msg-bubble assistant thinking">
                        <span class="typing"><span></span><span></span><span></span></span>
                      </div>
                    </div>
                  </div>
                }
              </div>
              }

              <form class="chat-composer" [formGroup]="askForm" (ngSubmit)="ask()">
                <div class="chat-composer-stack">
                  <app-prompt-picker
                    [selectedId]="selectedPromptId()"
                    (selectedIdChange)="selectedPromptId.set($event)"
                  />
                  <div class="chat-composer-row">
                    <input
                      formControlName="question"
                      placeholder="Ask about your data… e.g. monthly revenue by region"
                      autocomplete="off"
                      aria-label="Question"
                    />
                    <button type="submit" class="btn btn-primary" [disabled]="askForm.invalid || loading() || !selectedSourceId()">
                      {{ loading() ? 'Thinking…' : 'Ask' }}
                    </button>
                  </div>
                  <div class="chat-composer-hint">Press Enter to send · Follow-ups keep conversation context</div>
                </div>
              </form>
            }
          </div>
        </div>
      }
    </div>

    @if (schemaPanelOpen()) {
      <div class="modal-backdrop" (click)="closeSchemaPanel()">
        <div class="modal schema-modal" (click)="$event.stopPropagation()">
          <div class="modal-head">
            <h2>Schema</h2>
            <div class="modal-head-actions">
              <button type="button" class="btn-ghost tiny" (click)="loadSchema(true)" [disabled]="schemaLoading()">
                ↻ Refresh
              </button>
              <button type="button" class="icon-btn" title="Close" (click)="closeSchemaPanel()">✕</button>
            </div>
          </div>
          @if (selectedSource(); as src) {
            <p class="modal-sub">{{ src.name }}@if (schema()?.tables.length) { · {{ schema()!.tables.length }} tables }</p>
          }
          <div class="schema-modal-body">
            @if (schemaLoading()) {
              <p class="modal-hint">Loading schema…</p>
            } @else if (schema()?.tables.length) {
              <app-schema-tree [schema]="schema()" />
            } @else {
              <p class="modal-hint">No tables in scope for this datasource.</p>
            }
          </div>
        </div>
      </div>
    }

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

          <label class="modal-field">
            <span>Data refresh</span>
            <select [(ngModel)]="pinRefreshMode">
              <option value="snapshot">Snapshot — frozen at pin time</option>
              <option value="live">Live — re-run query on refresh</option>
            </select>
          </label>
          @if (pinRefreshMode === 'live') {
            <label class="modal-field">
              <span>Auto-refresh (optional)</span>
              <select [(ngModel)]="pinAutoRefreshSeconds">
                <option [ngValue]="null">Manual only</option>
                <option [ngValue]="60">Every 1 minute</option>
                <option [ngValue]="300">Every 5 minutes</option>
                <option [ngValue]="900">Every 15 minutes</option>
              </select>
            </label>
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
    .side-panel select {
      flex: 1; min-width: 0;
      padding: 9px 11px; border-radius: var(--radius-md);
      border: 1px solid var(--border-strong);
      background: var(--input-bg); color: var(--text); font-size: var(--text-base); font-family: inherit;
    }
    .side-panel select:focus { outline: none; border-color: var(--border-focus); box-shadow: 0 0 0 3px var(--primary-soft); }

    .source-row { display: flex; align-items: center; gap: 8px; }
    .schema-btn { flex-shrink: 0; width: 36px; height: 36px; justify-content: center; padding: 0; font-size: 16px; }

    .purpose-card { padding: 12px 14px; background: var(--primary-soft); border: 1px solid var(--primary-soft-2); border-radius: var(--radius-md); }
    .purpose-label { font-size: 10px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; color: var(--primary-text); margin-bottom: 4px; }
    .purpose-card p { margin: 0; font-size: var(--text-sm); color: var(--text-2); line-height: 1.5; }

    .history { display: flex; flex-direction: column; gap: 6px; flex: 1; min-height: 0; margin-top: 4px; padding-top: 12px; border-top: 1px solid var(--border); }
    .hist-head { display: flex; align-items: center; justify-content: space-between; }
    .new-chat {
      padding: 4px 10px; border-radius: var(--radius-pill);
      border: 1px solid var(--border-strong); background: var(--surface-2);
      color: var(--text-2); cursor: pointer; font-size: var(--text-xs); font-weight: 600; font-family: inherit;
    }
    .new-chat:hover { background: var(--primary-soft); color: var(--primary-text); border-color: var(--primary); }
    .hist-empty { font-size: var(--text-xs); color: var(--text-muted); padding: 4px 2px; line-height: 1.5; }
    .conv-main {
      flex: 1; min-width: 0; display: flex; align-items: center; gap: 6px;
      text-align: left; padding: 7px 9px; border: none; background: transparent;
      color: inherit; cursor: pointer; font-family: inherit;
    }
    .conv-star { color: var(--warning); font-size: 11px; }
    .conv-title { font-size: var(--text-sm); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .conv-actions { display: flex; gap: 2px; opacity: 0; flex-shrink: 0; }
    .conv-item:hover .conv-actions, .conv-item.active .conv-actions { opacity: 1; }
    .rename-input {
      flex: 1; min-width: 0; padding: 5px 8px; border-radius: var(--radius-sm);
      border: 1px solid var(--border-focus); background: var(--input-bg); color: var(--text);
      font-size: var(--text-sm); font-family: inherit;
    }

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
    .confirm-actions { display: flex; gap: 8px; flex-wrap: wrap; margin-top: 4px; }
    .error { color: var(--danger); font-size: var(--text-sm); }
    .thinking { padding: 16px !important; }

    .schema-modal { width: min(560px, 92vw); max-height: min(80vh, 720px); display: flex; flex-direction: column; }
    .schema-modal-body {
      flex: 1; min-height: 0; overflow: auto;
      padding: 4px 2px 2px; border-top: 1px solid var(--border); margin-top: 8px;
    }
    .modal-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 8px; }
    .modal-head h2 { margin: 0; font-size: var(--text-lg); }
    .modal-head-actions { display: flex; align-items: center; gap: 8px; }
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
    .icon-btn {
      display: inline-flex; align-items: center; padding: 3px 8px; border-radius: var(--radius-sm);
      border: 1px solid var(--border); background: var(--surface-2);
      color: var(--text-muted); cursor: pointer; font-size: var(--text-xs); font-family: inherit;
    }
    .icon-btn:hover { color: var(--text); border-color: var(--border-strong); }
    .icon-btn.xs { padding: 2px 5px; font-size: 11px; }
    .icon-btn.xs.danger:hover { background: var(--danger); color: #fff; border-color: var(--danger); }
  `],
})
export class TalkToDataComponent implements OnInit {
  private readonly dashboardService = inject(DashboardService);
  private readonly http = inject(HttpClient);
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly messagesPane = viewChild<ElementRef<HTMLElement>>('messagesPane');

  readonly sources = signal<DataSource[]>([]);
  readonly selectedSourceId = signal('');
  readonly schema = signal<Schema | null>(null);
  readonly schemaPanelOpen = signal(false);
  readonly schemaLoading = signal(false);
  readonly messages = signal<Message[]>([]);
  readonly loading = signal(false);
  readonly selectedPromptId = signal<string | null>(null);
  readonly pinning = signal(false);
  readonly copied = signal<string | null>(null);
  readonly pinModalOpen = signal(false);
  readonly pinDashboards = signal<Dashboard[]>([]);
  readonly pinMsg = signal<Message | null>(null);
  readonly pinCreateMode = signal(false);
  readonly pinError = signal('');
  pinSelectedDashboardId = '';
  pinNewDashboardName = 'My Dashboard';
  pinRefreshMode: 'snapshot' | 'live' = 'snapshot';
  pinAutoRefreshSeconds: number | null = null;
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
    this.schemaPanelOpen.set(false);
    this.newChat();
    if (id) {
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
              out.push({
                role: 'assistant',
                sql: this.assistantSqlFromDto(m),
                response,
                question: lastQuestion,
                awaitingConfirmation: !!m.metadata_json.awaiting_confirmation,
                proposedSql: m.metadata_json.pending_sql ?? undefined,
                interpretation: m.metadata_json.pending_interpretation ?? undefined,
              });
            } else {
              out.push({ role: 'assistant', error: m.content });
            }
          }
        }
        this.messages.set(out);
        this.scrollToBottom();
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
    this.schemaLoading.set(true);
    this.http.get<Schema>(`${API_BASE}/talk-to-data/sources/${id}/schema?refresh=${refresh}`).subscribe({
      next: (s) => {
        this.schema.set(s);
        this.schemaLoading.set(false);
      },
      error: () => this.schemaLoading.set(false),
    });
  }

  openSchemaPanel(): void {
    if (!this.selectedSourceId()) return;
    this.schemaPanelOpen.set(true);
    if (!this.schema()) {
      this.loadSchema(false);
    }
  }

  closeSchemaPanel(): void {
    this.schemaPanelOpen.set(false);
  }

  private assistantSqlFromDto(m: ChatMessageDto): string {
    const sqlMeta = m.metadata_json.sql;
    if (typeof sqlMeta === 'string' && sqlMeta.trim()) {
      return sqlMeta;
    }
    const content = m.content.trim();
    return content.toUpperCase().startsWith('SELECT') ? content : '';
  }

  quickAsk(q: string): void {
    this.ask(q);
  }

  confirmProposal(): void {
    this.ask('yes');
  }

  rejectProposal(): void {
    this.ask('no');
  }

  ask(override?: string): void {
    const q = (override ?? this.askForm.getRawValue().question ?? '').trim();
    if (!q || !this.selectedSourceId() || this.loading()) return;

    this.messages.update((m) => [...m, { role: 'user', question: q }]);
    if (override === undefined) this.askForm.reset();
    this.loading.set(true);
    this.scrollToBottom();

    this.http.post<AskResponse>(`${API_BASE}/talk-to-data/ask`, {
      datasource_id: this.selectedSourceId(),
      question: q,
      conversation_id: this.conversationId,
      prompt_template_id: this.selectedPromptId(),
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
          awaitingConfirmation: res.awaiting_confirmation,
          proposedSql: res.proposed_sql,
          interpretation: res.interpretation,
        }]);
        if (wasNew) this.reloadConversations();
        this.scrollToBottom();
      },
      error: (err: { error?: { detail?: string } }) => {
        this.loading.set(false);
        this.messages.update((m) => [...m, {
          role: 'assistant',
          error: err?.error?.detail ?? 'Query failed. Please try again.',
        }]);
        this.scrollToBottom();
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
    this.pinRefreshMode = 'snapshot';
    this.pinAutoRefreshSeconds = null;
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
      refresh_mode: this.pinRefreshMode,
      auto_refresh_seconds: this.pinRefreshMode === 'live' ? this.pinAutoRefreshSeconds : null,
      layout_json: { x: 0, y: 0, cols: 6, rows: 4 },
    }).subscribe({
      next: (card) => {
        this.pinning.set(false);
        this.closePinModal();
        const go = () => this.navigateToDashboard(dashboardId, card.id);
        if (this.pinRefreshMode === 'live') {
          this.dashboardService.refreshCard(dashboardId, card.id).subscribe({
            complete: go,
            error: go,
          });
          return;
        }
        go();
      },
      error: (err: { error?: { detail?: string } }) => {
        this.pinning.set(false);
        this.pinError.set(err?.error?.detail ?? 'Could not pin to dashboard.');
      },
    });
  }

  private navigateToDashboard(dashboardId: string, cardId: string): void {
    void this.router.navigate(['/dashboards', dashboardId], { queryParams: { card: cardId } });
  }

  private scrollToBottom(): void {
    setTimeout(() => {
      const el = this.messagesPane()?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    }, 0);
  }
}
