import { HttpClient } from '@angular/common/http';
import { Injectable, inject, signal } from '@angular/core';
import { tap } from 'rxjs/operators';

import { API_BASE } from './api.config';
import { storeToken } from './auth.interceptor';

type AuthResponse = { access_token: string; token_type: string };

@Injectable({ providedIn: 'root' })
export class AuthService {
  private readonly http = inject(HttpClient);
  readonly isAuthenticated = signal(!!localStorage.getItem('insightiq_token'));

  register(tenantName: string, email: string, password: string) {
    return this.http
      .post<AuthResponse>(`${API_BASE}/auth/register`, {
        tenant_name: tenantName,
        email,
        password,
      })
      .pipe(tap((res) => this.persist(res.access_token)));
  }

  login(email: string, password: string) {
    return this.http
      .post<AuthResponse>(`${API_BASE}/auth/login`, { email, password })
      .pipe(tap((res) => this.persist(res.access_token)));
  }

  logout(): void {
    localStorage.removeItem('insightiq_token');
    this.isAuthenticated.set(false);
  }

  private persist(token: string): void {
    storeToken(token);
    this.isAuthenticated.set(true);
  }
}
