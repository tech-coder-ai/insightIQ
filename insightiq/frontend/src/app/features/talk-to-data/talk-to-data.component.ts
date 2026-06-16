import { HttpClient } from '@angular/common/http';
import { Component, OnInit, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';

import { API_BASE } from '../../core/api.config';
import { AuthService } from '../../core/auth.service';
import { DataTableComponent } from '../../shared/data-table.component';

type DataSource = { id: string; name: string; db_type: string };
type ResponsePayload = {
  response_type: string;
  title?: string;
  data: { columns?: string[]; rows?: unknown[][]; message?: string };
};
type AskResponse = { conversation_id: string; sql: string; response: ResponsePayload };

@Component({
  standalone: true,
  imports: [ReactiveFormsModule, DataTableComponent],
  template: `
    <div class="page">
      <header>
        <div>
          <h1>Talk to Data</h1>
          <p>Register a Postgres source and ask a question</p>
        </div>
        <button type="button" (click)="logout()">Logout</button>
      </header>

      <section class="card">
        <h2>Register datasource</h2>
        <form class="grid" [formGroup]="sourceForm" (ngSubmit)="registerSource()">
          <input formControlName="name" placeholder="Source name" />
          <input formControlName="host" placeholder="Host" />
          <input formControlName="port" type="number" placeholder="Port" />
          <input formControlName="database" placeholder="Database" />
          <input formControlName="user" placeholder="User" />
          <input formControlName="password" type="password" placeholder="Password" />
          <button type="submit" class="primary">Register</button>
        </form>
        @if (sourceMessage) {
          <p class="msg">{{ sourceMessage }}</p>
        }
      </section>

      <section class="card">
        <h2>Ask a question</h2>
        <form class="ask" [formGroup]="askForm" (ngSubmit)="ask()">
          <select formControlName="datasourceId">
            <option value="">Select datasource</option>
            @for (ds of sources; track ds.id) {
              <option [value]="ds.id">{{ ds.name }} ({{ ds.db_type }})</option>
            }
          </select>
          <input formControlName="question" placeholder="e.g. show all users" />
          <button type="submit" class="primary" [disabled]="askForm.invalid">Ask</button>
        </form>

        @if (lastSql) {
          <pre class="sql">{{ lastSql }}</pre>
        }

        @if (tableColumns.length) {
          <app-data-table [columns]="tableColumns" [rows]="tableRows" />
        }
      </section>
    </div>
  `,
  styles: [
    `
      .page {
        max-width: 960px;
        margin: 0 auto;
        padding: 24px;
        display: grid;
        gap: 20px;
      }
      header {
        display: flex;
        justify-content: space-between;
        align-items: center;
        gap: 16px;
      }
      h1,
      h2 {
        margin: 0;
      }
      p {
        margin: 4px 0 0;
        opacity: 0.75;
      }
      .card {
        border: 1px solid rgba(255, 255, 255, 0.1);
        border-radius: 16px;
        padding: 20px;
        background: rgba(255, 255, 255, 0.03);
        display: grid;
        gap: 12px;
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
      }
      .msg {
        font-size: 13px;
        opacity: 0.85;
      }
      @media (max-width: 720px) {
        .ask {
          grid-template-columns: 1fr;
        }
      }
    `,
  ],
})
export class TalkToDataComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);

  sources: DataSource[] = [];
  sourceMessage = '';
  lastSql = '';
  tableColumns: string[] = [];
  tableRows: unknown[][] = [];

  readonly sourceForm = this.fb.group({
    name: ['Local Postgres', Validators.required],
    host: ['localhost', Validators.required],
    port: [5432, Validators.required],
    database: ['insightiq', Validators.required],
    user: ['insightiq', Validators.required],
    password: ['insightiq', Validators.required],
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

  registerSource(): void {
    if (this.sourceForm.invalid) return;
    const v = this.sourceForm.getRawValue();
    this.http
      .post(`${API_BASE}/talk-to-data/sources`, {
        name: v.name,
        db_type: 'postgres',
        connection: {
          host: v.host,
          port: Number(v.port),
          database: v.database,
          user: v.user,
          password: v.password,
        },
      })
      .subscribe({
        next: () => {
          this.sourceMessage = 'Datasource registered.';
          this.loadSources();
        },
        error: (err) => {
          this.sourceMessage = err?.error?.detail ?? 'Registration failed';
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
      })
      .subscribe({
        next: (res) => {
          this.lastSql = res.sql;
          this.tableColumns = res.response.data.columns ?? [];
          this.tableRows = res.response.data.rows ?? [];
        },
        error: (err) => {
          this.sourceMessage = err?.error?.detail ?? 'Query failed';
        },
      });
  }

  logout(): void {
    this.auth.logout();
    this.router.navigate(['/login']);
  }
}
