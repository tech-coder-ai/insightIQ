import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { tap } from 'rxjs/operators';

import { environment } from '../../environments/environment';
import { API_BASE } from './api.config';
import { storeToken } from './auth.interceptor';

type AuthResponse = { access_token: string; token_type: string };

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  readonly isAuthenticated = signal(
    environment.authDisabled || !!localStorage.getItem('insightiq_token'),
  );
  readonly email = signal<string | null>(localStorage.getItem('insightiq_email'));
  readonly role = signal<string>(
    environment.authDisabled ? 'admin' : decodeRole(localStorage.getItem('insightiq_token')),
  );

  isLoggedIn(): boolean {
    if (environment.authDisabled) return true;
    const loggedIn = !!localStorage.getItem('insightiq_token');
    if (this.isAuthenticated() !== loggedIn) {
      this.isAuthenticated.set(loggedIn);
    }
    return loggedIn;
  }

  isAdmin(): boolean {
    return this.role() === 'admin' || this.role() === 'super-admin';
  }

  register(tenantName: string, email: string, password: string) {
    return this.http
      .post<AuthResponse>(`${API_BASE}/auth/register`, {
        tenant_name: tenantName,
        email,
        password,
      })
      .pipe(tap((res) => this.persist(res.access_token, email)));
  }

  login(email: string, password: string) {
    return this.http
      .post<AuthResponse>(`${API_BASE}/auth/login`, { email, password })
      .pipe(tap((res) => this.persist(res.access_token, email)));
  }

  logout(): void {
    if (environment.authDisabled) return;
    localStorage.removeItem('insightiq_token');
    localStorage.removeItem('insightiq_email');
    this.isAuthenticated.set(false);
    this.email.set(null);
    this.role.set('viewer');
  }

  private persist(token: string, email: string): void {
    storeToken(token);
    localStorage.setItem('insightiq_email', email);
    this.email.set(email);
    this.isAuthenticated.set(true);
    this.role.set(decodeRole(token));
  }
}

function decodeRole(token: string | null): string {
  if (!token) return 'viewer';
  try {
    const payload = JSON.parse(atob(token.split('.')[1].replace(/-/g, '+').replace(/_/g, '/')));
    return typeof payload.role === 'string' ? payload.role : 'viewer';
  } catch {
    return 'viewer';
  }
}
