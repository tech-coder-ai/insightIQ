import { DecimalPipe, DatePipe } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Component, Input, OnChanges, SimpleChanges, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { API_BASE } from '../core/api.config';

type AdminSummary = {
  collection_id: string;
  collection_name: string;
  rag_profile: string;
  embedding_model: string;
  document_count: number;
  current_document_count: number;
  chunk_count: number;
  vector_points_estimate: number;
};

type AdminDocument = {
  id: string;
  registry_id: string;
  filename: string;
  version_number: number;
  is_current: boolean;
  status: string;
  content_hash: string | null;
  mime_type: string | null;
  file_size_bytes: number | null;
  page_count: number | null;
  chunk_count: number;
  has_original: boolean;
  created_at: string;
  metadata_json: Record<string, unknown>;
};

type AdminChunk = {
  id: string;
  chunk_id: string;
  document_id: string;
  filename: string;
  version_number: number | null;
  chunk_index: number;
  char_start: number;
  char_end: number;
  page_number: number | null;
  text_preview: string;
  qdrant_point_id: string | null;
  embedding_model: string | null;
  document_type?: string | null;
  tags: string[];
  bbox_json: Record<string, unknown> | null;
  highlight_regions: unknown[] | null;
};

type DocumentVersion = {
  id: string;
  version_number: number;
  is_current: boolean;
  status: string;
  content_hash: string | null;
  chunk_count: number;
  created_at: string;
  superseded_at: string | null;
};

@Component({
  selector: 'app-document-admin-panel',
  standalone: true,
  imports: [FormsModule, DecimalPipe, DatePipe],
  template: `
    <div class="admin-panel">
      <div class="admin-head">
        <div>
          <h2>Collection admin</h2>
          <p>Browse indexed vectors, document versions, and enterprise metadata.</p>
        </div>
        <div class="admin-tabs">
          <button type="button" class="tab" [class.active]="tab() === 'overview'" (click)="tab.set('overview')">Overview</button>
          <button type="button" class="tab" [class.active]="tab() === 'documents'" (click)="tab.set('documents')">Documents</button>
          <button type="button" class="tab" [class.active]="tab() === 'chunks'" (click)="tab.set('chunks')">Chunks</button>
        </div>
      </div>

      @if (loading()) {
        <p class="admin-hint">Loading admin data…</p>
      } @else if (error()) {
        <p class="admin-error">{{ error() }}</p>
      } @else {
        @if (tab() === 'overview' && summary()) {
          <div class="stats-grid">
            <div class="stat-card"><div class="stat-label">Current documents</div><div class="stat-value">{{ summary()!.current_document_count }}</div></div>
            <div class="stat-card"><div class="stat-label">Total versions</div><div class="stat-value">{{ summary()!.document_count }}</div></div>
            <div class="stat-card"><div class="stat-label">Indexed chunks</div><div class="stat-value">{{ summary()!.chunk_count }}</div></div>
            <div class="stat-card"><div class="stat-label">Embedding model</div><div class="stat-value sm">{{ summary()!.embedding_model }}</div></div>
            <div class="stat-card"><div class="stat-label">RAG profile</div><div class="stat-value sm">{{ summary()!.rag_profile }}</div></div>
            <div class="stat-card"><div class="stat-label">Vector points</div><div class="stat-value">{{ summary()!.vector_points_estimate }}</div></div>
          </div>
        }

        @if (tab() === 'documents') {
          <div class="admin-tab-body">
            <div class="admin-toolbar">
              <label class="checkbox-row">
                <input type="checkbox" [(ngModel)]="includeHistory" (ngModelChange)="loadDocuments()" />
                Show version history
              </label>
            </div>
            <div class="table-wrap admin-scroll-body">
            <table class="admin-table">
              <thead>
                <tr>
                  <th>File</th><th>Ver</th><th>Status</th><th>Chunks</th><th>Hash</th><th>Original</th><th>Indexed</th><th></th>
                </tr>
              </thead>
              <tbody>
                @for (doc of documents(); track doc.id) {
                  <tr [class.muted]="!doc.is_current">
                    <td>{{ doc.filename }}</td>
                    <td>v{{ doc.version_number }}</td>
                    <td><span class="badge">{{ doc.status }}</span></td>
                    <td>{{ doc.chunk_count }}</td>
                    <td class="mono">{{ doc.content_hash?.slice(0, 10) || '—' }}</td>
                    <td>{{ doc.has_original ? 'Yes' : 'No' }}</td>
                    <td>{{ doc.created_at | date: 'medium' }}</td>
                    <td><button type="button" class="btn btn-ghost btn-sm" (click)="showVersions(doc.registry_id)">Versions</button></td>
                  </tr>
                  @if (versionRegistry() === doc.registry_id && versions().length) {
                    <tr class="version-row">
                      <td colspan="8">
                        <div class="version-list">
                          @for (v of versions(); track v.id) {
                            <div class="version-item">
                              <strong>v{{ v.version_number }}</strong>
                              <span>{{ v.status }}</span>
                              <span>{{ v.chunk_count }} chunks</span>
                              <span class="mono">{{ v.content_hash?.slice(0, 12) || '—' }}</span>
                              <span>{{ v.created_at | date: 'short' }}</span>
                              @if (v.superseded_at) { <span>superseded {{ v.superseded_at | date: 'short' }}</span> }
                            </div>
                          }
                        </div>
                      </td>
                    </tr>
                  }
                }
              </tbody>
            </table>
            </div>
          </div>
        }

        @if (tab() === 'chunks') {
          <div class="admin-tab-body">
            <div class="admin-toolbar">
              <input [(ngModel)]="chunkQuery" placeholder="Search chunk text…" (keyup.enter)="loadChunks()" />
              <button type="button" class="btn btn-secondary btn-sm" (click)="loadChunks()">Search</button>
              <span class="chunk-count">{{ chunks().length }} chunk(s) shown</span>
            </div>
            <div class="table-wrap admin-scroll-body">
              <table class="admin-table">
                <thead>
                  <tr>
                    <th>Document</th><th>Idx</th><th>Page</th><th>Chars</th><th>Preview</th><th>Qdrant</th><th>Tags</th>
                  </tr>
                </thead>
                <tbody>
                  @for (chunk of chunks(); track chunk.id) {
                    <tr>
                      <td>{{ chunk.filename }}</td>
                      <td>{{ chunk.chunk_index }}</td>
                      <td>{{ chunk.page_number ?? '—' }}</td>
                      <td class="mono">{{ chunk.char_start }}–{{ chunk.char_end }}</td>
                      <td class="preview-cell">{{ chunk.text_preview }}</td>
                      <td class="mono">{{ chunk.qdrant_point_id?.slice(0, 8) || '—' }}</td>
                      <td>{{ chunk.tags.join(', ') || '—' }}</td>
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          </div>
        }
      }
    </div>
  `,
  styles: [
    `
      :host {
        display: flex;
        flex: 1;
        min-height: 0;
        overflow: hidden;
      }
      .admin-panel {
        display: flex;
        flex-direction: column;
        gap: var(--space-4);
        flex: 1;
        min-height: 0;
        overflow: hidden;
        padding: var(--space-4);
      }
      .admin-tab-body {
        display: flex;
        flex-direction: column;
        gap: var(--space-3);
        flex: 1;
        min-height: 0;
      }
      .admin-head { display: flex; justify-content: space-between; gap: var(--space-4); align-items: flex-start; flex-wrap: wrap; }
      .admin-head h2 { margin: 0 0 4px; font-size: var(--text-lg); }
      .admin-head p { margin: 0; color: var(--text-muted); font-size: var(--text-sm); }
      .admin-tabs { display: flex; gap: 6px; }
      .tab { border: 1px solid var(--border); background: var(--surface-2); border-radius: var(--radius-md); padding: 8px 12px; cursor: pointer; }
      .tab.active { border-color: var(--primary); background: var(--primary-soft); color: var(--primary-text); }
      .stats-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(160px, 1fr)); gap: 12px; }
      .stat-card { border: 1px solid var(--border); border-radius: var(--radius-md); padding: 14px; background: var(--surface); }
      .stat-label { font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); }
      .stat-value { font-size: var(--text-xl); font-weight: 700; margin-top: 4px; }
      .stat-value.sm { font-size: var(--text-sm); font-weight: 600; word-break: break-all; }
      .admin-toolbar { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
      .admin-toolbar input { flex: 1; min-width: 220px; padding: 8px 10px; border: 1px solid var(--border-strong); border-radius: var(--radius-md); background: var(--input-bg); color: var(--text); }
      .checkbox-row { display: inline-flex; align-items: center; gap: 8px; font-size: var(--text-sm); }
      .chunk-count { margin-left: auto; font-size: var(--text-xs); color: var(--text-muted); white-space: nowrap; }
      .table-wrap { border: 1px solid var(--border); border-radius: var(--radius-md); }
      .admin-scroll-body {
        flex: 1;
        min-height: 0;
        overflow: auto;
        overscroll-behavior: contain;
        -webkit-overflow-scrolling: touch;
      }
      .admin-scroll-body .admin-table thead th {
        position: sticky;
        top: 0;
        z-index: 1;
        box-shadow: inset 0 -1px 0 var(--border);
      }
      .admin-table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
      .admin-table th, .admin-table td { padding: 10px 12px; border-bottom: 1px solid var(--border); text-align: left; vertical-align: top; }
      .admin-table th { background: var(--surface-2); font-size: 10px; text-transform: uppercase; letter-spacing: 0.06em; color: var(--text-muted); }
      .admin-table tr.muted { opacity: 0.72; }
      .mono { font-family: var(--font-mono, ui-monospace, monospace); font-size: 11px; }
      .preview-cell { max-width: 320px; }
      .badge { display: inline-block; padding: 2px 8px; border-radius: 999px; background: var(--surface-2); font-size: 11px; }
      .version-list { display: grid; gap: 6px; padding: 8px 0; }
      .version-item { display: flex; flex-wrap: wrap; gap: 10px; font-size: var(--text-xs); color: var(--text-2); }
      .admin-hint, .admin-error { font-size: var(--text-sm); }
      .admin-error { color: var(--danger); }
    `,
  ],
})
export class DocumentAdminPanelComponent implements OnChanges {
  @Input({ required: true }) collectionId = '';

  private readonly http = inject(HttpClient);

  readonly tab = signal<'overview' | 'documents' | 'chunks'>('overview');
  readonly loading = signal(false);
  readonly error = signal('');
  readonly summary = signal<AdminSummary | null>(null);
  readonly documents = signal<AdminDocument[]>([]);
  readonly chunks = signal<AdminChunk[]>([]);
  readonly versions = signal<DocumentVersion[]>([]);
  readonly versionRegistry = signal<string | null>(null);

  includeHistory = false;
  chunkQuery = '';

  ngOnChanges(changes: SimpleChanges): void {
    if (changes['collectionId'] && this.collectionId) {
      this.refresh();
    }
  }

  refresh(): void {
    this.loading.set(true);
    this.error.set('');
    this.http.get<AdminSummary>(`${API_BASE}/talk-to-docs/collections/${this.collectionId}/admin/summary`).subscribe({
      next: (s) => {
        this.summary.set(s);
        this.loadDocuments();
        this.loadChunks();
        this.loading.set(false);
      },
      error: () => {
        this.loading.set(false);
        this.error.set('Could not load admin summary.');
      },
    });
  }

  loadDocuments(): void {
    const params = this.includeHistory ? '?include_history=true' : '';
    this.http
      .get<AdminDocument[]>(`${API_BASE}/talk-to-docs/collections/${this.collectionId}/admin/documents${params}`)
      .subscribe({ next: (rows) => this.documents.set(rows) });
  }

  loadChunks(): void {
    const params = new URLSearchParams({ limit: '200' });
    if (this.chunkQuery.trim()) params.set('q', this.chunkQuery.trim());
    this.http
      .get<AdminChunk[]>(`${API_BASE}/talk-to-docs/collections/${this.collectionId}/admin/chunks?${params}`)
      .subscribe({ next: (rows) => this.chunks.set(rows) });
  }

  showVersions(registryId: string): void {
    if (this.versionRegistry() === registryId) {
      this.versionRegistry.set(null);
      this.versions.set([]);
      return;
    }
    this.http.get<DocumentVersion[]>(`${API_BASE}/talk-to-docs/documents/registry/${registryId}/versions`).subscribe({
      next: (rows) => {
        this.versionRegistry.set(registryId);
        this.versions.set(rows);
      },
    });
  }
}
