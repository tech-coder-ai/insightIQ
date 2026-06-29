import { HttpClient } from '@angular/common/http';
import { Component, ElementRef, OnDestroy, OnInit, computed, inject, signal, viewChild } from '@angular/core';
import { FormBuilder, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';

import { API_BASE } from '../../core/api.config';
import { MarkdownDirective } from '../../core/markdown.directive';
import { PromptPickerComponent } from '../../shared/prompt-picker.component';

type Collection = { id: string; name: string; rag_profile: string; doc_count?: number };
type HighlightSpan = {
  chunk_id: string;
  document_id: string;
  char_start: number;
  char_end: number;
  color: string;
  ref_index?: number;
  text_snippet?: string;
  filename?: string;
  page_number?: number | null;
};
type ChunkDetail = {
  chunk_id: string;
  document_id: string;
  filename: string;
  page_number: number | null;
  char_start: number;
  char_end: number;
  text: string;
  excerpt: string;
};
type DocumentView = {
  document_id: string;
  filename: string;
  content: string;
  highlight_start: number | null;
  highlight_end: number | null;
  page_number: number | null;
};
type DocumentHighlightParts = { before: string; highlight: string; after: string };
type AskResponse = { conversation_id: string; answer: string; answer_html: string; highlight_spans: HighlightSpan[] };
type Message = { role: 'user' | 'assistant'; question?: string; answerMd?: string; highlights?: HighlightSpan[]; error?: string };
type Conversation = { id: string; title: string; starred: boolean; updated_at: string; datasource_id: string | null };
type ChatMessageDto = { id: string; conversation_id: string; role: 'user' | 'assistant' | 'system'; content: string; metadata_json: { highlight_spans_json?: HighlightSpan[] }; created_at: string };

type IngestionJob = {
  job_id: string;
  kind: 'file' | 'scrape';
  collection_id: string;
  stages: string[];
  stage: string;
  status: 'processing' | 'completed' | 'failed';
  detail: string;
  progress_current: number;
  progress_total: number;
  error: string | null;
  documents: { document_id: string; filename: string; chunks: number }[];
};

const STAGE_LABELS: Record<string, string> = {
  queued: 'Queued',
  fetching: 'Crawling pages',
  extracting: 'Extracting text',
  chunking: 'Chunking',
  indexing: 'Embedding & indexing',
  saving: 'Saving',
  completed: 'Done',
};

const RAG_PROFILES = [
  { value: 'naive',    label: 'Naive',    desc: 'Fast, simple vector search' },
  { value: 'advanced', label: 'Advanced', desc: 'Re-ranking + HyDE query expansion' },
  { value: 'graph',    label: 'Graph',    desc: 'Neo4j knowledge graph traversal' },
  { value: 'agentic',  label: 'Agentic',  desc: 'Multi-hop agent with reflection' },
];

@Component({
  standalone: true,
  imports: [ReactiveFormsModule, FormsModule, MarkdownDirective, PromptPickerComponent],
  template: `
    <div class="page page-chat">
      <div class="page-header">
        <div>
          <span class="label-eyebrow">Knowledge base</span>
          <h1>Talk to Documents</h1>
          <p>Upload documents, run the RAG pipeline, and chat with grounded answers and citations.</p>
        </div>
        <button class="btn btn-ghost" (click)="showNewCollection.set(!showNewCollection())">
          {{ showNewCollection() ? 'Cancel' : '+ New collection' }}
        </button>
      </div>

      <!-- ── New collection form ── -->
      @if (showNewCollection()) {
        <div class="panel">
          <h2>Create collection</h2>
          <form [formGroup]="colForm" (ngSubmit)="createCollection()">
            <label>
              <span>Collection name *</span>
              <input formControlName="name" placeholder="e.g. Product Documentation" />
            </label>

            <div class="rag-profiles">
              <div class="panel-label">RAG profile</div>
              <div class="profile-grid">
                @for (p of ragProfiles; track p.value) {
                  <button
                    type="button"
                    class="profile-card"
                    [class.selected]="colForm.get('rag_profile')?.value === p.value"
                    (click)="colForm.patchValue({ rag_profile: p.value })"
                  >
                    <strong>{{ p.label }}</strong>
                    <span>{{ p.desc }}</span>
                  </button>
                }
              </div>
            </div>

            @if (colStatus()) {
              <div [class]="colStatus().startsWith('✓') ? 'msg-ok' : 'msg-err'">{{ colStatus() }}</div>
            }

            <button type="submit" class="btn-primary" [disabled]="colForm.invalid || colSaving()">
              {{ colSaving() ? 'Creating…' : 'Create collection' }}
            </button>
          </form>
        </div>
      }

      @if (collections().length === 0 && !showNewCollection()) {
        <div class="empty">
          <div class="empty-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" width="28" height="28"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>
          </div>
          <h3>No collections yet</h3>
          <p>Create a collection and upload documents to start chatting.</p>
          <button class="btn btn-primary" (click)="showNewCollection.set(true)">Create collection</button>
        </div>
      } @else if (collections().length > 0) {
        <div class="chat-workspace">

          <!-- ── Left: collection list + upload ── -->
          <aside class="chat-side-panel side-panel">
            <div class="panel-label">Collections</div>
            <div class="collection-list">
              @for (c of collections(); track c.id) {
                <div class="collection-item" [class.active]="selectedCollection()?.id === c.id">
                  <button class="col-main" (click)="selectCollection(c)">
                    <div class="col-name">{{ c.name }}</div>
                    <div class="col-meta">{{ c.rag_profile }}</div>
                  </button>
                  <button class="col-del" title="Delete collection" (click)="deleteCollection(c, $event)">✕</button>
                </div>
              }
            </div>

            @if (selectedCollection()) {
              <div class="upload-section">
                <div class="panel-label">Add content</div>
                <div class="seg">
                  <button class="seg-btn" [class.active]="ingestMode() === 'file'" (click)="ingestMode.set('file')">File</button>
                  <button class="seg-btn" [class.active]="ingestMode() === 'url'" (click)="ingestMode.set('url')">URL</button>
                </div>

                @if (ingestMode() === 'file') {
                  <label class="upload-area" [class.dragging]="dragging()" (dragover)="$event.preventDefault(); dragging.set(true)"
                    (dragleave)="dragging.set(false)" (drop)="onDrop($event)">
                    <span class="upload-icon">📁</span>
                    <span>Drop file here or <u>browse</u></span>
                    <span class="upload-hint">PDF, DOCX, TXT, CSV, PPTX, MD</span>
                    <input type="file" (change)="onFile($event)" accept=".pdf,.docx,.txt,.csv,.pptx,.md" [disabled]="jobRunning()" />
                  </label>
                } @else {
                  <form class="url-form" [formGroup]="scrapeForm" (ngSubmit)="scrape()">
                    <label>
                      <span>Page URL</span>
                      <input formControlName="url" placeholder="https://docs.example.com" />
                    </label>
                    <div class="url-row">
                      <label>
                        <span>Crawl depth</span>
                        <select formControlName="depth">
                          <option [value]="0">0 — this page only</option>
                          <option [value]="1">1 — + linked pages</option>
                          <option [value]="2">2 levels</option>
                          <option [value]="3">3 levels</option>
                        </select>
                      </label>
                      <label>
                        <span>Max pages</span>
                        <input type="number" formControlName="max_pages" min="1" max="100" />
                      </label>
                    </div>
                    <button type="submit" class="btn-primary" [disabled]="scrapeForm.invalid || jobRunning()">
                      {{ jobRunning() ? 'Working…' : 'Scrape & index' }}
                    </button>
                    <span class="upload-hint">Same-site links only. Depth 0 indexes just the page you provide.</span>
                  </form>
                }

                <!-- ── Stage stepper ── -->
                @if (job(); as j) {
                  <div class="stepper" [class.failed]="j.status === 'failed'">
                    @for (st of j.stages; track st) {
                      @if (st !== 'completed') {
                        <div class="step" [attr.data-state]="stepState(j, st)">
                          <span class="dot">
                            @switch (stepState(j, st)) {
                              @case ('done') { ✓ }
                              @case ('error') { ✕ }
                              @case ('active') { <span class="spin"></span> }
                              @default { · }
                            }
                          </span>
                          <span class="step-label">{{ stageLabel(st) }}</span>
                        </div>
                      }
                    }
                  </div>
                  <div class="job-detail" [class.msg-err]="j.status === 'failed'" [class.msg-ok]="j.status === 'completed'">
                    {{ j.status === 'failed' ? (j.error || j.detail) : j.detail }}
                    @if (j.kind === 'scrape' && j.status === 'processing' && j.progress_total) {
                      <span class="prog"> ({{ j.progress_current }}/{{ j.progress_total }})</span>
                    }
                  </div>
                }
              </div>

              <!-- ── Conversation history ── -->
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

          <!-- ── Right: chat ── -->
          <div class="chat-panel">
            @if (!selectedCollection()) {
              <div class="chat-welcome">
                <div class="icon-tile" aria-hidden="true">
                  <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z"/><path d="M14 2v6h6"/></svg>
                </div>
                <h3>Select a collection</h3>
                <p>Pick a document collection from the sidebar to begin.</p>
              </div>
            } @else {
              <div class="chat-panel-head">
                <strong>{{ selectedCollection()!.name }}</strong>
                <span class="badge">{{ selectedCollection()!.rag_profile }}</span>
              </div>

              <div class="chat-messages" #messagesPane>
                @if (messages().length === 0 && !loading()) {
                  <div class="chat-welcome">
                    <div class="icon-tile" aria-hidden="true">
                      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"/></svg>
                    </div>
                    <h3>Ask your documents</h3>
                    <p>Upload content and get answers with source citations.</p>
                    <div class="prompt-starters">
                      @for (s of suggestions; track s) {
                        <button type="button" class="prompt-starter" (click)="quickAsk(s)">{{ s }}</button>
                      }
                    </div>
                  </div>
                }

                @for (msg of messages(); track $index) {
                  @if (msg.role === 'user') {
                    <div class="msg-row user">
                      <div class="msg-row-inner">
                        @if (editingIndex() === $index) {
                          <div class="msg-body">
                            <div class="edit-box">
                              <textarea [(ngModel)]="editDraft" rows="2" (keydown.enter)="$event.preventDefault(); saveEdit($index)"></textarea>
                              <div class="edit-actions">
                                <button class="btn btn-ghost btn-sm" (click)="cancelEdit()">Cancel</button>
                                <button class="btn btn-primary btn-sm" (click)="saveEdit($index)">Save &amp; resend</button>
                              </div>
                            </div>
                          </div>
                        } @else {
                          <div class="msg-body">
                            <div class="msg-bubble user">{{ msg.question }}</div>
                            <div class="msg-actions">
                              <button class="msg-icon-btn" title="Edit" (click)="startEdit($index, msg.question || '')">Edit</button>
                              <button class="msg-icon-btn" title="Copy" (click)="copy(msg.question || '', 'u' + $index)">
                                {{ copied() === 'u' + $index ? 'Copied' : 'Copy' }}
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
                              <div class="answer markdown" [appMarkdown]="msg.answerMd || ''"></div>
                              @if (msg.highlights && msg.highlights.length) {
                                <div class="sources">
                                  <div class="sources-head">References</div>
                                  @for (h of msg.highlights; track h.chunk_id) {
                                    <div class="source-entry">
                                      <button
                                        type="button"
                                        class="source-card"
                                        [style.borderLeftColor]="h.color"
                                        (click)="openSourcePreview(h.chunk_id)"
                                      >
                                        <span class="source-ref">[{{ h.ref_index || $index + 1 }}]</span>
                                        <span class="source-meta">
                                          {{ h.filename || ('Document ' + h.document_id.slice(0, 8)) }}
                                          @if (h.page_number) { · page {{ h.page_number }} }
                                        </span>
                                        @if (h.text_snippet) {
                                          <span class="source-snippet">"{{ h.text_snippet }}"</span>
                                        }
                                      </button>
                                      <button
                                        type="button"
                                        class="source-doc-btn"
                                        title="View highlighted passage in document"
                                        aria-label="View highlighted passage in document"
                                        (click)="openDocumentView(h)"
                                      >
                                        View in document
                                      </button>
                                    </div>
                                  }
                                </div>
                              }
                            }
                          </div>
                          @if (!msg.error) {
                            <div class="msg-actions">
                              <button class="msg-icon-btn" title="Copy answer" (click)="copy(msg.answerMd || '', 'a' + $index)">
                                {{ copied() === 'a' + $index ? 'Copied' : 'Copy answer' }}
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
                      <div class="msg-body">
                        <div class="msg-bubble assistant thinking">
                          <span class="typing"><span></span><span></span><span></span></span>
                        </div>
                      </div>
                    </div>
                  </div>
                }
              </div>

              <form class="chat-composer" [formGroup]="askForm" (ngSubmit)="ask()">
                <div class="chat-composer-stack">
                  <app-prompt-picker
                    [selectedId]="selectedPromptId()"
                    (selectedIdChange)="selectedPromptId.set($event)"
                  />
                  <div class="chat-composer-row">
                    <input
                      formControlName="question"
                      placeholder="Ask about your documents…"
                      autocomplete="off"
                      aria-label="Question"
                    />
                    <button type="submit" class="btn btn-primary" [disabled]="askForm.invalid || loading()">
                      {{ loading() ? 'Thinking…' : 'Ask' }}
                    </button>
                  </div>
                  <div class="chat-composer-hint">Answers include source citations · Follow-ups keep context</div>
                </div>
              </form>
            }
          </div>
        </div>
      }
    </div>

    @if (documentViewOpen()) {
      <div class="modal-backdrop" (click)="closeDocumentView()">
        <div class="modal doc-view-modal" (click)="$event.stopPropagation()">
          <div class="modal-head">
            <h2>{{ documentView()?.filename ?? 'Document' }}</h2>
            <button type="button" class="icon-btn" (click)="closeDocumentView()">✕</button>
          </div>
          @if (documentViewLoading()) {
            <p class="modal-hint">Loading document…</p>
          } @else if (documentView()) {
            <p class="preview-meta">
              @if (documentView()!.page_number) { Page {{ documentView()!.page_number }} · }
              @if (documentView()!.highlight_start != null && documentView()!.highlight_end != null) {
                Highlighted characters {{ documentView()!.highlight_start }}–{{ documentView()!.highlight_end }}
              }
            </p>
            <div class="doc-view-scroll">
              @if (documentHighlightParts()) {
                <pre class="doc-view-text"><span>{{ documentHighlightParts()!.before }}</span><mark id="chunk-highlight" class="chunk-highlight">{{ documentHighlightParts()!.highlight }}</mark><span>{{ documentHighlightParts()!.after }}</span></pre>
              } @else {
                <pre class="doc-view-text">{{ documentView()!.content }}</pre>
              }
            </div>
          }
        </div>
      </div>
    }

    @if (sourcePreviewOpen()) {
      <div class="modal-backdrop" (click)="closeSourcePreview()">
        <div class="modal preview-modal" (click)="$event.stopPropagation()">
          <div class="modal-head">
            <h2>Source preview</h2>
            <button type="button" class="icon-btn" (click)="closeSourcePreview()">✕</button>
          </div>
          @if (sourcePreviewLoading()) {
            <p class="modal-hint">Loading excerpt…</p>
          } @else if (sourcePreview()) {
            <p class="preview-meta">
              <strong>{{ sourcePreview()!.filename }}</strong>
              @if (sourcePreview()!.page_number) { · Page {{ sourcePreview()!.page_number }} }
              · Characters {{ sourcePreview()!.char_start }}–{{ sourcePreview()!.char_end }}
            </p>
            <pre class="preview-text">{{ sourcePreview()!.text }}</pre>
          }
        </div>
      </div>
    }
  `,
  styles: [`
    .page { max-width: 1140px; }
    h2 { margin: 0 0 var(--space-4); font-size: var(--text-lg); }

    .btn-primary {
      padding: 9px 16px; border-radius: var(--radius-md); border: none;
      background: var(--primary); color: var(--on-primary); font-size: var(--text-base);
      font-weight: 550; cursor: pointer; font-family: inherit;
      transition: background var(--dur-fast) var(--ease);
    }
    .btn-primary:hover:not(:disabled) { background: var(--primary-hover); }
    .btn-primary:disabled { opacity: 0.5; cursor: default; }
    .btn-ghost {
      padding: 7px 14px; border-radius: var(--radius-md);
      border: 1px solid var(--border-strong);
      background: transparent; color: var(--text-2); cursor: pointer; font-size: var(--text-sm);
      font-family: inherit; transition: all var(--dur-fast) var(--ease);
    }
    .btn-ghost:hover { background: var(--surface-2); color: var(--text); }

    /* panel */
    .panel {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg); padding: var(--space-6);
      margin-bottom: var(--space-6);
      display: flex; flex-direction: column; gap: var(--space-5);
      box-shadow: var(--shadow-sm);
    }
    .panel-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.08em; color: var(--text-muted); font-weight: 700; margin-bottom: 4px; }
    label { display: flex; flex-direction: column; gap: 6px; font-size: var(--text-xs); color: var(--text-2); font-weight: 550; }
    input, select {
      padding: 9px 12px; border-radius: var(--radius-md);
      border: 1px solid var(--border-strong);
      background: var(--input-bg); color: var(--text); font-size: var(--text-base); font-family: inherit;
      transition: border-color var(--dur-fast) var(--ease), box-shadow var(--dur-fast) var(--ease);
    }
    input:focus, select:focus { outline: none; border-color: var(--border-focus); box-shadow: 0 0 0 3px var(--primary-soft); }

    /* RAG profile picker */
    .profile-grid {
      display: grid; grid-template-columns: repeat(auto-fill, minmax(168px, 1fr)); gap: 10px;
    }
    .profile-card {
      display: flex; flex-direction: column; gap: 4px; text-align: left;
      padding: 13px; border-radius: var(--radius-md);
      border: 1px solid var(--border);
      background: var(--surface-2);
      cursor: pointer; color: inherit;
      transition: border-color var(--dur-fast) var(--ease), background var(--dur-fast) var(--ease);
    }
    .profile-card:hover { border-color: var(--primary); }
    .profile-card.selected { border-color: var(--primary); background: var(--primary-soft); }
    .profile-card span { font-size: var(--text-xs); color: var(--text-muted); }

    .msg-ok  { color: var(--success); font-size: var(--text-sm); }
    .msg-err { color: var(--danger); font-size: var(--text-sm); }

    .empty {
      text-align: center; padding: var(--space-12) var(--space-6);
      border: 1px dashed var(--border-strong); border-radius: var(--radius-lg);
      display: flex; flex-direction: column; align-items: center; gap: var(--space-4);
      color: var(--text-2);
    }
    .empty-icon { font-size: 48px; }

    /* workspace */
    .workspace {
      display: grid; grid-template-columns: 250px 1fr; gap: 20px;
      height: calc(100vh - 200px); min-height: 520px;
    }

    /* side panel */
    .side-panel {
      display: flex; flex-direction: column; gap: var(--space-4);
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg); padding: var(--space-4);
      overflow-y: auto; box-shadow: var(--shadow-sm);
    }
    .collection-list { display: flex; flex-direction: column; gap: 3px; }
    .collection-item {
      display: flex; align-items: center; gap: 4px; width: 100%;
      padding: 0 4px 0 0; border-radius: var(--radius-md);
      border: 1px solid transparent;
      background: transparent; color: inherit;
      transition: background var(--dur-fast) var(--ease);
    }
    .collection-item:hover { background: var(--surface-2); }
    .collection-item.active { border-color: var(--primary); background: var(--primary-soft); }
    .col-main {
      flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 2px;
      text-align: left; padding: 9px 11px; border: none; background: transparent;
      color: inherit; cursor: pointer; font-family: inherit;
    }
    .col-name { font-size: var(--text-base); font-weight: 550; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .col-meta { font-size: var(--text-xs); color: var(--text-muted); }
    .col-del {
      flex-shrink: 0; width: 24px; height: 24px; border-radius: var(--radius-sm);
      border: none; background: transparent; color: var(--text-muted);
      cursor: pointer; font-size: 12px; opacity: 0; transition: all var(--dur-fast) var(--ease);
    }
    .collection-item:hover .col-del { opacity: 1; }
    .col-del:hover { background: var(--danger); color: #fff; }

    /* upload area */
    .upload-area {
      position: relative; display: flex; flex-direction: column;
      align-items: center; gap: 5px;
      padding: 22px 12px;
      border: 1.5px dashed var(--border-strong);
      border-radius: var(--radius-md); cursor: pointer; text-align: center;
      font-size: var(--text-sm); color: var(--text-2);
      transition: border-color var(--dur-fast) var(--ease), background var(--dur-fast) var(--ease);
    }
    .upload-area:hover { border-color: var(--primary); }
    .upload-area.dragging { border-color: var(--primary); background: var(--primary-soft); }
    .upload-icon { font-size: 24px; }
    .upload-hint { color: var(--text-muted); font-size: var(--text-xs); }
    .upload-area input[type=file] { position: absolute; inset: 0; opacity: 0; cursor: pointer; }

    /* chat — content-specific only; layout from global styles.css */
    .answer { line-height: 1.7; font-size: var(--text-base); }
    .answer :global(cite) { font-style: normal; border-bottom: 1px dashed var(--primary-text); color: var(--primary-text); }
    .sources { display: grid; gap: 8px; margin-top: 4px; }
    .sources-head { font-size: var(--text-xs); color: var(--text-muted); font-weight: 700; text-transform: uppercase; letter-spacing: 0.06em; }
    .source-entry { display: grid; gap: 6px; }
    .source-card {
      display: grid; gap: 4px; text-align: left; width: 100%; padding: 10px 12px;
      border: 1px solid var(--border); border-left-width: 3px; border-radius: var(--radius-md);
      background: var(--surface); cursor: pointer; font-family: inherit;
      transition: background var(--dur-fast) var(--ease), border-color var(--dur-fast) var(--ease);
    }
    .source-card:hover { background: var(--surface-3); border-color: var(--border-strong); }
    .source-doc-btn {
      justify-self: start; display: inline-flex; align-items: center; gap: 6px;
      border: 1px solid var(--border-strong); border-radius: var(--radius-md);
      background: var(--surface-2); color: var(--text-2); cursor: pointer;
      font-size: var(--text-xs); font-family: inherit; padding: 5px 10px;
    }
    .source-doc-btn:hover {
      color: var(--primary-text); border-color: var(--primary); background: var(--primary-soft);
    }
    .source-ref { font-size: var(--text-xs); font-weight: 700; color: var(--primary-text); }
    .source-meta { font-size: var(--text-xs); color: var(--text-2); }
    .source-snippet { font-size: var(--text-sm); color: var(--text); line-height: 1.5; }
    .error { color: var(--danger); font-size: var(--text-sm); }

    .edit-box { display: flex; flex-direction: column; gap: 8px; width: min(480px, 100%); }
    .edit-box textarea {
      width: 100%; box-sizing: border-box; resize: vertical;
      padding: 10px 12px; border-radius: var(--radius-md);
      border: 1px solid var(--border-focus); background: var(--input-bg);
      color: var(--text); font-size: var(--text-base); font-family: inherit;
    }
    .edit-box textarea:focus { outline: none; box-shadow: 0 0 0 3px var(--primary-soft); }
    .edit-actions { display: flex; gap: 8px; justify-content: flex-end; }

    /* segmented toggle */
    .seg { display: flex; gap: 4px; padding: 3px; border-radius: var(--radius-md); background: var(--surface-2); border: 1px solid var(--border); }
    .seg-btn {
      flex: 1; padding: 6px 0; border: none; border-radius: calc(var(--radius-md) - 3px);
      background: transparent; color: var(--text-2); font-size: var(--text-xs); font-weight: 600;
      cursor: pointer; font-family: inherit; transition: all var(--dur-fast) var(--ease);
    }
    .seg-btn.active { background: var(--surface); color: var(--text); box-shadow: var(--shadow-sm); }

    /* url form */
    .url-form { display: flex; flex-direction: column; gap: 10px; }
    .url-form label { min-width: 0; }
    .url-form input, .url-form select { width: 100%; box-sizing: border-box; min-width: 0; }
    .url-row { display: grid; grid-template-columns: 1fr 84px; gap: 8px; }
    .url-form .btn-primary { padding: 8px 14px; }

    /* stage stepper */
    .stepper {
      display: flex; flex-direction: column; gap: 2px;
      padding: 10px 12px; border-radius: var(--radius-md);
      background: var(--surface-2); border: 1px solid var(--border); margin-top: 2px;
    }
    .step { display: flex; align-items: center; gap: 9px; font-size: var(--text-xs); color: var(--text-muted); padding: 2px 0; }
    .step .dot {
      width: 18px; height: 18px; border-radius: 50%; display: inline-flex;
      align-items: center; justify-content: center; font-size: 11px; flex-shrink: 0;
      background: var(--surface-3); color: var(--text-muted); border: 1px solid var(--border-strong);
    }
    .step[data-state=done]   { color: var(--text-2); }
    .step[data-state=done] .dot   { background: var(--success); color: #fff; border-color: var(--success); }
    .step[data-state=active] { color: var(--text); font-weight: 600; }
    .step[data-state=active] .dot { background: var(--primary-soft); border-color: var(--primary); color: var(--primary-text); }
    .step[data-state=error]  { color: var(--danger); font-weight: 600; }
    .step[data-state=error] .dot  { background: var(--danger); color: #fff; border-color: var(--danger); }
    .spin {
      width: 9px; height: 9px; border-radius: 50%;
      border: 2px solid var(--primary); border-top-color: transparent;
      animation: spin 0.7s linear infinite;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .job-detail { font-size: var(--text-xs); color: var(--text-2); line-height: 1.5; }
    .prog { color: var(--text-muted); }
    .upload-section { display: flex; flex-direction: column; gap: 10px; margin-top: 4px; }

    /* ── markdown rendering ── */
    .markdown { line-height: 1.7; font-size: var(--text-base); color: var(--text); overflow-wrap: anywhere; }
    .markdown > :first-child { margin-top: 0; }
    .markdown > :last-child { margin-bottom: 0; }
    .markdown h1, .markdown h2, .markdown h3, .markdown h4 {
      margin: 16px 0 8px; line-height: 1.3; font-weight: 650;
    }
    .markdown h1 { font-size: 1.4em; } .markdown h2 { font-size: 1.25em; }
    .markdown h3 { font-size: 1.1em; } .markdown h4 { font-size: 1em; }
    .markdown p { margin: 8px 0; }
    .markdown ul, .markdown ol { margin: 8px 0; padding-left: 22px; }
    .markdown li { margin: 4px 0; }
    .markdown a { color: var(--primary-text); text-decoration: underline; }
    .markdown strong { font-weight: 650; color: var(--text); }
    .markdown blockquote {
      margin: 10px 0; padding: 6px 14px; border-left: 3px solid var(--primary);
      background: var(--surface-3); color: var(--text-2); border-radius: 0 6px 6px 0;
    }
    .markdown code {
      font-family: var(--font-mono, ui-monospace, SFMono-Regular, Menlo, monospace);
      font-size: 0.88em; background: var(--surface-3); padding: 1px 5px; border-radius: 4px;
    }
    .markdown pre {
      margin: 12px 0; padding: 14px; border-radius: var(--radius-md);
      background: var(--surface-3); border: 1px solid var(--border);
      overflow-x: auto;
    }
    .markdown pre code { background: none; padding: 0; font-size: 0.85em; line-height: 1.6; }
    .markdown table {
      border-collapse: collapse; margin: 12px 0; width: 100%; font-size: var(--text-sm);
      display: block; overflow-x: auto;
    }
    .markdown th, .markdown td {
      border: 1px solid var(--border-strong); padding: 7px 11px; text-align: left;
    }
    .markdown thead th { background: var(--surface-3); font-weight: 650; }
    .markdown tbody tr:nth-child(even) { background: var(--surface-2); }
    .markdown hr { border: none; border-top: 1px solid var(--border); margin: 16px 0; }
    .markdown :global(cite) { font-style: normal; border-bottom: 1px dashed var(--primary-text); color: var(--primary-text); }
    .mermaid-diagram { margin: 14px 0; display: flex; justify-content: center; overflow-x: auto; }
    .mermaid-diagram svg { max-width: 100%; height: auto; }

    /* ── conversation history ── */
    .history { display: flex; flex-direction: column; gap: 6px; margin-top: 8px; padding-top: 12px; border-top: 1px solid var(--border); }
    .hist-head { display: flex; align-items: center; justify-content: space-between; }
    .new-chat {
      padding: 4px 10px; border-radius: var(--radius-pill);
      border: 1px solid var(--border-strong); background: var(--surface-2);
      color: var(--text-2); cursor: pointer; font-size: var(--text-xs); font-weight: 600; font-family: inherit;
      transition: all var(--dur-fast) var(--ease);
    }
    .new-chat:hover { background: var(--primary-soft); color: var(--primary-text); border-color: var(--primary); }
    .hist-empty { font-size: var(--text-xs); color: var(--text-muted); padding: 4px 2px; line-height: 1.5; }
    .conv-list { display: flex; flex-direction: column; gap: 2px; }
    .conv-item {
      display: flex; align-items: center; gap: 2px; border-radius: var(--radius-md);
      border: 1px solid transparent; padding-right: 2px;
      transition: background var(--dur-fast) var(--ease);
    }
    .conv-item:hover { background: var(--surface-2); }
    .conv-item.active { border-color: var(--primary); background: var(--primary-soft); }
    .conv-main {
      flex: 1; min-width: 0; display: flex; align-items: center; gap: 6px;
      text-align: left; padding: 7px 9px; border: none; background: transparent;
      color: inherit; cursor: pointer; font-family: inherit;
    }
    .conv-star { color: var(--warning, #d29922); font-size: 11px; flex-shrink: 0; }
    .conv-title { font-size: var(--text-sm); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
    .conv-actions { display: flex; gap: 2px; opacity: 0; flex-shrink: 0; transition: opacity var(--dur-fast) var(--ease); }
    .conv-item:hover .conv-actions, .conv-item.active .conv-actions { opacity: 1; }
    .icon-btn.xs { padding: 2px 5px; font-size: 11px; }
    .icon-btn.xs.danger:hover { background: var(--danger); color: #fff; border-color: var(--danger); }
    .rename-input {
      flex: 1; min-width: 0; padding: 5px 8px; border-radius: var(--radius-sm);
      border: 1px solid var(--border-focus); background: var(--input-bg); color: var(--text);
      font-size: var(--text-sm); font-family: inherit;
    }
    .rename-input:focus { outline: none; box-shadow: 0 0 0 3px var(--primary-soft); }

    .modal-backdrop {
      position: fixed; inset: 0; background: rgba(0, 0, 0, 0.45); z-index: 1000;
      display: grid; place-items: center; padding: var(--space-6);
    }
    .modal {
      width: min(720px, 100%); max-height: 85vh; overflow: auto;
      background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg);
      padding: var(--space-5); box-shadow: var(--shadow-lg);
    }
    .modal-head { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: var(--space-4); }
    .modal-head h2 { margin: 0; font-size: var(--text-lg); }
    .modal-hint { color: var(--text-muted); font-size: var(--text-sm); }
    .preview-meta { margin: 0 0 12px; color: var(--text-2); font-size: var(--text-sm); }
    .preview-text {
      margin: 0; white-space: pre-wrap; font-family: var(--font-mono); font-size: var(--text-sm);
      background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-md);
      padding: var(--space-4); line-height: 1.6;
    }
    .doc-view-modal { width: min(900px, 100%); }
    .doc-view-scroll {
      max-height: 60vh; overflow: auto; border: 1px solid var(--border);
      border-radius: var(--radius-md); background: var(--surface-2);
    }
    .doc-view-text {
      margin: 0; white-space: pre-wrap; word-break: break-word;
      font-family: var(--font-mono); font-size: var(--text-sm); line-height: 1.65;
      padding: var(--space-4);
    }
    .chunk-highlight {
      background: color-mix(in srgb, var(--warning, #d29922) 35%, transparent);
      color: var(--text); padding: 0 2px; border-radius: 2px;
      box-shadow: inset 0 -2px 0 color-mix(in srgb, var(--warning, #d29922) 70%, transparent);
    }
  `],
})
export class TalkToDocsComponent implements OnInit, OnDestroy {
  private readonly http = inject(HttpClient);
  private readonly fb = inject(FormBuilder);
  private readonly messagesPane = viewChild<ElementRef<HTMLElement>>('messagesPane');

  readonly collections = signal<Collection[]>([]);
  readonly selectedCollection = signal<Collection | null>(null);
  readonly messages = signal<Message[]>([]);
  readonly loading = signal(false);
  readonly selectedPromptId = signal<string | null>(null);
  readonly sourcePreview = signal<ChunkDetail | null>(null);
  readonly sourcePreviewLoading = signal(false);
  readonly sourcePreviewOpen = signal(false);
  readonly documentView = signal<DocumentView | null>(null);
  readonly documentViewLoading = signal(false);
  readonly documentViewOpen = signal(false);
  readonly documentHighlightParts = computed((): DocumentHighlightParts | null => {
    const doc = this.documentView();
    if (!doc || doc.highlight_start == null || doc.highlight_end == null) return null;
    const content = doc.content;
    const start = Math.max(0, Math.min(doc.highlight_start, content.length));
    const end = Math.max(start, Math.min(doc.highlight_end, content.length));
    if (end <= start) return null;
    return {
      before: content.slice(0, start),
      highlight: content.slice(start, end),
      after: content.slice(end),
    };
  });
  readonly showNewCollection = signal(false);
  readonly colSaving = signal(false);
  readonly colStatus = signal('');
  readonly dragging = signal(false);

  readonly ingestMode = signal<'file' | 'url'>('file');
  readonly job = signal<IngestionJob | null>(null);
  readonly jobRunning = computed(() => this.job()?.status === 'processing');

  readonly editingIndex = signal<number | null>(null);
  editDraft = '';
  readonly copied = signal<string | null>(null);

  readonly conversations = signal<Conversation[]>([]);
  readonly activeConversationId = signal<string | null>(null);
  readonly renamingId = signal<string | null>(null);
  renameDraft = '';

  private conversationId: string | null = null;
  private pollTimer: ReturnType<typeof setTimeout> | null = null;

  readonly ragProfiles = RAG_PROFILES;
  readonly suggestions = ['Summarize this document', 'List the key action items', 'What are the main findings?', 'Find any deadlines mentioned'];

  readonly colForm = this.fb.group({
    name: ['', Validators.required],
    rag_profile: ['naive', Validators.required],
  });

  readonly askForm = this.fb.group({
    question: ['', Validators.required],
  });

  readonly scrapeForm = this.fb.group({
    url: ['', [Validators.required, Validators.pattern(/^https?:\/\/.+/)]],
    depth: [0, Validators.required],
    max_pages: [20, [Validators.required, Validators.min(1), Validators.max(100)]],
  });

  ngOnInit(): void { this.loadCollections(); }

  ngOnDestroy(): void { this.stopPolling(); }

  stageLabel(stage: string): string { return STAGE_LABELS[stage] ?? stage; }

  stepState(j: IngestionJob, stage: string): 'done' | 'active' | 'error' | 'pending' {
    const current = j.stages.indexOf(j.stage);
    const idx = j.stages.indexOf(stage);
    if (j.status === 'completed') return 'done';
    if (j.status === 'failed') {
      if (idx < current) return 'done';
      if (idx === current) return 'error';
      return 'pending';
    }
    if (idx < current) return 'done';
    if (idx === current) return 'active';
    return 'pending';
  }

  loadCollections(): void {
    this.http.get<Collection[]>(`${API_BASE}/talk-to-docs/collections`).subscribe({
      next: (c) => this.collections.set(c),
    });
  }

  createCollection(): void {
    if (this.colForm.invalid) return;
    this.colSaving.set(true);
    this.http.post<Collection>(`${API_BASE}/talk-to-docs/collections`, this.colForm.getRawValue()).subscribe({
      next: (c) => {
        this.colSaving.set(false);
        this.colStatus.set('✓ Collection created.');
        this.loadCollections();
        setTimeout(() => { this.showNewCollection.set(false); this.colStatus.set(''); this.selectCollection(c); }, 1200);
      },
      error: (err: { error?: { detail?: string } }) => {
        this.colSaving.set(false);
        this.colStatus.set(err?.error?.detail ?? 'Creation failed.');
      },
    });
  }

  deleteCollection(c: Collection, ev: Event): void {
    ev.stopPropagation();
    if (!confirm(`Delete collection "${c.name}"? This permanently removes its documents and index.`)) return;
    this.http.delete(`${API_BASE}/talk-to-docs/collections/${c.id}`).subscribe({
      next: () => {
        this.collections.update((list) => list.filter((x) => x.id !== c.id));
        if (this.selectedCollection()?.id === c.id) {
          this.selectedCollection.set(null);
          this.messages.set([]);
          this.conversations.set([]);
          this.conversationId = null;
          this.activeConversationId.set(null);
          this.stopPolling();
          this.job.set(null);
        }
        this.loadCollections();
      },
      error: (err: { error?: { detail?: string } }) => {
        alert(err?.error?.detail ?? 'Could not delete collection.');
      },
    });
  }

  selectCollection(c: Collection): void {
    this.selectedCollection.set(c);
    this.messages.set([]);
    this.conversationId = null;
    this.activeConversationId.set(null);
    this.stopPolling();
    this.job.set(null);
    this.loadConversations(c.id);
  }

  loadConversations(collectionId: string): void {
    this.http.get<Conversation[]>(`${API_BASE}/chat/conversations?datasource_id=${collectionId}`).subscribe({
      next: (c) => this.conversations.set(c),
      error: () => this.conversations.set([]),
    });
  }

  newChat(): void {
    this.messages.set([]);
    this.conversationId = null;
    this.activeConversationId.set(null);
  }

  openConversation(cv: Conversation): void {
    this.activeConversationId.set(cv.id);
    this.conversationId = cv.id;
    this.messages.set([]);
    this.loading.set(true);
    this.http.get<ChatMessageDto[]>(`${API_BASE}/chat/messages?conversation_id=${cv.id}`).subscribe({
      next: (msgs) => {
        this.loading.set(false);
        this.messages.set(msgs.map((m) => m.role === 'user'
          ? { role: 'user', question: m.content }
          : { role: 'assistant', answerMd: m.content, highlights: m.metadata_json?.highlight_spans_json ?? [] }));
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
    const c = this.selectedCollection();
    if (c) this.loadConversations(c.id);
  }

  onFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.upload(input.files?.[0]);
    input.value = '';
  }

  onDrop(event: DragEvent): void {
    event.preventDefault();
    this.dragging.set(false);
    if (!this.jobRunning()) this.upload(event.dataTransfer?.files?.[0]);
  }

  private upload(file?: File): void {
    if (!file || !this.selectedCollection() || this.jobRunning()) return;
    const form = new FormData();
    form.append('file', file);
    this.http.post<IngestionJob>(
      `${API_BASE}/talk-to-docs/collections/${this.selectedCollection()!.id}/upload`, form
    ).subscribe({
      next: (j) => this.trackJob(j),
      error: (err: { error?: { detail?: string } }) => this.failJob(err?.error?.detail ?? 'Upload failed.'),
    });
  }

  scrape(): void {
    if (this.scrapeForm.invalid || !this.selectedCollection() || this.jobRunning()) return;
    const body = this.scrapeForm.getRawValue();
    this.http.post<IngestionJob>(
      `${API_BASE}/talk-to-docs/collections/${this.selectedCollection()!.id}/scrape`,
      { url: body.url, depth: Number(body.depth), max_pages: Number(body.max_pages) }
    ).subscribe({
      next: (j) => this.trackJob(j),
      error: (err: { error?: { detail?: string } }) => this.failJob(err?.error?.detail ?? 'Scrape failed.'),
    });
  }

  private trackJob(j: IngestionJob): void {
    this.job.set(j);
    if (j.status === 'processing') this.pollJob(j.job_id);
  }

  private pollJob(jobId: string): void {
    this.stopPolling();
    this.pollTimer = setTimeout(() => {
      this.http.get<IngestionJob>(`${API_BASE}/talk-to-docs/jobs/${jobId}`).subscribe({
        next: (j) => {
          this.job.set(j);
          if (j.status === 'processing') this.pollJob(jobId);
          else { this.stopPolling(); this.loadCollections(); }
        },
        error: () => this.stopPolling(),
      });
    }, 900);
  }

  private stopPolling(): void {
    if (this.pollTimer) { clearTimeout(this.pollTimer); this.pollTimer = null; }
  }

  private failJob(message: string): void {
    this.stopPolling();
    this.job.set({
      job_id: '', kind: this.ingestMode() === 'url' ? 'scrape' : 'file', collection_id: '',
      stages: ['queued', 'completed'], stage: 'queued', status: 'failed',
      detail: message, progress_current: 0, progress_total: 0, error: message, documents: [],
    });
  }

  quickAsk(q: string): void {
    this.ask(q);
  }

  ask(override?: string): void {
    const q = (override ?? this.askForm.getRawValue().question ?? '').trim();
    if (!q || !this.selectedCollection() || this.loading()) return;
    this.messages.update((m) => [...m, { role: 'user', question: q }]);
    if (override === undefined) this.askForm.reset();
    this.loading.set(true);
    this.scrollToBottom();

    this.http.post<AskResponse>(`${API_BASE}/talk-to-docs/ask`, {
      collection_id: this.selectedCollection()!.id,
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
          answerMd: res.answer,
          highlights: res.highlight_spans,
        }]);
        if (wasNew) this.reloadConversations();
        this.scrollToBottom();
      },
      error: (err: { error?: { detail?: string } }) => {
        this.loading.set(false);
        this.messages.update((m) => [...m, { role: 'assistant', error: err?.error?.detail ?? 'Ask failed.' }]);
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
    // Drop this question and everything after it, then re-ask.
    this.messages.update((m) => m.slice(0, index));
    this.ask(q);
  }

  copy(text: string, key: string): void {
    navigator.clipboard?.writeText(text).then(() => {
      this.copied.set(key);
      setTimeout(() => { if (this.copied() === key) this.copied.set(null); }, 1500);
    });
  }

  openSourcePreview(chunkId: string): void {
    this.documentViewOpen.set(false);
    this.sourcePreview.set(null);
    this.sourcePreviewOpen.set(true);
    this.sourcePreviewLoading.set(true);
    this.http.get<ChunkDetail>(`${API_BASE}/talk-to-docs/chunks/${encodeURIComponent(chunkId)}`).subscribe({
      next: (detail) => {
        this.sourcePreview.set(detail);
        this.sourcePreviewLoading.set(false);
      },
      error: () => {
        this.sourcePreviewLoading.set(false);
        alert('Could not load source excerpt.');
      },
    });
  }

  openDocumentView(h: HighlightSpan): void {
    this.sourcePreviewOpen.set(false);
    this.documentView.set(null);
    this.documentViewOpen.set(true);
    this.documentViewLoading.set(true);

    const loadDocument = (span: HighlightSpan): void => {
      const params = new URLSearchParams({
        char_start: String(span.char_start),
        char_end: String(span.char_end),
      });
      if (span.page_number) params.set('page_number', String(span.page_number));
      this.http
        .get<DocumentView>(`${API_BASE}/talk-to-docs/documents/${span.document_id}?${params.toString()}`)
        .subscribe({
          next: (doc) => {
            this.documentView.set(doc);
            this.documentViewLoading.set(false);
            window.setTimeout(() => {
              document.getElementById('chunk-highlight')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
            }, 50);
          },
          error: (err: { error?: { detail?: string } }) => {
            this.documentViewLoading.set(false);
            alert(err?.error?.detail ?? 'Could not load document.');
          },
        });
    };

    if (h.char_end > h.char_start) {
      loadDocument(h);
      return;
    }

    this.http.get<ChunkDetail>(`${API_BASE}/talk-to-docs/chunks/${encodeURIComponent(h.chunk_id)}`).subscribe({
      next: (detail) => loadDocument({ ...h, char_start: detail.char_start, char_end: detail.char_end, page_number: detail.page_number }),
      error: () => {
        this.documentViewLoading.set(false);
        alert('Could not resolve source location in document.');
      },
    });
  }

  closeDocumentView(): void {
    this.documentView.set(null);
    this.documentViewLoading.set(false);
    this.documentViewOpen.set(false);
  }

  closeSourcePreview(): void {
    this.sourcePreview.set(null);
    this.sourcePreviewLoading.set(false);
    this.sourcePreviewOpen.set(false);
  }

  private scrollToBottom(): void {
    setTimeout(() => {
      const el = this.messagesPane()?.nativeElement;
      if (el) el.scrollTop = el.scrollHeight;
    }, 0);
  }
}
