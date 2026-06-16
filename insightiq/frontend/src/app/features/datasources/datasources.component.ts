import { HttpClient } from '@angular/common/http';
import { Component, OnInit, inject, signal } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';

import { API_BASE } from '../../core/api.config';

type DataSource = {
  id: string;
  name: string;
  db_type: string;
  dialect: string;
  description?: string;
  metadata_status?: string;
  created_at?: string;
};

type ConnectorType = {
  key: string;
  label: string;
  icon: string;
  dialect: string;
  description: string;
  supported: boolean;
};

const CONNECTORS: ConnectorType[] = [
  { key: 'postgres',       label: 'PostgreSQL',    icon: '🐘', dialect: 'postgres',  description: 'PostgreSQL via asyncpg', supported: true },
  { key: 's3_object_store',label: 'S3 / MinIO',    icon: '🪣', dialect: 'duckdb',    description: 'Parquet/CSV on S3 or MinIO via DuckDB httpfs', supported: true },
  { key: 'duckdb_files',   label: 'File Upload',   icon: '📂', dialect: 'duckdb',    description: 'Upload a CSV / Parquet file and query it directly', supported: true },
  { key: 'mssql',          label: 'SQL Server',    icon: '🪟', dialect: 'mssql',     description: 'Microsoft SQL Server / Azure SQL', supported: true },
  { key: 'oracle',         label: 'Oracle',        icon: '🔴', dialect: 'oracle',    description: 'Oracle DB via python-oracledb', supported: true },
  { key: 'snowflake',      label: 'Snowflake',     icon: '❄️', dialect: 'snowflake', description: 'Snowflake data warehouse', supported: true },
  { key: 'hive',           label: 'Hive / Impala', icon: '🐝', dialect: 'hiveql',    description: 'HiveServer2 via Thrift', supported: true },
  { key: 'bigquery',       label: 'BigQuery',      icon: '☁️', dialect: 'bigquery',  description: 'Google BigQuery', supported: true },
];

const DB_COLORS: Record<string, string> = {
  postgres: '#336791', mssql: '#cc2927', oracle: '#f80000', snowflake: '#29b5e8',
  hive: '#f9a825', bigquery: '#4285f4', s3_object_store: '#ff9900', duckdb_files: '#ffd43b',
};

@Component({
  standalone: true,
  imports: [ReactiveFormsModule],
  template: `
    <div class="page">
      <div class="page-header">
        <div>
          <h1>Datasources</h1>
          <p>Register and manage connections to databases, warehouses, and object stores.</p>
        </div>
        @if (!showForm()) {
          <button class="btn-primary" (click)="showForm.set(true)">+ Add datasource</button>
        }
      </div>

      <!-- ── Registration form ── -->
      @if (showForm()) {
        <div class="panel">
          <div class="panel-header">
            <h2>New datasource</h2>
            <button class="btn-ghost" (click)="cancelForm()">✕ Cancel</button>
          </div>

          <!-- Connector type picker -->
          @if (!selectedConnector()) {
            <div class="connector-grid">
              @for (c of connectors; track c.key) {
                <button
                  class="connector-card"
                  [class.disabled]="!c.supported"
                  [disabled]="!c.supported"
                  [title]="c.supported ? '' : 'Connector coming soon'"
                  (click)="selectConnector(c)"
                >
                  @if (!c.supported) {
                    <span class="soon-badge">Soon</span>
                  }
                  <span class="connector-icon">{{ c.icon }}</span>
                  <strong>{{ c.label }}</strong>
                  <span class="connector-desc">{{ c.description }}</span>
                </button>
              }
            </div>
          } @else {
            <div class="selected-connector">
              <span class="connector-icon">{{ selectedConnector()!.icon }}</span>
              <strong>{{ selectedConnector()!.label }}</strong>
              <button class="btn-ghost small" (click)="selectedConnector.set(null)">Change</button>
            </div>

            <form [formGroup]="form" (ngSubmit)="register()">
              <div class="form-row">
                <label>
                  <span>Source name *</span>
                  <input formControlName="name" placeholder="e.g. Production DB" />
                </label>
              </div>
              <div class="form-row">
                <label class="full">
                  <span>Purpose / description (optional)</span>
                  <input formControlName="description" placeholder="What is this datasource used for? You can refine it with AI later." />
                </label>
              </div>

              <!-- ── PostgreSQL / MSSQL / Oracle ── -->
              @if (['postgres','mssql','oracle'].includes(selectedConnector()!.key)) {
                <div class="form-grid">
                  <label>
                    <span>Host *</span>
                    <input formControlName="host" placeholder="localhost" />
                  </label>
                  <label>
                    <span>Port *</span>
                    <input formControlName="port" type="number" [placeholder]="defaultPort()" />
                  </label>
                  <label>
                    <span>{{ selectedConnector()!.key === 'oracle' ? 'Service name' : 'Database' }} *</span>
                    <input formControlName="database" [placeholder]="selectedConnector()!.key === 'oracle' ? 'ORCL' : 'mydb'" />
                  </label>
                  <label>
                    <span>Username *</span>
                    <input formControlName="user" placeholder="readonly_user" />
                  </label>
                  <label>
                    <span>Password *</span>
                    <input formControlName="password" type="password" placeholder="••••••••" />
                  </label>
                  @if (selectedConnector()!.key === 'mssql') {
                    <label>
                      <span>Schema (optional)</span>
                      <input formControlName="schema_name" placeholder="dbo" />
                    </label>
                  }
                </div>
              }

              <!-- ── Snowflake ── -->
              @if (selectedConnector()!.key === 'snowflake') {
                <div class="form-grid">
                  <label>
                    <span>Account *</span>
                    <input formControlName="account" placeholder="org-account123" />
                  </label>
                  <label>
                    <span>Warehouse *</span>
                    <input formControlName="warehouse" placeholder="COMPUTE_WH" />
                  </label>
                  <label>
                    <span>Database *</span>
                    <input formControlName="database" placeholder="PROD_DB" />
                  </label>
                  <label>
                    <span>Schema (optional)</span>
                    <input formControlName="schema_name" placeholder="PUBLIC" />
                  </label>
                  <label>
                    <span>Username *</span>
                    <input formControlName="user" placeholder="analyst" />
                  </label>
                  <label>
                    <span>Password *</span>
                    <input formControlName="password" type="password" placeholder="••••••••" />
                  </label>
                  <label>
                    <span>Role (optional)</span>
                    <input formControlName="role" placeholder="ANALYST" />
                  </label>
                </div>
              }

              <!-- ── Hive ── -->
              @if (selectedConnector()!.key === 'hive') {
                <div class="form-grid">
                  <label>
                    <span>Host *</span>
                    <input formControlName="host" placeholder="hiveserver2.company.com" />
                  </label>
                  <label>
                    <span>Port *</span>
                    <input formControlName="port" type="number" placeholder="10000" />
                  </label>
                  <label>
                    <span>Database *</span>
                    <input formControlName="database" placeholder="default" />
                  </label>
                  <label>
                    <span>Auth method *</span>
                    <select formControlName="auth">
                      <option value="NOSASL">NOSASL</option>
                      <option value="LDAP">LDAP</option>
                      <option value="KERBEROS">Kerberos</option>
                    </select>
                  </label>
                  <label>
                    <span>Username</span>
                    <input formControlName="user" placeholder="hive" />
                  </label>
                  <label>
                    <span>Password</span>
                    <input formControlName="password" type="password" placeholder="••••••••" />
                  </label>
                </div>
              }

              <!-- ── BigQuery ── -->
              @if (selectedConnector()!.key === 'bigquery') {
                <div class="form-grid">
                  <label>
                    <span>GCP Project *</span>
                    <input formControlName="project" placeholder="my-gcp-project" />
                  </label>
                  <label>
                    <span>Dataset *</span>
                    <input formControlName="dataset" placeholder="analytics" />
                  </label>
                  <label class="full">
                    <span>Service account JSON (paste) *</span>
                    <textarea formControlName="credentials_json" rows="5" placeholder='{"type":"service_account",...}'></textarea>
                  </label>
                </div>
              }

              <!-- ── S3 / MinIO ── -->
              @if (selectedConnector()!.key === 's3_object_store') {
                <div class="form-grid">
                  <label>
                    <span>Endpoint (MinIO) or leave blank for AWS *</span>
                    <input formControlName="endpoint" placeholder="localhost:9000" />
                  </label>
                  <label>
                    <span>Region</span>
                    <input formControlName="region" placeholder="us-east-1" />
                  </label>
                  <label>
                    <span>Access key *</span>
                    <input formControlName="access_key" placeholder="minio" />
                  </label>
                  <label>
                    <span>Secret key *</span>
                    <input formControlName="secret_key" type="password" placeholder="••••••••" />
                  </label>
                  <label>
                    <span>URL style</span>
                    <select formControlName="url_style">
                      <option value="path">Path (MinIO)</option>
                      <option value="virtual-hosted">Virtual-hosted (AWS)</option>
                    </select>
                  </label>
                </div>
                <div class="table-globs">
                  <div class="section-label">File globs <span class="hint">(logical table → S3 glob pattern)</span></div>
                  @for (glob of globs(); track $index) {
                    <div class="glob-row">
                      <input [value]="glob.table" (input)="updateGlob($index, 'table', $any($event.target).value)" placeholder="sales" />
                      <span>→</span>
                      <input [value]="glob.pattern" (input)="updateGlob($index, 'pattern', $any($event.target).value)" placeholder="s3://bucket/sales/year=*/*.parquet" />
                      <button type="button" class="btn-ghost small" (click)="removeGlob($index)">✕</button>
                    </div>
                  }
                  <button type="button" class="btn-ghost small" (click)="addGlob()">+ Add file glob</button>
                </div>
              }

              <!-- ── File upload (DuckDB) ── -->
              @if (selectedConnector()!.key === 'duckdb_files') {
                <div class="form-grid">
                  <label>
                    <span>Table name *</span>
                    <input formControlName="table_name_single" placeholder="sales" />
                  </label>
                  <label class="full">
                    <span>CSV or Parquet file *</span>
                    <div class="file-drop" [class.has-file]="uploadFile()">
                      <input type="file" accept=".csv,.parquet,.pq" (change)="onFilePicked($event)" />
                      <span class="file-drop-icon">📁</span>
                      <span>{{ uploadFile() ? uploadFile()!.name : 'Choose a .csv or .parquet file' }}</span>
                    </div>
                  </label>
                </div>
              }

              @if (statusMessage()) {
                <div [class]="statusMessage().startsWith('✓') ? 'msg-ok' : 'msg-err'">{{ statusMessage() }}</div>
              }

              <div class="form-actions">
                <button type="submit" class="btn-primary" [disabled]="!canSubmit() || saving()">
                  {{ saving() ? 'Registering…' : 'Register datasource' }}
                </button>
              </div>
            </form>
          }
        </div>
      }

      <!-- ── Datasource list ── -->
      @if (sources().length === 0 && !showForm()) {
        <div class="empty">
          <div class="empty-icon">🗄</div>
          <p>No datasources yet. Click <strong>+ Add datasource</strong> to connect your first database.</p>
        </div>
      }

      <div class="source-list">
        @for (ds of sources(); track ds.id) {
          <div class="source-card" (click)="manage(ds.id)">
            <div class="source-badge" [style.background]="typeColor(ds.db_type)">
              {{ typeIcon(ds.db_type) }}
            </div>
            <div class="source-info">
              <div class="source-name-row">
                <span class="source-name">{{ ds.name }}</span>
                <span class="status-pill" [attr.data-status]="ds.metadata_status || 'draft'">{{ statusLabel(ds.metadata_status) }}</span>
              </div>
              <div class="source-meta">{{ typeLabel(ds.db_type) }} · dialect: {{ ds.dialect }}</div>
              @if (ds.description) {
                <div class="source-desc">{{ ds.description }}</div>
              }
            </div>
            <div class="source-actions" (click)="$event.stopPropagation()">
              <button class="btn-ghost small" (click)="manage(ds.id)">Manage</button>
              <button class="btn-ghost small" (click)="talkTo(ds.id)">Talk to it</button>
              <button class="btn-ghost small" (click)="testConnection(ds.id)">Test</button>
              <button class="btn-danger small" (click)="deleteSource(ds.id)">Delete</button>
            </div>
          </div>
        }
      </div>
    </div>
  `,
  styles: [`
    .page { max-width: 960px; }

    /* buttons */
    .btn-primary {
      display: inline-flex; align-items: center; gap: 6px;
      padding: 9px 16px; border-radius: var(--radius-md); border: none;
      background: var(--primary); color: var(--on-primary); font-size: var(--text-base);
      font-weight: 550; cursor: pointer; font-family: inherit;
      transition: background var(--dur-fast) var(--ease);
    }
    .btn-primary:hover:not(:disabled) { background: var(--primary-hover); }
    .btn-primary:disabled { opacity: 0.5; cursor: default; }
    .btn-ghost {
      padding: 7px 12px; border-radius: var(--radius-md);
      border: 1px solid var(--border-strong);
      background: transparent; color: var(--text-2); cursor: pointer; font-size: var(--text-sm);
      font-family: inherit; transition: all var(--dur-fast) var(--ease);
    }
    .btn-ghost:hover { background: var(--surface-2); color: var(--text); }
    .btn-ghost.small { padding: 4px 9px; font-size: var(--text-xs); }
    .btn-danger {
      padding: 4px 9px; border-radius: var(--radius-md); font-size: var(--text-xs);
      border: 1px solid var(--danger-soft); background: transparent;
      color: var(--danger); cursor: pointer; font-family: inherit;
      transition: background var(--dur-fast) var(--ease);
    }
    .btn-danger:hover { background: var(--danger-soft); }

    /* connector picker */
    .connector-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(168px, 1fr));
      gap: 12px;
      margin-top: 4px;
    }
    .connector-card {
      position: relative;
      display: flex; flex-direction: column; align-items: center; gap: 7px;
      padding: 20px 14px;
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      background: var(--surface-2);
      cursor: pointer; text-align: center; color: inherit;
      transition: border-color var(--dur-fast) var(--ease), background var(--dur-fast) var(--ease), transform var(--dur-fast) var(--ease);
    }
    .connector-card:hover:not(.disabled) { border-color: var(--primary); background: var(--primary-soft); transform: translateY(-2px); }
    .connector-card.disabled { opacity: 0.45; cursor: not-allowed; }
    .connector-card strong { font-size: var(--text-base); }
    .connector-icon { font-size: 28px; }
    .connector-desc { font-size: var(--text-xs); color: var(--text-muted); }
    .soon-badge {
      position: absolute; top: 8px; right: 8px;
      font-size: 9px; font-weight: 700; letter-spacing: 0.04em;
      padding: 2px 7px; border-radius: var(--radius-pill);
      background: var(--warning-soft); color: var(--warning); text-transform: uppercase;
    }

    /* file drop */
    .file-drop {
      position: relative;
      display: flex; align-items: center; gap: 10px;
      padding: 16px; border: 1.5px dashed var(--border-strong);
      border-radius: var(--radius-md); color: var(--text-2); cursor: pointer;
      transition: border-color var(--dur-fast) var(--ease), background var(--dur-fast) var(--ease);
    }
    .file-drop:hover { border-color: var(--primary); }
    .file-drop.has-file { border-color: var(--success); color: var(--text); }
    .file-drop-icon { font-size: 20px; }
    .file-drop input[type=file] { position: absolute; inset: 0; opacity: 0; cursor: pointer; }

    /* panel */
    .panel {
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-lg);
      padding: var(--space-6);
      margin-bottom: var(--space-8);
      box-shadow: var(--shadow-sm);
    }
    .panel-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: var(--space-5); }
    .panel-header h2 { margin: 0; font-size: var(--text-lg); }

    .selected-connector {
      display: flex; align-items: center; gap: 10px;
      padding: 10px 14px;
      background: var(--primary-soft);
      border: 1px solid var(--primary-soft-2);
      border-radius: var(--radius-md);
      margin-bottom: var(--space-5);
    }
    .selected-connector .btn-ghost { margin-left: auto; }

    /* form */
    form { display: flex; flex-direction: column; gap: var(--space-5); }
    .form-row { display: flex; gap: 12px; }
    .form-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(210px, 1fr));
      gap: 14px;
    }
    label { display: flex; flex-direction: column; gap: 6px; font-size: var(--text-xs); color: var(--text-2); font-weight: 550; }
    label.full { grid-column: 1 / -1; }
    input, select, textarea {
      padding: 9px 12px;
      border-radius: var(--radius-md);
      border: 1px solid var(--border-strong);
      background: var(--input-bg);
      color: var(--text);
      font-size: var(--text-base);
      font-family: inherit;
      transition: border-color var(--dur-fast) var(--ease), box-shadow var(--dur-fast) var(--ease);
    }
    input:focus, select:focus, textarea:focus { outline: none; border-color: var(--border-focus); box-shadow: 0 0 0 3px var(--primary-soft); }
    textarea { resize: vertical; font-family: var(--font-mono); font-size: var(--text-sm); }

    .section-label { font-size: var(--text-sm); color: var(--text-2); margin-bottom: 8px; font-weight: 550; }
    .hint { color: var(--text-muted); font-weight: 400; }
    .table-globs { display: flex; flex-direction: column; gap: 8px; }
    .glob-row { display: flex; align-items: center; gap: 8px; }
    .glob-row input { flex: 1; }
    .glob-row span { color: var(--text-muted); }

    .form-actions { display: flex; gap: 10px; }
    .info { font-size: var(--text-sm); color: var(--text-2); padding: 14px; background: var(--surface-2); border-radius: var(--radius-md); }
    .msg-ok  { color: var(--success); font-size: var(--text-sm); }
    .msg-err { color: var(--danger); font-size: var(--text-sm); }

    /* empty state */
    .empty {
      text-align: center; padding: var(--space-12) var(--space-6);
      border: 1px dashed var(--border-strong);
      border-radius: var(--radius-lg);
      color: var(--text-2);
    }
    .empty-icon { font-size: 42px; margin-bottom: 12px; }
    .empty strong { color: var(--text); }

    /* source cards */
    .source-list { display: flex; flex-direction: column; gap: 10px; }
    .source-card {
      display: flex; align-items: center; gap: 16px;
      padding: 14px 18px;
      background: var(--surface);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
      box-shadow: var(--shadow-sm);
      transition: border-color var(--dur-fast) var(--ease);
    }
    .source-card { cursor: pointer; }
    .source-card:hover { border-color: var(--border-strong); }
    .source-badge {
      width: 42px; height: 42px; border-radius: var(--radius-md);
      display: grid; place-items: center; font-size: 20px; flex-shrink: 0;
      background: var(--surface-3);
    }
    .source-info { flex: 1; min-width: 0; }
    .source-name-row { display: flex; align-items: center; gap: 10px; }
    .source-name { font-size: var(--text-md); font-weight: 600; }
    .source-meta { font-size: var(--text-xs); color: var(--text-muted); margin-top: 2px; }
    .source-desc { font-size: var(--text-sm); color: var(--text-2); margin-top: 5px; overflow: hidden; text-overflow: ellipsis; display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; }
    .source-actions { display: flex; gap: 8px; flex-shrink: 0; }
    .status-pill {
      font-size: 10px; font-weight: 650; padding: 2px 9px; border-radius: var(--radius-pill);
      background: var(--surface-3); color: var(--text-2); text-transform: capitalize;
    }
    .status-pill[data-status='approved'] { background: var(--success-soft); color: var(--success); }
    .status-pill[data-status='partially_approved'] { background: var(--warning-soft); color: var(--warning); }
  `],
})
export class DatasourcesComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly fb = inject(FormBuilder);
  private readonly router = inject(Router);

  readonly connectors = CONNECTORS;
  readonly sources = signal<DataSource[]>([]);
  readonly showForm = signal(false);
  readonly selectedConnector = signal<ConnectorType | null>(null);
  readonly saving = signal(false);
  readonly statusMessage = signal('');
  readonly globs = signal<{ table: string; pattern: string }[]>([
    { table: 'sales', pattern: 's3://bucket/sales/*.parquet' },
  ]);

  readonly uploadFile = signal<File | null>(null);

  readonly form = this.fb.group({
    name:              ['', Validators.required],
    description:       [''],
    table_name_single: ['data'],
    host:             [''],
    port:             [null as number | null],
    database:         [''],
    user:             [''],
    password:         [''],
    schema_name:      [''],
    account:          [''],
    warehouse:        [''],
    role:             [''],
    auth:             ['NOSASL'],
    endpoint:         [''],
    region:           ['us-east-1'],
    access_key:       [''],
    secret_key:       [''],
    url_style:        ['path'],
    project:          [''],
    dataset:          [''],
    credentials_json: [''],
  });

  ngOnInit(): void { this.loadSources(); }

  loadSources(): void {
    this.http.get<DataSource[]>(`${API_BASE}/talk-to-data/sources`).subscribe({
      next: (s) => this.sources.set(s),
    });
  }

  selectConnector(c: ConnectorType): void {
    if (!c.supported) return;
    this.selectedConnector.set(c);
    this.statusMessage.set('');
    this.uploadFile.set(null);
    this.form.patchValue({ port: this.defaultPort(c.key) as unknown as number });
  }

  cancelForm(): void {
    this.showForm.set(false);
    this.selectedConnector.set(null);
    this.uploadFile.set(null);
    this.form.reset({ url_style: 'path', region: 'us-east-1', auth: 'NOSASL', table_name_single: 'data', description: '' });
    this.statusMessage.set('');
    this.globs.set([{ table: 'sales', pattern: 's3://bucket/sales/*.parquet' }]);
  }

  onFilePicked(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.uploadFile.set(input.files?.[0] ?? null);
  }

  canSubmit(): boolean {
    const name = this.form.getRawValue().name;
    if (!name) return false;
    if (this.selectedConnector()?.key === 'duckdb_files') {
      return !!this.uploadFile();
    }
    return true;
  }

  register(): void {
    const c = this.selectedConnector();
    if (!c || !this.canSubmit()) return;

    if (c.key === 'duckdb_files') {
      this.uploadFileSource();
      return;
    }

    const v = this.form.getRawValue();
    let connection: Record<string, unknown> = {};

    if (['postgres', 'mssql', 'oracle'].includes(c.key)) {
      connection = { host: v.host, port: Number(v.port), database: v.database, user: v.user, password: v.password };
      if (v.schema_name) connection['schema'] = v.schema_name;
    } else if (c.key === 'snowflake') {
      connection = { account: v.account, warehouse: v.warehouse, database: v.database, user: v.user, password: v.password };
      if (v.schema_name) connection['schema'] = v.schema_name;
      if (v.role) connection['role'] = v.role;
    } else if (c.key === 'hive') {
      connection = { host: v.host, port: Number(v.port), database: v.database, auth: v.auth, user: v.user, password: v.password };
    } else if (c.key === 'bigquery') {
      connection = { project: v.project, dataset: v.dataset, credentials_json: v.credentials_json };
    } else if (c.key === 's3_object_store') {
      const tableGlobs: Record<string, string> = {};
      this.globs().forEach((g) => { if (g.table) tableGlobs[g.table] = g.pattern; });
      connection = { endpoint: v.endpoint, region: v.region, access_key: v.access_key, secret_key: v.secret_key, url_style: v.url_style, table_globs: tableGlobs };
    }

    this.saving.set(true);
    this.statusMessage.set('');
    this.http.post<DataSource>(`${API_BASE}/talk-to-data/sources`, {
      name: v.name,
      db_type: c.key,
      connection,
      description: v.description || '',
    }).subscribe({
      next: (ds) => {
        this.saving.set(false);
        this.statusMessage.set('✓ Datasource registered successfully.');
        this.openWizard(ds);
      },
      error: (err: { error?: { detail?: string } }) => {
        this.saving.set(false);
        this.statusMessage.set(err?.error?.detail ?? 'Registration failed. Check connection details.');
      },
    });
  }

  private uploadFileSource(): void {
    const file = this.uploadFile();
    const v = this.form.getRawValue();
    if (!file) return;

    const fd = new FormData();
    fd.append('name', v.name!);
    fd.append('table_name', v.table_name_single || 'data');
    fd.append('description', v.description || '');
    fd.append('file', file);

    this.saving.set(true);
    this.statusMessage.set('');
    this.http.post<DataSource>(`${API_BASE}/talk-to-data/sources/upload`, fd).subscribe({
      next: (ds) => {
        this.saving.set(false);
        this.statusMessage.set('✓ File uploaded and datasource created.');
        this.openWizard(ds);
      },
      error: (err: { error?: { detail?: string } }) => {
        this.saving.set(false);
        this.statusMessage.set(err?.error?.detail ?? 'Upload failed. Check the file format.');
      },
    });
  }

  private openWizard(ds: DataSource): void {
    setTimeout(() => {
      this.cancelForm();
      this.router.navigate(['/datasources', ds.id]);
    }, 700);
  }

  manage(id: string): void {
    this.router.navigate(['/datasources', id]);
  }

  talkTo(id: string): void {
    this.router.navigate(['/talk-to-data'], { queryParams: { source: id } });
  }

  testConnection(id: string): void {
    this.http.post(`${API_BASE}/talk-to-data/sources/${id}/test`, {}).subscribe({
      next: () => alert('Connection OK'),
      error: (err: { error?: { detail?: string } }) => alert(err?.error?.detail ?? 'Connection failed'),
    });
  }

  deleteSource(id: string): void {
    if (!confirm('Remove this datasource? This cannot be undone.')) return;
    this.http.delete(`${API_BASE}/talk-to-data/sources/${id}`).subscribe({
      next: () => this.loadSources(),
      error: (err: { error?: { detail?: string } }) => alert(err?.error?.detail ?? 'Delete failed'),
    });
  }

  addGlob(): void    { this.globs.update((g) => [...g, { table: '', pattern: '' }]); }
  removeGlob(i: number): void { this.globs.update((g) => g.filter((_, idx) => idx !== i)); }
  updateGlob(i: number, field: 'table' | 'pattern', value: string): void {
    this.globs.update((g) => g.map((item, idx) => idx === i ? { ...item, [field]: value } : item));
  }

  statusLabel(s?: string): string {
    if (s === 'partially_approved') return 'partial';
    return s || 'draft';
  }

  typeColor(t: string): string { return DB_COLORS[t] ? DB_COLORS[t] + '33' : 'rgba(255,255,255,0.08)'; }
  typeIcon(t: string): string { return CONNECTORS.find((c) => c.key === t)?.icon ?? '🗄'; }
  typeLabel(t: string): string { return CONNECTORS.find((c) => c.key === t)?.label ?? t; }

  defaultPort(type?: string): number | string {
    const t = type ?? this.selectedConnector()?.key ?? '';
    const ports: Record<string, number> = { postgres: 5432, mssql: 1433, oracle: 1521, hive: 10000 };
    return ports[t] ?? '';
  }
}
