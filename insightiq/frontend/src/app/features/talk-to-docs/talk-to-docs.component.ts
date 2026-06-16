import { HttpClient } from '@angular/common/http';
import { Component, OnInit, inject } from '@angular/core';
import { FormBuilder, FormsModule, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';

import { API_BASE } from '../../core/api.config';
import { AuthService } from '../../core/auth.service';
import { ChatSidebarComponent } from '../../shared/chat-sidebar.component';

type Collection = { id: string; name: string; rag_profile: string };
type HighlightSpan = {
  chunk_id: string;
  document_id: string;
  char_start: number;
  char_end: number;
  color: string;
};
type AskResponse = {
  conversation_id: string;
  answer: string;
  answer_html: string;
  highlight_spans: HighlightSpan[];
};

@Component({
  standalone: true,
  imports: [ReactiveFormsModule, FormsModule, ChatSidebarComponent],
  template: `
    <div class="layout">
      <app-chat-sidebar [activeId]="conversationId" (select)="conversationId = $event" />

      <div class="main">
        <header>
          <div>
            <h1>Talk to Documents</h1>
            <p>Upload documents, run the 10-stage RAG pipeline, view source highlights</p>
          </div>
          <button type="button" (click)="logout()">Logout</button>
        </header>

        <section class="card">
          <h2>Collection</h2>
          <form class="row" [formGroup]="colForm" (ngSubmit)="createCollection()">
            <input formControlName="name" placeholder="Collection name" />
            <select formControlName="rag_profile">
              <option value="naive">naive</option>
              <option value="advanced">advanced</option>
              <option value="graph">graph</option>
              <option value="agentic">agentic</option>
            </select>
            <button type="submit" class="primary">Create</button>
          </form>

          <select [(ngModel)]="selectedCollectionId" [ngModelOptions]="{ standalone: true }">
            <option value="">Select collection</option>
            @for (c of collections; track c.id) {
              <option [value]="c.id">{{ c.name }} ({{ c.rag_profile }})</option>
            }
          </select>

          <label class="upload">
            Upload document
            <input type="file" (change)="onFile($event)" [disabled]="!selectedCollectionId" />
          </label>
          @if (status) {
            <p class="status">{{ status }}</p>
          }
        </section>

        <section class="card">
          <h2>Ask</h2>
          <form class="row" [formGroup]="askForm" (ngSubmit)="ask()">
            <input formControlName="question" placeholder="Ask about your documents..." />
            <button type="submit" class="primary" [disabled]="askForm.invalid || !selectedCollectionId">
              Ask
            </button>
          </form>

          @if (answerHtml) {
            <div class="answer" [innerHTML]="answerHtml"></div>
          }

          @if (highlights.length) {
            <div class="highlights">
              <h3>Source highlights</h3>
              @for (h of highlights; track h.chunk_id) {
                <div class="span" [style.borderLeftColor]="h.color">
                  <span class="meta">doc {{ h.document_id.slice(0, 8) }} · chars {{ h.char_start }}-{{ h.char_end }}</span>
                </div>
              }
            </div>
          }
        </section>
      </div>
    </div>
  `,
  styles: [
    `
      .layout {
        display: flex;
        min-height: 100vh;
      }
      .main {
        flex: 1;
        padding: 24px;
        display: grid;
        gap: 20px;
        align-content: start;
      }
      header {
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      .card {
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        padding: 20px;
        background: rgba(255, 255, 255, 0.03);
        display: grid;
        gap: 12px;
      }
      .row {
        display: flex;
        gap: 10px;
        flex-wrap: wrap;
      }
      input,
      select,
      button {
        padding: 10px 12px;
        border-radius: 10px;
        border: 1px solid rgba(255, 255, 255, 0.12);
        background: rgba(0, 0, 0, 0.25);
        color: inherit;
      }
      .primary {
        background: rgba(88, 166, 255, 0.25);
      }
      .answer {
        padding: 16px;
        border-radius: 12px;
        background: rgba(0, 0, 0, 0.3);
        line-height: 1.6;
      }
      .answer cite {
        font-style: normal;
        border-bottom: 1px dashed currentColor;
      }
      .highlights .span {
        padding: 8px 12px;
        border-left: 3px solid;
        margin-top: 6px;
        background: rgba(255, 255, 255, 0.04);
        border-radius: 0 8px 8px 0;
      }
      .meta {
        font-size: 12px;
        opacity: 0.75;
      }
      .status {
        font-size: 13px;
        opacity: 0.85;
      }
      .upload input {
        display: block;
        margin-top: 6px;
      }
    `,
  ],
})
export class TalkToDocsComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);

  collections: Collection[] = [];
  selectedCollectionId = '';
  conversationId: string | null = null;
  status = '';
  answerHtml = '';
  highlights: HighlightSpan[] = [];

  readonly colForm = this.fb.group({
    name: ['Reports', Validators.required],
    rag_profile: ['naive', Validators.required],
  });

  readonly askForm = this.fb.group({
    question: ['Summarize the key points', Validators.required],
  });

  ngOnInit(): void {
    if (!this.auth.isAuthenticated()) {
      this.router.navigate(['/login']);
      return;
    }
    this.loadCollections();
  }

  loadCollections(): void {
    this.http.get<Collection[]>(`${API_BASE}/talk-to-docs/collections`).subscribe({
      next: (items) => (this.collections = items),
    });
  }

  createCollection(): void {
    if (this.colForm.invalid) return;
    this.http.post(`${API_BASE}/talk-to-docs/collections`, this.colForm.getRawValue()).subscribe({
      next: () => {
        this.status = 'Collection created.';
        this.loadCollections();
      },
    });
  }

  onFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file || !this.selectedCollectionId) return;
    const form = new FormData();
    form.append('file', file);
    this.http
      .post(`${API_BASE}/talk-to-docs/collections/${this.selectedCollectionId}/upload`, form)
      .subscribe({
        next: (res) => {
          this.status = `Uploaded (${JSON.stringify(res)}).`;
        },
        error: (err) => {
          this.status = err?.error?.detail ?? 'Upload failed';
        },
      });
  }

  ask(): void {
    if (this.askForm.invalid || !this.selectedCollectionId) return;
    this.http
      .post<AskResponse>(`${API_BASE}/talk-to-docs/ask`, {
        collection_id: this.selectedCollectionId,
        question: this.askForm.getRawValue().question,
        conversation_id: this.conversationId,
      })
      .subscribe({
        next: (res) => {
          this.conversationId = res.conversation_id;
          this.answerHtml = res.answer_html;
          this.highlights = res.highlight_spans;
        },
        error: (err) => {
          this.status = err?.error?.detail ?? 'Ask failed';
        },
      });
  }

  logout(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
  }
}
