import { HttpClient } from '@angular/common/http';
import { Component, EventEmitter, Input, OnInit, Output, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { API_BASE } from '../core/api.config';
import { ExportService } from '../core/export.service';

type Conversation = {
  id: string;
  title: string;
  folder: string | null;
  tags: string[];
  starred: boolean;
};

@Component({
  selector: 'app-chat-sidebar',
  standalone: true,
  imports: [FormsModule],
  template: `
    <aside class="sidebar">
      <div class="head">
        <h2>Chat History</h2>
        <input [(ngModel)]="search" (ngModelChange)="load()" placeholder="Search..." />
        @if (activeId) {
          <div class="export-row">
            <button type="button" (click)="exportActive('markdown')">Export MD</button>
            <button type="button" (click)="exportActive('pdf')">Export PDF</button>
          </div>
        }
      </div>
      <ul>
        @for (c of conversations; track c.id) {
          <li [class.active]="c.id === activeId" (click)="select.emit(c.id)">
            <div class="row">
              <span class="title">{{ c.title }}</span>
              <button type="button" (click)="toggleStar(c, $event)">
                {{ c.starred ? '★' : '☆' }}
              </button>
            </div>
            @if (c.folder) {
              <div class="meta">{{ c.folder }}</div>
            }
          </li>
        }
      </ul>
    </aside>
  `,
  styles: [
    `
      .sidebar {
        border-right: 1px solid rgba(255, 255, 255, 0.08);
        padding: 16px;
        min-width: 240px;
        max-width: 280px;
      }
      h2 {
        margin: 0 0 8px;
        font-size: 14px;
      }
      input {
        width: 100%;
        padding: 8px 10px;
        border-radius: 8px;
        border: 1px solid rgba(255, 255, 255, 0.12);
        background: rgba(0, 0, 0, 0.25);
        color: inherit;
        margin-bottom: 12px;
      }
      ul {
        list-style: none;
        margin: 0;
        padding: 0;
        display: grid;
        gap: 6px;
      }
      li {
        padding: 10px;
        border-radius: 10px;
        cursor: pointer;
        border: 1px solid transparent;
      }
      li:hover,
      li.active {
        background: rgba(255, 255, 255, 0.05);
        border-color: rgba(255, 255, 255, 0.08);
      }
      .row {
        display: flex;
        justify-content: space-between;
        gap: 8px;
      }
      .title {
        font-size: 13px;
        font-weight: 500;
      }
      .meta {
        font-size: 11px;
        opacity: 0.6;
        margin-top: 4px;
      }
      button {
        background: none;
        border: none;
        color: inherit;
        cursor: pointer;
      }
      .export-row {
        display: flex;
        gap: 6px;
        margin-bottom: 10px;
      }
      .export-row button {
        flex: 1;
        padding: 6px 8px;
        border-radius: 8px;
        border: 1px solid rgba(255, 255, 255, 0.12);
        font-size: 11px;
      }
    `,
  ],
})
export class ChatSidebarComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly exportService = inject(ExportService);

  @Input() activeId: string | null = null;
  @Output() select = new EventEmitter<string>();

  conversations: Conversation[] = [];
  search = '';

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    const params = this.search ? `?q=${encodeURIComponent(this.search)}` : '';
    this.http.get<Conversation[]>(`${API_BASE}/chat/conversations${params}`).subscribe({
      next: (items) => (this.conversations = items),
    });
  }

  toggleStar(conv: Conversation, event: Event): void {
    event.stopPropagation();
    this.http
      .patch<Conversation>(`${API_BASE}/chat/conversations/${conv.id}`, {
        starred: !conv.starred,
      })
      .subscribe({ next: () => this.load() });
  }

  exportActive(format: 'markdown' | 'pdf'): void {
    if (!this.activeId) return;
    this.exportService.exportConversation(this.activeId, format).subscribe({
      next: (res) => this.exportService.downloadBlob(res, `conversation.${format === 'markdown' ? 'md' : 'pdf'}`),
    });
  }
}
