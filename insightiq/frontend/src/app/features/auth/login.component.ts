import { Component, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';

import { AuthService } from '../../core/auth.service';

@Component({
  standalone: true,
  imports: [ReactiveFormsModule],
  template: `
    <div class="wrap">
      <form class="card" [formGroup]="form" (ngSubmit)="submit()">
        <h1>InsightIQ</h1>
        <p class="sub">Sign in or create a tenant</p>

        <label>
          Tenant name (register only)
          <input formControlName="tenantName" placeholder="Acme Corp" />
        </label>

        <label>
          Email
          <input formControlName="email" type="email" placeholder="you@company.com" />
        </label>

        <label>
          Password
          <input formControlName="password" type="password" placeholder="••••••••" />
        </label>

        @if (error) {
          <div class="error">{{ error }}</div>
        }

        <div class="actions">
          <button type="button" (click)="mode = 'login'" [class.active]="mode === 'login'">Login</button>
          <button type="button" (click)="mode = 'register'" [class.active]="mode === 'register'">Register</button>
          <button type="submit" class="primary">{{ mode === 'login' ? 'Login' : 'Register' }}</button>
        </div>
      </form>
    </div>
  `,
  styles: [
    `
      .wrap {
        min-height: 100vh;
        display: grid;
        place-items: center;
        padding: 24px;
      }
      .card {
        width: min(420px, 100%);
        display: grid;
        gap: 12px;
        padding: 24px;
        border-radius: 16px;
        border: 1px solid rgba(255, 255, 255, 0.1);
        background: rgba(255, 255, 255, 0.04);
      }
      h1 {
        margin: 0;
      }
      .sub {
        margin: 0 0 8px;
        opacity: 0.75;
      }
      label {
        display: grid;
        gap: 6px;
        font-size: 12px;
        opacity: 0.85;
      }
      input {
        padding: 10px 12px;
        border-radius: 10px;
        border: 1px solid rgba(255, 255, 255, 0.12);
        background: rgba(0, 0, 0, 0.25);
        color: inherit;
      }
      .actions {
        display: flex;
        gap: 8px;
        flex-wrap: wrap;
        margin-top: 8px;
      }
      button {
        border-radius: 10px;
        border: 1px solid rgba(255, 255, 255, 0.12);
        background: transparent;
        color: inherit;
        padding: 8px 12px;
        cursor: pointer;
      }
      .active,
      .primary {
        background: rgba(88, 166, 255, 0.25);
      }
      .error {
        color: #ff8f8f;
        font-size: 13px;
      }
    `,
  ],
})
export class LoginComponent {
  private readonly auth = inject(AuthService);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);

  mode: 'login' | 'register' = 'login';
  error = '';

  readonly form = this.fb.group({
    tenantName: [''],
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(8)]],
  });

  submit(): void {
    if (this.form.invalid) return;
    this.error = '';
    const { tenantName, email, password } = this.form.getRawValue();
    const req =
      this.mode === 'login'
        ? this.auth.login(email!, password!)
        : this.auth.register(tenantName || 'My Tenant', email!, password!);

    req.subscribe({
      next: () => this.router.navigate(['/talk-to-data']),
      error: (err: { error?: { detail?: string } }) => {
        this.error = err?.error?.detail ?? 'Authentication failed';
      },
    });
  }
}
