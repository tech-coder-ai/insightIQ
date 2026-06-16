import { HttpClient } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE } from './api.config';

export type ScheduledReport = {
  id: string;
  dashboard_id: string;
  recipient_email: string;
  interval_seconds: number;
  export_format: string;
  enabled: boolean;
  next_run_at: string | null;
};

@Injectable({ providedIn: 'root' })
export class ReportService {
  private readonly http = inject(HttpClient);

  list(): Observable<ScheduledReport[]> {
    return this.http.get<ScheduledReport[]>(`${API_BASE}/reports/schedules`);
  }

  create(body: {
    dashboard_id: string;
    recipient_email: string;
    interval_seconds?: number;
    export_format?: string;
  }): Observable<ScheduledReport> {
    return this.http.post<ScheduledReport>(`${API_BASE}/reports/schedules`, body);
  }

  runNow(scheduleId: string): Observable<{ status: string }> {
    return this.http.post<{ status: string }>(`${API_BASE}/reports/schedules/${scheduleId}/run-now`, {});
  }

  delete(scheduleId: string): Observable<{ status: string }> {
    return this.http.delete<{ status: string }>(`${API_BASE}/reports/schedules/${scheduleId}`);
  }
}
