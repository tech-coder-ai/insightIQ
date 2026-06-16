import { Component, OnInit, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { DashboardService } from '../../core/dashboard.service';

@Component({
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink],
  template: `
    <div class="page">
      <div class="page-header">
        <div>
          <h1>Dashboards</h1>
          <p>Pin query results and prompt outputs into live, shareable boards.</p>
        </div>
      </div>

      <form class="create" [formGroup]="form" (ngSubmit)="create()">
        <input class="input" formControlName="name" placeholder="New dashboard name" />
        <button type="submit" class="btn btn-primary">Create</button>
      </form>

      @if (dashboards.length === 0) {
        <div class="empty-state">
          <div class="icon">📐</div>
          <p>No dashboards yet. Create one above, or pin a result from Talk to Data.</p>
        </div>
      }

      <ul>
        @for (d of dashboards; track d.id) {
          <li>
            <a [routerLink]="['/dashboards', d.id]">
              <span class="d-icon">📊</span>
              <span class="d-name">{{ d.name }}</span>
              <span class="d-arrow">→</span>
            </a>
          </li>
        }
      </ul>
    </div>
  `,
  styles: [
    `
      .page { max-width: 760px; }
      .create {
        display: flex;
        gap: 10px;
        margin-bottom: var(--space-6);
      }
      .create .input { flex: 1; }
      ul {
        list-style: none;
        padding: 0;
        margin: 0;
        display: grid;
        gap: 10px;
      }
      li a {
        display: flex;
        align-items: center;
        gap: 12px;
        padding: 14px 16px;
        border-radius: var(--radius-md);
        border: 1px solid var(--border);
        background: var(--surface);
        color: var(--text);
        text-decoration: none;
        box-shadow: var(--shadow-sm);
        transition: border-color var(--dur-fast) var(--ease), transform var(--dur-fast) var(--ease);
      }
      li a:hover { border-color: var(--primary); transform: translateX(2px); }
      .d-icon { font-size: 18px; }
      .d-name { flex: 1; font-weight: 550; }
      .d-arrow { color: var(--text-muted); }
    `,
  ],
})
export class DashboardListComponent implements OnInit {
  private readonly dashboardService = inject(DashboardService);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);

  dashboards: { id: string; name: string }[] = [];
  readonly form = this.fb.group({ name: ['My Dashboard', Validators.required] });

  ngOnInit(): void {
    this.load();
  }

  load(): void {
    this.dashboardService.list().subscribe({ next: (items) => (this.dashboards = items) });
  }

  create(): void {
    if (this.form.invalid) return;
    this.dashboardService.create(this.form.getRawValue().name!).subscribe({
      next: (d) => this.router.navigate(['/dashboards', d.id]),
    });
  }
}
