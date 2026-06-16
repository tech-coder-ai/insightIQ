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
      <!-- Brand / marketing panel -->
      <aside class="brand-panel">
        <button class="theme-btn" (click)="toggleTheme()">{{ isDark() ? '☀️ Light' : '🌙 Dark' }}</button>
        <div class="brand-top">
          <span class="brand-mark">IQ</span>
          <span class="brand-name">InsightIQ</span>
        </div>
        <div class="brand-body">
          <h2>Talk to your data.<br />Trust every answer.</h2>
          <p>Natural-language analytics over your warehouses, documents, and object stores — with governed access, citations, and live dashboards.</p>
          <ul class="features">
            <li><span>📊</span> NL→SQL across Postgres, Snowflake, Oracle, MSSQL, Hive &amp; S3</li>
            <li><span>📄</span> 10-stage RAG over your documents with source highlighting</li>
            <li><span>📐</span> Live, shareable dashboards &amp; scheduled reports</li>
          </ul>
        </div>
        <div class="brand-foot">Enterprise-grade · Multi-tenant · Audited</div>
      </aside>

      <!-- Form panel -->
      <main class="form-panel">
        <div class="form-wrap">
          <div class="form-head">
            <h1>{{ mode === 'login' ? 'Welcome back' : 'Create your workspace' }}</h1>
            <p>{{ mode === 'login' ? 'Sign in to continue to InsightIQ.' : 'Set up your organisation in seconds.' }}</p>
          </div>

          <div class="segmented">
            <button type="button" [class.on]="mode === 'login'" (click)="mode = 'login'">Sign in</button>
            <button type="button" [class.on]="mode === 'register'" (click)="mode = 'register'">Create account</button>
          </div>

          <form [formGroup]="form" (ngSubmit)="submit()">
            @if (mode === 'register') {
              <div class="field">
                <span>Organisation name</span>
                <input class="input" formControlName="tenantName" placeholder="Acme Corp" autocomplete="organization" />
              </div>
            }

            <div class="field">
              <span>Email</span>
              <input class="input" formControlName="email" type="email" placeholder="you@company.com" autocomplete="email" />
            </div>

            <div class="field">
              <span>Password</span>
              <input class="input" formControlName="password" type="password" placeholder="At least 8 characters" autocomplete="current-password" />
            </div>

            @if (error) {
              <div class="alert alert-error">{{ error }}</div>
            }

            <button type="submit" class="btn btn-primary btn-block" [disabled]="form.invalid || loading">
              {{ loading ? 'Please wait…' : (mode === 'login' ? 'Sign in' : 'Create account') }}
            </button>
          </form>

          <p class="switch">
            {{ mode === 'login' ? "Don't have an account?" : 'Already have an account?' }}
            <button type="button" (click)="mode = mode === 'login' ? 'register' : 'login'">
              {{ mode === 'login' ? 'Create one' : 'Sign in' }}
            </button>
          </p>
        </div>
      </main>
    </div>
  `,
  styles: [`
    .auth { display: grid; grid-template-columns: 1.1fr 1fr; min-height: 100vh; }

    /* ── Brand panel ── */
    .brand-panel {
      position: relative;
      display: flex; flex-direction: column; justify-content: space-between;
      padding: var(--space-12);
      background:
        radial-gradient(900px 500px at 20% 10%, var(--primary-soft-2), transparent 55%),
        linear-gradient(160deg, var(--surface), var(--bg));
      border-right: 1px solid var(--border);
      overflow: hidden;
    }
    .brand-panel::after {
      content: ''; position: absolute; inset: auto -120px -160px auto;
      width: 420px; height: 420px; border-radius: 50%;
      background: radial-gradient(circle, var(--primary-soft-2), transparent 70%);
      filter: blur(10px);
    }
    .theme-btn {
      position: absolute; top: var(--space-6); right: var(--space-6);
      padding: 6px 12px; border-radius: var(--radius-pill);
      border: 1px solid var(--border-strong); background: var(--surface-2);
      color: var(--text-2); cursor: pointer; font-size: var(--text-sm); z-index: 2;
    }
    .theme-btn:hover { background: var(--surface-hover); color: var(--text); }

    .brand-top { display: flex; align-items: center; gap: 12px; position: relative; z-index: 1; }
    .brand-mark {
      width: 40px; height: 40px; border-radius: 11px;
      display: grid; place-items: center;
      background: linear-gradient(135deg, var(--primary), var(--primary-hover));
      color: #fff; font-weight: 700; box-shadow: var(--shadow-md);
    }
    .brand-name { font-size: var(--text-xl); font-weight: 700; }

    .brand-body { position: relative; z-index: 1; max-width: 460px; }
    .brand-body h2 { font-size: 34px; line-height: 1.15; font-weight: 700; letter-spacing: -0.02em; }
    .brand-body p { color: var(--text-2); font-size: var(--text-md); margin-top: var(--space-4); }
    .features { list-style: none; padding: 0; margin: var(--space-8) 0 0; display: flex; flex-direction: column; gap: 14px; }
    .features li { display: flex; align-items: center; gap: 12px; color: var(--text-2); font-size: var(--text-base); }
    .features li span { font-size: 18px; }

    .brand-foot { position: relative; z-index: 1; color: var(--text-muted); font-size: var(--text-sm); letter-spacing: 0.02em; }

    /* ── Form panel ── */
    .form-panel { display: grid; place-items: center; padding: var(--space-8); background: var(--bg); }
    .form-wrap { width: min(380px, 100%); display: flex; flex-direction: column; gap: var(--space-6); }
    .form-head h1 { font-size: var(--text-2xl); }
    .form-head p { color: var(--text-2); margin: 6px 0 0; }

    .segmented {
      display: grid; grid-template-columns: 1fr 1fr; gap: 4px; padding: 4px;
      background: var(--surface-2); border: 1px solid var(--border); border-radius: var(--radius-md);
    }
    .segmented button {
      padding: 8px; border: none; border-radius: var(--radius-sm); cursor: pointer;
      background: transparent; color: var(--text-2); font-size: var(--text-base); font-weight: 550;
      font-family: inherit; transition: all var(--dur-fast) var(--ease);
    }
    .segmented button.on { background: var(--surface); color: var(--text); box-shadow: var(--shadow-sm); }

    form { display: flex; flex-direction: column; gap: var(--space-4); }

    .switch { text-align: center; color: var(--text-2); font-size: var(--text-sm); margin: 0; }
    .switch button {
      border: none; background: none; color: var(--primary-text); cursor: pointer;
      font-weight: 600; font-size: var(--text-sm); font-family: inherit; padding: 0 2px;
    }
    .switch button:hover { text-decoration: underline; }

    @media (max-width: 880px) {
      .auth { grid-template-columns: 1fr; }
      .brand-panel { display: none; }
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
