import { HttpClient } from '@angular/common/http';
import { Component, OnInit, computed, inject, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import { API_BASE } from '../../core/api.config';
import { AuthService } from '../../core/auth.service';

type ColumnMeta = {
  name: string;
  data_type: string;
  nullable: boolean;
  is_primary_key: boolean;
  is_indexed: boolean;
};
type IndexMeta = { name: string; columns: string[]; unique: boolean };
type TableMeta = { name: string; columns: ColumnMeta[]; indexes: IndexMeta[] };
type Relationship = {
  from_table: string;
  from_column: string;
  to_table: string;
  to_column: string;
  source: string;
};
type GlossaryEntry = {
  id: string;
  table: string;
  column: string | null;
  definition: string;
  tags: string[];
  status: string;
  source: string;
  updated_by?: string | null;
  updated_at?: string | null;
};
type SchemaMetadata = { tables: TableMeta[]; relationships: Relationship[] };
type DataSourceDetail = {
  id: string;
  name: string;
  db_type: string;
  dialect: string;
  description: string;
  metadata_status: string;
  connection: Record<string, unknown>;
  schema_metadata: SchemaMetadata;
  selected_scope: { tables: Record<string, string[]> };
  relationships: Relationship[];
  glossary: GlossaryEntry[];
};

type Tab = 'overview' | 'connection' | 'tables' | 'relationships' | 'glossary' | 'approval';

@Component({
  standalone: true,
  imports: [FormsModule, RouterLink],
  template: `
    @if (detail(); as d) {
    <div class="page">
      <a routerLink="/datasources" class="back-link">← All datasources</a>

      <div class="page-header">
        <div class="title-row">
          <div class="ds-badge">{{ iconFor(d.db_type) }}</div>
          <div>
            <h1>{{ d.name }}</h1>
            <p class="subtitle">{{ d.db_type }} · dialect {{ d.dialect }}</p>
          </div>
          <span class="status-pill" [attr.data-status]="d.metadata_status">{{ statusLabel(d.metadata_status) }}</span>
        </div>
        <button class="btn-primary" (click)="talkToIt()">Talk to it →</button>
      </div>

      <div class="tabs">
        @for (t of tabs; track t.id) {
          <button class="tab" [class.active]="activeTab() === t.id" (click)="activeTab.set(t.id)">
            {{ t.label }}
            @if (t.id === 'approval' && pendingCount() > 0) { <span class="tab-count">{{ pendingCount() }}</span> }
          </button>
        }
      </div>

      @if (message()) {
        <div [class]="message().startsWith('✓') ? 'msg-ok' : 'msg-err'">{{ message() }}</div>
      }

      <!-- ── Overview ── -->
      @if (activeTab() === 'overview') {
        <div class="panel">
          <div class="panel-header">
            <h2>Purpose &amp; description</h2>
            <button class="btn-ghost small" (click)="generateDescription()" [disabled]="busy()">
              {{ busy() ? 'Working…' : '✨ Generate with AI' }}
            </button>
          </div>
          <label class="field">
            <span>Business context for AI (optional)</span>
            <input [(ngModel)]="descContext" placeholder="e.g. e-commerce orders and customers warehouse" />
          </label>
          <label class="field">
            <span>Description</span>
            <textarea [(ngModel)]="descDraft" rows="5" placeholder="Describe what this datasource contains and what it's used for…"></textarea>
          </label>
          <div class="form-actions">
            <button class="btn-primary" (click)="saveDescription()" [disabled]="busy()">Save description</button>
          </div>
        </div>
      }

      <!-- ── Connection ── -->
      @if (activeTab() === 'connection') {
        <div class="panel">
          <div class="panel-header">
            <h2>Connection settings</h2>
            <div class="panel-actions">
              @if (connectionEditable()) {
                <button class="btn-ghost small" (click)="testConnectionDraft()" [disabled]="busy()">
                  {{ busy() ? 'Testing…' : 'Test connection' }}
                </button>
                <button class="btn-primary small" (click)="saveConnection()" [disabled]="busy() || !nameDraft.trim()">
                  {{ busy() ? 'Saving…' : 'Save connection' }}
                </button>
              }
            </div>
          </div>

          @if (!connectionEditable()) {
            <p class="notice">
              This datasource reads from uploaded files. Connection settings cannot be changed here —
              create a new datasource to upload a different file.
            </p>
            @if (uploadedFiles().length) {
              <ul class="file-list">
                @for (f of uploadedFiles(); track f.table) {
                  <li><strong>{{ f.table }}</strong> <span class="muted">· {{ f.filename }}</span></li>
                }
              </ul>
            }
          } @else {
            <p class="hint">Update host, credentials, or other connection details. Leave secret fields blank to keep the stored values.</p>

            <label class="field">
              <span>Source name</span>
              <input [(ngModel)]="nameDraft" placeholder="Production DB" />
            </label>

            @if (['postgres','mssql','oracle'].includes(d.db_type)) {
              <div class="form-grid">
                <label class="field">
                  <span>Host</span>
                  <input [(ngModel)]="conn.host" placeholder="localhost" />
                </label>
                <label class="field">
                  <span>Port</span>
                  <input [(ngModel)]="conn.port" type="number" [placeholder]="defaultPort(d.db_type)" />
                </label>
                <label class="field">
                  <span>{{ d.db_type === 'oracle' ? 'Service name' : 'Database' }}</span>
                  <input [(ngModel)]="conn.database" />
                </label>
                <label class="field">
                  <span>Username</span>
                  <input [(ngModel)]="conn.user" />
                </label>
                <label class="field">
                  <span>Password</span>
                  <input [(ngModel)]="conn.password" type="password" [placeholder]="secretPlaceholder" autocomplete="new-password" />
                </label>
                @if (d.db_type === 'mssql') {
                  <label class="field">
                    <span>Schema (optional)</span>
                    <input [(ngModel)]="conn.schema_name" placeholder="dbo" />
                  </label>
                }
              </div>
            }

            @if (d.db_type === 'snowflake') {
              <div class="form-grid">
                <label class="field"><span>Account</span><input [(ngModel)]="conn.account" /></label>
                <label class="field"><span>Warehouse</span><input [(ngModel)]="conn.warehouse" /></label>
                <label class="field"><span>Database</span><input [(ngModel)]="conn.database" /></label>
                <label class="field"><span>Schema (optional)</span><input [(ngModel)]="conn.schema_name" placeholder="PUBLIC" /></label>
                <label class="field"><span>Username</span><input [(ngModel)]="conn.user" /></label>
                <label class="field"><span>Password</span><input [(ngModel)]="conn.password" type="password" [placeholder]="secretPlaceholder" autocomplete="new-password" /></label>
                <label class="field"><span>Role (optional)</span><input [(ngModel)]="conn.role" /></label>
              </div>
            }

            @if (d.db_type === 'hive') {
              <div class="form-grid">
                <label class="field"><span>Host</span><input [(ngModel)]="conn.host" /></label>
                <label class="field"><span>Port</span><input [(ngModel)]="conn.port" type="number" placeholder="10000" /></label>
                <label class="field"><span>Database</span><input [(ngModel)]="conn.database" /></label>
                <label class="field">
                  <span>Auth method</span>
                  <select [(ngModel)]="conn.auth">
                    <option value="NOSASL">NOSASL</option>
                    <option value="LDAP">LDAP</option>
                    <option value="KERBEROS">Kerberos</option>
                  </select>
                </label>
                <label class="field"><span>Username</span><input [(ngModel)]="conn.user" /></label>
                <label class="field"><span>Password</span><input [(ngModel)]="conn.password" type="password" [placeholder]="secretPlaceholder" autocomplete="new-password" /></label>
              </div>
            }

            @if (d.db_type === 'bigquery') {
              <div class="form-grid">
                <label class="field"><span>GCP Project</span><input [(ngModel)]="conn.project" /></label>
                <label class="field"><span>Dataset</span><input [(ngModel)]="conn.dataset" /></label>
                <label class="field full">
                  <span>Service account JSON</span>
                  <textarea [(ngModel)]="conn.credentials_json" rows="5" [placeholder]="secretPlaceholder"></textarea>
                </label>
              </div>
            }

            @if (d.db_type === 's3_object_store') {
              <div class="form-grid">
                <label class="field"><span>Endpoint</span><input [(ngModel)]="conn.endpoint" placeholder="localhost:9000" /></label>
                <label class="field"><span>Region</span><input [(ngModel)]="conn.region" /></label>
                <label class="field"><span>Access key</span><input [(ngModel)]="conn.access_key" [placeholder]="secretPlaceholder" /></label>
                <label class="field"><span>Secret key</span><input [(ngModel)]="conn.secret_key" type="password" [placeholder]="secretPlaceholder" autocomplete="new-password" /></label>
                <label class="field">
                  <span>URL style</span>
                  <select [(ngModel)]="conn.url_style">
                    <option value="path">Path (MinIO)</option>
                    <option value="virtual-hosted">Virtual-hosted (AWS)</option>
                  </select>
                </label>
              </div>
              <div class="table-globs">
                <div class="section-label">File globs</div>
                @for (glob of connectionGlobs(); track $index) {
                  <div class="glob-row">
                    <input [value]="glob.table" (input)="updateConnectionGlob($index, 'table', $any($event.target).value)" placeholder="sales" />
                    <span>→</span>
                    <input [value]="glob.pattern" (input)="updateConnectionGlob($index, 'pattern', $any($event.target).value)" placeholder="s3://bucket/sales/*.parquet" />
                    <button type="button" class="btn-ghost small" (click)="removeConnectionGlob($index)">✕</button>
                  </div>
                }
                <button type="button" class="btn-ghost small" (click)="addConnectionGlob()">+ Add file glob</button>
              </div>
            }
          }
        </div>
      }

      <!-- ── Tables & Columns ── -->
      @if (activeTab() === 'tables') {
        <div class="panel">
          <div class="panel-header">
            <h2>Tables &amp; columns</h2>
            <div class="panel-actions">
              <button class="btn-ghost small" (click)="refreshSchema()" [disabled]="busy()">↻ Re-introspect</button>
              <button class="btn-primary small" (click)="saveScope()" [disabled]="busy() || !hasScopeSelection()">Save scope</button>
            </div>
          </div>
          <p class="hint">Checked columns are exposed to Talk to Data and prompt bindings. Uncheck sensitive fields you do not want the AI to use.</p>
          @if (!d.schema_metadata.tables.length) {
            <p class="empty-line">No tables discovered.</p>
          }
          @for (t of d.schema_metadata.tables; track t.name) {
            <details class="table-block">
              <summary>
                <label class="scope-check" (click)="$event.stopPropagation()">
                  <input
                    type="checkbox"
                    [checked]="isTableFullyInScope(t.name)"
                    [class.partial]="isTablePartiallyInScope(t.name)"
                    (click)="onScopeTableCheckboxClick(t.name, $event)"
                  />
                  <strong>{{ t.name }}</strong>
                </label>
                <span class="muted">{{ scopeColumnCount(t.name) }}/{{ t.columns.length }} in scope · {{ t.indexes.length }} indexes</span>
              </summary>
              <table class="col-table">
                <thead>
                  <tr><th>In scope</th><th>Column</th><th>Type</th><th>Keys</th><th>Glossary</th><th>Tags</th></tr>
                </thead>
                <tbody>
                  @for (c of t.columns; track c.name) {
                    <tr>
                      <td>
                        <input
                          type="checkbox"
                          [checked]="isColumnInScope(t.name, c.name)"
                          (change)="toggleScopeColumn(t.name, c.name, $any($event.target).checked)"
                        />
                      </td>
                      <td class="mono">{{ c.name }}</td>
                      <td class="muted">{{ c.data_type }}{{ c.nullable ? '' : ' · not null' }}</td>
                      <td>
                        @if (c.is_primary_key) { <span class="badge pk">PK</span> }
                        @if (c.is_indexed && !c.is_primary_key) { <span class="badge idx">IDX</span> }
                      </td>
                      <td class="muted">{{ glossaryFor(t.name, c.name)?.definition || '—' }}</td>
                      <td>
                        @for (tag of glossaryFor(t.name, c.name)?.tags || []; track tag) {
                          <span class="chip">{{ tag }}</span>
                        }
                      </td>
                    </tr>
                  }
                </tbody>
              </table>
              @if (t.indexes.length) {
                <div class="idx-list">
                  <span class="idx-title">Indexes:</span>
                  @for (ix of t.indexes; track ix.name) {
                    <span class="chip idx">{{ ix.name }}{{ ix.unique ? ' (unique)' : '' }} [{{ ix.columns.join(', ') }}]</span>
                  }
                </div>
              }
            </details>
          }
        </div>
      }

      <!-- ── Relationships ── -->
      @if (activeTab() === 'relationships') {
        <div class="panel">
          <div class="panel-header">
            <h2>Relationships</h2>
            <button class="btn-primary small" (click)="saveRelationships()" [disabled]="busy()">Save relationships</button>
          </div>
          @if (!relationships().length) {
            <p class="empty-line">No relationships yet. Add foreign-key links below to help question answering.</p>
          }
          <table class="rel-table">
            <thead>
              <tr><th>From table</th><th>From column</th><th>To table</th><th>To column</th><th>Source</th><th></th></tr>
            </thead>
            <tbody>
              @for (r of relationships(); track $index) {
                <tr>
                  <td class="mono">{{ r.from_table }}</td>
                  <td class="mono">{{ r.from_column }}</td>
                  <td class="mono">{{ r.to_table }}</td>
                  <td class="mono">{{ r.to_column }}</td>
                  <td><span class="badge" [class.idx]="r.source === 'introspected'">{{ r.source }}</span></td>
                  <td><button class="btn-danger small" (click)="removeRelationship($index)">✕</button></td>
                </tr>
              }
            </tbody>
          </table>

          <div class="add-rel">
            <div class="section-label">Add relationship</div>
            <div class="rel-form">
              <select [(ngModel)]="newRel.from_table" (ngModelChange)="newRel.from_column = ''">
                <option value="">From table…</option>
                @for (t of d.schema_metadata.tables; track t.name) { <option [value]="t.name">{{ t.name }}</option> }
              </select>
              <select [(ngModel)]="newRel.from_column">
                <option value="">column…</option>
                @for (c of columnsOf(newRel.from_table); track c) { <option [value]="c">{{ c }}</option> }
              </select>
              <span class="arrow">→</span>
              <select [(ngModel)]="newRel.to_table" (ngModelChange)="newRel.to_column = ''">
                <option value="">To table…</option>
                @for (t of d.schema_metadata.tables; track t.name) { <option [value]="t.name">{{ t.name }}</option> }
              </select>
              <select [(ngModel)]="newRel.to_column">
                <option value="">column…</option>
                @for (c of columnsOf(newRel.to_table); track c) { <option [value]="c">{{ c }}</option> }
              </select>
              <button class="btn-ghost small" (click)="addRelationship()" [disabled]="!canAddRel()">+ Add</button>
            </div>
          </div>
        </div>
      }

      <!-- ── Glossary & Tags ── -->
      @if (activeTab() === 'glossary') {
        <div class="panel">
          <div class="panel-header">
            <h2>Glossary &amp; tags</h2>
            <div class="header-actions">
              <button class="btn-primary small" (click)="saveGlossary()" [disabled]="busy()">Save</button>
            </div>
          </div>

          <div class="gen-bar">
            <div class="gen-row">
              <span class="section-label">Generate with AI</span>
              <input class="ctx-input" [(ngModel)]="glossaryContext" placeholder="Business context to guide definitions (optional)" />
              <button class="btn-ghost small" (click)="generateGlossary()" [disabled]="busy()">
                {{ busy() ? 'Working…' : '✨ Generate' }}
              </button>
            </div>
            <div class="gen-row">
              <span class="section-label">Bulk upload (CSV: table, column, definition, tags)</span>
              <input type="file" accept=".csv" (change)="onGlossaryFile($event)" />
            </div>
            <div class="gen-row">
              <label class="filter-label">Filter table
                <select [(ngModel)]="glossaryFilter">
                  <option value="">All tables</option>
                  @for (t of d.schema_metadata.tables; track t.name) { <option [value]="t.name">{{ t.name }}</option> }
                </select>
              </label>
            </div>
          </div>

          @if (!filteredGlossary().length) {
            <p class="empty-line">No glossary entries. Generate with AI or upload a CSV to get started.</p>
          }
          <table class="gloss-table">
            <thead>
              <tr><th>Target</th><th>Definition</th><th>Tags (comma sep)</th><th>Status</th></tr>
            </thead>
            <tbody>
              @for (g of filteredGlossary(); track g.id) {
                <tr>
                  <td class="mono">{{ g.table }}{{ g.column ? '.' + g.column : '' }}</td>
                  <td><input class="cell-input" [(ngModel)]="g.definition" /></td>
                  <td><input class="cell-input" [ngModel]="g.tags.join(', ')" (ngModelChange)="setTags(g, $event)" /></td>
                  <td><span class="badge" [attr.data-status]="g.status">{{ g.status }}</span></td>
                </tr>
              }
            </tbody>
          </table>
        </div>
      }

      <!-- ── Approval ── -->
      @if (activeTab() === 'approval') {
        <div class="panel">
          <div class="panel-header">
            <h2>Approval</h2>
            @if (isAdmin) {
              <button class="btn-primary small" (click)="approveAll()" [disabled]="busy() || !pendingCount()">Approve all</button>
            }
          </div>
          @if (!isAdmin) {
            <p class="notice">You can author and edit metadata, but only an admin can approve it. Pending items are shown below.</p>
          }
          @if (!glossary().length) {
            <p class="empty-line">Nothing to approve yet.</p>
          }
          @for (t of tablesWithGlossary(); track t) {
            <div class="approve-group">
              <div class="approve-head">
                <strong>{{ t }}</strong>
                <span class="muted">{{ approvedCountFor(t) }}/{{ countFor(t) }} approved</span>
                @if (isAdmin) {
                  <button class="btn-ghost small" (click)="approveTable(t)" [disabled]="busy()">Approve table</button>
                }
              </div>
              <table class="gloss-table">
                <thead><tr><th>Target</th><th>Definition</th><th>Status</th>@if (isAdmin) { <th></th> }</tr></thead>
                <tbody>
                  @for (g of glossaryForTable(t); track g.id) {
                    <tr>
                      <td class="mono">{{ g.table }}{{ g.column ? '.' + g.column : '' }}</td>
                      <td class="muted">{{ g.definition || '—' }}</td>
                      <td><span class="badge" [attr.data-status]="g.status">{{ g.status }}</span></td>
                      @if (isAdmin) {
                        <td>
                          @if (g.status !== 'approved') {
                            <button class="btn-ghost small" (click)="approveOne(g)" [disabled]="busy()">Approve</button>
                          } @else { <span class="muted">✓</span> }
                        </td>
                      }
                    </tr>
                  }
                </tbody>
              </table>
            </div>
          }
        </div>
      }
    </div>
    }
  `,
  styles: [`
    .page { max-width: 1040px; }
    .back-link { font-size: var(--text-sm); color: var(--text-2); text-decoration: none; }
    .back-link:hover { color: var(--text); }
    .page-header { display: flex; justify-content: space-between; align-items: flex-start; margin: 10px 0 18px; gap: 16px; }
    .title-row { display: flex; align-items: center; gap: 14px; }
    .title-row h1 { margin: 0; font-size: var(--text-2xl); }
    .subtitle { margin: 2px 0 0; color: var(--text-muted); font-size: var(--text-sm); }
    .ds-badge { width: 46px; height: 46px; border-radius: var(--radius-md); display: grid; place-items: center; font-size: 22px; background: var(--surface-3); }

    .status-pill { font-size: var(--text-xs); font-weight: 650; padding: 4px 10px; border-radius: var(--radius-pill); background: var(--surface-3); color: var(--text-2); text-transform: capitalize; }
    .status-pill[data-status='approved'] { background: var(--success-soft); color: var(--success); }
    .status-pill[data-status='partially_approved'] { background: var(--warning-soft); color: var(--warning); }

    .tabs { display: flex; gap: 4px; border-bottom: 1px solid var(--border); margin-bottom: 18px; }
    .tab { position: relative; padding: 10px 16px; background: none; border: none; color: var(--text-2); cursor: pointer; font-family: inherit; font-size: var(--text-base); border-bottom: 2px solid transparent; margin-bottom: -1px; }
    .tab:hover { color: var(--text); }
    .tab.active { color: var(--primary); border-bottom-color: var(--primary); font-weight: 600; }
    .tab-count { background: var(--warning); color: #1a1200; font-size: 10px; font-weight: 700; padding: 1px 6px; border-radius: var(--radius-pill); margin-left: 5px; }

    .panel { background: var(--surface); border: 1px solid var(--border); border-radius: var(--radius-lg); padding: var(--space-6); box-shadow: var(--shadow-sm); }
    .panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-5); }
    .panel-header h2 { margin: 0; font-size: var(--text-lg); }
    .panel-actions { display: flex; gap: 8px; flex-wrap: wrap; }
    .scope-check {
      display: inline-flex; flex-direction: row; align-items: center; gap: 8px;
      cursor: pointer; font-weight: 500; margin: 0;
    }
    .scope-check input[type='checkbox'],
    .col-table input[type='checkbox'] {
      width: 16px; height: 16px; min-width: 16px; margin: 0; padding: 0;
      accent-color: var(--primary); cursor: pointer;
    }
    .scope-check input[type='checkbox'].partial { opacity: 0.65; }
    .hint { color: var(--text-muted); font-size: var(--text-sm); margin: 0 0 var(--space-4); }
    .header-actions { display: flex; gap: 8px; }

    .field { display: flex; flex-direction: column; gap: 6px; font-size: var(--text-xs); color: var(--text-2); font-weight: 550; margin-bottom: 14px; }
    .field.full { grid-column: 1 / -1; }
    .form-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
      gap: 0 14px;
      margin-bottom: 8px;
    }
    .form-grid .field { margin-bottom: 14px; }
    .table-globs { display: flex; flex-direction: column; gap: 8px; margin-top: 8px; }
    .glob-row { display: flex; align-items: center; gap: 8px; }
    .glob-row input { flex: 1; }
    .glob-row span { color: var(--text-muted); }
    .file-list { margin: 0; padding-left: 18px; }
    .file-list li { margin-bottom: 6px; font-size: var(--text-sm); }
    input:not([type='checkbox']):not([type='radio']), select, textarea { padding: 9px 12px; border-radius: var(--radius-md); border: 1px solid var(--border-strong); background: var(--input-bg); color: var(--text); font-size: var(--text-base); font-family: inherit; }
    input:not([type='checkbox']):not([type='radio']):focus, select:focus, textarea:focus { outline: none; border-color: var(--border-focus); box-shadow: 0 0 0 3px var(--primary-soft); }
    textarea { resize: vertical; }

    .btn-primary { display: inline-flex; align-items: center; gap: 6px; padding: 9px 16px; border-radius: var(--radius-md); border: none; background: var(--primary); color: var(--on-primary); font-size: var(--text-base); font-weight: 550; cursor: pointer; font-family: inherit; }
    .btn-primary:hover:not(:disabled) { background: var(--primary-hover); }
    .btn-primary:disabled { opacity: 0.5; cursor: default; }
    .btn-primary.small { padding: 5px 11px; font-size: var(--text-sm); }
    .btn-ghost { padding: 7px 12px; border-radius: var(--radius-md); border: 1px solid var(--border-strong); background: transparent; color: var(--text-2); cursor: pointer; font-size: var(--text-sm); font-family: inherit; }
    .btn-ghost:hover { background: var(--surface-2); color: var(--text); }
    .btn-ghost.small { padding: 4px 9px; font-size: var(--text-xs); }
    .btn-danger { padding: 4px 9px; border-radius: var(--radius-md); font-size: var(--text-xs); border: 1px solid var(--danger-soft); background: transparent; color: var(--danger); cursor: pointer; font-family: inherit; }
    .btn-danger:hover { background: var(--danger-soft); }

    .form-actions { display: flex; gap: 10px; margin-top: 4px; }
    .msg-ok { color: var(--success); font-size: var(--text-sm); margin-bottom: 12px; }
    .msg-err { color: var(--danger); font-size: var(--text-sm); margin-bottom: 12px; }
    .empty-line { color: var(--text-muted); font-size: var(--text-sm); }
    .notice { font-size: var(--text-sm); color: var(--text-2); background: var(--surface-2); padding: 10px 14px; border-radius: var(--radius-md); margin-bottom: 14px; }
    .section-label { font-size: var(--text-sm); color: var(--text-2); font-weight: 550; }
    .muted { color: var(--text-muted); font-size: var(--text-xs); }
    .mono { font-family: var(--font-mono); font-size: var(--text-sm); }

    .table-block { border: 1px solid var(--border); border-radius: var(--radius-md); margin-bottom: 10px; padding: 4px 12px; }
    .table-block summary { cursor: pointer; padding: 8px 0; display: flex; gap: 10px; align-items: baseline; }
    .col-table, .rel-table, .gloss-table { width: 100%; border-collapse: collapse; font-size: var(--text-sm); }
    th { text-align: left; color: var(--text-muted); font-weight: 550; font-size: var(--text-xs); padding: 6px 8px; border-bottom: 1px solid var(--border); }
    td { padding: 6px 8px; border-bottom: 1px solid var(--border); vertical-align: middle; }
    .cell-input { width: 100%; padding: 5px 8px; font-size: var(--text-sm); }

    .badge { display: inline-block; font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: var(--radius-pill); background: var(--surface-3); color: var(--text-2); margin-right: 4px; text-transform: capitalize; }
    .badge.pk { background: var(--primary-soft); color: var(--primary); }
    .badge.idx { background: var(--surface-3); color: var(--text-2); }
    .badge[data-status='approved'] { background: var(--success-soft); color: var(--success); }
    .badge[data-status='pending'] { background: var(--warning-soft); color: var(--warning); }
    .chip { display: inline-block; font-size: 11px; padding: 2px 8px; border-radius: var(--radius-pill); background: var(--primary-soft); color: var(--primary); margin: 0 4px 2px 0; }
    .chip.idx { background: var(--surface-3); color: var(--text-2); font-family: var(--font-mono); }
    .idx-list { padding: 8px 0; display: flex; flex-wrap: wrap; gap: 4px; align-items: center; }
    .idx-title { font-size: var(--text-xs); color: var(--text-muted); margin-right: 4px; }

    .add-rel { margin-top: 16px; padding-top: 14px; border-top: 1px solid var(--border); }
    .rel-form { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-top: 8px; }
    .rel-form select { min-width: 130px; }
    .arrow { color: var(--text-muted); }

    .gen-bar { display: flex; flex-direction: column; gap: 10px; padding: 12px 14px; background: var(--surface-2); border-radius: var(--radius-md); margin-bottom: 16px; }
    .gen-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
    .ctx-input { flex: 1; min-width: 220px; }
    .filter-label { display: flex; align-items: center; gap: 8px; font-size: var(--text-xs); color: var(--text-2); }

    .approve-group { margin-bottom: 18px; }
    .approve-head { display: flex; align-items: center; gap: 12px; margin-bottom: 6px; }
  `],
})
export class DatasourceDetailComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly auth = inject(AuthService);

  readonly tabs: { id: Tab; label: string }[] = [
    { id: 'overview', label: 'Overview' },
    { id: 'connection', label: 'Connection' },
    { id: 'tables', label: 'Tables & Columns' },
    { id: 'relationships', label: 'Relationships' },
    { id: 'glossary', label: 'Glossary & Tags' },
    { id: 'approval', label: 'Approval' },
  ];

  readonly detail = signal<DataSourceDetail | null>(null);
  readonly activeTab = signal<Tab>('overview');
  readonly relationships = signal<Relationship[]>([]);
  readonly glossary = signal<GlossaryEntry[]>([]);
  readonly selectedScope = signal<Record<string, string[]>>({});
  readonly busy = signal(false);
  readonly message = signal('');

  readonly connectionGlobs = signal<{ table: string; pattern: string }[]>([]);

  descDraft = '';
  descContext = '';
  nameDraft = '';
  readonly secretPlaceholder = 'Leave blank to keep current';
  conn = {
    host: '',
    port: null as number | null,
    database: '',
    user: '',
    password: '',
    schema_name: '',
    account: '',
    warehouse: '',
    role: '',
    auth: 'NOSASL',
    endpoint: '',
    region: 'us-east-1',
    access_key: '',
    secret_key: '',
    url_style: 'path',
    project: '',
    dataset: '',
    credentials_json: '',
  };
  glossaryContext = '';
  glossaryFilter = '';
  newRel: Relationship = { from_table: '', from_column: '', to_table: '', to_column: '', source: 'manual' };

  readonly isAdmin = this.auth.isAdmin();

  private id = '';

  readonly pendingCount = computed(() => this.glossary().filter((g) => g.status !== 'approved').length);

  readonly connectionEditable = computed(() => this.detail()?.db_type !== 'duckdb_files');

  readonly uploadedFiles = computed(() => {
    const files = this.detail()?.connection?.['files'];
    if (!files || typeof files !== 'object') return [];
    return Object.entries(files as Record<string, string>).map(([table, filename]) => ({ table, filename }));
  });

  readonly filteredGlossary = computed(() => {
    const f = this.glossaryFilter;
    return f ? this.glossary().filter((g) => g.table === f) : this.glossary();
  });

  ngOnInit(): void {
    this.id = this.route.snapshot.paramMap.get('id') ?? '';
    const tab = this.route.snapshot.queryParamMap.get('tab') as Tab | null;
    if (tab) this.activeTab.set(tab);
    this.load();
  }

  load(): void {
    this.http.get<DataSourceDetail>(`${API_BASE}/talk-to-data/sources/${this.id}`).subscribe({
      next: (d) => {
        this.detail.set(d);
        this.descDraft = d.description || '';
        this.nameDraft = d.name;
        this.initConnectionFromDetail(d);
        this.relationships.set([...d.relationships]);
        this.glossary.set(d.glossary.map((g) => ({ ...g, tags: [...g.tags] })));
        this.initScopeFromDetail(d);
      },
      error: (err) => this.message.set(err?.error?.detail ?? 'Failed to load datasource.'),
    });
  }

  // ── Connection ──
  initConnectionFromDetail(d: DataSourceDetail): void {
    const c = d.connection || {};
    this.conn = {
      host: String(c['host'] ?? ''),
      port: c['port'] != null ? Number(c['port']) : null,
      database: String(c['database'] ?? ''),
      user: String(c['user'] ?? ''),
      password: '',
      schema_name: String(c['schema'] ?? c['schema_name'] ?? ''),
      account: String(c['account'] ?? ''),
      warehouse: String(c['warehouse'] ?? ''),
      role: String(c['role'] ?? ''),
      auth: String(c['auth'] ?? 'NOSASL'),
      endpoint: String(c['endpoint'] ?? ''),
      region: String(c['region'] ?? 'us-east-1'),
      access_key: '',
      secret_key: '',
      url_style: String(c['url_style'] ?? 'path'),
      project: String(c['project'] ?? ''),
      dataset: String(c['dataset'] ?? ''),
      credentials_json: '',
    };

    const tableGlobs = c['table_globs'];
    if (tableGlobs && typeof tableGlobs === 'object') {
      this.connectionGlobs.set(
        Object.entries(tableGlobs as Record<string, string>).map(([table, pattern]) => ({ table, pattern })),
      );
    } else {
      this.connectionGlobs.set([{ table: '', pattern: '' }]);
    }
  }

  buildConnectionPayload(): Record<string, unknown> {
    const d = this.detail();
    if (!d) return {};

    const includeSecret = (key: keyof typeof this.conn, payload: Record<string, unknown>): void => {
      const value = this.conn[key];
      if (typeof value === 'string' && value.trim()) payload[key] = value.trim();
    };

    if (['postgres', 'mssql', 'oracle'].includes(d.db_type)) {
      const payload: Record<string, unknown> = {
        host: this.conn.host,
        port: Number(this.conn.port),
        database: this.conn.database,
        user: this.conn.user,
      };
      includeSecret('password', payload);
      if (this.conn.schema_name) payload['schema'] = this.conn.schema_name;
      return payload;
    }

    if (d.db_type === 'snowflake') {
      const payload: Record<string, unknown> = {
        account: this.conn.account,
        warehouse: this.conn.warehouse,
        database: this.conn.database,
        user: this.conn.user,
      };
      includeSecret('password', payload);
      if (this.conn.schema_name) payload['schema'] = this.conn.schema_name;
      if (this.conn.role) payload['role'] = this.conn.role;
      return payload;
    }

    if (d.db_type === 'hive') {
      const payload: Record<string, unknown> = {
        host: this.conn.host,
        port: Number(this.conn.port),
        database: this.conn.database,
        auth: this.conn.auth,
        user: this.conn.user,
      };
      includeSecret('password', payload);
      return payload;
    }

    if (d.db_type === 'bigquery') {
      const payload: Record<string, unknown> = {
        project: this.conn.project,
        dataset: this.conn.dataset,
      };
      includeSecret('credentials_json', payload);
      return payload;
    }

    if (d.db_type === 's3_object_store') {
      const tableGlobs: Record<string, string> = {};
      this.connectionGlobs().forEach((g) => {
        if (g.table.trim()) tableGlobs[g.table.trim()] = g.pattern;
      });
      const payload: Record<string, unknown> = {
        endpoint: this.conn.endpoint,
        region: this.conn.region,
        url_style: this.conn.url_style,
        table_globs: tableGlobs,
      };
      includeSecret('access_key', payload);
      includeSecret('secret_key', payload);
      return payload;
    }

    return {};
  }

  testConnectionDraft(): void {
    this.busy.set(true);
    this.message.set('');
    this.http.post<{ ok: boolean }>(`${API_BASE}/talk-to-data/sources/${this.id}/test`, {
      connection: this.buildConnectionPayload(),
    }).subscribe({
      next: () => {
        this.busy.set(false);
        this.message.set('✓ Connection successful.');
      },
      error: (err) => {
        this.busy.set(false);
        this.message.set(err?.error?.detail ?? 'Connection test failed.');
      },
    });
  }

  saveConnection(): void {
    if (!this.nameDraft.trim()) return;
    this.busy.set(true);
    this.message.set('');
    this.http.patch<DataSourceDetail>(`${API_BASE}/talk-to-data/sources/${this.id}`, {
      name: this.nameDraft.trim(),
      connection: this.buildConnectionPayload(),
    }).subscribe({
      next: () => {
        this.busy.set(false);
        this.message.set('✓ Connection saved.');
        this.load();
      },
      error: (err) => {
        this.busy.set(false);
        this.message.set(err?.error?.detail ?? 'Save connection failed.');
      },
    });
  }

  addConnectionGlob(): void {
    this.connectionGlobs.update((g) => [...g, { table: '', pattern: '' }]);
  }

  removeConnectionGlob(index: number): void {
    this.connectionGlobs.update((g) => g.filter((_, i) => i !== index));
  }

  updateConnectionGlob(index: number, field: 'table' | 'pattern', value: string): void {
    this.connectionGlobs.update((g) => g.map((item, i) => (i === index ? { ...item, [field]: value } : item)));
  }

  defaultPort(dbType: string): string {
    const ports: Record<string, number> = { postgres: 5432, mssql: 1433, oracle: 1521, hive: 10000 };
    return String(ports[dbType] ?? '');
  }

  // ── Overview ──
  saveDescription(): void {
    this.busy.set(true);
    this.http.patch<DataSourceDetail>(`${API_BASE}/talk-to-data/sources/${this.id}`, { description: this.descDraft }).subscribe({
      next: () => { this.busy.set(false); this.message.set('✓ Description saved.'); this.patchDetail({ description: this.descDraft }); },
      error: (err) => { this.busy.set(false); this.message.set(err?.error?.detail ?? 'Save failed.'); },
    });
  }

  generateDescription(): void {
    this.busy.set(true);
    this.message.set('');
    this.http.post<{ description: string }>(`${API_BASE}/talk-to-data/sources/${this.id}/description/generate`, { context: this.descContext }).subscribe({
      next: (res) => { this.busy.set(false); this.descDraft = res.description; this.message.set('✓ Draft generated — review and save.'); },
      error: (err) => { this.busy.set(false); this.message.set(err?.error?.detail ?? 'Generation failed.'); },
    });
  }

  // ── Tables ──
  refreshSchema(): void {
    this.busy.set(true);
    this.http.get<SchemaMetadata>(`${API_BASE}/talk-to-data/sources/${this.id}/schema?refresh=true`).subscribe({
      next: () => { this.busy.set(false); this.message.set('✓ Schema re-introspected.'); this.load(); },
      error: (err) => { this.busy.set(false); this.message.set(err?.error?.detail ?? 'Re-introspection failed.'); },
    });
  }

  initScopeFromDetail(d: DataSourceDetail): void {
    const stored = d.selected_scope?.tables ?? {};
    if (Object.keys(stored).length) {
      this.selectedScope.set({ ...stored });
      return;
    }
    const scope: Record<string, string[]> = {};
    for (const table of d.schema_metadata.tables) {
      scope[table.name] = table.columns.map((c) => c.name);
    }
    this.selectedScope.set(scope);
  }

  hasScopeSelection(): boolean {
    return Object.values(this.selectedScope()).some((cols) => cols.length > 0);
  }

  isTableFullyInScope(table: string): boolean {
    const selected = this.selectedScope()[table]?.length ?? 0;
    const total = this.detail()?.schema_metadata.tables.find((t) => t.name === table)?.columns.length ?? 0;
    return total > 0 && selected === total;
  }

  isTablePartiallyInScope(table: string): boolean {
    const selected = this.selectedScope()[table]?.length ?? 0;
    const total = this.detail()?.schema_metadata.tables.find((t) => t.name === table)?.columns.length ?? 0;
    return selected > 0 && selected < total;
  }

  onScopeTableCheckboxClick(table: string, event: MouseEvent): void {
    event.stopPropagation();
    const previewTable = this.detail()?.schema_metadata.tables.find((t) => t.name === table);
    if (!previewTable) return;

    const next = { ...this.selectedScope() };
    if (this.isTableFullyInScope(table)) {
      delete next[table];
    } else {
      next[table] = previewTable.columns.map((c) => c.name);
    }
    this.selectedScope.set(next);
  }

  isColumnInScope(table: string, column: string): boolean {
    return this.selectedScope()[table]?.includes(column) ?? false;
  }

  scopeColumnCount(table: string): number {
    return this.selectedScope()[table]?.length ?? 0;
  }

  toggleScopeColumn(table: string, column: string, checked: boolean): void {
    const next = { ...this.selectedScope() };
    const cols = new Set(next[table] ?? []);
    if (checked) cols.add(column);
    else cols.delete(column);
    if (cols.size) next[table] = [...cols];
    else delete next[table];
    this.selectedScope.set(next);
  }

  saveScope(): void {
    if (!this.hasScopeSelection()) return;
    this.busy.set(true);
    this.http.put<{ tables: Record<string, string[]> }>(`${API_BASE}/talk-to-data/sources/${this.id}/scope`, {
      selected_scope: { tables: this.selectedScope() },
    }).subscribe({
      next: (res) => {
        this.busy.set(false);
        this.selectedScope.set({ ...res.tables });
        this.message.set('✓ Scope saved.');
      },
      error: (err) => {
        this.busy.set(false);
        this.message.set(err?.error?.detail ?? 'Save scope failed.');
      },
    });
  }

  glossaryFor(table: string, column: string): GlossaryEntry | undefined {
    return this.glossary().find((g) => g.table === table && g.column === column);
  }

  // ── Relationships ──
  columnsOf(table: string): string[] {
    const d = this.detail();
    return d?.schema_metadata.tables.find((t) => t.name === table)?.columns.map((c) => c.name) ?? [];
  }

  canAddRel(): boolean {
    const r = this.newRel;
    return !!(r.from_table && r.from_column && r.to_table && r.to_column);
  }

  addRelationship(): void {
    if (!this.canAddRel()) return;
    this.relationships.update((rels) => [...rels, { ...this.newRel, source: 'manual' }]);
    this.newRel = { from_table: '', from_column: '', to_table: '', to_column: '', source: 'manual' };
  }

  removeRelationship(i: number): void {
    this.relationships.update((rels) => rels.filter((_, idx) => idx !== i));
  }

  saveRelationships(): void {
    this.busy.set(true);
    this.http.put<Relationship[]>(`${API_BASE}/talk-to-data/sources/${this.id}/relationships`, this.relationships()).subscribe({
      next: (res) => { this.busy.set(false); this.relationships.set(res); this.message.set('✓ Relationships saved.'); },
      error: (err) => { this.busy.set(false); this.message.set(err?.error?.detail ?? 'Save failed.'); },
    });
  }

  // ── Glossary ──
  setTags(entry: GlossaryEntry, value: string): void {
    entry.tags = value.split(',').map((t) => t.trim()).filter(Boolean);
  }

  saveGlossary(): void {
    this.busy.set(true);
    this.http.put<GlossaryEntry[]>(`${API_BASE}/talk-to-data/sources/${this.id}/glossary`, this.glossary()).subscribe({
      next: (res) => { this.busy.set(false); this.setGlossary(res); this.message.set('✓ Glossary saved.'); },
      error: (err) => { this.busy.set(false); this.message.set(err?.error?.detail ?? 'Save failed.'); },
    });
  }

  generateGlossary(): void {
    this.busy.set(true);
    this.message.set('');
    const tables = this.glossaryFilter ? [this.glossaryFilter] : [];
    this.http.post<GlossaryEntry[]>(`${API_BASE}/talk-to-data/sources/${this.id}/glossary/generate`, { tables, context: this.glossaryContext }).subscribe({
      next: (res) => { this.busy.set(false); this.setGlossary(res); this.message.set('✓ Glossary generated — review and approve.'); },
      error: (err) => { this.busy.set(false); this.message.set(err?.error?.detail ?? 'Generation failed.'); },
    });
  }

  onGlossaryFile(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0];
    if (!file) return;
    const fd = new FormData();
    fd.append('file', file);
    this.busy.set(true);
    this.http.post<GlossaryEntry[]>(`${API_BASE}/talk-to-data/sources/${this.id}/glossary/upload`, fd).subscribe({
      next: (res) => { this.busy.set(false); this.setGlossary(res); this.message.set('✓ Glossary uploaded.'); input.value = ''; },
      error: (err) => { this.busy.set(false); this.message.set(err?.error?.detail ?? 'Upload failed.'); input.value = ''; },
    });
  }

  // ── Approval ──
  tablesWithGlossary(): string[] {
    return [...new Set(this.glossary().map((g) => g.table))].sort();
  }
  glossaryForTable(table: string): GlossaryEntry[] {
    return this.glossary().filter((g) => g.table === table);
  }
  countFor(table: string): number { return this.glossaryForTable(table).length; }
  approvedCountFor(table: string): number { return this.glossaryForTable(table).filter((g) => g.status === 'approved').length; }

  approveOne(g: GlossaryEntry): void { this.approve({ ids: [g.id] }); }
  approveTable(table: string): void { this.approve({ table }); }
  approveAll(): void { this.approve({ all: true }); }

  private approve(body: { ids?: string[]; table?: string; all?: boolean }): void {
    this.busy.set(true);
    this.http.post<GlossaryEntry[]>(`${API_BASE}/talk-to-data/sources/${this.id}/glossary/approve`, body).subscribe({
      next: (res) => { this.busy.set(false); this.setGlossary(res); this.message.set('✓ Approved.'); },
      error: (err) => { this.busy.set(false); this.message.set(err?.error?.detail ?? 'Approval failed.'); },
    });
  }

  talkToIt(): void {
    this.router.navigate(['/talk-to-data'], { queryParams: { source: this.id } });
  }

  iconFor(t: string): string {
    const icons: Record<string, string> = {
      postgres: '🐘', mssql: '🪟', oracle: '🔴', snowflake: '❄️',
      hive: '🐝', bigquery: '☁️', s3_object_store: '🪣', duckdb_files: '📂',
    };
    return icons[t] ?? '🗄';
  }

  statusLabel(s: string): string {
    return s === 'partially_approved' ? 'partially approved' : s;
  }

  private setGlossary(entries: GlossaryEntry[]): void {
    this.glossary.set(entries.map((g) => ({ ...g, tags: [...(g.tags || [])] })));
    const d = this.detail();
    if (d) this.detail.set({ ...d, metadata_status: this.rollup(entries) });
  }

  private rollup(entries: GlossaryEntry[]): string {
    if (!entries.length) return 'draft';
    const statuses = new Set(entries.map((e) => e.status));
    if (statuses.size === 1 && statuses.has('approved')) return 'approved';
    if (statuses.has('approved')) return 'partially_approved';
    return 'draft';
  }

  private patchDetail(patch: Partial<DataSourceDetail>): void {
    const d = this.detail();
    if (d) this.detail.set({ ...d, ...patch });
  }
}
