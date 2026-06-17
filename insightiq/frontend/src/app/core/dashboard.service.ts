import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE } from './api.config';

export type Dashboard = { id: string; name: string; global_filters_json: Record<string, unknown> };
export type DashboardCard = {
  id: string;
  title: string;
  card_type: string;
  layout_json: { x: number; y: number; cols: number; rows: number };
  refresh_mode: string;
  source_type: string;
  snapshot_response_json: Record<string, unknown>;
  auto_refresh_seconds: number | null;
};
export type DashboardDetail = Dashboard & { cards: DashboardCard[] };

@Injectable({ providedIn: 'root' })
export class DashboardService {
  private readonly http = inject(HttpClient);

  list(): Observable<Dashboard[]> {
    return this.http.get<Dashboard[]>(`${API_BASE}/dashboards`);
  }

  get(id: string): Observable<DashboardDetail> {
    return this.http.get<DashboardDetail>(`${API_BASE}/dashboards/${id}`);
  }

  create(name: string): Observable<Dashboard> {
    return this.http.post<Dashboard>(`${API_BASE}/dashboards`, { name });
  }

  pinCard(
    dashboardId: string,
    body: {
      title: string;
      card_type: string;
      response: Record<string, unknown>;
      source_type: string;
      source_config: Record<string, unknown>;
      refresh_mode?: string;
      layout_json?: Record<string, unknown>;
    },
  ): Observable<DashboardCard> {
    return this.http.post<DashboardCard>(`${API_BASE}/dashboards/${dashboardId}/cards`, body);
  }

  updateCard(
    dashboardId: string,
    cardId: string,
    body: { title?: string; layout_json?: Record<string, unknown> },
  ): Observable<DashboardCard> {
    return this.http.patch<DashboardCard>(`${API_BASE}/dashboards/${dashboardId}/cards/${cardId}`, body);
  }

  updateLayout(dashboardId: string, cardId: string, layout_json: Record<string, unknown>): Observable<DashboardCard> {
    return this.updateCard(dashboardId, cardId, { layout_json });
  }

  refreshCard(dashboardId: string, cardId: string): Observable<DashboardCard> {
    return this.http.post<DashboardCard>(`${API_BASE}/dashboards/${dashboardId}/cards/${cardId}/refresh`, {});
  }

  removeCard(dashboardId: string, cardId: string): Observable<void> {
    return this.http.delete<void>(`${API_BASE}/dashboards/${dashboardId}/cards/${cardId}`);
  }

  updateFilters(dashboardId: string, global_filters_json: Record<string, unknown>): Observable<Dashboard> {
    return this.http.patch<Dashboard>(`${API_BASE}/dashboards/${dashboardId}/filters`, { global_filters_json });
  }

  share(dashboardId: string): Observable<{ token: string; url_path: string }> {
    return this.http.post<{ token: string; url_path: string }>(`${API_BASE}/dashboards/${dashboardId}/share`, {});
  }

  getPublic(token: string): Observable<DashboardDetail> {
    return this.http.get<DashboardDetail>(`${API_BASE}/public/dashboards/${token}`);
  }
}
