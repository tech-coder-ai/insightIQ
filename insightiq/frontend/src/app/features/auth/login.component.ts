import { Component, computed, inject } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { Router } from '@angular/router';

import { AuthService } from '../../core/auth.service';
import { ThemeService } from '../../core/theme.service';

@Component({
  standalone: true,
  imports: [ReactiveFormsModule],
  template: `
    <div class="auth">
      <aside class="brand-panel">
        <button type="button" class="theme-btn" (click)="toggleTheme()">
          {{ isDark() ? 'Light mode' : 'Dark mode' }}
        </button>

        <div class="brand-top">
          <span class="brand-mark">IQ</span>
          <span class="brand-name">InsightIQ</span>
        </div>

        <div class="brand-body">
          <p class="label-eyebrow">Enterprise analytics platform</p>
          <h2>Talk to your data.<br />Trust every answer.</h2>
          <p>
            Natural-language analytics over warehouses, documents, and object stores —
            with governed access, citations, and live dashboards.
          </p>

          <ul class="features">
            <li>
              <span class="check" aria-hidden="true"></span>
              NL→SQL across Postgres, Snowflake, Oracle, MSSQL, Hive &amp; S3
            </li>
            <li>
              <span class="check" aria-hidden="true"></span>
              Multi-stage RAG over documents with source citations
            </li>
            <li>
              <span class="check" aria-hidden="true"></span>
              Shareable dashboards and governed prompt library
            </li>
          </ul>

          <div class="stats">
            <div class="stat"><strong>10-stage</strong><span>RAG pipeline</span></div>
            <div class="stat"><strong>Multi-tenant</strong><span>Workspace isolation</span></div>
            <div class="stat"><strong>Read-only</strong><span>SQL guardrails</span></div>
          </div>
        </div>

        <div class="brand-foot">SOC-ready architecture · Role-based access · Audit trails</div>
      </aside>

      <main class="form-panel">
        <div class="form-card">
          <div class="form-head">
            <h1>{{ mode === 'login' ? 'Welcome back' : 'Create workspace' }}</h1>
            <p>{{ mode === 'login' ? 'Sign in to your InsightIQ workspace.' : 'Register your organisation to get started.' }}</p>
          </div>

          <div class="segmented" role="tablist">
            <button type="button" role="tab" [class.on]="mode === 'login'" [attr.aria-selected]="mode === 'login'" (click)="mode = 'login'">Sign in</button>
            <button type="button" role="tab" [class.on]="mode === 'register'" [attr.aria-selected]="mode === 'register'" (click)="mode = 'register'">Register</button>
          </div>

          <form [formGroup]="form" (ngSubmit)="submit()">
            @if (mode === 'register') {
              <div class="field">
                <span>Organisation name</span>
                <input class="input" formControlName="tenantName" placeholder="Acme Corp" autocomplete="organization" />
              </div>
            }

            <div class="field">
              <span>Work email</span>
              <input class="input" formControlName="email" type="email" placeholder="you@company.com" autocomplete="email" />
            </div>

            <div class="field">
              <span>Password</span>
              <input class="input" formControlName="password" type="password" placeholder="Minimum 8 characters" autocomplete="current-password" />
            </div>

            @if (error) {
              <div class="alert alert-error">{{ error }}</div>
            }

            <button type="submit" class="btn btn-primary btn-block" [disabled]="form.invalid || loading">
              {{ loading ? 'Please wait…' : (mode === 'login' ? 'Sign in' : 'Create account') }}
            </button>
          </form>

          <p class="switch">
            {{ mode === 'login' ? "Don't have an account?" : 'Already registered?' }}
            <button type="button" (click)="mode = mode === 'login' ? 'register' : 'login'">
              {{ mode === 'login' ? 'Create one' : 'Sign in' }}
            </button>
          </p>
        </div>
      </main>
    </div>
  `,
  styles: [`
    .auth {
      display: grid;
      grid-template-columns: 1.15fr 1fr;
      min-height: 100vh;
    }

    .brand-panel {
      position: relative;
      display: flex;
      flex-direction: column;
      justify-content: space-between;
      padding: var(--space-12);
      background:
        radial-gradient(ellipse 70% 50% at 10% 0%, rgba(59, 130, 246, 0.15), transparent 55%),
        radial-gradient(ellipse 50% 40% at 90% 100%, rgba(99, 102, 241, 0.08), transparent 50%),
        var(--surface);
      border-right: 1px solid var(--border);
      overflow: hidden;
    }
    .brand-panel::before {
      content: '';
      position: absolute;
      inset: 0;
      background: linear-gradient(180deg, transparent 60%, rgba(59, 130, 246, 0.04));
      pointer-events: none;
    }

    .theme-btn {
      position: absolute;
      top: var(--space-6);
      right: var(--space-6);
      padding: 8px 14px;
      border-radius: var(--radius-md);
      border: 1px solid var(--border-strong);
      background: var(--surface-2);
      color: var(--text-2);
      cursor: pointer;
      font-size: var(--text-sm);
      font-family: inherit;
      font-weight: 500;
      z-index: 2;
      transition: all var(--dur-fast) var(--ease);
    }
    .theme-btn:hover { background: var(--surface-hover); color: var(--text); }

    .brand-top {
      display: flex;
      align-items: center;
      gap: 14px;
      position: relative;
      z-index: 1;
    }
    .brand-mark {
      width: 44px;
      height: 44px;
      border-radius: var(--radius-md);
      display: grid;
      place-items: center;
      background: var(--primary-gradient);
      color: #fff;
      font-family: var(--font-display);
      font-weight: 700;
      font-size: 14px;
      box-shadow: var(--shadow-glow);
    }
    .brand-name {
      font-family: var(--font-display);
      font-size: var(--text-xl);
      font-weight: 700;
      letter-spacing: -0.03em;
    }

    .brand-body {
      position: relative;
      z-index: 1;
      max-width: 480px;
      margin: var(--space-10) 0;
    }
    .brand-body .label-eyebrow { margin-bottom: var(--space-4); display: block; }
    .brand-body h2 {
      font-size: clamp(28px, 4vw, 40px);
      line-height: 1.12;
      margin-bottom: var(--space-4);
    }
    .brand-body > p {
      color: var(--text-2);
      font-size: var(--text-md);
      line-height: 1.65;
      margin: 0;
    }

    .features {
      list-style: none;
      padding: 0;
      margin: var(--space-8) 0 0;
      display: flex;
      flex-direction: column;
      gap: var(--space-4);
    }
    .features li {
      display: flex;
      align-items: flex-start;
      gap: var(--space-3);
      color: var(--text-2);
      font-size: var(--text-base);
      line-height: 1.5;
    }
    .check {
      width: 20px;
      height: 20px;
      border-radius: 50%;
      flex-shrink: 0;
      margin-top: 1px;
      background: var(--success-soft);
      border: 1px solid rgba(34, 197, 94, 0.25);
      position: relative;
    }
    .check::after {
      content: '';
      position: absolute;
      left: 6px;
      top: 4px;
      width: 5px;
      height: 9px;
      border: solid var(--success);
      border-width: 0 2px 2px 0;
      transform: rotate(45deg);
    }

    .stats {
      display: grid;
      grid-template-columns: repeat(3, 1fr);
      gap: var(--space-3);
      margin-top: var(--space-8);
    }
    .stat {
      padding: var(--space-4);
      border-radius: var(--radius-md);
      background: var(--surface-2);
      border: 1px solid var(--border);
    }
    .stat strong {
      display: block;
      font-family: var(--font-display);
      font-size: var(--text-sm);
      color: var(--text);
      margin-bottom: 4px;
    }
    .stat span { font-size: var(--text-xs); color: var(--text-muted); }

    .brand-foot {
      position: relative;
      z-index: 1;
      color: var(--text-muted);
      font-size: var(--text-xs);
      letter-spacing: 0.04em;
      text-transform: uppercase;
    }

    .form-panel {
      display: grid;
      place-items: center;
      padding: var(--space-8);
      background: var(--bg-grad);
    }
    .form-card {
      width: min(420px, 100%);
      padding: var(--space-8);
      border-radius: var(--radius-xl);
      border: 1px solid var(--border);
      background: var(--surface);
      box-shadow: var(--shadow-md);
      display: flex;
      flex-direction: column;
      gap: var(--space-6);
    }
    .form-head h1 {
      font-family: var(--font-display);
      font-size: var(--text-2xl);
    }
    .form-head p { color: var(--text-2); margin: var(--space-2) 0 0; line-height: 1.5; }

    .segmented {
      display: grid;
      grid-template-columns: 1fr 1fr;
      gap: 4px;
      padding: 4px;
      background: var(--surface-2);
      border: 1px solid var(--border);
      border-radius: var(--radius-md);
    }
    .segmented button {
      padding: 10px;
      border: none;
      border-radius: calc(var(--radius-md) - 4px);
      cursor: pointer;
      background: transparent;
      color: var(--text-2);
      font-size: var(--text-base);
      font-weight: 550;
      font-family: inherit;
      transition: all var(--dur-fast) var(--ease);
    }
    .segmented button.on {
      background: var(--surface);
      color: var(--text);
      box-shadow: var(--shadow-xs);
    }

    form { display: flex; flex-direction: column; gap: var(--space-4); }

    .switch {
      text-align: center;
      color: var(--text-2);
      font-size: var(--text-sm);
      margin: 0;
    }
    .switch button {
      border: none;
      background: none;
      color: var(--primary-text);
      cursor: pointer;
      font-weight: 600;
      font-size: var(--text-sm);
      font-family: inherit;
      padding: 0 4px;
    }
    .switch button:hover { text-decoration: underline; }

    @media (max-width: 960px) {
      .auth { grid-template-columns: 1fr; }
      .brand-panel {
        padding: var(--space-6);
        border-right: none;
        border-bottom: 1px solid var(--border);
        min-height: auto;
      }
      .brand-body { margin: var(--space-6) 0; }
      .stats { grid-template-columns: 1fr; }
      .brand-foot { display: none; }
    }
    @media (max-width: 640px) {
      .brand-body h2 { font-size: 26px; }
      .features, .stats { display: none; }
      .form-card { padding: var(--space-6); box-shadow: none; border: none; background: transparent; }
    }
  `],
})
export class LoginComponent {
  private readonly auth = inject(AuthService);
  private readonly theme = inject(ThemeService);
  private readonly router = inject(Router);
  private readonly fb = inject(FormBuilder);

  mode: 'login' | 'register' = 'login';
  error = '';
  loading = false;

  isDark = computed(() => this.theme.theme() === 'dark');

  readonly form = this.fb.group({
    tenantName: [''],
    email: ['', [Validators.required, Validators.email]],
    password: ['', [Validators.required, Validators.minLength(8)]],
  });

  toggleTheme(): void { this.theme.toggle(); }

  submit(): void {
    if (this.form.invalid || this.loading) return;
    this.error = '';
    this.loading = true;
    const { tenantName, email, password } = this.form.getRawValue();
    const req = this.mode === 'login'
      ? this.auth.login(email!, password!)
      : this.auth.register(tenantName || 'My Organisation', email!, password!);

    req.subscribe({
      next: () => this.router.navigate(['/datasources']),
      error: (err: { error?: { detail?: string } }) => {
        this.loading = false;
        this.error = err?.error?.detail ?? 'Authentication failed. Please try again.';
      },
    });
  }
}
