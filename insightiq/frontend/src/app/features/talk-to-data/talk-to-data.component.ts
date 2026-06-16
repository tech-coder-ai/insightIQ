import { HttpClient } from '@angular/common/http';
import { Component, OnInit, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';

import { DashboardService } from '../../core/dashboard.service';
import { API_BASE } from '../../core/api.config';
import { AuthService } from '../../core/auth.service';
import { ChatSidebarComponent } from '../../shared/chat-sidebar.component';
import { ResponseRendererComponent } from '../../shared/response-renderer.component';
import { SchemaTreeComponent } from '../../shared/schema-tree.component';

type DataSource = { id: string; name: string; db_type: string; dialect: string };
type Schema = { tables: { name: string; columns: { name: string; data_type: string }[] }[] };
type ResponsePayload = { response_type: string; title?: string; data: Record<string, unknown> };
type AskResponse = { conversation_id: string; sql: string; response: ResponsePayload };

@Component({
  standalone: true,
  imports: [
    ReactiveFormsModule,
    ChatSidebarComponent,
    SchemaTreeComponent,
    ResponseRendererComponent,
  ],
  template: `
    <div class="layout">
      <app-chat-sidebar [activeId]="conversationId" (select)="onSelectConversation($event)" />

      <div class="main">
        <header>
          <div>
            <h1>Talk to Data</h1>
            <p>Postgres, S3/MinIO (DuckDB), schema introspection, and dynamic responses</p>
          </div>
          <button type="button" (click)="logout()">Logout</button>
        </header>

        <div class="tabs">
          <button [class.active]="sourceTab === 'postgres'" (click)="sourceTab = 'postgres'">Postgres</button>
          <button [class.active]="sourceTab === 's3'" (click)="sourceTab = 's3'">S3 / MinIO</button>
        </div>

        <section class="card">
          <h2>Register datasource</h2>
          @if (sourceTab === 'postgres') {
            <form class="grid" [formGroup]="pgForm" (ngSubmit)="registerPostgres()">
              <input formControlName="name" placeholder="Source name" />
              <input formControlName="host" placeholder="Host" />
              <input formControlName="port" type="number" placeholder="Port" />
              <input formControlName="database" placeholder="Database" />
              <input formControlName="user" placeholder="User" />
              <input formControlName="password" type="password" placeholder="Password" />
              <button type="submit" class="primary">Register Postgres</button>
            </form>
          } @else {
            <form class="grid" [formGroup]="s3Form" (ngSubmit)="registerS3()">
              <input formControlName="name" placeholder="Source name" />
              <input formControlName="endpoint" placeholder="Endpoint (localhost:9000)" />
              <input formControlName="region" placeholder="Region" />
              <input formControlName="access_key" placeholder="Access key" />
              <input formControlName="secret_key" type="password" placeholder="Secret key" />
              <input formControlName="table_name" placeholder="Logical table name" />
              <input formControlName="glob" placeholder="s3://bucket/path/*.parquet" />
              <button type="submit" class="primary">Register S3</button>
            </form>
          }
          @if (statusMessage) {
            <p class="msg">{{ statusMessage }}</p>
          }
        </section>

        <div class="split">
          <section class="card">
            <div class="row-head">
              <h2>Schema</h2>
              <button type="button" (click)="loadSchema()" [disabled]="!selectedSourceId">Refresh</button>
              <button type="button" (click)="generateGlossary()" [disabled]="!selectedSourceId">
                Generate glossary
              </button>
            </div>
            <app-schema-tree [schema]="schema" />
          </section>

          <section class="card">
            <h2>Ask a question</h2>
            <form class="ask" [formGroup]="askForm" (ngSubmit)="ask()">
              <select formControlName="datasourceId" (change)="onSourceChange()">
                <option value="">Select datasource</option>
                @for (ds of sources; track ds.id) {
                  <option [value]="ds.id">{{ ds.name }} ({{ ds.db_type }})</option>
                }
              </select>
              <input formControlName="question" placeholder="e.g. revenue by region chart" />
              <button type="submit" class="primary" [disabled]="askForm.invalid">Ask</button>
            </form>

            @if (lastSql) {
              <pre class="sql">{{ lastSql }}</pre>
            }
            <app-response-renderer [payload]="lastResponse" />
            @if (lastResponse) {
              <button type="button" class="pin" (click)="pinToDashboard()">Pin to dashboard</button>
            }
          </section>
        </div>
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
      h1,
      h2 {
        margin: 0;
      }
      p {
        margin: 4px 0 0;
        opacity: 0.75;
      }
      .tabs {
        display: flex;
        gap: 8px;
      }
      .tabs button.active {
        background: rgba(88, 166, 255, 0.25);
      }
      .card {
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        padding: 20px;
        background: rgba(255, 255, 255, 0.03);
        display: grid;
        gap: 12px;
      }
      .split {
        display: grid;
        grid-template-columns: 1fr 2fr;
        gap: 16px;
      }
      .grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(140px, 1fr));
        gap: 10px;
      }
      .ask {
        display: grid;
        grid-template-columns: 1fr 2fr auto;
        gap: 10px;
      }
      .row-head {
        display: flex;
        gap: 8px;
        align-items: center;
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
      button {
        cursor: pointer;
      }
      .primary {
        background: rgba(88, 166, 255, 0.25);
      }
      .sql {
        padding: 12px;
        border-radius: 10px;
        background: rgba(0, 0, 0, 0.35);
        overflow: auto;
        font-size: 12px;
      }
      .msg {
        font-size: 13px;
      }
      .pin {
        margin-top: 12px;
        padding: 8px 12px;
        border-radius: 8px;
        border: 1px solid rgba(255, 255, 255, 0.12);
        background: rgba(88, 166, 255, 0.2);
        color: inherit;
        cursor: pointer;
      }
        .layout {
          flex-direction: column;
        }
        .split {
          grid-template-columns: 1fr;
        }
        .ask {
          grid-template-columns: 1fr;
        }
      }
    `,
  ],
})
export class TalkToDataComponent implements OnInit {
  private readonly dashboardService = inject(DashboardService);
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);

  sources: DataSource[] = [];
  schema: Schema | null = null;
  statusMessage = '';
  lastSql = '';
  lastResponse: ResponsePayload | null = null;
  lastAskMeta: { sql: string; datasourceId: string; question: string } | null = null;
  conversationId: string | null = null;
  selectedSourceId = '';
  sourceTab: 'postgres' | 's3' = 'postgres';

  readonly pgForm = this.fb.group({
    name: ['Local Postgres', Validators.required],
    host: ['localhost', Validators.required],
    port: [5432, Validators.required],
    database: ['insightiq', Validators.required],
    user: ['insightiq', Validators.required],
    password: ['insightiq', Validators.required],
  });

  readonly s3Form = this.fb.group({
    name: ['MinIO Sales', Validators.required],
    endpoint: ['localhost:9000', Validators.required],
    region: ['us-east-1', Validators.required],
    access_key: ['minio', Validators.required],
    secret_key: ['minio123456', Validators.required],
    table_name: ['sales', Validators.required],
    glob: ['s3://dw/sales/*.parquet', Validators.required],
  });

  readonly askForm = this.fb.group({
    datasourceId: ['', Validators.required],
    question: ['show all users', Validators.required],
  });

  ngOnInit(): void {
    if (!this.auth.isAuthenticated()) {
      this.router.navigate(['/login']);
      return;
    }
    this.loadSources();
  }

  loadSources(): void {
    this.http.get<DataSource[]>(`${API_BASE}/talk-to-data/sources`).subscribe({
      next: (sources) => (this.sources = sources),
    });
  }

  registerPostgres(): void {
    const v = this.pgForm.getRawValue();
    this.registerSource('postgres', {
      host: v.host,
      port: Number(v.port),
      database: v.database,
      user: v.user,
      password: v.password,
    }, v.name!);
  }

  registerS3(): void {
    const v = this.s3Form.getRawValue();
    this.registerSource(
      's3_object_store',
      {
        endpoint: v.endpoint,
        region: v.region,
        access_key: v.access_key,
        secret_key: v.secret_key,
        url_style: 'path',
        table_globs: { [v.table_name!]: v.glob },
      },
      v.name!,
    );
  }

  registerSource(dbType: string, connection: Record<string, unknown>, name: string): void {
    this.http
      .post(`${API_BASE}/talk-to-data/sources`, { name, db_type: dbType, connection })
      .subscribe({
        next: () => {
          this.statusMessage = 'Datasource registered.';
          this.loadSources();
        },
        error: (err) => {
          this.statusMessage = err?.error?.detail ?? 'Registration failed';
        },
      });
  }

  onSourceChange(): void {
    this.selectedSourceId = this.askForm.getRawValue().datasourceId ?? '';
    this.loadSchema();
  }

  loadSchema(): void {
    if (!this.selectedSourceId) return;
    this.http
      .get<Schema>(`${API_BASE}/talk-to-data/sources/${this.selectedSourceId}/schema?refresh=true`)
      .subscribe({ next: (schema) => (this.schema = schema) });
  }

  generateGlossary(): void {
    if (!this.selectedSourceId) return;
    this.http
      .post(`${API_BASE}/talk-to-data/sources/${this.selectedSourceId}/glossary/generate`, {})
      .subscribe({
        next: (terms) => {
          this.statusMessage = `Glossary generated (${(terms as unknown[]).length} terms).`;
        },
      });
  }

  ask(): void {
    if (this.askForm.invalid) return;
    const v = this.askForm.getRawValue();
    this.http
      .post<AskResponse>(`${API_BASE}/talk-to-data/ask`, {
        datasource_id: v.datasourceId,
        question: v.question,
        conversation_id: this.conversationId,
      })
      .subscribe({
        next: (res) => {
          this.conversationId = res.conversation_id;
          this.lastSql = res.sql;
          this.lastResponse = res.response;
          this.lastAskMeta = {
            sql: res.sql,
            datasourceId: v.datasourceId!,
            question: v.question!,
          };
        },
        error: (err) => {
          this.statusMessage = err?.error?.detail ?? 'Query failed';
        },
      });
  }

  pinToDashboard(): void {
    if (!this.lastResponse || !this.lastAskMeta) return;
    const name = window.prompt('Dashboard name (or leave default to use first dashboard)', 'My Dashboard');
    this.dashboardService.list().subscribe({
      next: (dashboards) => {
        const pin = (dashboardId: string) => {
          this.dashboardService
            .pinCard(dashboardId, {
              title: this.lastAskMeta!.question,
              card_type: this.lastResponse!.response_type,
              response: this.lastResponse!,
              source_type: 'sql',
              source_config: {
                datasource_id: this.lastAskMeta!.datasourceId,
                sql: this.lastAskMeta!.sql,
                question: this.lastAskMeta!.question,
              },
              refresh_mode: 'live',
            })
            .subscribe({
              next: () => {
                this.statusMessage = 'Pinned to dashboard.';
              },
            });
        };
        if (dashboards.length) {
          pin(dashboards[0].id);
        } else {
          this.dashboardService.create(name || 'My Dashboard').subscribe({
            next: (d) => pin(d.id),
          });
        }
      },
    });
  }

  onSelectConversation(id: string): void {
    this.conversationId = id;
  }

  logout(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
  }
}
