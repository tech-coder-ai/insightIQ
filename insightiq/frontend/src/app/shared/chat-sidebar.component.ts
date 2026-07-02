import { HttpClient } from '@angular/common/http';
import { Component, EventEmitter, Input, OnInit, Output, inject } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { API_BASE } from '../core/api.config';
import { ExportService } from '../core/export.service';
import { IconComponent } from './icon.component';

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
  imports: [FormsModule, IconComponent],
  template: `
    <aside class="sidebar">
      <div class="head">
        <h2>Chat History</h2>
        <input [(ngModel)]="search" (ngModelChange)="load()" placeholder="Search..." />
        @if (activeId) {
          <div class="export-row">
            <button type="button" (click)="exportActive('markdown')">Export MD</button>
            <button type="button" (click)="exportActive('pdf')">Export PDF</button>
            <button type="button" (click)="exportActive('pptx')">Export PPT</button>
          </div>
        }
      </div>
      <ul>
        @for (c of conversations; track c.id) {
          <li [class.active]="c.id === activeId" (click)="select.emit(c.id)">
            <div class="row">
              <span class="title">{{ c.title }}</span>
              <button type="button" [attr.aria-label]="c.starred ? 'Unstar' : 'Star'" (click)="toggleStar(c, $event)">
                <app-icon [name]="c.starred ? 'star-filled' : 'star-outline'" [size]="12" />
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
        border-right: 1px solid var(--border);
        padding: var(--space-4);
        min-width: 240px;
        max-width: 280px;
      }
      h2 {
        margin: 0 0 8px;
        font-size: var(--text-base);
      }
      input {
        width: 100%;
        padding: 9px 11px;
        border-radius: var(--radius-md);
        border: 1px solid var(--border-strong);
        background: var(--input-bg);
        color: var(--text);
        margin-bottom: 12px;
        font-family: inherit;
      }
      input:focus { outline: none; border-color: var(--border-focus); box-shadow: 0 0 0 3px var(--primary-soft); }
      ul {
        list-style: none;
        margin: 0;
        padding: 0;
        display: grid;
        gap: 4px;
      }
      li {
        padding: 10px;
        border-radius: var(--radius-md);
        cursor: pointer;
        border: 1px solid transparent;
        transition: background var(--dur-fast) var(--ease);
      }
      li:hover { background: var(--surface-2); }
      li.active {
        background: var(--primary-soft);
        border-color: var(--primary);
      }
      .row {
        display: flex;
        justify-content: space-between;
        gap: 8px;
      }
      .title {
        font-size: var(--text-sm);
        font-weight: 500;
      }
      .meta {
        font-size: var(--text-xs);
        color: var(--text-muted);
        margin-top: 4px;
      }
      button {
        background: none;
        border: none;
        color: var(--text-2);
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
        border-radius: var(--radius-md);
        border: 1px solid var(--border-strong);
        font-size: var(--text-xs);
      }
      .export-row button:hover { background: var(--surface-2); color: var(--text); }
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

  exportActive(format: 'markdown' | 'pdf' | 'pptx'): void {
    if (!this.activeId) return;
    const ext = format === 'markdown' ? 'md' : format;
    this.exportService.exportConversation(this.activeId, format).subscribe({
      next: (res) => this.exportService.downloadBlob(res, `conversation.${ext}`),
    });
  }
}
