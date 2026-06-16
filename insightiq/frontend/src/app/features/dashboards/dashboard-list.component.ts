import { Component, OnInit, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router, RouterLink } from '@angular/router';

import { DashboardService } from '../../core/dashboard.service';
import { AuthService } from '../../core/auth.service';

@Component({
  standalone: true,
  imports: [ReactiveFormsModule, RouterLink],
  template: `
    <div class="page">
      <header>
        <h1>Dashboards</h1>
        <a routerLink="/">Home</a>
      </header>

      <form class="create" [formGroup]="form" (ngSubmit)="create()">
        <input formControlName="name" placeholder="New dashboard name" />
        <button type="submit" class="primary">Create</button>
      </form>

      <ul>
        @for (d of dashboards; track d.id) {
          <li>
            <a [routerLink]="['/dashboards', d.id]">{{ d.name }}</a>
          </li>
        }
      </ul>
    </div>
  `,
  styles: [
    `
      .page {
        padding: 24px;
        max-width: 720px;
        margin: 0 auto;
      }
      header {
        display: flex;
        justify-content: space-between;
        align-items: center;
      }
      .create {
        display: flex;
        gap: 8px;
        margin: 20px 0;
      }
      input,
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
      ul {
        list-style: none;
        padding: 0;
        display: grid;
        gap: 8px;
      }
      li a {
        display: block;
        padding: 12px;
        border-radius: 10px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        color: #8ec5ff;
        text-decoration: none;
      }
    `,
  ],
})
export class DashboardListComponent implements OnInit {
  private readonly dashboardService = inject(DashboardService);
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);

  dashboards: { id: string; name: string }[] = [];
  readonly form = this.fb.group({ name: ['My Dashboard', Validators.required] });

  ngOnInit(): void {
    if (!this.auth.isAuthenticated()) {
      this.router.navigate(['/login']);
      return;
    }
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
